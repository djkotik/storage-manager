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
        
        # Reset scanner state completely before starting new scan
        self.scanning = False
        self.stop_scan = False
        self.current_scan = None
        self.scan_start_time = None
        self.current_path = None
        
        # Now set up for new scan
        self.scanning = True
        self.stop_scan = False
        self.scan_start_time = time.time()
        logger.info(f"Set scan_start_time to: {self.scan_start_time}")
        
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
        
        # Force stop any running scans in database with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                running_scans = ScanRecord.query.filter_by(status='running').all()
                for scan in running_scans:
                    scan.status = 'failed'
                    scan.error_message = 'Force reset by user'
                    scan.end_time = datetime.utcnow()
                db.session.commit()
                logger.info(f"Force reset {len(running_scans)} running scans in database")
                break
            except Exception as e:
                logger.warning(f"Database reset attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    try:
                        db.session.rollback()
                        db.session.close()
                        db.session.remove()
                        time.sleep(2)
                    except:
                        pass
                else:
                    logger.error(f"Failed to reset database after {max_retries} attempts")
        
        # Reset all state variables
        self.scan_start_time = None
        self.current_path = None
        
        logger.info("Scanner state reset complete")

    def cleanup_database_connections(self):
        """Clean up database connections to prevent locking issues"""
        try:
            logger.info("Cleaning up database connections...")
            db.session.rollback()
            db.session.close()
            db.session.remove()
            logger.info("Database connections cleaned up")
        except Exception as e:
            logger.warning(f"Error cleaning up database connections: {e}")

    def get_scan_status(self) -> Dict:
        """Get current scan status"""
        # First check if we have an active scan in memory
        if self.current_scan and self.scanning:
            # Ensure we have the current scan record from database
            try:
                current_scan_from_db = ScanRecord.query.get(self.current_scan.id)
                if current_scan_from_db and current_scan_from_db.status != 'running':
                    logger.warning(f"Scan {self.current_scan.id} status is {current_scan_from_db.status}, not running")
                    # Reset our state since scan is no longer running
                    self.scanning = False
                    self.current_scan = None
                    return {'status': 'idle'}
            except Exception as e:
                logger.warning(f"Error checking scan status from database: {e}")
            
            # Calculate elapsed time - add debugging
            if self.scan_start_time is None:
                logger.warning("scan_start_time is None - this should not happen during active scan")
                elapsed_time = 0
            else:
                elapsed_time = time.time() - self.scan_start_time
                logger.debug(f"Elapsed time calculation: {time.time()} - {self.scan_start_time} = {elapsed_time}")
            
            current_path = getattr(self, 'current_path', 'Unknown')
            
            # Get current progress from in-memory variables (more accurate than database)
            total_files = getattr(self, '_total_files', self.current_scan.total_files or 0)
            total_directories = getattr(self, '_total_directories', self.current_scan.total_directories or 0)
            total_size = getattr(self, '_total_size', self.current_scan.total_size or 0)
            
            # Calculate processing rate
            processing_rate = None
            if elapsed_time > 0 and total_files > 0:
                files_per_second = total_files / elapsed_time
                processing_rate = f"{files_per_second:.1f} files/sec"
            
            # Estimate completion time based on current progress
            estimated_completion = None
            progress_percentage = 0
            if total_directories > 0 and elapsed_time > 0:
                # Rough estimate: assume 210,006 total directories based on logs
                total_estimated_dirs = 210006
                progress_percentage = min(100, (total_directories / total_estimated_dirs) * 100)
                
                if progress_percentage > 0:
                    estimated_total_time = elapsed_time / (progress_percentage / 100)
                    estimated_remaining = estimated_total_time - elapsed_time
                    estimated_completion = datetime.fromtimestamp(time.time() + estimated_remaining)
            
            # Format scan duration for display
            scan_duration = self._format_duration(elapsed_time)
            
            response_data = {
                'scan_id': self.current_scan.id,
                'status': self.current_scan.status,
                'start_time': self.current_scan.start_time.isoformat(),
                'end_time': self.current_scan.end_time.isoformat() if self.current_scan.end_time else None,
                'total_files': total_files,
                'total_directories': total_directories,
                'total_size': total_size,
                'total_size_formatted': format_size(total_size),
                'scanning': self.scanning,
                'elapsed_time': elapsed_time,
                'elapsed_time_formatted': scan_duration,
                'current_path': current_path,
                'estimated_completion': estimated_completion.isoformat() if estimated_completion else None,
                'progress_percentage': progress_percentage,
                'processing_rate': processing_rate,
                'scan_duration': scan_duration  # Ensure this is always set
            }
            
            # Add debugging information
            logger.debug(f"Scan status response: elapsed_time={elapsed_time}, scan_duration='{scan_duration}', elapsed_time_formatted='{scan_duration}'")
            
            return response_data
        
        # If no active scan in memory, check for recent scan activity in database
        try:
            # Look for the most recent scan (completed, failed, or stopped)
            recent_scan = ScanRecord.query.order_by(ScanRecord.start_time.desc()).first()
            
            if recent_scan:
                # If the scan was very recent (within last 5 minutes) and failed, show it
                time_since_scan = (datetime.utcnow() - recent_scan.start_time).total_seconds()
                
                if time_since_scan < 300:  # 5 minutes
                    if recent_scan.status in ['failed', 'stopped']:
                        logger.info(f"Recent scan {recent_scan.id} {recent_scan.status} - showing status")
                        
                        # Calculate duration
                        if recent_scan.end_time:
                            duration = (recent_scan.end_time - recent_scan.start_time).total_seconds()
                        else:
                            duration = time_since_scan
                        
                        return {
                            'status': recent_scan.status,
                            'scan_id': recent_scan.id,
                            'start_time': recent_scan.start_time.isoformat(),
                            'end_time': recent_scan.end_time.isoformat() if recent_scan.end_time else None,
                            'total_files': recent_scan.total_files or 0,
                            'total_directories': recent_scan.total_directories or 0,
                            'total_size': recent_scan.total_size or 0,
                            'total_size_formatted': format_size(recent_scan.total_size or 0),
                            'scanning': False,
                            'elapsed_time': duration,
                            'elapsed_time_formatted': self._format_duration(duration),
                            'current_path': 'Scan completed',
                            'error_message': recent_scan.error_message,
                            'scan_duration': self._format_duration(duration)
                        }
        except Exception as e:
            logger.warning(f"Error checking recent scan activity: {e}")
        
        # No active or recent scan found
        return {'status': 'idle'}
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to human readable format"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"

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
            
            # Store progress in instance variables for real-time access
            self._total_files = 0
            self._total_directories = 0
            self._total_size = 0
            
            # Get max shares to scan setting
            max_shares_to_scan = int(get_setting('max_shares_to_scan', '0'))
            shares_scanned = 0
            
            # Clear old file records for this scan
            FileRecord.query.filter_by(scan_id=self.current_scan.id).delete()
            
            # Get appdata exclusion setting
            skip_appdata = get_setting('skip_appdata', 'true').lower() == 'true'
            logger.info(f"Appdata exclusion setting: {skip_appdata}")
            
            # SIMPLIFIED AND AGGRESSIVE appdata exclusion function
            def is_appdata_path(path_str):
                """Simple check if path contains appdata - EXTREMELY AGGRESSIVE"""
                if not skip_appdata:
                    return False
                
                path_lower = path_str.lower()
                
                # Check for ANY occurrence of appdata in the path
                if 'appdata' in path_lower:
                    logger.info(f"EXCLUDING appdata path: {path_str}")
                    return True
                
                # Also exclude other problematic directories that might cause delays
                problematic_patterns = [
                    'cache', 'temp', 'tmp', 'logs', 'log', 'backup', 'backups',
                    'xteve', 'plex', 'emby', 'jellyfin', 'sonarr', 'radarr', 
                    'lidarr', 'readarr', 'sabnzbd', 'nzbget', 'transmission', 
                    'deluge', 'qbit', 'qbittorrent', 'docker', 'containers'
                ]
                
                for pattern in problematic_patterns:
                    if pattern in path_lower:
                        logger.info(f"EXCLUDING problematic directory: {path_str}")
                        return True
                
                return False
            
            # CRITICAL: Check if the starting path itself should be excluded
            if is_appdata_path(str(self.data_path)):
                logger.error(f"Starting path {self.data_path} is excluded - cannot scan")
                raise Exception(f"Cannot scan excluded path: {self.data_path}")
            
            # Enhanced timeout and stuck detection - ULTRA AGGRESSIVE
            last_directory_time = time.time()
            directory_timeout = 10  # 10 seconds timeout per directory (reduced from 15)
            last_heartbeat = time.time()
            heartbeat_interval = 5  # Log heartbeat every 5 seconds (reduced from 10)
            last_path = None
            last_path_change = time.time()
            
            # Add overall scan timeout protection
            scan_start_time = time.time()
            max_scan_time = self.max_duration * 3600  # Convert hours to seconds
            
            # Track progress logging
            last_progress_log = time.time()
            progress_log_interval = 10  # Log progress every 10 seconds (reduced from 20)
            
            # Track stuck detection - ULTRA AGGRESSIVE
            stuck_timeout = 20  # 20 seconds without path change (reduced from 30)
            
            # Database cleanup tracking
            last_db_cleanup = time.time()
            db_cleanup_interval = 300  # Clean up database connections every 5 minutes
            
            # COMPLETE REWRITE: Use os.walk with aggressive filtering
            logger.info("Starting directory walk with aggressive appdata exclusion...")
            
            for root, dirs, files in os.walk(self.data_path):
                if self.stop_scan:
                    logger.info("Scan stopped by user request")
                    break
                
                # CRITICAL: Check if current directory should be excluded
                if is_appdata_path(root):
                    logger.info(f"SKIPPING excluded directory: {root}")
                    # Remove all subdirectories to prevent recursion
                    dirs.clear()
                    continue
                
                # Check for directory timeout
                current_time = time.time()
                if current_time - last_directory_time > directory_timeout:
                    logger.error(f"Directory timeout: {root} has been processing for {directory_timeout} seconds")
                    # Force skip this directory and continue
                    logger.info(f"FORCED SKIP of timeout directory: {root}")
                    dirs.clear()
                    files.clear()
                    continue
                last_directory_time = current_time
                    
                # Track current path for progress reporting
                self.current_path = root
                
                # Enhanced stuck detection and progress logging
                if last_path != root:
                    last_path = root
                    last_path_change = current_time
                    logger.info(f"Processing directory: {root}")
                    
                    # Log progress every 500 directories
                    if total_directories % 500 == 0:
                        elapsed_time = current_time - self.scan_start_time
                        logger.info(f"=== SCAN PROGRESS ===")
                        logger.info(f"Files processed: {total_files:,}")
                        logger.info(f"Directories processed: {total_directories:,}")
                        logger.info(f"Total size: {format_size(total_size)}")
                        logger.info(f"Current path: {root}")
                        logger.info(f"Elapsed time: {self._format_duration(elapsed_time)}")
                else:
                    # Check for stuck detection - shorter timeout
                    if current_time - last_path_change > stuck_timeout:
                        logger.error(f"SCAN STUCK: {root} has been processing for {current_time - last_path_change:.0f} seconds")
                        logger.error(f"Files in current directory: {len(files)}, Subdirectories: {len(dirs)}")
                        # Force skip this directory
                        dirs.clear()
                        files.clear()
                        logger.info(f"FORCED SKIP of stuck directory: {root}")
                        continue
                
                # Force skip any directory that has been processing for too long (emergency escape)
                if current_time - last_directory_time > 10:  # 10 seconds per directory max (reduced from 15)
                    logger.error(f"Directory processing timeout exceeded: {root} - forcing skip")
                    dirs.clear()
                    files.clear()
                    last_directory_time = current_time
                    continue
                
                # Log current directory being processed with detailed info
                logger.info(f"Processing directory: {root} (contains {len(dirs)} subdirs, {len(files)} files)")
                
                # Skip very large directories that might cause delays
                if len(files) > 10000:
                    logger.warning(f"SKIPPING extremely large directory: {root} contains {len(files):,} files - skipping to avoid delays")
                    dirs.clear()
                    files.clear()
                    continue
                if len(dirs) > 1000:
                    logger.warning(f"SKIPPING extremely deep directory: {root} contains {len(dirs):,} subdirectories - skipping to avoid delays")
                    dirs.clear()
                    files.clear()
                    continue
                
                # Warn about large directories that might cause delays
                if len(files) > 5000:
                    logger.warning(f"Large directory detected: {root} contains {len(files):,} files - this may take a while")
                if len(dirs) > 500:
                    logger.warning(f"Deep directory structure detected: {root} contains {len(dirs):,} subdirectories - this may take a while")
                
                # Heartbeat log every 5 seconds
                if current_time - last_heartbeat > heartbeat_interval:
                    elapsed_time = current_time - self.scan_start_time
                    logger.info(f"Scan heartbeat: Still processing {root} (total: {total_files:,} files, {total_directories:,} dirs, {format_size(total_size)}, elapsed: {self._format_duration(elapsed_time)})")
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
                
                # Process directories and files in batches to reduce database contention
                batch_size = 100  # Process in batches of 100
                dir_batch = []
                file_batch = []
                
                # Process directories
                logger.info(f"Processing {len(dirs)} directories in {root}")
                for dir_name in dirs:
                    try:
                        dir_path = Path(root) / dir_name
                        
                        # DOUBLE CHECK: Make sure we're not processing an appdata directory
                        if is_appdata_path(str(dir_path)):
                            logger.info(f"SKIPPING appdata subdirectory: {dir_path}")
                            continue
                        
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
                        dir_batch.append(file_record)
                        total_directories += 1
                        self._total_directories = total_directories
                        
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Error accessing directory {dir_path}: {e}")
                
                # Process files
                logger.info(f"Processing {len(files)} files in {root}")
                for file_name in files:
                    try:
                        file_path = Path(root) / file_name
                        
                        # DOUBLE CHECK: Make sure we're not processing an appdata file
                        if is_appdata_path(str(file_path)):
                            logger.info(f"SKIPPING appdata file: {file_path}")
                            continue
                        
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
                        file_batch.append(file_record)
                        
                        total_files += 1
                        total_size += stat.st_size
                        self._total_files = total_files
                        self._total_size = total_size
                        
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Error accessing file {file_path}: {e}")
                
                # Commit batches to database with improved error handling
                try:
                    # Add directory batch
                    if dir_batch:
                        db.session.bulk_save_objects(dir_batch)
                        logger.info(f"Committed {len(dir_batch)} directories to database")
                    
                    # Add file batch
                    if file_batch:
                        db.session.bulk_save_objects(file_batch)
                        logger.info(f"Committed {len(file_batch)} files to database")
                    
                    # Commit the batch with retry logic
                    max_retries = 3
                    retry_count = 0
                    committed = False
                    
                    while retry_count < max_retries and not committed:
                        try:
                            db.session.commit()
                            committed = True
                            logger.info(f"Successfully committed batch to database")
                        except Exception as commit_error:
                            retry_count += 1
                            logger.warning(f"Database commit attempt {retry_count} failed: {commit_error}")
                            
                            if "database is locked" in str(commit_error) or "QueuePool limit" in str(commit_error):
                                # Wait longer between retries for database locks
                                wait_time = retry_count * 3  # 3, 6, 9 seconds
                                logger.info(f"Database locked, waiting {wait_time} seconds before retry {retry_count}")
                                time.sleep(wait_time)
                                
                                # Force session cleanup
                                try:
                                    db.session.rollback()
                                    db.session.close()
                                    db.session.remove()
                                    # Small delay to let database settle
                                    time.sleep(1)
                                except:
                                    pass
                            else:
                                # For other errors, don't retry
                                break
                    
                    if not committed:
                        logger.error(f"Failed to commit batch after {max_retries} attempts - skipping batch")
                        # Clear the batches to avoid memory buildup
                        dir_batch.clear()
                        file_batch.clear()
                        
                except Exception as e:
                    logger.error(f"Error preparing batch for database: {e}")
                    # Clear the session and continue
                    try:
                        db.session.rollback()
                        db.session.close()
                        db.session.remove()
                    except:
                        pass
                
                # Update scan record more frequently to ensure data is saved (every 50 files or 3 seconds)
                current_time = time.time()
                if (total_files % 50 == 0 or current_time - last_update_time > 3):
                    try:
                        # Update scan record with current progress
                        self.current_scan.total_files = total_files
                        self.current_scan.total_directories = total_directories
                        self.current_scan.total_size = total_size
                        
                        # Commit with retry logic for scan record updates
                        max_retries = 3
                        retry_count = 0
                        committed = False
                        
                        while retry_count < max_retries and not committed:
                            try:
                                db.session.commit()
                                committed = True
                                last_update_time = current_time
                                elapsed_time = current_time - self.scan_start_time
                                logger.info(f"Processed {total_files:,} files, {total_directories:,} directories, {format_size(total_size)} in {self._format_duration(elapsed_time)}")
                            except Exception as commit_error:
                                retry_count += 1
                                logger.warning(f"Scan record update attempt {retry_count} failed: {commit_error}")
                                
                                if "database is locked" in str(commit_error) or "QueuePool limit" in str(commit_error):
                                    # Wait between retries
                                    wait_time = retry_count * 2  # 2, 4, 6 seconds
                                    logger.info(f"Database locked during scan update, waiting {wait_time} seconds before retry {retry_count}")
                                    time.sleep(wait_time)
                                    
                                    # Force session cleanup
                                    try:
                                        db.session.rollback()
                                        db.session.close()
                                        db.session.remove()
                                        time.sleep(1)
                                    except:
                                        pass
                                else:
                                    # For other errors, don't retry
                                    break
                        
                        if not committed:
                            logger.error(f"Failed to update scan record after {max_retries} attempts - continuing scan")
                            
                    except Exception as e:
                        logger.error(f"Error updating scan progress: {e}")
                        # Try to recover from database errors
                        try:
                            db.session.rollback()
                            db.session.close()
                            db.session.remove()
                        except:
                            pass
                
                # Log progress every 100 directories for better visibility
                if total_directories % 100 == 0:
                    elapsed_time = current_time - self.scan_start_time
                    logger.info(f"Processed {total_directories:,} directories so far in {self._format_duration(elapsed_time)}")
                
                # Log detailed progress every minute
                if current_time - last_progress_log > progress_log_interval:
                    elapsed_time = current_time - self.scan_start_time
                    rate_files = total_files / elapsed_time if elapsed_time > 0 else 0
                    rate_dirs = total_directories / elapsed_time if elapsed_time > 0 else 0
                    logger.info(f"Progress update: {total_files:,} files, {total_directories:,} dirs, {format_size(total_size)} in {self._format_duration(elapsed_time)} ({rate_files:.1f} files/s, {rate_dirs:.1f} dirs/s)")
                    last_progress_log = current_time
                
                # Periodic database cleanup to prevent connection buildup
                if current_time - last_db_cleanup > db_cleanup_interval:
                    logger.info("Performing periodic database cleanup...")
                    self.cleanup_database_connections()
                    last_db_cleanup = current_time
            
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
            
            elapsed_time = time.time() - self.scan_start_time
            logger.info(f"Scan completed: {total_files} files, {total_directories} directories, {total_size} bytes in {self._format_duration(elapsed_time)}")
            
        except Exception as e:
            logger.error(f"Scan failed: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Ensure the scan record is properly updated with error information
            if self.current_scan:
                try:
                    # Get the current scan from database to ensure we have the latest
                    scan_record = ScanRecord.query.get(self.current_scan.id)
                    if scan_record:
                        scan_record.status = 'failed'
                        scan_record.error_message = f"Scan failed: {str(e)}"
                        scan_record.end_time = datetime.utcnow()
                        db.session.commit()
                        logger.info(f"Scan record updated with error: ID {scan_record.id}")
                    else:
                        logger.error("Could not find scan record in database to update")
                except Exception as db_error:
                    logger.error(f"Error updating scan record with error: {db_error}")
                    # Try to rollback and continue
                    try:
                        db.session.rollback()
                    except:
                        pass
        finally:
            logger.info(f"=== SCANNER THREAD ENDING ===")
            # Clean up scan state
            logger.info("Cleaning up scan state...")
            self.scanning = False
            self.current_scan = None
            logger.info("Scan state cleaned up")

    def _extract_media_metadata(self, file_record: FileRecord, file_path: Path):
        """Extract metadata from media files"""
        try:
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