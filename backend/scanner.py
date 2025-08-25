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

from models import FileRecord, MediaFile, StorageHistory

# Import db and models from Flask app - this should work within app context  
from app import db

# Global scanner state reference
scanner_state = None

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
        self.current_scan_id = None
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
            # Ensure Flask context for database operations
            try:
                from flask import current_app
                current_app.extensions['sqlalchemy']
                # We have Flask context, proceed normally
                from app import ScanRecord
                running_scans = db.session.query(ScanRecord).filter_by(status='running').all()
                for scan in running_scans:
                    scan.status = 'failed'
                    scan.error_message = 'Superseded by new scan'
                    scan.end_time = datetime.utcnow()
                db.session.commit()
                logger.info(f"Marked {len(running_scans)} existing running scans as failed")
            except RuntimeError:
                # No Flask context, create one
                from app import app, ScanRecord
                with app.app_context():
                    running_scans = db.session.query(ScanRecord).filter_by(status='running').all()
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
        self.current_scan_id = None
        self.scan_start_time = None
        self.current_path = None
        
        # Now set up for new scan
        self.scanning = True
        self.stop_scan = False
        self.scan_start_time = time.time()
        logger.info(f"Set scan_start_time to: {self.scan_start_time}")
        
        # Create scan record
        try:
            # Ensure Flask context for database operations
            try:
                from flask import current_app
                current_app.extensions['sqlalchemy']
                # We have Flask context, proceed normally
                from app import ScanRecord
                self.current_scan = ScanRecord(
                    start_time=datetime.utcnow(),
                    status='running'
                )
                db.session.add(self.current_scan)
                db.session.commit()
                # Store the scan ID for later reference
                self.current_scan_id = self.current_scan.id
            except RuntimeError:
                # No Flask context, create one
                from app import app, ScanRecord
                with app.app_context():
                    self.current_scan = ScanRecord(
                        start_time=datetime.utcnow(),
                        status='running'
                    )
                    db.session.add(self.current_scan)
                    db.session.commit()
                    # Store the scan ID for later reference
                    self.current_scan_id = self.current_scan.id
        except Exception as e:
            logger.error(f"Error creating scan record: {e}")
            raise
        
        # Start scan in background thread
        logger.info(f"About to start scan thread for scan ID {self.current_scan_id}")
        scan_thread = threading.Thread(target=self._scan_filesystem)
        scan_thread.daemon = True
        scan_thread.start()
        logger.info(f"Scan thread started successfully for scan ID {self.current_scan_id}")
        
        logger.info(f"Started scan session {self.current_scan_id}")
        return self.current_scan_id

    def stop_current_scan(self):
        """Stop the current scan"""
        self.stop_scan = True
        logger.info("Scan stop requested")
    
    def update_scanner_state(self, total_files, total_directories, total_size, current_path):
        """Update global scanner state for dashboard display"""
        global scanner_state
        if scanner_state is not None:
            scanner_state['total_files'] = total_files
            scanner_state['total_directories'] = total_directories
            scanner_state['total_size'] = total_size
            scanner_state['current_path'] = current_path
            # Ensure scanner state shows we're scanning
            scanner_state['scanning'] = self.scanning

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
                from app import ScanRecord
                running_scans = db.session.query(ScanRecord).filter_by(status='running').all()
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
                from app import ScanRecord
                current_scan_from_db = db.session.query(ScanRecord).get(self.current_scan_id)
                if current_scan_from_db and current_scan_from_db.status != 'running':
                    logger.warning(f"Scan {self.current_scan_id} status is {current_scan_from_db.status}, not running")
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
            total_files = getattr(self, '_total_files', 0)
            total_directories = getattr(self, '_total_directories', 0)
            total_size = getattr(self, '_total_size', 0)
            
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
                'scan_id': self.current_scan_id,
                'status': 'running',  # We know it's running if we're in this branch
                'start_time': datetime.fromtimestamp(self.scan_start_time).isoformat() if self.scan_start_time else None,
                'end_time': None,  # Running scan has no end time
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
            from app import ScanRecord
            recent_scan = db.session.query(ScanRecord).order_by(ScanRecord.start_time.desc()).first()
            
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
        
        # Ensure Flask context for the entire scanning process
        try:
            from flask import current_app
            current_app.extensions['sqlalchemy']
            # We have Flask context, proceed normally
            logger.info("Scanner thread has Flask context")
        except RuntimeError:
            # No Flask context, create one for the entire method
            from app import app
            logger.info("Scanner thread creating Flask context")
            with app.app_context():
                return self._scan_filesystem_with_context()
        except Exception as e:
            logger.error(f"Error checking Flask context: {e}")
            # Try to create context anyway
            from app import app
            with app.app_context():
                return self._scan_filesystem_with_context()
                
        # If we have context, proceed normally
        return self._scan_filesystem_with_context()
    
    def _scan_filesystem_with_context(self):
        """Main scanning implementation - assumes Flask context is available"""
        global scanner_state
        
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
    
            
            def is_excluded_share(share_name):
                """Check if a share should be excluded"""
                share_lower = share_name.lower()
                
                # Check skip_appdata setting
                skip_appdata = get_setting('skip_appdata', 'true').lower() == 'true'
                if skip_appdata and ('appdata' in share_lower or share_lower == 'appdata'):
                    logger.info(f"Excluding appdata share: {share_name} (skip_appdata setting enabled)")
                    return True
                
                # Also exclude other problematic shares
                excluded_shares = [
                    'cache', 'temp', 'tmp', 'logs', 'log', 'backup', 'backups',
                    'xteve', 'plex', 'emby', 'jellyfin', 'sonarr', 'radarr', 
                    'lidarr', 'readarr', 'sabnzbd', 'nzbget', 'transmission', 
                    'deluge', 'qbit', 'qbittorrent', 'docker', 'containers'
                ]
                
                for excluded in excluded_shares:
                    if excluded in share_lower:
                        logger.info(f"EXCLUDING problematic share: {share_name}")
                        return True
                
                return False
            
            # CRITICAL: Check if the starting path itself should be excluded
            if is_excluded_share(os.path.basename(self.data_path)):
                logger.error(f"Starting path {self.data_path} is excluded - cannot scan")
                raise Exception(f"Cannot scan excluded path: {self.data_path}")
            
            # Enhanced timeout and stuck detection
            last_directory_time = time.time()
            directory_timeout = 10  # 10 seconds timeout per directory
            last_heartbeat = time.time()
            heartbeat_interval = 5  # Log heartbeat every 5 seconds
            last_path = None
            last_path_change = time.time()
            
            # Add overall scan timeout protection
            scan_start_time = time.time()
            max_scan_time = self.max_duration * 3600  # Convert hours to seconds
            
            # Track progress logging
            last_progress_log = time.time()
            progress_log_interval = 10  # Log progress every 10 seconds
            
            # Track stuck detection
            stuck_timeout = 20  # 20 seconds without path change
            
            # Database cleanup tracking
            last_db_cleanup = time.time()
            db_cleanup_interval = 300  # Clean up database connections every 5 minutes
            
            # COMPLETE REWRITE: Manual directory traversal with share-level exclusion
            logger.error("🚨 STARTING BULLETPROOF SCAN WITH APPDATA EXCLUSION v1.7.2+ 🚨")
            logger.error(f"🚨 SCANNER VERSION CHECK: This should show if container is updated")
            
            # CRITICAL: Initialize scan_start_time if not already set
            if self.scan_start_time is None:
                self.scan_start_time = time.time()
                logger.info(f"Initialized scan_start_time to: {self.scan_start_time}")
            
            # Get all top-level shares/directories
            try:
                top_level_items = os.listdir(self.data_path)
                logger.error(f"🚨 Found {len(top_level_items)} top-level items in {self.data_path}")
                logger.error(f"🚨 Top-level items: {top_level_items}")
            except Exception as e:
                logger.error(f"Error listing top-level directories: {e}")
                raise
            
            # Process each top-level share
            for share_name in top_level_items:
                if self.stop_scan:
                    logger.info("Scan stopped by user request")
                    break
                
                share_path = os.path.join(self.data_path, share_name)
                
                # CRITICAL: Check if this share should be excluded BEFORE processing
                if is_excluded_share(share_name):
                    logger.error(f"🚨 SKIPPING EXCLUDED SHARE: {share_name} at {share_path}")
                    continue
                
                logger.error(f"🚨 PROCESSING ALLOWED SHARE: {share_name} at {share_path}")
                
                # Check if it's a directory
                if not os.path.isdir(share_path):
                    logger.info(f"Skipping non-directory: {share_path}")
                    continue
                
                # Create FileRecord for the top-level share directory itself
                try:
                    if not self.current_scan_id:
                        logger.error(f"🚨 CRITICAL: current_scan_id is None during share processing: {share_path}")
                        continue
                    
                    # Create record for the share directory (e.g., /data/tv shows)
                    share_record = FileRecord(
                        path=share_path,
                        name=share_name,
                        size=0,
                        is_directory=True,
                        parent_path=str(self.data_path),  # parent is /data
                        scan_id=self.current_scan_id
                    )
                    db.session.add(share_record)
                    total_directories += 1
                    self._total_directories = total_directories
                    logger.info(f"Created top-level share record: {share_path} (parent: {self.data_path})")
                    
                except Exception as e:
                    logger.error(f"Error creating share directory record for {share_path}: {e}")
                    db.session.rollback()
                    continue
                
                # Now scan this share recursively
                try:
                    for root, dirs, files in os.walk(share_path):
                        if self.stop_scan:
                            logger.info("Scan stopped by user request")
                            break
                        
                        # Check skip_appdata setting for directory filtering
                        skip_appdata = get_setting('skip_appdata', 'true').lower() == 'true'
                        if skip_appdata:
                            # Filter out appdata directories from dirs list
                            original_dirs = dirs.copy()
                            dirs[:] = [d for d in dirs if 'appdata' not in d.lower()]
                            if len(original_dirs) != len(dirs):
                                logger.info(f"Filtered out {len(original_dirs) - len(dirs)} appdata directories from {root} (skip_appdata setting enabled)")
                        
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
                            # Check for stuck detection
                            if current_time - last_path_change > stuck_timeout:
                                logger.error(f"SCAN STUCK: {root} has been processing for {current_time - last_path_change:.0f} seconds")
                                logger.error(f"Files in current directory: {len(files)}, Subdirectories: {len(dirs)}")
                                # Force skip this directory
                                dirs.clear()
                                files.clear()
                                logger.info(f"FORCED SKIP of stuck directory: {root}")
                                continue
                        
                        # Force skip any directory that has been processing for too long (emergency escape)
                        if current_time - last_directory_time > 10:  # 10 seconds per directory max
                            logger.error(f"Directory processing timeout exceeded: {root} - forcing skip")
                            dirs.clear()
                            files.clear()
                            continue
                        
                        # Process directories first
                        for dir_name in dirs:
                             if self.stop_scan:
                                 break
                             
                             dir_path = os.path.join(root, dir_name)
                             
                             try:
                                 # Ensure we have a scan record
                                 if not self.current_scan_id:
                                     logger.error(f"🚨 CRITICAL: current_scan_id is None during directory processing: {dir_path}")
                                     continue
                                
                                 # Create directory record using FileRecord with is_directory=True
                                 dir_record = FileRecord(
                                     path=dir_path,
                                     name=dir_name,
                                     size=0,
                                     is_directory=True,
                                     parent_path=root,
                                     scan_id=self.current_scan_id
                                 )
                                 db.session.add(dir_record)
                                 total_directories += 1
                                 self._total_directories = total_directories
                                
                                 # Commit every 100 directories to prevent memory buildup
                                 if total_directories % 100 == 0:
                                     db.session.commit()
                                     logger.debug(f"Committed {total_directories} directories")
                                     
                             except Exception as e:
                                 logger.error(f"Error processing directory {dir_path}: {e}")
                                 db.session.rollback()
                                 continue
                        
                        # Process files
                        for file_name in files:
                            if self.stop_scan:
                                break
                            
                            file_path = os.path.join(root, file_name)
                            
                            try:
                                # Ensure we have a scan record
                                if not self.current_scan_id:
                                    logger.error(f"🚨 CRITICAL: current_scan_id is None during file processing: {file_path}")
                                    continue
                                
                                # Get file stats
                                stat = os.stat(file_path)
                                file_size = stat.st_size
                                
                                # Extract file extension
                                file_extension = Path(file_path).suffix.lower() if Path(file_path).suffix else None
                                
                                # Create file record
                                file_record = FileRecord(
                                    path=file_path,
                                    name=file_name,
                                    size=file_size,
                                    extension=file_extension,
                                    parent_path=root,
                                    scan_id=self.current_scan_id
                                )
                                
                                # Extract media metadata if applicable
                                self._extract_media_metadata(file_record, Path(file_path))
                                
                                db.session.add(file_record)
                                total_files += 1
                                total_size += file_size
                                self._total_files = total_files
                                self._total_size = total_size
                                
                                # Commit every 1000 files to prevent memory buildup
                                if total_files % 1000 == 0:
                                    db.session.commit()
                                    logger.debug(f"Committed {total_files} files")
                                    
                            except Exception as e:
                                logger.error(f"Error processing file {file_path}: {e}")
                                db.session.rollback()
                                continue
                        
                        # Update progress in database periodically
                        current_time = time.time()
                        if current_time - last_update_time > 30:  # Update every 30 seconds
                            try:
                                # Ensure we have a scan record
                                if self.current_scan_id:
                                    from app import ScanRecord
                                    scan_record = db.session.query(ScanRecord).get(self.current_scan_id)
                                    if scan_record:
                                        scan_record.total_files = total_files
                                        scan_record.total_directories = total_directories
                                        scan_record.total_size = total_size
                                        db.session.commit()
                                    else:
                                        logger.error(f"🚨 CRITICAL: scan_record not found for ID {self.current_scan_id}")
                                else:
                                    logger.error(f"🚨 CRITICAL: current_scan_id is None during progress update")
                                
                                # CRITICAL: Update global scanner_state for dashboard display
                                self.update_scanner_state(total_files, total_directories, total_size, share_path)
                                
                                last_update_time = current_time
                                logger.debug(f"Updated scan progress: {total_files} files, {total_directories} dirs, {format_size(total_size)}")
                            except Exception as e:
                                logger.error(f"Error updating scan progress: {e}")
                                db.session.rollback()
                        
                        # Heartbeat logging
                        if current_time - last_heartbeat > heartbeat_interval:
                            logger.info(f"Heartbeat: Processing {root} - {total_files} files, {total_directories} dirs")
                            last_heartbeat = current_time
                        
                        # Database cleanup
                        if current_time - last_db_cleanup > db_cleanup_interval:
                            self.cleanup_database_connections()
                            last_db_cleanup = current_time
                        
                        # Check overall scan timeout
                        if current_time - scan_start_time > max_scan_time:
                            logger.warning(f"Scan timeout reached ({self.max_duration} hours) - stopping scan")
                            break
                
                except Exception as e:
                    logger.error(f"Error scanning share {share_name}: {e}")
                    continue
            
            # Final commit with Flask context protection
            try:
                # Ensure we have a scan record first
                if not self.current_scan_id:
                    logger.error(f"🚨 CRITICAL: current_scan_id is None during finalization!")
                    return
                
                # Ensure we're in Flask context for final operations
                try:
                    from flask import current_app
                    # Test if we have current app context
                    current_app.extensions['sqlalchemy']
                except RuntimeError:
                    # No app context, we need to create one
                    from app import app, ScanRecord, FolderInfo
                    with app.app_context():
                        scan_record = db.session.query(ScanRecord).get(self.current_scan_id)
                        if scan_record:
                            scan_record.total_files = total_files
                            scan_record.total_directories = total_directories
                            scan_record.total_size = total_size
                            scan_record.status = 'completed'
                            scan_record.end_time = datetime.utcnow()
                            db.session.commit()
                            
                            # Create FolderInfo records for top shares and file tree
                            logger.info("🔧 STARTING FOLDERINFO CREATION (with app context) for top shares and file tree...")
                            self._create_folder_info_records()
                            logger.info("✅ COMPLETED FOLDERINFO CREATION (with app context)")
                else:
                    # We have app context, proceed normally
                    from app import ScanRecord, FolderInfo
                    scan_record = db.session.query(ScanRecord).get(self.current_scan_id)
                    if scan_record:
                        scan_record.total_files = total_files
                        scan_record.total_directories = total_directories
                        scan_record.total_size = total_size
                        scan_record.status = 'completed'
                        scan_record.end_time = datetime.utcnow()
                        db.session.commit()
                        
                        # Create FolderInfo records for top shares and file tree
                        logger.info("🔧 STARTING FOLDERINFO CREATION for top shares and file tree...")
                        self._create_folder_info_records()
                        logger.info("✅ COMPLETED FOLDERINFO CREATION")
                    
                logger.info(f"Scan completed successfully: {total_files:,} files, {total_directories:,} directories, {format_size(total_size)}")
                
                # Post-scan processing - ensure we have Flask context
                try:
                    from flask import current_app
                    current_app.extensions['sqlalchemy']
                    # We have app context, proceed with post-processing
                    self._run_post_scan_processing(total_files, total_directories, total_size)
                except RuntimeError:
                    # No app context, create one for post-processing
                    from app import app
                    with app.app_context():
                        self._run_post_scan_processing(total_files, total_directories, total_size)
                
                # CRITICAL: Update global scanner_state on successful completion
                if scanner_state is not None:
                    scanner_state['scanning'] = False
                    scanner_state['current_path'] = 'Scan completed'
                    scanner_state['total_files'] = total_files
                    scanner_state['total_directories'] = total_directories
                    scanner_state['total_size'] = total_size
                    logger.info("Updated global scanner_state - scan completed successfully")
            except Exception as e:
                logger.error(f"Error finalizing scan: {e}")
                try:
                    db.session.rollback()
                except:
                    logger.error("Failed to rollback session")
                # Don't raise - we want to continue cleanup
            
        except Exception as e:
            logger.error(f"Scan failed: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Ensure the scan record is properly updated with error information
            if self.current_scan:
                try:
                    # Ensure we're in Flask context for database operations
                    try:
                        from flask import current_app
                        current_app.extensions['sqlalchemy']
                        # We have app context, proceed normally
                        from app import ScanRecord
                        scan_record = db.session.query(ScanRecord).get(self.current_scan_id)
                        if scan_record:
                            scan_record.status = 'failed'
                            scan_record.error_message = f"Scan failed: {str(e)}"
                            scan_record.end_time = datetime.utcnow()
                            db.session.commit()
                            logger.info(f"Updated scan {scan_record.id} status to failed")
                    except RuntimeError:
                        # No app context, create one
                        from app import app
                        with app.app_context():
                            from app import ScanRecord
                            scan_record = db.session.query(ScanRecord).get(self.current_scan_id)
                            if scan_record:
                                scan_record.status = 'failed'
                                scan_record.error_message = f"Scan failed: {str(e)}"
                                scan_record.end_time = datetime.utcnow()
                                db.session.commit()
                                logger.info(f"Updated scan {scan_record.id} status to failed")
                except Exception as db_error:
                    logger.error(f"Error updating failed scan record: {db_error}")
            
            raise
        finally:
            # Clean up scanner state
            self.scanning = False
            self.current_scan = None
            
            # CRITICAL: Update global scanner_state to show scan is no longer running
            if scanner_state is not None:
                scanner_state['scanning'] = False
                scanner_state['current_path'] = ''
                logger.info("Updated global scanner_state - scan finished")
            
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
    
    def _run_post_scan_processing(self, total_files, total_directories, total_size):
        """Run post-scan processing: folder calculations, duplicates, and storage history"""
        try:
            # Calculate comprehensive folder totals FIRST
            logger.info("Calculating folder totals...")
            try:
                from app import calculate_folder_totals_during_scan
                calculate_folder_totals_during_scan(str(self.data_path), self.current_scan_id)
                logger.info("Folder totals calculated successfully")
            except Exception as e:
                logger.error(f"Error calculating folder totals: {e}")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error details: {str(e)}")
                # Continue with the scan even if folder totals fail
                logger.warning("Continuing scan without folder totals...")
            
            # Detect duplicates
            logger.info("Starting duplicate detection...")
            try:
                from app import detect_duplicates
                detect_duplicates(self.current_scan_id)
                logger.info("Duplicate detection completed")
            except Exception as e:
                logger.error(f"Error detecting duplicates: {e}")
                logger.warning("Continuing scan without duplicate detection...")
            
            # Save storage history
            logger.info("Saving storage history...")
            try:
                from app import save_storage_history
                save_storage_history(self.current_scan_id)
                logger.info("Storage history saved")
            except Exception as e:
                logger.error(f"Error saving storage history: {e}")
                logger.warning("Continuing scan without storage history...")
                
        except Exception as e:
            logger.error(f"Error during post-scan processing: {e}")
            # Don't fail the entire scan for post-processing errors
            logger.warning("Post-scan processing failed, but scan data is preserved")
    
    def _create_folder_info_records(self):
        """Create FolderInfo records for directories to support top shares and file tree"""
        try:
            from app import FolderInfo
            from models import FileRecord
            from sqlalchemy import func
            
            logger.info("Starting FolderInfo creation process...")
            
            # Clear existing FolderInfo records for this scan
            db.session.query(FolderInfo).filter_by(scan_id=self.current_scan_id).delete()
            
            # Get all directories from this scan
            directories = db.session.query(FileRecord).filter_by(
                scan_id=self.current_scan_id,
                is_directory=True
            ).all()
            
            logger.info(f"Processing {len(directories)} directories for FolderInfo creation...")
            
            for directory in directories:
                try:
                    # Calculate directory depth  
                    depth = directory.path.count('/') - str(self.data_path).count('/')
                    
                    # Debug logging for depth calculation
                    if depth == 1:
                        logger.info(f"TOP-LEVEL DIRECTORY: {directory.path} (depth={depth})")
                    
                    # Get total size and file counts for this directory (including subdirectories)
                    result = db.session.query(
                        func.sum(FileRecord.size).label('total_size'),
                        func.count(FileRecord.id).label('total_count'),
                        func.sum(func.case([(FileRecord.is_directory == False, 1)], else_=0)).label('file_count'),
                        func.sum(func.case([(FileRecord.is_directory == True, 1)], else_=0)).label('directory_count')
                    ).filter(
                        FileRecord.path.like(f"{directory.path}/%"),
                        FileRecord.scan_id == self.current_scan_id
                    ).first()
                    
                    # Get direct children counts
                    direct_result = db.session.query(
                        func.count(func.case([(FileRecord.is_directory == False, 1)], else_=0)).label('direct_files'),
                        func.count(func.case([(FileRecord.is_directory == True, 1)], else_=0)).label('direct_dirs')
                    ).filter(
                        FileRecord.parent_path == directory.path,
                        FileRecord.scan_id == self.current_scan_id
                    ).first()
                    
                    # Create FolderInfo record
                    folder_info = FolderInfo(
                        path=directory.path,
                        name=directory.name,
                        parent_path=directory.parent_path,
                        total_size=result.total_size or 0,
                        file_count=result.file_count or 0,
                        directory_count=result.directory_count or 0,
                        direct_file_count=direct_result.direct_files or 0,
                        direct_directory_count=direct_result.direct_dirs or 0,
                        depth=depth,
                        scan_id=self.current_scan_id,
                        updated_at=datetime.utcnow()
                    )
                    
                    db.session.add(folder_info)
                    
                except Exception as e:
                    logger.error(f"Error creating FolderInfo for {directory.path}: {e}")
                    continue
            
            # Commit all FolderInfo records
            db.session.commit()
            logger.info(f"Successfully created FolderInfo records for {len(directories)} directories")
            
        except Exception as e:
            logger.error(f"Error in _create_folder_info_records: {e}")
            db.session.rollback() 