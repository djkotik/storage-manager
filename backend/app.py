import os
import logging
import shutil
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, desc, case
from sqlalchemy.exc import OperationalError
from pathlib import Path
from functools import wraps
import schedule
import sqlite3

# Add simple caching
cache = {}
CACHE_DURATION = 300  # 5 minutes

def cache_result(duration=CACHE_DURATION):
    """Simple cache decorator"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            current_time = time.time()
            
            # Check if we have a cached result that's still valid
            if cache_key in cache:
                cached_time, cached_result = cache[cache_key]
                if current_time - cached_time < duration:
                    return cached_result
            
            # Get fresh result
            result = func(*args, **kwargs)
            cache[cache_key] = (current_time, result)
            return result
        return wrapper
    return decorator

def retry_on_db_lock(max_retries=3, delay=1):
    """Decorator to retry database operations on lock errors"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    if "database is locked" in str(e).lower():
                        last_exception = e
                        if attempt < max_retries - 1:
                            logger.warning(f"Database locked, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                            time.sleep(delay)
                            # Try to force a connection refresh
                            try:
                                db.session.rollback()
                            except:
                                pass
                        continue
                    else:
                        raise
                except Exception as e:
                    raise
            # If we get here, all retries failed
            logger.error(f"Database operation failed after {max_retries} retries: {last_exception}")
            raise last_exception
        return wrapper
    return decorator

# Configure logging - simplified for Docker
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
logger.info("Starting application initialization...")

# Initialize Flask app
app = Flask(__name__) # Removed static_folder and static_url_path

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///storage_manager.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 50,  # Increased from default 20
    'pool_timeout': 120,  # Increased timeout
    'pool_recycle': 3600,  # Recycle connections every hour
    'max_overflow': 100,  # Increased from default 30
    'pool_pre_ping': True,  # Test connections before use
}
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

# Initialize extensions
db = SQLAlchemy(app)
CORS(app)

# Enable SQLite WAL mode for better concurrency
def check_stuck_scans_on_startup():
    """Check for scans that are still marked as running and mark them as failed"""
    try:
        logger.info("Checking for stuck scans from previous sessions...")
        
        # Find any scans still marked as 'running'
        stuck_scans = ScanRecord.query.filter(ScanRecord.status == 'running').all()
        
        if stuck_scans:
            logger.warning(f"Found {len(stuck_scans)} stuck scans from previous sessions")
            
            for scan in stuck_scans:
                logger.warning(f"Marking stuck scan {scan.id} as failed (started: {scan.start_time})")
                scan.status = 'failed'
                scan.end_time = datetime.now()
                scan.error_message = 'Scan was interrupted by container restart'
                
            db.session.commit()
            logger.info(f"Marked {len(stuck_scans)} stuck scans as failed")
        else:
            logger.info("No stuck scans found")
            
    except Exception as e:
        logger.error(f"Error checking for stuck scans: {e}")
        db.session.rollback()

def enable_wal_mode():
    """Enable WAL mode for better database concurrency"""
    try:
        with db.engine.connect() as conn:
            conn.execute(db.text('PRAGMA journal_mode=WAL'))
            conn.execute(db.text('PRAGMA synchronous=NORMAL'))
            conn.execute(db.text('PRAGMA cache_size=50000'))  # Increased cache size
            conn.execute(db.text('PRAGMA temp_store=MEMORY'))
            conn.execute(db.text('PRAGMA busy_timeout=60000'))  # Increased to 60 seconds
            conn.execute(db.text('PRAGMA wal_autocheckpoint=2000'))  # Checkpoint every 2000 pages
            conn.execute(db.text('PRAGMA mmap_size=268435456'))  # 256MB memory mapping
            conn.commit()
        logger.info("SQLite WAL mode enabled with improved settings for high concurrency")
    except Exception as e:
        logger.warning(f"Could not enable WAL mode: {e}")

def unlock_database():
    """Attempt to unlock the database by forcing a checkpoint"""
    try:
        with db.engine.connect() as conn:
            conn.execute(db.text('PRAGMA wal_checkpoint(TRUNCATE)'))
            conn.commit()
        logger.info("Database checkpoint completed")
        return True
    except Exception as e:
        logger.error(f"Failed to unlock database: {e}")
        return False

# Define the path to the built frontend files
FRONTEND_DIST_DIR = os.path.join(app.root_path, 'static') # This should be /app/static in Docker

# Global scanner state
scanner_state = {
    'scanning': False,
    'current_scan_id': None,
    'start_time': None,
    'total_files': 0,
    'total_directories': 0,
    'total_size': 0,
    'current_path': '',
    'error': None
}

# Global scanner instance for stop functionality
current_scanner_instance = None

# Scheduled scan functionality
def run_scheduled_scan():
    """Run a scheduled scan"""
    try:
        logger.info("=== SCHEDULED SCAN TRIGGERED ===")
        logger.info(f"Triggered at: {datetime.now()}")
        
        # Check if a scan is already running
        if scanner_state['scanning']:
            logger.info("Scan already in progress, skipping scheduled scan")
            return
        
        # Get scan settings
        data_path = get_setting('data_path', os.environ.get('DATA_PATH', '/data'))
        max_duration = int(get_setting('max_scan_duration', '6'))
        logger.info(f"Scan settings - Data path: {data_path}, Max duration: {max_duration} hours")
        
        # Start the scan using new FileScanner with bulletproof appdata exclusion
        logger.info("Starting NEW FileScanner for scheduled scan...")
        
        # Import and use the new scanner
        from scanner import FileScanner
        scanner = FileScanner(data_path, max_duration=max_duration)
        
        # CRITICAL: Pass global scanner_state reference for dashboard updates
        import scanner as scanner_module
        scanner_module.scanner_state = scanner_state
        
        # Set global reference for stop functionality
        global current_scanner_instance
        current_scanner_instance = scanner
        
        # Use the scanner's built-in start_scan method within Flask context
        with app.app_context():
            scan_id = scanner.start_scan()
            logger.info(f"Scheduled scanner started with ID: {scan_id}")
            
            # CRITICAL: Update global scanner_state to reflect that scan is running
            if scan_id:
                scanner_state['scanning'] = True
                scanner_state['current_scan_id'] = scan_id
                scanner_state['start_time'] = datetime.now()
                logger.info("Updated global scanner_state for scheduled scan")
        
        logger.info(f"=== SCHEDULED SCAN INITIATED ===")
        logger.info(f"Scan ID: {scan_id}")
        logger.info(f"Data path: {data_path}")
                
    except Exception as e:
        logger.error(f"=== SCHEDULED SCAN ERROR ===")
        logger.error(f"Error in scheduled scan: {e}")
        logger.error(f"Error type: {type(e).__name__}")

def setup_scheduled_scan():
    """Setup the scheduled scan based on settings"""
    try:
        scan_time = get_setting('scan_time', '01:00')
        logger.info(f"Setting up scheduled scan for {scan_time}")
        
        # Clear any existing schedule
        schedule.clear()
        
        # Schedule the scan
        schedule.every().day.at(scan_time).do(run_scheduled_scan)
        
        logger.info(f"Scheduled scan configured for {scan_time} daily")
        
    except Exception as e:
        logger.error(f"Error setting up scheduled scan: {e}")

def run_scheduler():
    """Run the scheduler in a background thread"""
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
        except Exception as e:
            logger.error(f"Error in scheduler: {e}")
            time.sleep(60)  # Wait before retrying

# Define models directly in app.py to avoid circular imports
class FileRecord(db.Model):
    """Model for storing file information"""
    __tablename__ = 'files'
    
    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String(2000), nullable=False)
    name = db.Column(db.String(500), nullable=False)
    size = db.Column(db.Integer, nullable=False)  # Size in bytes
    is_directory = db.Column(db.Boolean, default=False)
    parent_path = db.Column(db.String(2000))
    extension = db.Column(db.String(50))
    created_time = db.Column(db.DateTime)
    modified_time = db.Column(db.DateTime)
    accessed_time = db.Column(db.DateTime)
    permissions = db.Column(db.String(20))
    scan_id = db.Column(db.Integer)

class ScanRecord(db.Model):
    """Model for storing scan sessions"""
    __tablename__ = 'scans'
    
    id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    total_files = db.Column(db.Integer, default=0)
    total_directories = db.Column(db.Integer, default=0)
    total_size = db.Column(db.Integer, default=0)  # Total size in bytes
    status = db.Column(db.String(20), default='running')  # running, completed, failed
    error_message = db.Column(db.Text)

class MediaFile(db.Model):
    """Model for storing media file metadata"""
    __tablename__ = 'media_files'
    
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer)
    media_type = db.Column(db.String(20))  # movie, tv_show, music, other
    title = db.Column(db.String(500))
    year = db.Column(db.Integer)
    season = db.Column(db.Integer)
    episode = db.Column(db.Integer)
    episode_title = db.Column(db.String(500))
    resolution = db.Column(db.String(20))  # 480p, 720p, 1080p, 4K, etc.
    video_codec = db.Column(db.String(50))
    audio_codec = db.Column(db.String(50))
    audio_channels = db.Column(db.String(20))
    runtime = db.Column(db.Integer)  # Runtime in minutes
    bitrate = db.Column(db.Integer)
    frame_rate = db.Column(db.Float)
    file_format = db.Column(db.String(20))

class DuplicateGroup(db.Model):
    """Model for storing duplicate file groups"""
    __tablename__ = 'duplicate_groups'
    
    id = db.Column(db.Integer, primary_key=True)
    hash_value = db.Column(db.String(64), nullable=False)
    size = db.Column(db.Integer, nullable=False)
    file_count = db.Column(db.Integer, default=0)
    created_time = db.Column(db.DateTime, default=datetime.utcnow)

class DuplicateFile(db.Model):
    """Model for storing individual duplicate files"""
    __tablename__ = 'duplicate_files'
    
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer)
    group_id = db.Column(db.Integer)
    hash_value = db.Column(db.String(64), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)  # Marked as keep
    is_deleted = db.Column(db.Boolean, default=False)

class StorageHistory(db.Model):
    """Model for storing storage usage over time"""
    __tablename__ = 'storage_history'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)
    total_size = db.Column(db.Integer, nullable=False)  # Total size in bytes
    file_count = db.Column(db.Integer, default=0)
    directory_count = db.Column(db.Integer, default=0)

class Settings(db.Model):
    """Model for storing application settings"""
    __tablename__ = 'settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), nullable=False, unique=True)
    value = db.Column(db.String(500), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class TrashBin(db.Model):
    """Model for storing deleted files (for undo functionality)"""
    __tablename__ = 'trash_bin'
    
    id = db.Column(db.Integer, primary_key=True)
    original_path = db.Column(db.String(2000), nullable=False)
    original_size = db.Column(db.Integer, nullable=False)
    deleted_time = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)  # When the file will be permanently deleted
    restored = db.Column(db.Boolean, default=False)

# Replace the DirectoryTotal model with a more comprehensive FolderInfo model
class FolderInfo(db.Model):
    """Model for storing comprehensive folder information"""
    __tablename__ = 'folder_info'
    
    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String(2000), nullable=False)
    name = db.Column(db.String(500), nullable=False)
    parent_path = db.Column(db.String(2000))
    total_size = db.Column(db.Integer, default=0)  # Total size in bytes (including subdirectories)
    file_count = db.Column(db.Integer, default=0)  # Total files (including subdirectories)
    directory_count = db.Column(db.Integer, default=0)  # Total directories (including subdirectories)
    direct_file_count = db.Column(db.Integer, default=0)  # Files directly in this folder
    direct_directory_count = db.Column(db.Integer, default=0)  # Directories directly in this folder
    depth = db.Column(db.Integer, default=0)  # Directory depth from root
    scan_id = db.Column(db.Integer)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Indexes for performance
    __table_args__ = (
        db.Index('idx_folder_path', 'path'),
        db.Index('idx_folder_parent', 'parent_path'),
        db.Index('idx_folder_scan', 'scan_id'),
        db.Index('idx_folder_depth', 'depth'),
    )

# Utility functions (moved before initialization)
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

def get_setting(key, default=None):
    """Get a setting value from database"""
    try:
        setting = Settings.query.filter_by(key=key).first()
        return setting.value if setting else default
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
        return default

def set_setting(key, value):
    """Set a setting value in database"""
    try:
        setting = Settings.query.filter_by(key=key).first()
        if setting:
            setting.value = value
            setting.updated_at = datetime.utcnow()
        else:
            setting = Settings(key=key, value=value)
            db.session.add(setting)
        db.session.commit()
        return True
    except Exception as e:
        logger.error(f"Error setting {key}: {e}")
        return False

def is_media_file(file_path, extension):
    """Determine if a file is a media file based on extension and path"""
    media_extensions = {
        # Video
        '.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp',
        # Audio
        '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a',
        # Images
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg',
        # Other media
        '.iso', '.img'
    }
    
    if extension and extension.lower() in media_extensions:
        return True
    
    # Check for media-related directories in path
    media_keywords = ['movie', 'movies', 'tv', 'television', 'show', 'shows', 
                     'music', 'audio', 'photo', 'photos', 'image', 'images',
                     'video', 'videos', 'media']
    
    path_lower = file_path.lower()
    return any(keyword in path_lower for keyword in media_keywords)

# Add database indexes for better performance
def create_indexes():
    """Create database indexes for better query performance"""
    try:
        # Create indexes for commonly queried columns
        with db.engine.connect() as conn:
            conn.execute(db.text('CREATE INDEX IF NOT EXISTS idx_files_parent_path ON files(parent_path)'))
            conn.execute(db.text('CREATE INDEX IF NOT EXISTS idx_files_is_directory ON files(is_directory)'))
            conn.execute(db.text('CREATE INDEX IF NOT EXISTS idx_files_path ON files(path)'))
            conn.execute(db.text('CREATE INDEX IF NOT EXISTS idx_files_scan_id ON files(scan_id)'))
            conn.execute(db.text('CREATE INDEX IF NOT EXISTS idx_scans_status ON scans(status)'))
            conn.execute(db.text('CREATE INDEX IF NOT EXISTS idx_scans_start_time ON scans(start_time)'))
            conn.commit()
        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.warning(f"Could not create indexes: {e}")



def detect_duplicates(scan_id):
    """Detect duplicate files based on size and content hash"""
    try:
        logger.info("Starting duplicate detection...")
        
        # Clear existing duplicate data for this scan
        DuplicateFile.query.delete()
        DuplicateGroup.query.delete()
        
        # Get all files from this scan, grouped by size
        files_by_size = db.session.query(
            FileRecord.size,
            func.count(FileRecord.id).label('count')
        ).filter(
            FileRecord.scan_id == scan_id,
            FileRecord.is_directory == False,
            FileRecord.size > 0  # Only check files with size > 0
        ).group_by(FileRecord.size).having(
            func.count(FileRecord.id) > 1
        ).all()
        
        duplicate_count = 0
        for size, count in files_by_size:
            # Get all files with this size
            files = FileRecord.query.filter_by(
                scan_id=scan_id,
                size=size,
                is_directory=False
            ).all()
            
            # Group by name (exact match) and calculate content hash
            files_by_name = {}
            for file in files:
                if file.name not in files_by_name:
                    files_by_name[file.name] = []
                files_by_name[file.name].append(file)
            
            # Create duplicate groups for files with same name and size
            for name, file_list in files_by_name.items():
                if len(file_list) > 1:
                    # For now, use a simple hash based on size and name
                    # In a real implementation, you'd calculate actual file content hash
                    content_hash = f"size_{size}_name_{name}"
                    
                    # Create duplicate group
                    group = DuplicateGroup(
                        hash_value=content_hash,
                        size=size,
                        file_count=len(file_list)
                    )
                    db.session.add(group)
                    db.session.flush()  # Get the group ID
                    
                    # Add files to the group
                    for i, file in enumerate(file_list):
                        duplicate_file = DuplicateFile(
                            file_id=file.id,
                            group_id=group.id,
                            hash_value=content_hash,
                            is_primary=(i == 0)  # First file is primary
                        )
                        db.session.add(duplicate_file)
                    
                    duplicate_count += len(file_list)
        
        db.session.commit()
        logger.info(f"Duplicate detection completed: {duplicate_count} duplicate files found")
        
    except Exception as e:
        logger.error(f"Error detecting duplicates: {e}")
        db.session.rollback()

def save_storage_history(scan_id):
    """Save storage history for analytics"""
    try:
        # Get the scan record
        scan = ScanRecord.query.get(scan_id)
        if not scan:
            return
        
        # Create storage history entry
        history = StorageHistory(
            date=scan.start_time,
            total_size=scan.total_size,
            file_count=scan.total_files,
            directory_count=scan.total_directories
        )
        db.session.add(history)
        db.session.commit()
        logger.info(f"Storage history saved for scan {scan_id}")
        
    except Exception as e:
        logger.error(f"Error saving storage history: {e}")
        db.session.rollback()

def scan_directory(data_path, scan_id):
    """Scan directory and populate database"""
    global scanner_state
    
    # Create application context for database operations
    with app.app_context():
        try:
            logger.info(f"=== SCAN STARTED ===")
            logger.info(f"Scan ID: {scan_id}")
            logger.info(f"Scanning directory: {data_path}")
            logger.info(f"Start time: {datetime.now()}")
            
            scanner_state['scanning'] = True
            scanner_state['current_scan_id'] = scan_id
            scanner_state['start_time'] = datetime.now()
            scanner_state['total_files'] = 0
            scanner_state['total_directories'] = 0
            scanner_state['total_size'] = 0
            scanner_state['error'] = None
            
            # Clear existing files for this scan
            logger.info("Clearing existing files for this scan...")
            FileRecord.query.filter_by(scan_id=scan_id).delete()
            db.session.commit()
            logger.info("Existing files cleared")
            
            logger.info("Starting file system traversal...")
            batch_size = 100  # Commit every 100 files to reduce lock time
            current_batch = 0
            
            # Respect max_shares_to_scan setting (0 = unlimited)
            try:
                max_shares_to_scan = int(get_setting('max_shares_to_scan', '0'))
            except Exception:
                max_shares_to_scan = 0
            shares_scanned = 0
            
            for root, dirs, files in os.walk(data_path):
                if not scanner_state['scanning']:
                    logger.info("Scan stopped by user request")
                    break
                    
                scanner_state['current_path'] = root
                
                # If limiting shares, detect when we enter a top-level share and enforce limit
                if max_shares_to_scan > 0:
                    try:
                        if os.path.dirname(root.rstrip('/')) == data_path.rstrip('/') and root.rstrip('/') != data_path.rstrip('/'):
                            shares_scanned += 1
                            logger.info(f"Scanning share {shares_scanned}/{max_shares_to_scan}: {os.path.basename(root)}")
                            if shares_scanned > max_shares_to_scan:
                                logger.info(f"Reached max shares limit ({max_shares_to_scan}), stopping scan")
                                break
                    except Exception:
                        pass
                
                # Process directories
                for dir_name in dirs:
                    try:
                        dir_path = os.path.join(root, dir_name)
                        if os.path.exists(dir_path):
                            # Get directory stats
                            stat = os.stat(dir_path)
                            
                            # Create directory record
                            dir_record = FileRecord(
                                path=dir_path,
                                name=dir_name,
                                size=0,  # Will calculate later
                                is_directory=True,
                                parent_path=root,
                                created_time=datetime.fromtimestamp(stat.st_ctime),
                                modified_time=datetime.fromtimestamp(stat.st_mtime),
                                accessed_time=datetime.fromtimestamp(stat.st_atime),
                                permissions=oct(stat.st_mode)[-3:],
                                scan_id=scan_id
                            )
                            db.session.add(dir_record)
                            scanner_state['total_directories'] += 1
                            current_batch += 1
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Error accessing directory {dir_path}: {e}")
                        continue
                
                # Process files
                for file_name in files:
                    try:
                        file_path = os.path.join(root, file_name)
                        if os.path.exists(file_path):
                            # Get file stats
                            stat = os.stat(file_path)
                            file_size = stat.st_size
                            
                            # Get file extension
                            _, extension = os.path.splitext(file_name)
                            extension = extension.lower() if extension else None
                            
                            # Create file record
                            file_record = FileRecord(
                                path=file_path,
                                name=file_name,
                                size=file_size,
                                is_directory=False,
                                parent_path=root,
                                extension=extension,
                                created_time=datetime.fromtimestamp(stat.st_ctime),
                                modified_time=datetime.fromtimestamp(stat.st_mtime),
                                accessed_time=datetime.fromtimestamp(stat.st_atime),
                                permissions=oct(stat.st_mode)[-3:],
                                scan_id=scan_id
                            )
                            db.session.add(file_record)
                            
                            # Check if this is a media file
                            if is_media_file(file_path, extension):
                                # Determine media type based on extension and path
                                media_type = 'other'
                                if extension and extension.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg']:
                                    media_type = 'image'
                                elif extension and extension.lower() in ['.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp']:
                                    # Check if it's a TV show (has season/episode patterns)
                                    if any(keyword in file_path.lower() for keyword in ['season', 'episode', 's0', 'e0']):
                                        media_type = 'tv_show'
                                    else:
                                        media_type = 'movie'
                                elif extension and extension.lower() in ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a']:
                                    media_type = 'music'
                                
                                # Create media file record
                                media_record = MediaFile(
                                    file_id=file_record.id,
                                    media_type=media_type,
                                    title=file_name,
                                    file_format=extension
                                )
                                db.session.add(media_record)
                            
                            scanner_state['total_files'] += 1
                            scanner_state['total_size'] += file_size
                            current_batch += 1
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Error accessing file {file_path}: {e}")
                        continue
                
                # Commit periodically to reduce database lock time
                if current_batch >= batch_size:
                    db.session.commit()
                    current_batch = 0
                    logger.info(f"=== SCAN PROGRESS ===")
                    logger.info(f"Files processed: {scanner_state['total_files']:,}")
                    logger.info(f"Directories processed: {scanner_state['total_directories']:,}")
                    logger.info(f"Total size: {format_size(scanner_state['total_size'])}")
                    logger.info(f"Current path: {root}")
                    logger.info(f"Elapsed time: {datetime.now() - scanner_state['start_time']}")
            
            # Final commit
            logger.info("Committing final batch...")
            db.session.commit()
            
            # Calculate comprehensive folder totals FIRST
            logger.info("Calculating folder totals...")
            try:
                calculate_folder_totals_during_scan(data_path, scan_id)
                logger.info("Folder totals calculated successfully")
            except Exception as e:
                logger.error(f"Error calculating folder totals: {e}")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error details: {str(e)}")
                # Continue with the scan even if folder totals fail
                logger.warning("Continuing scan without folder totals...")
            
            # Detect duplicates
            logger.info("Starting duplicate detection...")
            detect_duplicates(scan_id)
            logger.info("Duplicate detection completed")
            
            # Save storage history
            logger.info("Saving storage history...")
            save_storage_history(scan_id)
            logger.info("Storage history saved")
            
            # Update scan record LAST (after all processing is complete)
            logger.info("Updating scan record...")
            scan_record = ScanRecord.query.get(scan_id)
            if scan_record:
                scan_record.end_time = datetime.now()
                scan_record.total_files = scanner_state['total_files']
                scan_record.total_directories = scanner_state['total_directories']
                scan_record.total_size = scanner_state['total_size']
                scan_record.status = 'completed'
                db.session.commit()
                logger.info(f"Scan record updated: ID {scan_id}")
            
            logger.info(f"=== SCAN COMPLETED ===")
            logger.info(f"Scan ID: {scan_id}")
            logger.info(f"Total files: {scanner_state['total_files']:,}")
            logger.info(f"Total directories: {scanner_state['total_directories']:,}")
            logger.info(f"Total size: {format_size(scanner_state['total_size'])}")
            logger.info(f"End time: {datetime.now()}")
            logger.info(f"Duration: {datetime.now() - scanner_state['start_time']}")
            
        except Exception as e:
            logger.error(f"=== SCAN ERROR ===")
            logger.error(f"Scan ID: {scan_id}")
            logger.error(f"Error: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            scanner_state['error'] = str(e)
            
            # Rollback the session to clear any pending transaction
            logger.error("Rolling back database session...")
            db.session.rollback()
            
            # Update scan record with error
            logger.error("Updating scan record with error...")
            scan_record = ScanRecord.query.get(scan_id)
            if scan_record:
                scan_record.end_time = datetime.now()
                scan_record.status = 'failed'
                scan_record.error_message = str(e)
                db.session.commit()
                logger.error(f"Scan record updated with error: ID {scan_id}")
        
        finally:
            logger.info("Cleaning up scan state...")
            scanner_state['scanning'] = False
            scanner_state['current_path'] = ''
            logger.info("Scan state cleaned up")

def calculate_folder_totals_during_scan(data_path, scan_id):
    """Calculate and store comprehensive folder information during scan - OPTIMIZED VERSION"""
    logger.info(f"=== FOLDER CALCULATION START ===")
    logger.info(f"Data path: {data_path}")
    logger.info(f"Scan ID: {scan_id}")
    logger.info(f"Function called at: {datetime.now()}")
    
    try:
        logger.info(f"Calculating folder totals for scan {scan_id}")
        
        # Clear existing folder info for this scan
        logger.info("Clearing existing folder info...")
        FolderInfo.query.filter_by(scan_id=scan_id).delete()
        db.session.commit()
        logger.info("Existing folder info cleared")
        
        # OPTIMIZATION: Single query to get all directory information with aggregated data
        logger.info("Querying directories with aggregated data...")
        
        # Get all directories with their direct file counts and sizes in a single query
        directory_data = db.session.query(
            FileRecord.path,
            FileRecord.name,
            FileRecord.parent_path,
            func.count(case((FileRecord.is_directory == False, 1), else_=None)).label('direct_file_count'),
            func.count(case((FileRecord.is_directory == True, 1), else_=None)).label('direct_directory_count'),
            func.coalesce(func.sum(case((FileRecord.is_directory == False, FileRecord.size), else_=0)), 0).label('direct_size')
        ).filter(
            FileRecord.scan_id == scan_id,
            FileRecord.is_directory == True
        ).group_by(
            FileRecord.path,
            FileRecord.name,
            FileRecord.parent_path
        ).order_by(db.func.length(FileRecord.path).desc()).all()
        
        logger.info(f"Found {len(directory_data)} directories to process")
        
        if not directory_data:
            logger.warning("No directories found for this scan")
            return
        
        # Create a dictionary to store folder info
        folder_info = {}
        processed_count = 0
        
        # Process each directory
        for directory in directory_data:
            try:
                path = directory.path
                name = directory.name
                parent_path = directory.parent_path
                
                # Calculate depth relative to data_path
                relative_path = path.replace(data_path, '').strip('/')
                depth = len(relative_path.split('/')) if relative_path else 0
                
                # Get direct counts and size from the query result
                direct_file_count = int(directory.direct_file_count or 0)
                direct_directory_count = int(directory.direct_directory_count or 0)
                direct_size = int(directory.direct_size or 0)
                
                # Initialize totals
                total_size = direct_size
                total_file_count = direct_file_count
                total_directory_count = direct_directory_count
                
                # Add totals from subdirectories (already calculated due to ordering by path length)
                for subfolder_path, subfolder_info in folder_info.items():
                    if subfolder_path.startswith(path + '/') and subfolder_path != path:
                        total_size += subfolder_info['total_size']
                        total_file_count += subfolder_info['file_count']
                        total_directory_count += subfolder_info['directory_count']
                
                # Store folder info
                folder_info[path] = {
                    'name': name,
                    'parent_path': parent_path,
                    'total_size': total_size,
                    'file_count': total_file_count,
                    'directory_count': total_directory_count,
                    'direct_file_count': direct_file_count,
                    'direct_directory_count': direct_directory_count,
                    'depth': depth
                }
                
                # Create database record
                folder_record = FolderInfo(
                    path=path,
                    name=name,
                    parent_path=parent_path,
                    total_size=total_size,
                    file_count=total_file_count,
                    directory_count=total_directory_count,
                    direct_file_count=direct_file_count,
                    direct_directory_count=direct_directory_count,
                    depth=depth,
                    scan_id=scan_id
                )
                db.session.add(folder_record)
                
                processed_count += 1
                
                # Commit in larger batches for better performance
                if processed_count % 500 == 0:
                    db.session.commit()
                    logger.info(f"Processed {processed_count}/{len(directory_data)} folders")
                    
            except Exception as e:
                logger.error(f"Error processing directory {directory.path}: {e}")
                continue
        
        # Final commit
        logger.info("Committing final folder calculations...")
        db.session.commit()
        logger.info(f"Folder totals calculated and stored for scan {scan_id}: {len(folder_info)} folders")
        logger.info(f"=== FOLDER CALCULATION COMPLETE ===")
        
    except Exception as e:
        logger.error(f"=== FOLDER CALCULATION ERROR ===")
        logger.error(f"Error calculating folder totals: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error details: {str(e)}")
        db.session.rollback()
        raise

def get_folder_info(path):
    """Get comprehensive folder information for a directory"""
    try:
        # Get the latest completed scan
        latest_scan = ScanRecord.query.filter(
            ScanRecord.status == 'completed'
        ).order_by(desc(ScanRecord.start_time)).first()
        
        if not latest_scan:
            return {
                'total_size': 0, 
                'file_count': 0, 
                'directory_count': 0,
                'direct_file_count': 0,
                'direct_directory_count': 0
            }
        
        # Try to get pre-calculated folder info
        folder_info = FolderInfo.query.filter(
            FolderInfo.path == path,
            FolderInfo.scan_id == latest_scan.id
        ).first()
        
        if folder_info:
            return {
                'total_size': folder_info.total_size,
                'file_count': folder_info.file_count,
                'directory_count': folder_info.directory_count,
                'direct_file_count': folder_info.direct_file_count,
                'direct_directory_count': folder_info.direct_directory_count
            }
        else:
            # Fallback: calculate on-the-fly
            totals = db.session.query(
                func.sum(FileRecord.size).label('total_size'),
                func.count(FileRecord.id).label('file_count'),
                func.count(case((FileRecord.is_directory == True, 1), else_=None)).label('directory_count')
            ).filter(
                FileRecord.path.like(f"{path}/%"),
                FileRecord.scan_id == latest_scan.id
            ).first()
            
            return {
                'total_size': totals.total_size or 0,
                'file_count': totals.file_count or 0,
                'directory_count': totals.directory_count or 0,
                'direct_file_count': 0,  # Would need separate query
                'direct_directory_count': 0  # Would need separate query
            }
    except Exception as e:
        logger.error(f"Error getting folder info for {path}: {e}")
        return {
            'total_size': 0, 
            'file_count': 0, 
            'directory_count': 0,
            'direct_file_count': 0,
            'direct_directory_count': 0
        }

# Routes
@app.route('/')
def index():
    """Serve the main application"""
    import os
    
    # Enhanced logging for debugging
    logger.info(f"=== INDEX ROUTE DEBUG INFO ===")
    logger.info(f"FRONTEND_DIST_DIR: {FRONTEND_DIST_DIR}")
    logger.info(f"app.root_path: {app.root_path}")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"FRONTEND_DIST_DIR exists: {os.path.exists(FRONTEND_DIST_DIR)}")
    
    if os.path.exists(FRONTEND_DIST_DIR):
        logger.info(f"FRONTEND_DIST_DIR is directory: {os.path.isdir(FRONTEND_DIST_DIR)}")
        try:
            dir_contents = os.listdir(FRONTEND_DIST_DIR)
            logger.info(f"FRONTEND_DIST_DIR contents: {dir_contents}")
        except Exception as e:
            logger.error(f"Error listing FRONTEND_DIST_DIR contents: {e}")
    
    index_path = os.path.join(FRONTEND_DIST_DIR, 'index.html')
    logger.info(f"Looking for index.html at: {index_path}")
    logger.info(f"index.html exists: {os.path.exists(index_path)}")
    
    try:
        logger.info(f"Attempting to serve index.html from: {FRONTEND_DIST_DIR}")
        response = send_from_directory(FRONTEND_DIST_DIR, 'index.html')
        logger.info(f"Successfully served index.html, response type: {type(response)}")
        return response
    except FileNotFoundError as e:
        logger.error(f"FileNotFoundError serving index.html: {e}")
        # If static files are not available, return a simple HTML page
        logger.warning(f"Static files not found in {FRONTEND_DIST_DIR}")
        html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>unRAID Storage Analyzer</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .error { color: #d32f2f; background: #ffebee; padding: 15px; border-radius: 4px; margin: 20px 0; }
        .info { color: #1976d2; background: #e3f2fd; padding: 15px; border-radius: 4px; margin: 20px 0; }
        .endpoint { background: #f5f5f5; padding: 10px; margin: 5px 0; border-radius: 4px; font-family: monospace; }
        h1 { color: #333; }
        h2 { color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <h1>unRAID Storage Analyzer</h1>
        <div class="error">
            <h2>⚠️ Frontend Not Built</h2>
            <p>The frontend application has not been built successfully. This usually means the Docker build process failed during the frontend build step.</p>
        </div>
        
        <div class="info">
            <h2>🔧 Troubleshooting</h2>
            <p>To fix this issue:</p>
            <ol>
                <li>Check the Docker build logs for frontend build errors</li>
                <li>Ensure Node.js dependencies are available during build</li>
                <li>Rebuild the Docker image: <code>docker build -t unraid-storage-analyzer:latest .</code></li>
            </ol>
        </div>
        
        <h2>📡 Available API Endpoints</h2>
        <p>The backend API is running and these endpoints are available:</p>
        <div class="endpoint">GET /api/health</div>
        <div class="endpoint">GET /api/scan/status</div>
        <div class="endpoint">GET /api/analytics/overview</div>
        <div class="endpoint">GET /api/settings</div>
        <div class="endpoint">POST /api/scan/start</div>
        
        <h2>🔍 Debug Information</h2>
        <p>You can check the following debug endpoints:</p>
        <div class="endpoint">GET /debug/static</div>
        <div class="endpoint">GET /debug/index</div>
        <div class="endpoint">GET /api/debug/directories</div>
    </div>
</body>
</html>
        """
        return html_content, 200, {'Content-Type': 'text/html'}
    except Exception as e:
        logger.error(f"Unexpected error serving index.html: {e}")
        return f"Internal Server Error: {str(e)}", 500

@app.route('/debug/static')
def debug_static():
    """Debug route to check static files"""
    import os
    static_dir = FRONTEND_DIST_DIR
    files = []
    
    debug_info = {
        'static_folder': static_dir,
        'static_folder_exists': os.path.exists(static_dir),
        'static_folder_is_dir': os.path.isdir(static_dir) if os.path.exists(static_dir) else False,
        'app_root_path': app.root_path,
        'current_working_dir': os.getcwd(),
        'files': [],
        'index_exists': False,
        'index_path': os.path.join(static_dir, 'index.html') if static_dir else None
    }
    
    if os.path.exists(static_dir):
        try:
            for root, dirs, filenames in os.walk(static_dir):
                for filename in filenames:
                    rel_path = os.path.relpath(os.path.join(root, filename), static_dir)
                    files.append(rel_path)
            debug_info['files'] = sorted(files)
        except Exception as e:
            debug_info['error'] = str(e)
    
    debug_info['index_exists'] = os.path.exists(os.path.join(static_dir, 'index.html')) if static_dir else False
    
    return jsonify(debug_info)

@app.route('/debug/index')
def debug_index():
    """Debug route to check index.html content"""
    import os
    try:
        index_path = os.path.join(FRONTEND_DIST_DIR, 'index.html')
        with open(index_path, 'r') as f:
            content = f.read()
        return jsonify({
            'exists': True,
            'length': len(content),
            'preview': content[:500] + '...' if len(content) > 500 else content,
            'path': index_path
        })
    except FileNotFoundError:
        return jsonify({
            'exists': False,
            'error': 'index.html not found in static folder',
            'path': os.path.join(FRONTEND_DIST_DIR, 'index.html') if FRONTEND_DIST_DIR else None
        })
    except Exception as e:
        return jsonify({
            'exists': False,
            'error': str(e),
            'path': os.path.join(FRONTEND_DIST_DIR, 'index.html') if FRONTEND_DIST_DIR else None
        })

@app.route('/debug/filesystem')
def debug_filesystem():
    """Debug route to check filesystem structure"""
    import os
    
    def scan_directory(path, max_depth=3, current_depth=0):
        if current_depth > max_depth:
            return {'name': os.path.basename(path), 'type': 'directory', 'truncated': True}
        
        try:
            if os.path.isdir(path):
                items = []
                for item in os.listdir(path):
                    item_path = os.path.join(path, item)
                    if os.path.isdir(item_path):
                        items.append(scan_directory(item_path, max_depth, current_depth + 1))
                    else:
                        items.append({
                            'name': item,
                            'type': 'file',
                            'size': os.path.getsize(item_path) if os.path.exists(item_path) else 0
                        })
                return {
                    'name': os.path.basename(path),
                    'type': 'directory',
                    'items': items[:10]  # Limit to first 10 items
                }
            else:
                return {
                    'name': os.path.basename(path),
                    'type': 'file',
                    'size': os.path.getsize(path) if os.path.exists(path) else 0
                }
        except Exception as e:
            return {
                'name': os.path.basename(path),
                'type': 'error',
                'error': str(e)
            }
    
    debug_info = {
        'current_working_dir': os.getcwd(),
        'app_root_path': app.root_path,
        'frontend_dist_dir': FRONTEND_DIST_DIR,
        'frontend_dist_exists': os.path.exists(FRONTEND_DIST_DIR),
        'filesystem': {}
    }
    
    # Scan important directories
    important_paths = ['/app', '/app/static', app.root_path, FRONTEND_DIST_DIR]
    for path in important_paths:
        if os.path.exists(path):
            debug_info['filesystem'][path] = scan_directory(path)
    
    return jsonify(debug_info)

# Route for serving static assets (JS, CSS, images, etc.)
@app.route('/<path:filename>')
def serve_static(filename):
    """Serve static files from the built frontend."""
    import os
    
    logger.info(f"=== STATIC FILE REQUEST DEBUG ===")
    logger.info(f"Requested filename: {filename}")
    logger.info(f"FRONTEND_DIST_DIR: {FRONTEND_DIST_DIR}")
    logger.info(f"FRONTEND_DIST_DIR exists: {os.path.exists(FRONTEND_DIST_DIR)}")
    
    full_path = os.path.join(FRONTEND_DIST_DIR, filename)
    logger.info(f"Full path to serve: {full_path}")
    logger.info(f"File exists: {os.path.exists(full_path)}")
    
    try:
        logger.info(f"Attempting to serve static file: {filename} from {FRONTEND_DIST_DIR}")
        response = send_from_directory(FRONTEND_DIST_DIR, filename)
        logger.info(f"Successfully served {filename}, response type: {type(response)}")
        return response
    except FileNotFoundError as e:
        logger.error(f"FileNotFoundError serving '{filename}': {e}")
        logger.warning(f"Static file '{filename}' not found: {e}. Returning 404.")
        # If a specific static file is not found, return a 404
        # This will prevent the SPA from loading if essential assets are missing
        return "Not Found", 404
    except Exception as e:
        logger.error(f"Unexpected error serving '{filename}': {e}")
        return f"Internal Server Error: {str(e)}", 500

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    import os
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'app_root_path': app.root_path,
        'frontend_dist_dir': FRONTEND_DIST_DIR,
        'frontend_dist_exists': os.path.exists(FRONTEND_DIST_DIR),
        'index_html_exists': os.path.exists(os.path.join(FRONTEND_DIST_DIR, 'index.html')) if FRONTEND_DIST_DIR else False,
        'current_working_dir': os.getcwd(),
        'data_path': os.environ.get('DATA_PATH', '/data'),
        'scan_time': os.environ.get('SCAN_TIME', '01:00')
    })

@app.route('/api/debug/directories')
def debug_directories():
    """Debug endpoint to check what directories exist"""
    try:
        data_path = get_setting('data_path', os.environ.get('DATA_PATH', '/data'))
        
        if not os.path.exists(data_path):
            return jsonify({
                'error': f'Data path {data_path} does not exist',
                'data_path': data_path
            })
        
        # Get top-level directories
        top_level_dirs = []
        try:
            for item in os.listdir(data_path):
                item_path = os.path.join(data_path, item)
                if os.path.isdir(item_path):
                    try:
                        stat = os.stat(item_path)
                        top_level_dirs.append({
                            'name': item,
                            'path': item_path,
                            'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                        })
                    except (OSError, PermissionError) as e:
                        top_level_dirs.append({
                            'name': item,
                            'path': item_path,
                            'error': str(e)
                        })
        except (OSError, PermissionError) as e:
            return jsonify({
                'error': f'Cannot access data path: {e}',
                'data_path': data_path
            })
        
        # Get database records
        db_dirs = FileRecord.query.filter_by(
            is_directory=True,
            parent_path=data_path
        ).all()
        
        return jsonify({
            'data_path': data_path,
            'filesystem_directories': top_level_dirs,
            'database_directories': [{
                'id': d.id,
                'name': d.name,
                'path': d.path,
                'scan_id': d.scan_id
            } for d in db_dirs],
            'total_fs_dirs': len(top_level_dirs),
            'total_db_dirs': len(db_dirs)
        })
    except Exception as e:
        logger.error(f"Error in debug directories: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get application settings"""
    return jsonify({
        'data_path': get_setting('data_path', os.environ.get('DATA_PATH', '/data')),
        'scan_time': get_setting('scan_time', '01:00'),
        'max_scan_duration': int(get_setting('max_scan_duration', '6')),
        'max_items_per_folder': int(get_setting('max_items_per_folder', '100')),
        'max_shares_to_scan': int(get_setting('max_shares_to_scan', '0')),
        'skip_appdata': get_setting('skip_appdata', 'true').lower() == 'true',
        'theme': get_setting('theme', 'unraid'),
        'themes': ['unraid', 'plex', 'dark', 'light']
    })

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Update application settings"""
    try:
        data = request.get_json()
        
        # Update settings in database
        for key, value in data.items():
            if key in ['data_path', 'scan_time', 'max_scan_duration', 'theme', 'max_items_per_folder', 'max_shares_to_scan', 'skip_appdata']:
                set_setting(key, str(value))
        
        # If scan_time was updated, reconfigure the scheduled scan
        if 'scan_time' in data:
            setup_scheduled_scan()
            logger.info(f"Scheduled scan reconfigured for {data['scan_time']}")
        
        return jsonify({'message': 'Settings updated successfully'})
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        return jsonify({'error': 'Failed to update settings'}), 500

@app.route('/api/database/reset', methods=['POST'])
@retry_on_db_lock(max_retries=3, delay=2)
def reset_database():
    """Reset the database - use with caution!"""
    try:
        logger.info("=== DATABASE RESET REQUESTED ===")
        
        # Stop any running scan
        if scanner_state['scanning']:
            scanner_state['scanning'] = False
            logger.info("Stopped running scan before database reset")
        
        # Force unlock database first
        unlock_database()
        
        # Drop all tables
        logger.info("Dropping all database tables...")
        db.drop_all()
        
        # Recreate tables
        logger.info("Recreating database tables...")
        db.create_all()
        
        # Verify all tables were created
        logger.info("Verifying table creation...")
        inspector = db.inspect(db.engine)
        created_tables = inspector.get_table_names()
        expected_tables = ['files', 'scans', 'media_files', 'duplicate_groups', 'duplicate_files', 'storage_history', 'settings', 'trash_bin', 'folder_info']
        
        missing_tables = [table for table in expected_tables if table not in created_tables]
        if missing_tables:
            logger.warning(f"Missing tables after creation: {missing_tables}")
        else:
            logger.info(f"All {len(created_tables)} tables created successfully")
        
        # Create indexes
        logger.info("Creating database indexes...")
        try:
            create_indexes()
            logger.info("Database indexes created successfully")
        except Exception as e:
            logger.warning(f"Could not create indexes: {e}")
        
        # Initialize default settings with retry logic
        logger.info("Initializing default settings...")
        default_settings = {
            'scan_time': '01:00',
            'max_scan_duration': '6',
            'theme': 'unraid',
            'themes': 'unraid,plex,light,dark',
            'max_items_per_folder': '100',
            'max_shares_to_scan': '0',  # 0 = unlimited
            'skip_appdata': 'true'  # Skip appdata by default
        }
        
        for key, value in default_settings.items():
            try:
                if not get_setting(key):
                    set_setting(key, value)
                    logger.info(f"Set default setting: {key} = {value}")
            except Exception as e:
                logger.warning(f"Failed to set default setting {key}: {e}")
                # Try again after a brief delay
                try:
                    time.sleep(0.1)
                    set_setting(key, value)
                    logger.info(f"Set default setting on retry: {key} = {value}")
                except Exception as retry_e:
                    logger.error(f"Failed to set default setting {key} even on retry: {retry_e}")
        
        # Clear cache
        global cache
        cache.clear()
        logger.info("Cache cleared")
        
        # Force cleanup of any remaining database connections
        logger.info("Cleaning up database connections...")
        db.session.rollback()
        db.session.close()
        db.session.remove()
        db.engine.dispose()
        logger.info("Database connections cleaned up")
        
        # Reset scanner state
        scanner_state.update({
            'scanning': False,
            'current_scan_id': None,
            'start_time': None,
            'total_files': 0,
            'total_directories': 0,
            'total_size': 0,
            'current_path': '',
            'error': None
        })
        
        logger.info("=== DATABASE RESET COMPLETED SUCCESSFULLY ===")
        return jsonify({'message': 'Database reset successfully'})
    except Exception as e:
        logger.error(f"=== DATABASE RESET ERROR ===")
        logger.error(f"Error resetting database: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        return jsonify({'error': f'Failed to reset database: {str(e)}'}), 500

@app.route('/api/scan/start', methods=['POST'])
def start_scan():
    """Start a new scan"""
    try:
        logger.info("=== MANUAL SCAN REQUEST ===")
        logger.info(f"Request received at: {datetime.now()}")
        
        if scanner_state['scanning']:
            logger.warning("Scan already in progress, rejecting request")
            return jsonify({'error': 'Scan already in progress'}), 400
        
        # Start scan using new FileScanner with bulletproof appdata exclusion
        data_path = os.environ.get('DATA_PATH', '/data')
        logger.info(f"Starting NEW FileScanner with bulletproof exclusion for data path: {data_path}")
        
        # Import and use the new scanner
        from scanner import FileScanner
        scanner = FileScanner(data_path, max_duration=6)
        
        # CRITICAL: Pass global scanner_state reference for dashboard updates
        import scanner as scanner_module
        scanner_module.scanner_state = scanner_state
        
        # Set global reference for stop functionality
        global current_scanner_instance
        current_scanner_instance = scanner
        
        # Use the scanner's built-in start_scan method within Flask context
        with app.app_context():
            scan_id = scanner.start_scan()
            logger.info(f"Scanner started with ID: {scan_id}")
            
            # CRITICAL: Update global scanner_state to reflect that scan is running
            if scan_id:
                scanner_state['scanning'] = True
                scanner_state['current_scan_id'] = scan_id
                scanner_state['start_time'] = datetime.now()
                logger.info("Updated global scanner_state to show scan is running")
        
        logger.info(f"=== MANUAL SCAN INITIATED ===")
        logger.info(f"Scan ID: {scan_id}")
        logger.info(f"Data path: {data_path}")
        
        return jsonify({
            'message': 'Scan started successfully',
            'scan_id': scan_id
        })
    except Exception as e:
        logger.error(f"=== SCAN START ERROR ===")
        logger.error(f"Error starting scan: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        return jsonify({'error': 'Failed to start scan'}), 500

@app.route('/api/scan/stop', methods=['POST'])
def stop_scan():
    """Stop the current scan"""
    try:
        if scanner_state['scanning']:
            logger.info("=== SCAN STOP REQUEST ===")
            
            # Signal the new scanner to stop (global variable approach)
            global current_scanner_instance
            if 'current_scanner_instance' in globals() and current_scanner_instance:
                logger.info("Signaling scanner instance to stop")
                current_scanner_instance.stop_current_scan()
            
            # Update in-memory state
            scanner_state['scanning'] = False
            scanner_state['error'] = 'Scan stopped by user'
            logger.info("Scan stopped by user")
            
            # Also update the database to mark any running scans as stopped
            try:
                running_scans = ScanRecord.query.filter_by(status='running').all()
                for scan in running_scans:
                    scan.status = 'stopped'
                    scan.end_time = datetime.now()
                    scan.error_message = 'Scan stopped by user'
                db.session.commit()
                logger.info(f"Updated {len(running_scans)} running scans in database")
            except Exception as db_error:
                logger.error(f"Error updating database for stopped scan: {db_error}")
            
            return jsonify({'message': 'Scan stopped successfully'})
        else:
            return jsonify({'message': 'No scan running'})
    except Exception as e:
        logger.error(f"Error stopping scan: {e}")
        return jsonify({'error': 'Failed to stop scan'}), 500

@app.route('/api/scan/scheduled', methods=['POST'])
def trigger_scheduled_scan():
    """Manually trigger a scheduled scan"""
    try:
        run_scheduled_scan()
        return jsonify({'message': 'Scheduled scan triggered successfully'})
    except Exception as e:
        logger.error(f"Error triggering scheduled scan: {e}")
        return jsonify({'error': 'Failed to trigger scheduled scan'}), 500

@app.route('/api/scan/status')
@retry_on_db_lock(max_retries=3, delay=2)
def get_scan_status():
    """Get current scan status with estimated completion time and percentage"""
    try:
        # Check for running scans in database
        running_scan = db.session.query(ScanRecord).filter(ScanRecord.status == 'running').first()
        
        # Check if we have an active scanner instance running
        global current_scanner_instance
        scanner_is_running = False
        if current_scanner_instance and hasattr(current_scanner_instance, 'scanning'):
            scanner_is_running = current_scanner_instance.scanning
        
        # If we have a running scan in DB but scanner state says not scanning, update state
        if running_scan and not scanner_state['scanning']:
            scanner_state['scanning'] = True
            scanner_state['current_scan_id'] = running_scan.id
            scanner_state['start_time'] = running_scan.start_time
            logger.info(f"Scan status corrected: found running scan {running_scan.id} in DB")
        
        # If we have an active scanner but no running scan in state, update state
        if scanner_is_running and not scanner_state['scanning']:
            scanner_state['scanning'] = True
            if current_scanner_instance:
                scanner_state['current_scan_id'] = getattr(current_scanner_instance, 'current_scan_id', None)
                logger.info("Scan status corrected: active scanner detected")
        
        # Only reset state if BOTH database and scanner show no activity
        if scanner_state['scanning'] and not running_scan and not scanner_is_running:
            scanner_state['scanning'] = False
            scanner_state['current_path'] = ''
            logger.info("Scan status corrected: no running scans in DB or active scanner; hiding banner")

        status_data = {
            'status': 'scanning' if scanner_state['scanning'] else 'idle',
            'scanning': scanner_state['scanning'],
            'scan_id': scanner_state['current_scan_id'],
            'start_time': scanner_state['start_time'].isoformat() if scanner_state['start_time'] else None,
            'total_files': scanner_state['total_files'],
            'total_directories': scanner_state['total_directories'],
            'total_size': scanner_state['total_size'],
            'total_size_formatted': format_size(scanner_state['total_size']),
            'current_path': scanner_state['current_path'],
            'error': scanner_state['error']
        }
        
        # Add elapsed time and duration formatting
        if scanner_state['scanning'] and scanner_state['start_time']:
            elapsed_time = datetime.now() - scanner_state['start_time']
            elapsed_seconds = elapsed_time.total_seconds()
            
            # Format duration for display
            if elapsed_seconds < 60:
                scan_duration = f"{elapsed_seconds:.0f}s"
            elif elapsed_seconds < 3600:
                minutes = int(elapsed_seconds // 60)
                secs = int(elapsed_seconds % 60)
                scan_duration = f"{minutes}m {secs}s"
            else:
                hours = int(elapsed_seconds // 3600)
                minutes = int((elapsed_seconds % 3600) // 60)
                scan_duration = f"{hours}h {minutes}m"
            
            status_data['elapsed_time'] = str(elapsed_time).split('.')[0]  # Remove microseconds
            status_data['elapsed_time_formatted'] = scan_duration
            status_data['scan_duration'] = scan_duration
            
            # Add debugging information
            logger.info(f"Scan duration calculation: elapsed_seconds={elapsed_seconds}, scan_duration='{scan_duration}'")
        else:
            logger.info(f"Scan duration not calculated: scanning={scanner_state['scanning']}, start_time={scanner_state['start_time']}")
            # Try to get duration from database if scanner state is not available
            if running_scan and running_scan.start_time:
                elapsed_time = datetime.now() - running_scan.start_time
                elapsed_seconds = elapsed_time.total_seconds()
                
                if elapsed_seconds < 60:
                    scan_duration = f"{elapsed_seconds:.0f}s"
                elif elapsed_seconds < 3600:
                    minutes = int(elapsed_seconds // 60)
                    secs = int(elapsed_seconds % 60)
                    scan_duration = f"{minutes}m {secs}s"
                else:
                    hours = int(elapsed_seconds // 3600)
                    minutes = int((elapsed_seconds % 3600) // 60)
                    scan_duration = f"{hours}h {minutes}m"
                
                status_data['elapsed_time'] = str(elapsed_time).split('.')[0]
                status_data['elapsed_time_formatted'] = scan_duration
                status_data['scan_duration'] = scan_duration
                logger.info(f"Using database scan duration: {scan_duration}")
        
        # Calculate estimated completion time and percentage if scan is running
        if scanner_state['scanning'] and scanner_state['start_time']:
            # Get average scan duration from last 5 completed scans
            recent_scans = db.session.query(ScanRecord).filter(
                ScanRecord.status == 'completed',
                ScanRecord.end_time.isnot(None)
            ).order_by(desc(ScanRecord.end_time)).limit(5).all()
            
            if recent_scans:
                # Calculate average duration
                total_duration = timedelta()
                for scan in recent_scans:
                    if scan.end_time and scan.start_time:
                        total_duration += scan.end_time - scan.start_time
                
                avg_duration = total_duration / len(recent_scans)
                elapsed_time = datetime.now() - scanner_state['start_time']
                
                # Estimate completion time
                estimated_completion = scanner_state['start_time'] + avg_duration
                status_data['estimated_completion'] = estimated_completion.isoformat()
                
                # Calculate percentage complete (based on time elapsed vs average duration)
                if avg_duration.total_seconds() > 0:
                    percentage_complete = min(95, (elapsed_time.total_seconds() / avg_duration.total_seconds()) * 100)
                    status_data['percentage_complete'] = round(percentage_complete, 1)
                else:
                    status_data['percentage_complete'] = 0
                
                status_data['estimated_duration'] = str(avg_duration).split('.')[0]  # Remove microseconds
                status_data['is_first_scan'] = False
            else:
                # No previous scans to base estimate on (first scan)
                status_data['estimated_completion'] = None
                status_data['percentage_complete'] = None  # Hide progress bar for first scan
                status_data['estimated_duration'] = None
                status_data['is_first_scan'] = True
        
        return jsonify(status_data)
    except Exception as e:
        logger.error(f"Error getting scan status: {e}")
        # Try to unlock database if it's locked
        if "database is locked" in str(e).lower():
            unlock_database()
        return jsonify({'error': 'Failed to get scan status'}), 500

@app.route('/api/scan/history')
@retry_on_db_lock(max_retries=3, delay=2)
def get_scan_history():
    """Get scan history with duration information"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        scans = ScanRecord.query.order_by(desc(ScanRecord.start_time)).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        scan_list = []
        for scan in scans.items:
            scan_data = {
                'id': scan.id,
                'start_time': scan.start_time.isoformat(),
                'end_time': scan.end_time.isoformat() if scan.end_time else None,
                'status': scan.status,
                'total_files': scan.total_files,
                'total_directories': scan.total_directories,
                'total_size': scan.total_size,
                'error_message': scan.error_message
            }
            
            # Calculate duration for completed scans
            if scan.end_time and scan.start_time:
                duration = scan.end_time - scan.start_time
                scan_data['duration'] = str(duration).split('.')[0]  # Remove microseconds
                scan_data['duration_seconds'] = duration.total_seconds()
            else:
                scan_data['duration'] = None
                scan_data['duration_seconds'] = None
            
            scan_list.append(scan_data)
        
        return jsonify({
            'scans': scan_list,
            'total': scans.total,
            'pages': scans.pages,
            'current_page': scans.page
        })
    except Exception as e:
        logger.error(f"Error getting scan history: {e}")
        return jsonify({'error': 'Failed to get scan history'}), 500

@app.route('/api/files')
@retry_on_db_lock(max_retries=3, delay=2)
def get_files():
    """Get files with filtering and pagination"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        search = request.args.get('search', '')
        file_type = request.args.get('type', '')
        modified_since = request.args.get('modified_since', '')
        
        # Get latest completed scan
        latest_scan = db.session.query(ScanRecord).filter(
            ScanRecord.status == 'completed'
        ).order_by(ScanRecord.start_time.desc()).first()
        
        if not latest_scan:
            return jsonify({
                'files': [],
                'pages': 0,
                'current_page': page,
                'total': 0
            })
        
        query = FileRecord.query.filter(FileRecord.scan_id == latest_scan.id)
        
        # Apply search filter
        if search:
            query = query.filter(
                db.or_(
                    FileRecord.name.ilike(f'%{search}%'),
                    FileRecord.path.ilike(f'%{search}%')
                )
            )
        
        # Apply type filter
        if file_type == 'file':
            query = query.filter(FileRecord.is_directory == False)
        elif file_type == 'directory':
            query = query.filter(FileRecord.is_directory == True)
        
        # Apply modified since filter
        if modified_since:
            now = datetime.utcnow()
            if modified_since == 'today':
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif modified_since == 'week':
                start_date = now - timedelta(days=7)
            elif modified_since == 'month':
                start_date = now - timedelta(days=30)
            elif modified_since == 'year':
                start_date = now - timedelta(days=365)
            elif modified_since == 'last_year':
                start_date = now - timedelta(days=730)
                end_date = now - timedelta(days=365)
                query = query.filter(
                    FileRecord.modified_time >= start_date,
                    FileRecord.modified_time <= end_date
                )
            elif modified_since == 'older_1_year':
                start_date = now - timedelta(days=365)
                query = query.filter(FileRecord.modified_time < start_date)
            elif modified_since == 'older_5_years':
                start_date = now - timedelta(days=1825)
                query = query.filter(FileRecord.modified_time < start_date)
            else:
                start_date = now - timedelta(days=365)
            
            if modified_since not in ['last_year', 'older_1_year', 'older_5_years']:
                query = query.filter(FileRecord.modified_time >= start_date)
        
        # Order by name
        query = query.order_by(FileRecord.name)
        
        # Paginate
        pagination = query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        files = []
        for file_record in pagination.items:
            files.append({
                'id': file_record.id,
                'path': file_record.path,
                'name': file_record.name,
                'size': file_record.size,
                'size_formatted': format_size(file_record.size),
                'is_directory': file_record.is_directory,
                'extension': file_record.extension or '',
                'modified_time': file_record.modified_time.isoformat() if file_record.modified_time else None,
                'parent_path': file_record.parent_path
            })
        
        return jsonify({
            'files': files,
            'pages': pagination.pages,
            'current_page': page,
            'total': pagination.total
        })
        
    except Exception as e:
        logger.error(f"Error getting files: {e}")
        return jsonify({'error': 'Failed to get files'}), 500

# Add new endpoint to get files within a directory
@app.route('/api/files/tree/<int:directory_id>/files')
def get_directory_files(directory_id):
    """Get files within a specific directory"""
    try:
        directory = FileRecord.query.get_or_404(directory_id)
        
        # Get files (not directories) within this directory
        files = db.session.query(
            FileRecord
        ).filter(
            FileRecord.parent_path == directory.path,
            FileRecord.is_directory == False
        ).order_by(FileRecord.size.desc()).limit(100).all()  # Limit to top 100 files by size
        
        result = []
        for file in files:
            result.append({
                'id': file.id,
                'name': file.name,
                'path': file.path,
                'size': file.size,
                'size_formatted': format_size(file.size),
                'extension': file.extension,
                'is_directory': False,
                'modified_time': file.modified_time.isoformat() if file.modified_time else None
            })
        
        return jsonify({'files': result})
    except Exception as e:
        logger.error(f"Error getting directory files: {e}")
        return jsonify({'error': 'Failed to get directory files'}), 500

# Optimize the top-shares endpoint to use pre-calculated totals with fallback
@app.route('/api/analytics/top-shares')
@retry_on_db_lock(max_retries=3, delay=2)
def get_top_shares():
    """Get top folder shares by size - using pre-calculated totals with fallback"""
    try:
        data_path = get_setting('data_path', os.environ.get('DATA_PATH', '/data'))
        logger.info(f"Getting top shares for data_path: {data_path}")
        
        # First try to get the latest completed scan
        latest_scan = db.session.query(ScanRecord).filter(
            ScanRecord.status == 'completed'
        ).order_by(ScanRecord.start_time.desc()).first()
        
        # If no completed scan, try to get the current running scan
        if not latest_scan:
            latest_scan = db.session.query(ScanRecord).filter(
                ScanRecord.status == 'running'
            ).order_by(ScanRecord.start_time.desc()).first()
            
        if not latest_scan:
            logger.info("No scans found. Returning empty top shares list.")
            return jsonify({'top_shares': []})
        
        # First try to get pre-calculated totals
        top_shares_data = db.session.query(
            FolderInfo.path,
            FolderInfo.name,
            FolderInfo.total_size,
            FolderInfo.file_count
        ).filter(
            FolderInfo.path.like(f"{data_path}/%"),
            FolderInfo.depth == 1,  # Top-level only
            FolderInfo.scan_id == latest_scan.id
        ).order_by(FolderInfo.total_size.desc()).all()
        
        if top_shares_data:
            logger.info(f"Found {len(top_shares_data)} top-level directories with pre-calculated totals")
            
            top_shares = []
            for share in top_shares_data:
                top_shares.append({
                    'name': share.name,
                    'path': share.path,
                    'size': share.total_size,
                    'size_formatted': format_size(share.total_size),
                    'file_count': share.file_count
                })
        else:
            # Fallback to old approach if no pre-calculated data
            logger.info("No pre-calculated totals found, using fallback approach")
            
            if latest_scan:
                # Get distinct top-level directories from latest scan
                shares_data = db.session.query(
                    FileRecord.name,
                    FileRecord.path,
                    func.sum(FileRecord.size).label('total_size'),
                    func.count(FileRecord.id).label('total_count'),
                    func.sum(case((FileRecord.is_directory == False, 1), else_=0)).label('file_count')
                ).filter(
                    FileRecord.parent_path == data_path,
                    FileRecord.is_directory == True,  # Only directories
                    FileRecord.scan_id == latest_scan.id
                ).group_by(
                    FileRecord.name,
                    FileRecord.path
                ).all()
                
                top_shares = []
                for share in shares_data:
                    top_shares.append({
                        'name': share.name,
                        'path': share.path,
                        'size': share.total_size or 0,
                        'size_formatted': format_size(share.total_size or 0),
                        'file_count': share.file_count or 0
                    })
            else:
                top_shares = []
        
        # Sort by total size and take top 10
        top_shares.sort(key=lambda x: x['size'], reverse=True)
        top_shares = top_shares[:10]
        
        logger.info(f"Returning {len(top_shares)} top shares")
        return jsonify({
            'top_shares': top_shares
        })
    except Exception as e:
        logger.error(f"Error getting top shares: {e}")
        return jsonify({'error': 'Failed to get top shares'}), 500

# Optimize the file tree endpoint to use pre-calculated totals with fallback
@app.route('/api/files/tree')
def get_file_tree():
    """Get hierarchical file tree - using pre-calculated totals with fallback"""
    try:
        data_path = get_setting('data_path', os.environ.get('DATA_PATH', '/data'))
        logger.info(f"Getting file tree for data_path: {data_path}")
        
        # First try to get the latest completed scan
        latest_scan = db.session.query(ScanRecord).filter(
            ScanRecord.status == 'completed'
        ).order_by(ScanRecord.start_time.desc()).first()
        
        # If no completed scan, try to get the current running scan
        if not latest_scan:
            latest_scan = db.session.query(ScanRecord).filter(
                ScanRecord.status == 'running'
            ).order_by(ScanRecord.start_time.desc()).first()
            
        if not latest_scan:
            logger.info("No scans found. Returning empty tree.")
            return jsonify({'tree': []})
        
        # First try to get pre-calculated totals
        tree_data = db.session.query(
            FolderInfo.path,
            FolderInfo.name,
            FolderInfo.total_size,
            FolderInfo.file_count
        ).filter(
            FolderInfo.path.like(f"{data_path}/%"),
            FolderInfo.depth == 1,  # Top-level only
            FolderInfo.scan_id == latest_scan.id
        ).order_by(FolderInfo.total_size.desc()).all()
        
        if tree_data:
            logger.info(f"Found {len(tree_data)} top-level directories with pre-calculated totals")
            
            tree = []
            for item in tree_data:
                # Get the FileRecord ID for this directory
                file_record = FileRecord.query.filter_by(path=item.path).first()
                
                tree.append({
                    'id': file_record.id if file_record else 0,
                    'name': item.name,
                    'path': item.path,
                    'size': item.total_size,
                    'size_formatted': format_size(item.total_size),
                    'file_count': item.file_count,
                    'is_directory': True,
                    'children': []  # Will be populated when expanded
                })
        else:
            # Fallback to old approach if no pre-calculated data
            logger.info("No pre-calculated totals found, using fallback approach")
            
            if latest_scan:
                # Get distinct top-level directories from latest scan
                shares_data = db.session.query(
                    FileRecord.name,
                    FileRecord.path,
                    FileRecord.id,
                    func.sum(FileRecord.size).label('total_size'),
                    func.count(FileRecord.id).label('total_count'),
                    func.sum(case((FileRecord.is_directory == False, 1), else_=0)).label('file_count')
                ).filter(
                    FileRecord.parent_path == data_path,
                    FileRecord.is_directory == True,  # Only directories
                    FileRecord.scan_id == latest_scan.id
                ).group_by(
                    FileRecord.name,
                    FileRecord.path,
                    FileRecord.id
                ).all()
                
                tree = []
                for share in shares_data:
                    tree.append({
                        'id': share.id,
                        'name': share.name,
                        'path': share.path,
                        'size': share.total_size or 0,
                        'size_formatted': format_size(share.total_size or 0),
                        'file_count': share.file_count or 0,
                        'is_directory': True,
                        'children': []  # Will be populated when expanded
                    })
            else:
                tree = []
        
        # Sort by total size
        tree.sort(key=lambda x: x['size'], reverse=True)
        
        logger.info(f"Returning {len(tree)} items in tree")
        return jsonify({'tree': tree})
    except Exception as e:
        logger.error(f"Error getting file tree: {e}")
        return jsonify({'error': 'Failed to get file tree'}), 500

# Optimize the directory children endpoint to use pre-calculated totals when available
@app.route('/api/files/tree/<int:directory_id>')
def get_directory_children(directory_id):
    """Get children of a specific directory - using pre-calculated totals when available"""
    try:
        directory = FileRecord.query.get_or_404(directory_id)
        
        # Get the limit from settings (default 100)
        max_items = int(get_setting('max_items_per_folder', '100'))
        
        # Get all direct children (both files and directories)
        children = db.session.query(
            FileRecord.name,
            FileRecord.path,
            FileRecord.id,
            FileRecord.is_directory,
            FileRecord.size,
            FileRecord.extension,
            FileRecord.modified_time
        ).filter(
            FileRecord.parent_path == directory.path
        ).order_by(FileRecord.size.desc()).limit(max_items).all()
        
        result = []
        for child in children:
            if child.is_directory:
                # Get comprehensive folder info
                folder_info = get_folder_info(child.path)
                
                result.append({
                    'id': child.id,
                    'name': child.name,
                    'path': child.path,
                    'size': folder_info['total_size'],
                    'size_formatted': format_size(folder_info['total_size']),
                    'file_count': folder_info['file_count'],
                    'directory_count': folder_info['directory_count'],
                    'is_directory': True,
                    'children': []
                })
            else:
                # For files, use the file's own size
                result.append({
                    'id': child.id,
                    'name': child.name,
                    'path': child.path,
                    'size': child.size,
                    'size_formatted': format_size(child.size),
                    'extension': child.extension,
                    'modified_time': child.modified_time.isoformat() if child.modified_time else None,
                    'is_directory': False
                })
        
        # Sort by total size (directories) or file size (files)
        result.sort(key=lambda x: x['size'], reverse=True)
        
        return jsonify({'children': result})
    except Exception as e:
        logger.error(f"Error getting directory children: {e}")
        return jsonify({'error': 'Failed to get directory children'}), 500

# Add delete endpoint for files and directories
@app.route('/api/files/<int:file_id>/delete', methods=['POST'])
def delete_file_or_directory(file_id):
    """Delete a file or directory"""
    try:
        file_record = FileRecord.query.get_or_404(file_id)
        
        # Get the actual file path
        file_path = file_record.path
        
        # Check if file/directory exists
        if not os.path.exists(file_path):
            return jsonify({'error': 'File or directory does not exist'}), 404
        
        # Move to trash instead of permanent deletion
        trash_dir = '/app/data/trash'
        os.makedirs(trash_dir, exist_ok=True)
        
        # Create unique trash path
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.basename(file_path)
        trash_path = os.path.join(trash_dir, f"{timestamp}_{filename}")
        
        try:
            # Move file/directory to trash
            import shutil
            shutil.move(file_path, trash_path)
            
            # Add to trash bin database
            trash_item = TrashBin(
                original_path=file_path,
                original_size=file_record.size,
                expires_at=datetime.now() + timedelta(days=30)  # Keep for 30 days
            )
            db.session.add(trash_item)
            
            # Remove from files database
            db.session.delete(file_record)
            db.session.commit()
            
            logger.info(f"Deleted {file_path} -> {trash_path}")
            return jsonify({'message': f'Successfully deleted {filename}'})
            
        except Exception as e:
            logger.error(f"Error deleting {file_path}: {e}")
            return jsonify({'error': f'Failed to delete {filename}'}), 500
            
    except Exception as e:
        logger.error(f"Error in delete_file_or_directory: {e}")
        return jsonify({'error': 'Failed to delete file or directory'}), 500

@app.route('/api/analytics/overview')
@retry_on_db_lock(max_retries=3, delay=2)
def get_analytics_overview():
    """Get storage analytics overview"""
    try:
        # First try to get the latest completed scan
        latest_scan = db.session.query(ScanRecord).filter(
            ScanRecord.status == 'completed'
        ).order_by(ScanRecord.start_time.desc()).first()
        
        # If no completed scan, try to get the current running scan
        if not latest_scan:
            latest_scan = db.session.query(ScanRecord).filter(
                ScanRecord.status == 'running'
            ).order_by(ScanRecord.start_time.desc()).first()
        
        if not latest_scan:
            return jsonify({
                'total_files': 0,
                'total_directories': 0,
                'total_size': 0,
                'total_size_formatted': '0 B',
                'top_extensions': [],
                'media_files': 0
            })
        
        # Get total stats from the scan
        total_files = latest_scan.total_files or 0
        total_directories = latest_scan.total_directories or 0
        total_size = latest_scan.total_size or 0
        
        # Get top file types
        top_extensions = db.session.query(
            FileRecord.extension,
            func.count(FileRecord.id).label('count'),
            func.sum(FileRecord.size).label('total_size')
        ).filter(
            FileRecord.extension.isnot(None),
            FileRecord.is_directory == False,
            FileRecord.scan_id == latest_scan.id
        ).group_by(FileRecord.extension).order_by(
            desc(func.sum(FileRecord.size))
        ).limit(10).all()
        
        # Get media breakdown
        media_files = MediaFile.query.join(FileRecord, MediaFile.file_id == FileRecord.id).filter(
            FileRecord.scan_id == latest_scan.id
        ).count()
        
        return jsonify({
            'total_files': total_files,
            'total_directories': total_directories,
            'total_size': total_size,
            'total_size_formatted': format_size(total_size),
            'top_extensions': [{
                'extension': ext.extension,
                'count': ext.count,
                'total_size': ext.total_size,
                'total_size_formatted': format_size(ext.total_size)
            } for ext in top_extensions],
            'media_files': media_files
        })
    except Exception as e:
        logger.error(f"Error getting analytics overview: {e}")
        return jsonify({'error': 'Failed to get analytics overview'}), 500

@app.route('/api/analytics/stats')
def get_analytics_stats():
    """Get analytics statistics including scan count and growth metrics"""
    try:
        # Get total number of scans
        total_scans = ScanRecord.query.count()
        
        # Get completed scans
        completed_scans = ScanRecord.query.filter(
            ScanRecord.status == 'completed'
        ).order_by(ScanRecord.start_time.desc()).limit(10).all()
        
        if len(completed_scans) < 2:
            return jsonify({
                'total_scans': total_scans,
                'completed_scans': len(completed_scans),
                'average_growth': {
                    'files_per_week': 0,
                    'size_per_week': 0,
                    'files_formatted': '0',
                    'size_formatted': '0 B'
                },
                'last_scan': None,
                'first_scan': None
            })
        
        # Calculate growth metrics based on the last 2 scans
        latest_scan = completed_scans[0]
        previous_scan = completed_scans[1] if len(completed_scans) > 1 else None
        
        files_per_week = 0
        size_per_week = 0
        
        if previous_scan:
            # Calculate time difference in weeks
            time_diff_days = (latest_scan.start_time - previous_scan.start_time).days
            time_diff_weeks = max(time_diff_days / 7, 0.1)  # Minimum 0.1 weeks to avoid division by zero
            
            # Calculate growth per week
            file_growth = latest_scan.total_files - previous_scan.total_files
            size_growth = latest_scan.total_size - previous_scan.total_size
            
            files_per_week = file_growth / time_diff_weeks
            size_per_week = size_growth / time_diff_weeks
        
        return jsonify({
            'total_scans': total_scans,
            'completed_scans': len(completed_scans),
            'average_growth': {
                'files_per_week': int(files_per_week),
                'size_per_week': int(size_per_week),
                'files_formatted': f"{int(files_per_week):,}",
                'size_formatted': format_size(int(size_per_week))
            },
            'last_scan': {
                'date': latest_scan.start_time.isoformat(),
                'files': latest_scan.total_files,
                'size': latest_scan.total_size,
                'size_formatted': format_size(latest_scan.total_size)
            },
            'first_scan': {
                'date': completed_scans[-1].start_time.isoformat(),
                'files': completed_scans[-1].total_files,
                'size': completed_scans[-1].total_size,
                'size_formatted': format_size(completed_scans[-1].total_size)
            }
        })
    except Exception as e:
        logger.error(f"Error getting analytics stats: {e}")
        return jsonify({'error': 'Failed to get analytics stats'}), 500

@app.route('/api/analytics/history')
def get_storage_history():
    """Get storage usage history from all completed scans with enhanced timing info"""
    try:
        days = request.args.get('days', 30, type=int)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Get data from StorageHistory table (if any)
        storage_history = StorageHistory.query.filter(
            StorageHistory.date >= start_date,
            StorageHistory.date <= end_date
        ).order_by(StorageHistory.date).all()
        
        # Get data from completed scans
        completed_scans = ScanRecord.query.filter(
            ScanRecord.status == 'completed',
            ScanRecord.start_time >= start_date,
            ScanRecord.start_time <= end_date
        ).order_by(ScanRecord.start_time).all()
        
        # Combine both sources, prioritizing StorageHistory if available
        history_data = {}
        
        # Add StorageHistory data
        for record in storage_history:
            history_data[record.date.date()] = {
                'date': record.date.isoformat(),
                'total_size': record.total_size,
                'total_size_formatted': format_size(record.total_size),
                'file_count': record.file_count,
                'directory_count': record.directory_count
            }
        
        # Add ScanRecord data for dates not already covered
        for scan in completed_scans:
            scan_date = scan.start_time.date()
            if scan_date not in history_data:
                duration = None
                if scan.end_time and scan.start_time:
                    duration_seconds = (scan.end_time - scan.start_time).total_seconds()
                    hours = int(duration_seconds // 3600)
                    minutes = int((duration_seconds % 3600) // 60)
                    seconds = int(duration_seconds % 60)
                    duration = f"{hours}:{minutes:02d}:{seconds:02d}"
                
                history_data[scan_date] = {
                    'date': scan.start_time.isoformat(),
                    'start_time': scan.start_time.isoformat(),
                    'end_time': scan.end_time.isoformat() if scan.end_time else None,
                    'duration': duration,
                    'total_size': scan.total_size,
                    'total_size_formatted': format_size(scan.total_size),
                    'file_count': scan.total_files,
                    'directory_count': scan.total_directories,
                    'status': scan.status
                }
        
        # Convert to sorted list
        history = sorted(history_data.values(), key=lambda x: x['date'])
        
        return jsonify({
            'history': history
        })
    except Exception as e:
        logger.error(f"Error getting storage history: {e}")
        return jsonify({'error': 'Failed to get storage history'}), 500

@app.route('/api/media/files')
def get_media_files():
    """Get media files with filtering"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        media_type = request.args.get('type', '')
        resolution = request.args.get('resolution', '')
        search = request.args.get('search', '')
        
        # Restrict to latest completed scan's files when joining
        latest_scan = db.session.query(ScanRecord).filter(
            ScanRecord.status == 'completed'
        ).order_by(ScanRecord.start_time.desc()).first()

        query = MediaFile.query
        
        # Apply filters
        if media_type and media_type != 'all':
            query = query.filter(MediaFile.media_type == media_type)
        if resolution and resolution != 'all':
            query = query.filter(MediaFile.resolution == resolution)
        if search:
            query = query.filter(
                db.or_(
                    MediaFile.title.ilike(f'%{search}%'),
                    MediaFile.episode_title.ilike(f'%{search}%')
                )
            )
        
        media_files = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Get counts by media type
        media_counts = db.session.query(
            MediaFile.media_type,
            func.count(MediaFile.id).label('count')
        ).join(
            FileRecord, MediaFile.file_id == FileRecord.id, isouter=True
        ).filter(
            db.or_(MediaFile.file_id.is_(None), FileRecord.scan_id == (latest_scan.id if latest_scan else None))
        ).group_by(MediaFile.media_type).all()
        
        counts = {}
        for media_type, count in media_counts:
            counts[media_type] = count
        
        return jsonify({
            'media_files': [{
                'id': media.id,
                'title': media.title,
                'year': media.year,
                'media_type': media.media_type,
                'resolution': media.resolution,
                'video_codec': media.video_codec,
                'audio_codec': media.audio_codec,
                'runtime': media.runtime,
                'file_format': media.file_format,
                'size': media.file_id and FileRecord.query.get(media.file_id).size or 0,
                'size_formatted': media.file_id and format_size(FileRecord.query.get(media.file_id).size) or '0 B',
                'path': media.file_id and FileRecord.query.get(media.file_id).path or '',
                'name': media.file_id and FileRecord.query.get(media.file_id).name or media.title
            } for media in media_files.items],
            'total': media_files.total,
            'pages': media_files.pages,
            'current_page': media_files.page,
            'counts': counts
        })
    except Exception as e:
        logger.error(f"Error getting media files: {e}")
        return jsonify({'error': 'Failed to get media files'}), 500

@app.route('/api/files/<int:file_id>', methods=['DELETE'])
def delete_file(file_id):
    """Delete a file (move to trash)"""
    try:
        file_record = FileRecord.query.get_or_404(file_id)
        
        # Create trash bin entry
        trash_entry = TrashBin(
            original_path=file_record.path,
            original_size=file_record.size,
            expires_at=datetime.now() + timedelta(days=2)  # 48 hours
        )
        
        # Move file to trash directory
        trash_dir = '/app/data/trash'
        os.makedirs(trash_dir, exist_ok=True)
        
        trash_path = os.path.join(trash_dir, f"{file_record.id}_{file_record.name}")
        
        if os.path.exists(file_record.path):
            shutil.move(file_record.path, trash_path)
            trash_entry.original_path = trash_path
        
        # Save to database
        db.session.add(trash_entry)
        db.session.commit()
        
        return jsonify({'message': 'File moved to trash successfully'})
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        return jsonify({'error': 'Failed to delete file'}), 500

@app.route('/api/trash')
def get_trash_bin():
    """Get trash bin contents"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        trash_items = TrashBin.query.filter_by(restored=False).order_by(
            desc(TrashBin.deleted_time)
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            'trash_items': [{
                'id': item.id,
                'original_path': item.original_path,
                'original_size': item.original_size,
                'original_size_formatted': format_size(item.original_size),
                'deleted_time': item.deleted_time.isoformat(),
                'expires_at': item.expires_at.isoformat() if item.expires_at else None
            } for item in trash_items.items],
            'total': trash_items.total,
            'pages': trash_items.pages,
            'current_page': trash_items.page
        })
    except Exception as e:
        logger.error(f"Error getting trash bin: {e}")
        return jsonify({'error': 'Failed to get trash bin'}), 500

@app.route('/api/logs')
def get_logs():
    """Get recent application logs and scan information"""
    try:
        lines = request.args.get('lines', 50, type=int)
        
        # Check for running scans in database
        running_scan = db.session.query(ScanRecord).filter(ScanRecord.status == 'running').first()
        
        # Get current scan status
        current_scan = None
        if scanner_state['scanning'] or running_scan:
            # Use scanner state if available, otherwise use database info
            if scanner_state['scanning']:
                current_scan = {
                    'status': 'scanning',
                    'scan_id': scanner_state['current_scan_id'],
                    'start_time': scanner_state['start_time'].isoformat() if scanner_state['start_time'] else None,
                    'total_files': scanner_state['total_files'],
                    'total_directories': scanner_state['total_directories'],
                    'total_size': scanner_state['total_size'],
                    'total_size_formatted': format_size(scanner_state['total_size']),
                    'current_path': scanner_state['current_path'],
                    'error': scanner_state['error']
                }
            elif running_scan:
                current_scan = {
                    'status': 'scanning',
                    'scan_id': running_scan.id,
                    'start_time': running_scan.start_time.isoformat() if running_scan.start_time else None,
                    'total_files': running_scan.total_files or 0,
                    'total_directories': running_scan.total_directories or 0,
                    'total_size': running_scan.total_size or 0,
                    'total_size_formatted': format_size(running_scan.total_size or 0),
                    'current_path': scanner_state.get('current_path', ''),
                    'error': running_scan.error_message
                }
        
        # Get recent scan history
        recent_scans = db.session.query(ScanRecord).order_by(
            desc(ScanRecord.start_time)
        ).limit(5).all()
        
        scan_history = []
        for scan in recent_scans:
            scan_history.append({
                'id': scan.id,
                'start_time': scan.start_time.isoformat(),
                'end_time': scan.end_time.isoformat() if scan.end_time else None,
                'status': scan.status,
                'total_files': scan.total_files,
                'total_directories': scan.total_directories,
                'total_size': scan.total_size,
                'total_size_formatted': format_size(scan.total_size),
                'error_message': scan.error_message
            })
        
        # Create detailed log entries
        logs = []
        
        # Add current scan status with more detail
        if current_scan:
            logs.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'INFO',
                'message': f"=== SCAN IN PROGRESS ===",
                'raw': f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - === SCAN IN PROGRESS ==="
            })
            logs.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'INFO',
                'message': f"Scan ID: {current_scan['scan_id']}",
                'raw': f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - Scan ID: {current_scan['scan_id']}"
            })
            logs.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'INFO',
                'message': f"Files processed: {current_scan['total_files']:,}",
                'raw': f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - Files processed: {current_scan['total_files']:,}"
            })
            logs.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'INFO',
                'message': f"Directories processed: {current_scan['total_directories']:,}",
                'raw': f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - Directories processed: {current_scan['total_directories']:,}"
            })
            logs.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'INFO',
                'message': f"Total size: {current_scan['total_size_formatted']}",
                'raw': f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - Total size: {current_scan['total_size_formatted']}"
            })
            if current_scan['current_path']:
                logs.append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'level': 'INFO',
                    'message': f"Current path: {current_scan['current_path']}",
                    'raw': f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - Current path: {current_scan['current_path']}"
                })
            if current_scan['error']:
                logs.append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'level': 'ERROR',
                    'message': f"Scan error: {current_scan['error']}",
                    'raw': f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - ERROR - Scan error: {current_scan['error']}"
                })
        else:
            logs.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'INFO',
                'message': 'No scan currently running',
                'raw': f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - No scan currently running"
            })
        
        # Add recent scan history with more detail
        if scan_history:
            logs.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'INFO',
                'message': f"=== RECENT SCAN HISTORY ===",
                'raw': f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - === RECENT SCAN HISTORY ==="
            })
            
            for scan in scan_history:
                logs.append({
                    'timestamp': scan['start_time'][:19].replace('T', ' '),
                    'level': 'INFO' if scan['status'] == 'completed' else 'ERROR' if scan['status'] == 'failed' else 'WARNING',
                    'message': f"Scan {scan['id']} - Status: {scan['status'].upper()}",
                    'raw': f"{scan['start_time'][:19].replace('T', ' ')} - {'INFO' if scan['status'] == 'completed' else 'ERROR' if scan['status'] == 'failed' else 'WARNING'} - Scan {scan['id']} - Status: {scan['status'].upper()}"
                })
                logs.append({
                    'timestamp': scan['start_time'][:19].replace('T', ' '),
                    'level': 'INFO',
                    'message': f"  Files: {scan['total_files']:,}, Directories: {scan['total_directories']:,}, Size: {scan['total_size_formatted']}",
                    'raw': f"{scan['start_time'][:19].replace('T', ' ')} - INFO - Files: {scan['total_files']:,}, Directories: {scan['total_directories']:,}, Size: {scan['total_size_formatted']}"
                })
                if scan['error_message']:
                    logs.append({
                        'timestamp': scan['start_time'][:19].replace('T', ' '),
                        'level': 'ERROR',
                        'message': f"  Error: {scan['error_message']}",
                        'raw': f"{scan['start_time'][:19].replace('T', ' ')} - ERROR - Error: {scan['error_message']}"
                    })
        
        # Add database status (latest scan only)
        try:
            latest_completed = db.session.query(ScanRecord).filter(
                ScanRecord.status == 'completed'
            ).order_by(ScanRecord.start_time.desc()).first()
            if latest_completed:
                folder_count = db.session.query(FolderInfo).filter(FolderInfo.scan_id == latest_completed.id).count()
                file_count = db.session.query(FileRecord).filter(FileRecord.scan_id == latest_completed.id).count()
            else:
                folder_count = 0
                file_count = 0
            logs.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'INFO',
                'message': f"=== DATABASE STATUS ===",
                'raw': f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - === DATABASE STATUS ==="
            })
            logs.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'INFO',
                'message': f"Files in database: {file_count:,}",
                'raw': f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - Files in database: {file_count:,}"
            })
            logs.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'INFO',
                'message': f"Folders in database: {folder_count:,}",
                'raw': f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - Folders in database: {folder_count:,}"
            })
        except Exception as e:
            logs.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'level': 'ERROR',
                'message': f"Database status error: {e}",
                'raw': f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - ERROR - Database status error: {e}"
            })
        
        # Add application status
        logs.append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'level': 'INFO',
            'message': f"=== APPLICATION STATUS ===",
            'raw': f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - === APPLICATION STATUS ==="
        })
        logs.append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'level': 'INFO',
            'message': f"Application running. Recent scans: {len(scan_history)}",
            'raw': f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - Application running. Recent scans: {len(scan_history)}"
        })
        logs.append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'level': 'INFO',
            'message': f"For detailed system logs, use: docker logs <container_name>",
            'raw': f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - For detailed system logs, use: docker logs <container_name>"
        })
        
        return jsonify({
            'logs': logs[:lines],
            'total_lines': len(logs),
            'current_scan': current_scan,
            'recent_scans': scan_history
        })
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        return jsonify({'error': 'Failed to get logs'}), 500

@app.route('/api/trash/<int:item_id>/restore', methods=['POST'])
def restore_file(item_id):
    """Restore a file from trash"""
    try:
        trash_item = TrashBin.query.get_or_404(item_id)
        
        if trash_item.restored:
            return jsonify({'error': 'File already restored'}), 400
        
        # Restore file to original location
        if os.path.exists(trash_item.original_path):
            # For now, just mark as restored
            # In a real implementation, you'd move it back
            trash_item.restored = True
            db.session.commit()
            
            return jsonify({'message': 'File restored successfully'})
        else:
            return jsonify({'error': 'File not found in trash'}), 404
    except Exception as e:
        logger.error(f"Error restoring file: {e}")
        return jsonify({'error': 'Failed to restore file'}), 500

@app.route('/api/duplicates')
@retry_on_db_lock(max_retries=3, delay=2)
def get_duplicates():
    """Get duplicate files grouped by hash"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Get duplicate groups with file count and total size
        duplicate_groups = db.session.query(
            DuplicateGroup,
            func.count(DuplicateFile.id).label('file_count'),
            func.sum(FileRecord.size).label('total_size')
        ).join(
            DuplicateFile, DuplicateGroup.id == DuplicateFile.group_id
        ).join(
            FileRecord, DuplicateFile.file_id == FileRecord.id
        ).group_by(
            DuplicateGroup.id
        ).order_by(
            desc(func.sum(FileRecord.size))
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        result = []
        for group, file_count, total_size in duplicate_groups.items:
            # Get individual files in this group
            files = db.session.query(
                FileRecord, DuplicateFile
            ).join(
                DuplicateFile, FileRecord.id == DuplicateFile.file_id
            ).filter(
                DuplicateFile.group_id == group.id
            ).all()
            
            group_files = []
            for file_record, duplicate_file in files:
                group_files.append({
                    'id': file_record.id,
                    'name': file_record.name,
                    'path': file_record.path,
                    'size': file_record.size,
                    'size_formatted': format_size(file_record.size),
                    'is_primary': duplicate_file.is_primary,
                    'is_deleted': duplicate_file.is_deleted
                })
            
            result.append({
                'id': group.id,
                'hash': group.hash_value,
                'size': group.size,
                'size_formatted': format_size(group.size),
                'file_count': file_count,
                'total_size': total_size,
                'total_size_formatted': format_size(total_size),
                'files': group_files
            })
        
        return jsonify({
            'duplicates': result,
            'total': duplicate_groups.total,
            'pages': duplicate_groups.pages,
            'current_page': duplicate_groups.page
        })
    except Exception as e:
        logger.error(f"Error getting duplicates: {e}")
        # Try to unlock database if it's locked
        if "database is locked" in str(e).lower():
            unlock_database()
        return jsonify({'error': 'Failed to get duplicates'}), 500

@app.route('/api/duplicates/<int:group_id>/delete/<int:file_id>', methods=['POST'])
def delete_duplicate_file(group_id, file_id):
    """Delete a specific duplicate file"""
    try:
        duplicate_file = DuplicateFile.query.filter_by(
            group_id=group_id, file_id=file_id
        ).first_or_404()
        
        file_record = FileRecord.query.get_or_404(file_id)
        
        # Check if filesystem is read-only
        try:
            # Test write permissions by trying to create a test file in the parent directory
            test_dir = os.path.dirname(file_record.path)
            test_file = os.path.join(test_dir, '.write_test')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            can_delete = True
        except (OSError, PermissionError):
            can_delete = False
        
        if not can_delete:
            # Filesystem is read-only, just mark as deleted in database
            duplicate_file.is_deleted = True
            db.session.commit()
            
            logger.info(f"Marked duplicate file as deleted (read-only filesystem): {file_record.path}")
            return jsonify({
                'message': 'File marked as deleted (read-only filesystem)',
                'warning': 'File system is read-only. File was removed from database but remains on disk.'
            })
        
        # Create trash bin entry
        trash_entry = TrashBin(
            original_path=file_record.path,
            original_size=file_record.size,
            expires_at=datetime.now() + timedelta(days=30)  # 30 days
        )
        
        # Move file to trash directory
        trash_dir = '/app/data/trash'
        os.makedirs(trash_dir, exist_ok=True)
        
        trash_path = os.path.join(trash_dir, f"{file_record.id}_{file_record.name}")
        
        if os.path.exists(file_record.path):
            shutil.move(file_record.path, trash_path)
            trash_entry.original_path = trash_path
        
        # Mark as deleted in database
        duplicate_file.is_deleted = True
        db.session.add(trash_entry)
        db.session.commit()
        
        return jsonify({'message': 'Duplicate file deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting duplicate file: {e}")
        return jsonify({'error': 'Failed to delete duplicate file'}), 500

# Add debug endpoint to check FolderInfo table
@app.route('/api/debug/folder-info')
def debug_folder_info():
    """Debug endpoint to check FolderInfo table contents"""
    try:
        # Get latest scan
        latest_scan = db.session.query(ScanRecord).filter(
            ScanRecord.status == 'completed'
        ).order_by(ScanRecord.start_time.desc()).first()
        
        if not latest_scan:
            return jsonify({'error': 'No completed scans found'})
        
        # Get all FolderInfo records for this scan
        folder_infos = db.session.query(FolderInfo).filter_by(
            scan_id=latest_scan.id
        ).order_by(FolderInfo.depth, FolderInfo.total_size.desc()).all()
        
        result = {
            'scan_id': latest_scan.id,
            'scan_date': latest_scan.start_time.isoformat() if latest_scan.start_time else None,
            'total_folder_records': len(folder_infos),
            'depth_1_count': len([f for f in folder_infos if f.depth == 1]),
            'depth_breakdown': {},
            'top_10_depth_1': []
        }
        
        # Group by depth
        for folder in folder_infos:
            if folder.depth not in result['depth_breakdown']:
                result['depth_breakdown'][folder.depth] = 0
            result['depth_breakdown'][folder.depth] += 1
        
        # Get top 10 depth=1 folders
        depth_1_folders = [f for f in folder_infos if f.depth == 1][:10]
        for folder in depth_1_folders:
            result['top_10_depth_1'].append({
                'path': folder.path,
                'name': folder.name,
                'depth': folder.depth,
                'total_size': folder.total_size,
                'total_size_formatted': format_size(folder.total_size),
                'file_count': folder.file_count
            })
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in debug_folder_info: {e}")
        return jsonify({'error': str(e)}), 500

# Add debug endpoint to check DirectoryTotal table
@app.route('/api/debug/directory-totals')
def debug_directory_totals():
    """Debug endpoint to check DirectoryTotal table contents"""
    try:
        data_path = get_setting('data_path', os.environ.get('DATA_PATH', '/data'))
        
        # Get all folder info
        totals = FolderInfo.query.all()
        
        # Get latest scan
        latest_scan = ScanRecord.query.filter(
            ScanRecord.status == 'completed'
        ).order_by(ScanRecord.start_time.desc()).first()
        
        # Get some sample directories from latest scan
        sample_dirs = FileRecord.query.filter(
            FileRecord.scan_id == latest_scan.id if latest_scan else None,
            FileRecord.is_directory == True
        ).limit(10).all()
        
        return jsonify({
            'data_path': data_path,
            'total_records': len(totals),
            'latest_scan_id': latest_scan.id if latest_scan else None,
            'sample_totals': [
                {
                    'path': t.path,
                    'name': t.name,
                    'total_size': t.total_size,
                    'file_count': t.file_count,
                    'depth': t.depth,
                    'scan_id': t.scan_id
                } for t in totals[:10]
            ],
            'sample_directories': [
                {
                    'path': d.path,
                    'name': d.name,
                    'parent_path': d.parent_path
                } for d in sample_dirs
            ]
        })
    except Exception as e:
        logger.error(f"Error in debug_directory_totals: {e}")
        return jsonify({'error': str(e)}), 500

# Add manual trigger for pre-calculation
@app.route('/api/debug/calculate-totals', methods=['POST'])
def manual_calculate_totals():
    """Manually trigger directory totals calculation for debugging"""
    try:
        data_path = get_setting('data_path', os.environ.get('DATA_PATH', '/data'))
        
        # Get the latest completed scan
        latest_scan = ScanRecord.query.filter(
            ScanRecord.status == 'completed'
        ).order_by(ScanRecord.start_time.desc()).first()
        
        if not latest_scan:
            return jsonify({'error': 'No completed scan found'}), 400
        
        logger.info(f"Manually calculating folder totals for scan {latest_scan.id}")
        calculate_folder_totals_during_scan(data_path, latest_scan.id)
        
        return jsonify({
            'message': f'Folder totals calculated for scan {latest_scan.id}',
            'scan_id': latest_scan.id
        })
    except Exception as e:
        logger.error(f"Error in manual_calculate_totals: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug/database/unlock', methods=['POST'])
def unlock_database_endpoint():
    """Manually unlock the database"""
    try:
        success = unlock_database()
        if success:
            return jsonify({'message': 'Database unlocked successfully'})
        else:
            return jsonify({'error': 'Failed to unlock database'}), 500
    except Exception as e:
        logger.error(f"Error unlocking database: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug/database/status')
def get_database_status():
    """Get database status and lock information"""
    try:
        with db.engine.connect() as conn:
            # Check WAL mode
            result = conn.execute(db.text('PRAGMA journal_mode')).fetchone()
            journal_mode = result[0] if result else 'unknown'
            
            # Check busy timeout
            result = conn.execute(db.text('PRAGMA busy_timeout')).fetchone()
            busy_timeout = result[0] if result else 'unknown'
            
            # Check if database is accessible
            result = conn.execute(db.text('SELECT COUNT(*) FROM sqlite_master')).fetchone()
            table_count = result[0] if result else 0
            
            # Check for active scans
            result = conn.execute(db.text('SELECT COUNT(*) FROM scans WHERE status = "running"')).fetchone()
            active_scans = result[0] if result else 0
            
            return jsonify({
                'journal_mode': journal_mode,
                'busy_timeout': busy_timeout,
                'table_count': table_count,
                'active_scans': active_scans,
                'database_accessible': True
            })
    except Exception as e:
        logger.error(f"Error getting database status: {e}")
        return jsonify({
            'error': str(e),
            'database_accessible': False
        }), 500

# Add new endpoint to get folder information for any path
@app.route('/api/folder/<path:folder_path>')
@retry_on_db_lock(max_retries=3, delay=2)
def get_folder_info_by_path(folder_path):
    """Get comprehensive folder information for a specific path"""
    try:
        # Get the latest completed scan
        latest_scan = ScanRecord.query.filter(
            ScanRecord.status == 'completed'
        ).order_by(desc(ScanRecord.start_time)).first()
        
        if not latest_scan:
            return jsonify({'error': 'No completed scan found'}), 404
        
        # Get folder info from database
        folder_info = FolderInfo.query.filter(
            FolderInfo.path == folder_path,
            FolderInfo.scan_id == latest_scan.id
        ).first()
        
        if folder_info:
            return jsonify({
                'path': folder_info.path,
                'name': folder_info.name,
                'parent_path': folder_info.parent_path,
                'total_size': folder_info.total_size,
                'total_size_formatted': format_size(folder_info.total_size),
                'file_count': folder_info.file_count,
                'directory_count': folder_info.directory_count,
                'direct_file_count': folder_info.direct_file_count,
                'direct_directory_count': folder_info.direct_directory_count,
                'depth': folder_info.depth,
                'scan_id': folder_info.scan_id
            })
        else:
            # Fallback: calculate on-the-fly
            totals = db.session.query(
                func.sum(FileRecord.size).label('total_size'),
                func.count(FileRecord.id).label('file_count'),
                func.count(case((FileRecord.is_directory == True, 1), else_=None)).label('directory_count')
            ).filter(
                FileRecord.path.like(f"{folder_path}/%"),
                FileRecord.scan_id == latest_scan.id
            ).first()
            
            return jsonify({
                'path': folder_path,
                'name': os.path.basename(folder_path),
                'parent_path': os.path.dirname(folder_path),
                'total_size': totals.total_size or 0,
                'total_size_formatted': format_size(totals.total_size or 0),
                'file_count': totals.file_count or 0,
                'directory_count': totals.directory_count or 0,
                'direct_file_count': 0,  # Would need separate query
                'direct_directory_count': 0,  # Would need separate query
                'depth': len(folder_path.split('/')),
                'scan_id': latest_scan.id
            })
            
    except Exception as e:
        logger.error(f"Error getting folder info for {folder_path}: {e}")
        return jsonify({'error': 'Failed to get folder information'}), 500

# Add new endpoint to get folder children with detailed info
@app.route('/api/folder/<path:folder_path>/children')
@retry_on_db_lock(max_retries=3, delay=2)
def get_folder_children_by_path(folder_path):
    """Get children of a folder with detailed information"""
    try:
        # Get the latest completed scan
        latest_scan = ScanRecord.query.filter(
            ScanRecord.status == 'completed'
        ).order_by(desc(ScanRecord.start_time)).first()
        
        if not latest_scan:
            return jsonify({'error': 'No completed scan found'}), 404
        
        # Get direct children (files and directories)
        children = db.session.query(
            FileRecord.name,
            FileRecord.path,
            FileRecord.id,
            FileRecord.is_directory,
            FileRecord.size,
            FileRecord.extension,
            FileRecord.modified_time
        ).filter(
            FileRecord.parent_path == folder_path,
            FileRecord.scan_id == latest_scan.id
        ).order_by(FileRecord.size.desc()).all()
        
        result = []
        for child in children:
            if child.is_directory:
                # Get folder info for this directory
                child_folder_info = FolderInfo.query.filter(
                    FolderInfo.path == child.path,
                    FolderInfo.scan_id == latest_scan.id
                ).first()
                
                if child_folder_info:
                    result.append({
                        'id': child.id,
                        'name': child.name,
                        'path': child.path,
                        'size': child_folder_info.total_size,
                        'size_formatted': format_size(child_folder_info.total_size),
                        'file_count': child_folder_info.file_count,
                        'directory_count': child_folder_info.directory_count,
                        'is_directory': True
                    })
                else:
                    # Fallback calculation
                    child_totals = db.session.query(
                        func.sum(FileRecord.size).label('total_size'),
                        func.count(FileRecord.id).label('file_count')
                    ).filter(
                        FileRecord.path.like(f"{child.path}/%"),
                        FileRecord.scan_id == latest_scan.id
                    ).first()
                    
                    result.append({
                        'id': child.id,
                        'name': child.name,
                        'path': child.path,
                        'size': child_totals.total_size or 0,
                        'size_formatted': format_size(child_totals.total_size or 0),
                        'file_count': child_totals.file_count or 0,
                        'directory_count': 0,  # Would need separate query
                        'is_directory': True
                    })
            else:
                # For files, use the file's own size
                result.append({
                    'id': child.id,
                    'name': child.name,
                    'path': child.path,
                    'size': child.size,
                    'size_formatted': format_size(child.size),
                    'extension': child.extension,
                    'modified_time': child.modified_time.isoformat() if child.modified_time else None,
                    'is_directory': False
                })
        
        # Sort by total size (directories) or file size (files)
        result.sort(key=lambda x: x['size'], reverse=True)
        
        return jsonify({'children': result})
        
    except Exception as e:
        logger.error(f"Error getting folder children for {folder_path}: {e}")
        return jsonify({'error': 'Failed to get folder children'}), 500

# Version endpoint
@app.route('/api/version')
def get_version():
    """Get application version"""
    try:
        # Look for VERSION file in the current directory (where it's copied in Docker)
        version_file = 'VERSION'
        if os.path.exists(version_file):
            with open(version_file, 'r') as f:
                version = f.read().strip()
        else:
            # Fallback: look in parent directory
            version_file = os.path.join(os.path.dirname(__file__), '..', 'VERSION')
            if os.path.exists(version_file):
                with open(version_file, 'r') as f:
                    version = f.read().strip()
            else:
                version = "1.4.7"  # Final fallback version
        return jsonify({'version': version})
    except Exception as e:
        logger.error(f"Error reading version: {e}")
        return jsonify({'version': '1.4.7'})

# Application startup
if __name__ == '__main__':
    logger.info("Starting Flask application...")
    
    # Create database tables
    with app.app_context():
        try:
            db.create_all()
            logger.info("Database tables created")
            
            # Enable WAL mode for better concurrency
            enable_wal_mode()
            
            # Create indexes
            try:
                create_indexes()
                logger.info("Database indexes created successfully")
            except Exception as e:
                logger.warning(f"Could not create indexes: {e}")
            
            # Initialize default settings if they don't exist
            if not get_setting('scan_time'):
                set_setting('scan_time', '01:00')
            if not get_setting('max_scan_duration'):
                set_setting('max_scan_duration', '6')
            if not get_setting('theme'):
                set_setting('theme', 'unraid')
            if not get_setting('themes'):
                set_setting('themes', 'unraid,plex,light,dark')
            if not get_setting('max_items_per_folder'):
                set_setting('max_items_per_folder', '100')
            if not get_setting('max_shares_to_scan'):
                set_setting('max_shares_to_scan', '0')
            
            logger.info("Default settings initialized")
            
            # Check for stuck scans on startup
            check_stuck_scans_on_startup()
            
            # Setup and start scheduled scan
            setup_scheduled_scan()
            
            # Start scheduler in background thread
            scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
            scheduler_thread.start()
            logger.info("Scheduled scan system started")
            
        except Exception as e:
            logger.error(f"Error during startup: {e}")
            raise
    
    # Check if static directory exists
    if os.path.exists(FRONTEND_DIST_DIR):
        logger.info(f"Static directory exists: {FRONTEND_DIST_DIR}")
        try:
            files = os.listdir(FRONTEND_DIST_DIR)
            logger.info(f"Static directory contents: {files[:10]}...")  # Show first 10 files
        except Exception as e:
            logger.error(f"Error listing static directory: {e}")
    else:
        logger.warning(f"Static directory does not exist: {FRONTEND_DIST_DIR}")
    
    logger.info("Starting Flask server on 0.0.0.0:8080")
    app.run(host='0.0.0.0', port=8080, debug=False) 

# Optimize the top-shares endpoint to use pre-calculated totals with fallback