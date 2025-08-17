import os
import hashlib
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re
# Removed mutagen imports - metadata extraction moved to separate process
# from mutagen import File as MutagenFile
# from mutagen.mp4 import MP4
# from mutagen.avi import AVI
# from mutagen.asf import ASF
# from mutagen.flac import FLAC
# from mutagen.mp3 import MP3
# from mutagen.oggvorbis import OggVorbis

from app import db
from models import FileRecord, ScanRecord, MediaFile, StorageHistory

# Import get_setting function
def get_setting(key, default=None):
    """Get setting from database or environment"""
    try:
        from app import get_setting as app_get_setting
        return app_get_setting(key, default)
    except ImportError:
        return default

logger = logging.getLogger(__name__)

def format_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f} {size_names[i]}"

class FileScanner:
    """Efficient file system scanner for unRAID storage analysis"""
    
    def __init__(self, data_path: str = "/data", max_duration: int = 6):
        self.data_path = Path(data_path)
        self.max_duration = max_duration * 3600  # Convert to seconds
        self.scan_start_time = None
        self.current_scan = None
        self.scanning = False
        self.stop_scan = False
        
        # Media file extensions
        self.video_extensions = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.mts'}
        self.audio_extensions = {'.mp3', '.flac', '.wav', '.aac', '.ogg', '.m4a', '.wma'}
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
        
        # TV Show patterns
        self.tv_patterns = [
            r'(.+?)[\.\s]S(\d{1,2})E(\d{1,2})',  # Show Name S01E01
            r'(.+?)[\.\s](\d{1,2})x(\d{1,2})',   # Show Name 1x01
            r'(.+?)[\.\s]Season[\.\s](\d{1,2})[\.\s]Episode[\.\s](\d{1,2})',  # Show Name Season 1 Episode 01
        ]
        
        # Movie patterns
        self.movie_patterns = [
            r'(.+?)[\.\s]\((\d{4})\)',  # Movie Name (2023)
            r'(.+?)[\.\s](\d{4})',      # Movie Name 2023
        ]
        
        # Resolution patterns
        self.resolution_patterns = [
            r'(\d{3,4})p',
            r'(\d{3,4})i',
            r'4K',
            r'2160p',
            r'1080p',
            r'720p',
            r'480p',
        ]
        
        # Codec patterns
        self.video_codec_patterns = [
            r'H\.264',
            r'H\.265',
            r'HEVC',
            r'AVC',
            r'x264',
            r'x265',
            r'XviD',
            r'DivX',
        ]
        
        self.audio_codec_patterns = [
            r'AC3',
            r'AAC',
            r'DTS',
            r'FLAC',
            r'MP3',
            r'OGG',
            r'PCM',
        ]

    def start_scan(self) -> int:
        """Start a new scan session"""
        if self.scanning:
            logger.warning("Scan already in progress")
            return None
            
        # Mark any existing running scans as failed
        try:
            running_scans = ScanRecord.query.filter_by(status='running').all()
            for scan in running_scans:
                scan.status = 'failed'
                scan.error_message = 'Superseded by new scan'
                scan.end_time = datetime.utcnow()
            db.session.commit()
            logger.info(f"Marked {len(running_scans)} existing running scans as failed")
        except Exception as e:
            logger.error(f"Error cleaning up old scans: {e}")
            
        self.scanning = True
        self.stop_scan = False
        self.scan_start_time = time.time()
        
        # Create scan record
        self.current_scan = ScanRecord(
            start_time=datetime.utcnow(),
            status='running'
        )
        db.session.add(self.current_scan)
        db.session.commit()
        
        # Start scan in background thread
        logger.info(f"About to start scan thread for scan ID {self.current_scan.id}")
        scan_thread = threading.Thread(target=self._scan_filesystem)
        scan_thread.daemon = True
        scan_thread.start()
        logger.info(f"Scan thread started successfully for scan ID {self.current_scan.id}")
        
        logger.info(f"Started scan session {self.current_scan.id}")
        return self.current_scan.id

    def stop_current_scan(self):
        """Stop the current scan"""
        self.stop_scan = True
        logger.info("Scan stop requested")
        
        # Force stop any running scan in database
        try:
            running_scans = ScanRecord.query.filter_by(status='running').all()
            for scan in running_scans:
                scan.status = 'stopped'
                scan.error_message = 'Stopped by user request'
                scan.end_time = datetime.utcnow()
            db.session.commit()
            logger.info(f"Force stopped {len(running_scans)} running scans in database")
        except Exception as e:
            logger.error(f"Error force stopping scans: {e}")
        
        # Reset scanning state
        self.scanning = False
        self.current_scan = None

    def force_reset(self):
        """Force reset scanner state and clear any stuck scans"""
        logger.info("Force resetting scanner state")
        
        # Stop any running scan
        self.stop_scan = True
        self.scanning = False
        self.current_scan = None
        
        # Force stop any running scans in database
        try:
            running_scans = ScanRecord.query.filter_by(status='running').all()
            for scan in running_scans:
                scan.status = 'failed'
                scan.error_message = 'Force reset by user'
                scan.end_time = datetime.utcnow()
            db.session.commit()
            logger.info(f"Force reset {len(running_scans)} running scans in database")
        except Exception as e:
            logger.error(f"Error force resetting scans: {e}")
        
        # Reset all state variables
        self.scan_start_time = None
        self.current_path = None
        
        logger.info("Scanner state reset complete")

    def get_scan_status(self) -> Dict:
        """Get current scan status"""
        if not self.current_scan:
            return {'status': 'idle'}
        
        # Calculate elapsed time and estimated completion
        elapsed_time = time.time() - self.scan_start_time if self.scan_start_time else 0
        current_path = getattr(self, 'current_path', 'Unknown')
        
        # Calculate processing rate
        processing_rate = None
        if elapsed_time > 0 and self.current_scan.total_files > 0:
            files_per_second = self.current_scan.total_files / elapsed_time
            processing_rate = f"{files_per_second:.1f} files/sec"
        
        # Estimate completion time based on current progress
        estimated_completion = None
        progress_percentage = 0
        if self.current_scan.total_directories > 0 and elapsed_time > 0:
            # Rough estimate: assume 210,006 total directories based on logs
            total_estimated_dirs = 210006
            progress_percentage = min(100, (self.current_scan.total_directories / total_estimated_dirs) * 100)
            
            if progress_percentage > 0:
                estimated_total_time = elapsed_time / (progress_percentage / 100)
                estimated_remaining = estimated_total_time - elapsed_time
                estimated_completion = datetime.fromtimestamp(time.time() + estimated_remaining)
            
        return {
            'scan_id': self.current_scan.id,
            'status': self.current_scan.status,
            'start_time': self.current_scan.start_time.isoformat(),
            'end_time': self.current_scan.end_time.isoformat() if self.current_scan.end_time else None,
            'total_files': self.current_scan.total_files,
            'total_directories': self.current_scan.total_directories,
            'total_size': self.current_scan.total_size,
            'total_size_formatted': format_size(self.current_scan.total_size),
            'scanning': self.scanning,
            'elapsed_time': elapsed_time,
            'elapsed_time_formatted': self._format_duration(elapsed_time),
            'current_path': current_path,
            'estimated_completion': estimated_completion.isoformat() if estimated_completion else None,
            'progress_percentage': progress_percentage,
            'processing_rate': processing_rate,
            'scan_duration': self._format_duration(elapsed_time)
        }
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to human readable format"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.0f}m {seconds % 60:.0f}s"
        else:
            hours = seconds / 3600
            minutes = (seconds % 3600) / 60
            return f"{hours:.0f}h {minutes:.0f}m"

    def _scan_filesystem(self):
        """Main scanning method with proper appdata exclusion"""
        logger.info(f"=== SCANNER THREAD STARTED ===")
        logger.info(f"Thread ID: {threading.current_thread().ident}")
        logger.info(f"Starting filesystem scan of {self.data_path}")
        try:
            
            total_files = 0
            total_directories = 0
            total_size = 0
            last_update_time = time.time()
            
            # Get max shares to scan setting
            max_shares_to_scan = int(get_setting('max_shares_to_scan', '0'))
            shares_scanned = 0
            
            # Clear old file records for this scan
            FileRecord.query.filter_by(scan_id=self.current_scan.id).delete()
            
            # Add timeout mechanism
            last_directory_time = time.time()
            directory_timeout = 300  # 5 minutes timeout per directory
            last_heartbeat = time.time()
            heartbeat_interval = 30  # 30 seconds
            
            # Add overall scan timeout protection
            scan_start_time = time.time()
            max_scan_time = self.max_duration * 3600  # Convert hours to seconds
            
            # Track progress logging
            last_progress_log = time.time()
            progress_log_interval = 60  # Log progress every minute
            
            # Track stuck detection
            last_path_change = time.time()
            stuck_timeout = 600  # 10 minutes without path change
            last_path = None
            
            # Debug: Check appdata setting at start
            skip_appdata_setting = get_setting('skip_appdata', 'true')
            logger.info(f"Appdata exclusion setting: {skip_appdata_setting}")
            
            # Pre-filter directories to exclude appdata if setting is enabled
            skip_appdata = get_setting('skip_appdata', 'true').lower() == 'true'
            logger.info(f"skip_appdata variable value: {skip_appdata}")
            if skip_appdata:
                logger.info("Appdata exclusion enabled - will skip all appdata directories")
            else:
                logger.warning("Appdata exclusion DISABLED - will scan appdata directories")
            
            # Function to check if a path should be excluded
            def should_exclude_path(path):
                """Check if a path should be excluded from scanning"""
                if not skip_appdata:
                    return False
                
                path_lower = path.lower()
                # Check for appdata in the path
                if 'appdata' in path_lower:
                    logger.info(f"EXCLUDING appdata path: {path}")
                    return True
                
                return False
            
            # Custom walk function that properly excludes appdata
            def safe_walk(path):
                """Custom walk function that excludes appdata directories before entering them"""
                def walk_directories(start_path):
                    """Recursive directory walker that excludes appdata"""
                    try:
                        # Get all items in current directory
                        items = os.listdir(start_path)
                        dirs = []
                        files = []
                        
                        for item in items:
                            item_path = os.path.join(start_path, item)
                            
                            # CRITICAL FIX: Check the FULL PATH for appdata, not just the item name
                            if skip_appdata and 'appdata' in item_path.lower():
                                logger.info(f"Skipping appdata directory: {item_path}")
                                continue
                                
                            if os.path.isdir(item_path):
                                dirs.append(item)
                            elif os.path.isfile(item_path):
                                files.append(item)
                        
                        # Yield current directory
                        yield start_path, dirs, files
                        
                        # Recursively process subdirectories
                        for dir_name in dirs:
                            subdir_path = os.path.join(start_path, dir_name)
                            # Double-check we're not entering appdata
                            if skip_appdata and 'appdata' in subdir_path.lower():
                                logger.info(f"Preventing entry into appdata: {subdir_path}")
                                continue
                            yield from walk_directories(subdir_path)
                            
                    except PermissionError:
                        logger.warning(f"Permission denied accessing: {start_path}")
                    except Exception as e:
                        logger.error(f"Error processing directory {start_path}: {e}")
                
                return walk_directories(path)
            
            # CRITICAL: Check if the starting path itself should be excluded
            if should_exclude_path(str(self.data_path)):
                logger.error(f"Starting path {self.data_path} is excluded - cannot scan")
                raise Exception(f"Cannot scan excluded path: {self.data_path}")
            
            # Main scanning loop using custom safe_walk
            for root, dirs, files in safe_walk(self.data_path):
                if self.stop_scan:
                    logger.info("Scan stopped by user request")
                    break
                
                # Check for directory timeout
                current_time = time.time()
                if current_time - last_directory_time > directory_timeout:
                    logger.error(f"Directory timeout: {root} has been processing for {directory_timeout} seconds")
                    raise Exception(f"Directory processing timeout: {root}")
                last_directory_time = current_time
                    
                # Track current path for progress reporting
                self.current_path = root
                
                # Check for stuck detection
                if last_path != root:
                    last_path = root
                    last_path_change = current_time
                    logger.info(f"Processing directory: {root}")
                else:
                    # Use shorter timeout for any directory that seems stuck
                    current_stuck_timeout = 60  # 1 minute timeout for stuck detection
                    if current_time - last_path_change > current_stuck_timeout:
                        logger.error(f"Scan appears stuck: {root} has been processing for {current_time - last_path_change:.0f} seconds")
                        # Force skip this directory by clearing everything
                        dirs.clear()
                        files.clear()
                        logger.info(f"Forced skip of stuck directory: {root}")
                        continue
                
                # Force skip any directory that has been processing for too long (emergency escape)
                if current_time - last_directory_time > 120:  # 2 minutes per directory max
                    logger.error(f"Directory processing timeout exceeded: {root} - forcing skip")
                    dirs.clear()
                    files.clear()
                    last_directory_time = current_time
                    continue
                
                # Log current directory being processed with detailed info
                logger.info(f"Processing directory: {root} (contains {len(dirs)} subdirs, {len(files)} files)")
                
                # Warn about very large directories that might cause delays
                if len(files) > 10000:
                    logger.warning(f"Large directory detected: {root} contains {len(files):,} files - this may take a while")
                if len(dirs) > 1000:
                    logger.warning(f"Deep directory structure detected: {root} contains {len(dirs):,} subdirectories - this may take a while")
                
                # Heartbeat log every 30 seconds
                if current_time - last_heartbeat > heartbeat_interval:
                    logger.info(f"Scan heartbeat: Still processing {root} (total: {total_files:,} files, {total_directories:,} dirs, {format_size(total_size)})")
                    last_heartbeat = current_time
                    
                # Check if we've exceeded max duration
                if time.time() - scan_start_time > max_scan_time:
                    logger.warning(f"Scan stopped due to max duration limit ({self.max_duration} hours)")
                    break
                
                # Check if we've reached max shares limit (only check at top-level directories)
                if max_shares_to_scan > 0:
                    # Check if this is a top-level directory (direct child of data_path)
                    if Path(root).parent == Path(self.data_path):
                        shares_scanned += 1
                        logger.info(f"Scanning share {shares_scanned}/{max_shares_to_scan}: {Path(root).name}")
                        
                        if shares_scanned >= max_shares_to_scan:
                            logger.info(f"Reached max shares limit ({max_shares_to_scan}), stopping scan")
                            break
                
                # Process directories
                logger.info(f"Processing {len(dirs)} directories in {root}")
                for dir_name in dirs:
                    try:
                        dir_path = Path(root) / dir_name
                        stat = dir_path.stat()
                        
                        file_record = FileRecord(
                            path=str(dir_path),
                            name=dir_name,
                            size=0,
                            is_directory=True,
                            parent_path=str(Path(root)),
                            created_time=datetime.fromtimestamp(stat.st_ctime),
                            modified_time=datetime.fromtimestamp(stat.st_mtime),
                            accessed_time=datetime.fromtimestamp(stat.st_atime),
                            permissions=oct(stat.st_mode)[-3:],
                            scan_id=self.current_scan.id
                        )
                        db.session.add(file_record)
                        total_directories += 1
                        
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Error accessing directory {dir_path}: {e}")
                
                # Process files
                logger.info(f"Processing {len(files)} files in {root}")
                for file_name in files:
                    try:
                        file_path = Path(root) / file_name
                        stat = file_path.stat()
                        
                        # Get file extension
                        extension = file_path.suffix.lower()
                        
                        file_record = FileRecord(
                            path=str(file_path),
                            name=file_name,
                            size=stat.st_size,
                            is_directory=False,
                            parent_path=str(Path(root)),
                            extension=extension,
                            created_time=datetime.fromtimestamp(stat.st_ctime),
                            modified_time=datetime.fromtimestamp(stat.st_mtime),
                            accessed_time=datetime.fromtimestamp(stat.st_atime),
                            permissions=oct(stat.st_mode)[-3:],
                            scan_id=self.current_scan.id
                        )
                        db.session.add(file_record)
                        
                        total_files += 1
                        total_size += stat.st_size
                        
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Error accessing file {file_path}: {e}")
                
                # Update scan record less frequently to reduce database contention (every 100 files or 5 seconds)
                current_time = time.time()
                if (total_files % 100 == 0 or current_time - last_update_time > 5):
                    try:
                        db.session.commit()
                        
                        # Update scan record with current progress
                        self.current_scan.total_files = total_files
                        self.current_scan.total_directories = total_directories
                        self.current_scan.total_size = total_size
                        db.session.commit()
                        
                        last_update_time = current_time
                        logger.info(f"Processed {total_files:,} files, {total_directories:,} directories, {format_size(total_size)}")
                    except Exception as e:
                        logger.error(f"Error updating scan progress: {e}")
                        # Try to recover from database errors
                        try:
                            db.session.rollback()
                            # Force a new connection if we hit pool limits
                            if "QueuePool limit" in str(e) or "connection timed out" in str(e):
                                logger.info("Database pool exhausted, forcing connection refresh")
                                db.session.close()
                                db.session.remove()
                        except:
                            pass
                
                # Log progress every 100 directories for better visibility
                if total_directories % 100 == 0:
                    logger.info(f"Processed {total_directories:,} directories so far")
                
                # Log detailed progress every minute
                if current_time - last_progress_log > progress_log_interval:
                    elapsed_time = current_time - self.scan_start_time
                    rate_files = total_files / elapsed_time if elapsed_time > 0 else 0
                    rate_dirs = total_directories / elapsed_time if elapsed_time > 0 else 0
                    logger.info(f"Progress update: {total_files:,} files, {total_directories:,} dirs, {format_size(total_size)} in {elapsed_time:.0f}s ({rate_files:.1f} files/s, {rate_dirs:.1f} dirs/s)")
                    last_progress_log = current_time
            
            # Final commit
            db.session.commit()
            
            # Update scan record
            self.current_scan.total_files = total_files
            self.current_scan.total_directories = total_directories
            self.current_scan.total_size = total_size
            self.current_scan.end_time = datetime.utcnow()
            self.current_scan.status = 'completed'
            db.session.commit()
            
            # Record storage history
            self._record_storage_history(total_size, total_files, total_directories)
            
            logger.info(f"Scan completed: {total_files} files, {total_directories} directories, {total_size} bytes")
            
        except Exception as e:
            logger.error(f"Scan failed: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            if self.current_scan:
                self.current_scan.status = 'failed'
                self.current_scan.error_message = str(e)
                self.current_scan.end_time = datetime.utcnow()
                db.session.commit()
        finally:
            logger.info(f"=== SCANNER THREAD ENDING ===")
            self.scanning = False

    def _extract_media_metadata(self, file_record: FileRecord, file_path: Path):
        """Extract metadata from media files"""
        try:
            # Try to extract metadata using mutagen
            # media_file = MutagenFile(str(file_path))
            # if not media_file:
            #     return
                
            # Determine media type and extract basic info
            extension = file_path.suffix.lower()
            filename = file_path.stem
            
            media_type = 'other'
            title = None
            year = None
            season = None
            episode = None
            resolution = None
            video_codec = None
            audio_codec = None
            runtime = None
            
            # Check if it's a TV show
            for pattern in self.tv_patterns:
                match = re.search(pattern, filename, re.IGNORECASE)
                if match:
                    media_type = 'tv_show'
                    title = match.group(1).strip()
                    season = int(match.group(2))
                    episode = int(match.group(3))
                    break
            
            # Check if it's a movie
            if media_type == 'other':
                for pattern in self.movie_patterns:
                    match = re.search(pattern, filename, re.IGNORECASE)
                    if match:
                        media_type = 'movie'
                        title = match.group(1).strip()
                        year = int(match.group(2))
                        break
            
            # Extract resolution and codec info from filename
            for pattern in self.resolution_patterns:
                match = re.search(pattern, filename, re.IGNORECASE)
                if match:
                    resolution = match.group(0)
                    break
            
            for pattern in self.video_codec_patterns:
                if pattern.lower() in filename.lower():
                    video_codec = pattern
                    break
            
            for pattern in self.audio_codec_patterns:
                if pattern.lower() in filename.lower():
                    audio_codec = pattern
                    break
            
            # Try to get runtime from metadata
            # if hasattr(media_file, 'info') and hasattr(media_file.info, 'length'):
            #     runtime = int(media_file.info.length / 60)  # Convert to minutes
            
            # Create media file record
            media_record = MediaFile(
                file_id=file_record.id,
                media_type=media_type,
                title=title,
                year=year,
                season=season,
                episode=episode,
                resolution=resolution,
                video_codec=video_codec,
                audio_codec=audio_codec,
                runtime=runtime,
                file_format=extension[1:] if extension else None
            )
            db.session.add(media_record)
            
        except Exception as e:
            logger.debug(f"Error extracting metadata from {file_path}: {e}")

    def _record_storage_history(self, total_size: int, total_files: int, total_directories: int):
        """Record storage usage for historical tracking"""
        try:
            # Check if we already have a record for today
            today = datetime.utcnow().date()
            existing_record = StorageHistory.query.filter(
                db.func.date(StorageHistory.date) == today
            ).first()
            
            if existing_record:
                # Update existing record
                existing_record.total_size = total_size
                existing_record.file_count = total_files
                existing_record.directory_count = total_directories
            else:
                # Create new record
                history_record = StorageHistory(
                    date=datetime.utcnow(),
                    total_size=total_size,
                    file_count=total_files,
                    directory_count=total_directories
                )
                db.session.add(history_record)
            
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Error recording storage history: {e}")

    def get_file_hash(self, file_path: str, chunk_size: int = 8192) -> str:
        """Calculate SHA256 hash of a file"""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating hash for {file_path}: {e}")
            return None 