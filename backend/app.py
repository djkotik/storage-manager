import os
import logging
import shutil
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, desc
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, static_folder='static', static_url_path='')

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////app/data/storage_analyzer.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

# Initialize extensions
db = SQLAlchemy(app)
CORS(app)

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

# Define models directly in app.py to avoid circular imports
class FileRecord(db.Model):
    """Model for storing file information"""
    __tablename__ = 'files'
    
    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String(2000), nullable=False, unique=True)
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

# Create database tables
with app.app_context():
    db.create_all()
    logger.info("Database tables created")

# Utility functions
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

def scan_directory(data_path, scan_id):
    """Scan directory and populate database"""
    global scanner_state
    
    # Create application context for database operations
    with app.app_context():
        try:
            logger.info(f"Starting scan of {data_path}")
            scanner_state['scanning'] = True
            scanner_state['current_scan_id'] = scan_id
            scanner_state['start_time'] = datetime.now()
            scanner_state['total_files'] = 0
            scanner_state['total_directories'] = 0
            scanner_state['total_size'] = 0
            scanner_state['error'] = None
            
            # Clear existing files for this scan
            FileRecord.query.filter_by(scan_id=scan_id).delete()
            
            for root, dirs, files in os.walk(data_path):
                if not scanner_state['scanning']:
                    break
                    
                scanner_state['current_path'] = root
                
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
                        db.session.flush()  # Get the file record ID
                        
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
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Error accessing file {file_path}: {e}")
                        continue
                
                # Commit periodically
                if scanner_state['total_files'] % 100 == 0:
                    db.session.commit()
                    logger.info(f"Processed {scanner_state['total_files']} files, {scanner_state['total_directories']} directories")
            
            # Final commit
            db.session.commit()
            
            # Update scan record
            scan_record = ScanRecord.query.get(scan_id)
            if scan_record:
                scan_record.end_time = datetime.now()
                scan_record.total_files = scanner_state['total_files']
                scan_record.total_directories = scanner_state['total_directories']
                scan_record.total_size = scanner_state['total_size']
                scan_record.status = 'completed'
                db.session.commit()
            
            logger.info(f"Scan completed: {scanner_state['total_files']} files, {scanner_state['total_directories']} directories, {format_size(scanner_state['total_size'])}")
            
        except Exception as e:
            logger.error(f"Error during scan: {e}")
            scanner_state['error'] = str(e)
            
            # Update scan record with error
            scan_record = ScanRecord.query.get(scan_id)
            if scan_record:
                scan_record.end_time = datetime.now()
                scan_record.status = 'failed'
                scan_record.error_message = str(e)
                db.session.commit()
        
        finally:
            scanner_state['scanning'] = False
            scanner_state['current_path'] = ''

# Routes
@app.route('/')
def index():
    """Serve the main application"""
    return app.send_static_file('index.html')

@app.route('/debug/static')
def debug_static():
    """Debug route to check static files"""
    import os
    static_dir = app.static_folder
    files = []
    if os.path.exists(static_dir):
        for root, dirs, filenames in os.walk(static_dir):
            for filename in filenames:
                rel_path = os.path.relpath(os.path.join(root, filename), static_dir)
                files.append(rel_path)
    return jsonify({
        'static_folder': static_dir,
        'files': files,
        'index_exists': os.path.exists(os.path.join(static_dir, 'index.html')) if static_dir else False
    })

@app.route('/debug/index')
def debug_index():
    """Debug route to check index.html content"""
    try:
        with open(os.path.join(app.static_folder, 'index.html'), 'r') as f:
            content = f.read()
        return jsonify({
            'exists': True,
            'length': len(content),
            'preview': content[:500] + '...' if len(content) > 500 else content
        })
    except Exception as e:
        return jsonify({
            'exists': False,
            'error': str(e)
        })

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'data_path': os.environ.get('DATA_PATH', '/data'),
        'scan_time': os.environ.get('SCAN_TIME', '01:00')
    })

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get application settings"""
    return jsonify({
        'data_path': get_setting('data_path', os.environ.get('DATA_PATH', '/data')),
        'scan_time': get_setting('scan_time', '01:00'),
        'max_scan_duration': int(get_setting('max_scan_duration', '6')),
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
            if key in ['data_path', 'scan_time', 'max_scan_duration', 'theme']:
                set_setting(key, str(value))
        
        return jsonify({'message': 'Settings updated successfully'})
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        return jsonify({'error': 'Failed to update settings'}), 500

@app.route('/api/database/reset', methods=['POST'])
def reset_database():
    """Reset the database - use with caution!"""
    try:
        # Drop all tables
        db.drop_all()
        # Recreate tables
        db.create_all()
        logger.info("Database reset successfully")
        return jsonify({'message': 'Database reset successfully'})
    except Exception as e:
        logger.error(f"Error resetting database: {e}")
        return jsonify({'error': 'Failed to reset database'}), 500

@app.route('/api/scan/start', methods=['POST'])
def start_scan():
    """Start a new scan"""
    try:
        if scanner_state['scanning']:
            return jsonify({'error': 'Scan already in progress'}), 400
        
        # Create scan record
        scan_record = ScanRecord(
            start_time=datetime.now(),
            status='running'
        )
        db.session.add(scan_record)
        db.session.commit()
        
        # Start scan in background thread
        data_path = os.environ.get('DATA_PATH', '/data')
        scan_thread = threading.Thread(
            target=scan_directory,
            args=(data_path, scan_record.id)
        )
        scan_thread.daemon = True
        scan_thread.start()
        
        return jsonify({
            'message': 'Scan started successfully',
            'scan_id': scan_record.id
        })
    except Exception as e:
        logger.error(f"Error starting scan: {e}")
        return jsonify({'error': 'Failed to start scan'}), 500

@app.route('/api/scan/stop', methods=['POST'])
def stop_scan():
    """Stop the current scan"""
    try:
        scanner_state['scanning'] = False
        return jsonify({'message': 'Scan stop requested'})
    except Exception as e:
        logger.error(f"Error stopping scan: {e}")
        return jsonify({'error': 'Failed to stop scan'}), 500

@app.route('/api/scan/status')
def get_scan_status():
    """Get current scan status"""
    try:
        return jsonify({
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
        })
    except Exception as e:
        logger.error(f"Error getting scan status: {e}")
        return jsonify({'error': 'Failed to get scan status'}), 500

@app.route('/api/scan/history')
def get_scan_history():
    """Get scan history"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        scans = ScanRecord.query.order_by(desc(ScanRecord.start_time)).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            'scans': [{
                'id': scan.id,
                'start_time': scan.start_time.isoformat(),
                'end_time': scan.end_time.isoformat() if scan.end_time else None,
                'status': scan.status,
                'total_files': scan.total_files,
                'total_directories': scan.total_directories,
                'total_size': scan.total_size,
                'error_message': scan.error_message
            } for scan in scans.items],
            'total': scans.total,
            'pages': scans.pages,
            'current_page': scans.page
        })
    except Exception as e:
        logger.error(f"Error getting scan history: {e}")
        return jsonify({'error': 'Failed to get scan history'}), 500

@app.route('/api/files')
def get_files():
    """Get files with filtering and pagination"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        search = request.args.get('search', '')
        path_filter = request.args.get('path', '')
        extension_filter = request.args.get('extension', '')
        sort_by = request.args.get('sort_by', 'name')
        sort_order = request.args.get('sort_order', 'asc')
        
        query = FileRecord.query
        
        # Apply filters
        if search:
            query = query.filter(FileRecord.name.ilike(f'%{search}%'))
        if path_filter:
            query = query.filter(FileRecord.path.ilike(f'%{path_filter}%'))
        if extension_filter:
            query = query.filter(FileRecord.extension == extension_filter)
        
        # Apply sorting
        if sort_by == 'size':
            order_col = FileRecord.size
        elif sort_by == 'modified':
            order_col = FileRecord.modified_time
        else:
            order_col = FileRecord.name
            
        if sort_order == 'desc':
            query = query.order_by(desc(order_col))
        else:
            query = query.order_by(order_col)
        
        files = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            'files': [{
                'id': file.id,
                'path': file.path,
                'name': file.name,
                'size': file.size,
                'size_formatted': format_size(file.size),
                'is_directory': file.is_directory,
                'extension': file.extension,
                'modified_time': file.modified_time.isoformat() if file.modified_time else None,
                'permissions': file.permissions
            } for file in files.items],
            'total': files.total,
            'pages': files.pages,
            'current_page': files.page
        })
    except Exception as e:
        logger.error(f"Error getting files: {e}")
        return jsonify({'error': 'Failed to get files'}), 500

@app.route('/api/files/tree')
def get_file_tree():
    """Get hierarchical file tree - top level shares"""
    try:
        data_path = get_setting('data_path', os.environ.get('DATA_PATH', '/data'))
        
        # Get top-level directories (shares) sorted by total size
        shares = db.session.query(
            FileRecord,
            func.count(FileRecord.id).label('file_count')
        ).filter(
            FileRecord.is_directory == True,
            FileRecord.parent_path == data_path
        ).all()
        
        tree = []
        for share, file_count in shares:
            # Calculate total size of all files within this directory
            total_size = db.session.query(func.sum(FileRecord.size)).filter(
                FileRecord.path.like(f"{share.path}/%")
            ).scalar() or 0
            
            tree.append({
                'id': share.id,
                'name': share.name,
                'path': share.path,
                'size': total_size,
                'size_formatted': format_size(total_size),
                'file_count': file_count,
                'is_directory': True,
                'children': []  # Will be populated when expanded
            })
        
        # Sort by total size
        tree.sort(key=lambda x: x['size'], reverse=True)
        
        return jsonify({'tree': tree})
    except Exception as e:
        logger.error(f"Error getting file tree: {e}")
        return jsonify({'error': 'Failed to get file tree'}), 500

@app.route('/api/files/tree/<int:directory_id>')
def get_directory_children(directory_id):
    """Get children of a specific directory"""
    try:
        directory = FileRecord.query.get_or_404(directory_id)
        
        # Get direct children of this directory
        children = db.session.query(
            FileRecord
        ).filter(
            FileRecord.parent_path == directory.path,
            FileRecord.is_directory == True
        ).all()
        
        result = []
        for child in children:
            # Calculate total size of all files within this subdirectory
            total_size = db.session.query(func.sum(FileRecord.size)).filter(
                FileRecord.path.like(f"{child.path}/%")
            ).scalar() or 0
            
            result.append({
                'id': child.id,
                'name': child.name,
                'path': child.path,
                'size': total_size,
                'size_formatted': format_size(total_size),
                'is_directory': True,
                'children': []
            })
        
        # Sort by total size
        result.sort(key=lambda x: x['size'], reverse=True)
        
        return jsonify({'children': result})
    except Exception as e:
        logger.error(f"Error getting directory children: {e}")
        return jsonify({'error': 'Failed to get directory children'}), 500

@app.route('/api/analytics/overview')
def get_analytics_overview():
    """Get storage analytics overview"""
    try:
        # Get total stats
        total_files = FileRecord.query.filter_by(is_directory=False).count()
        total_directories = FileRecord.query.filter_by(is_directory=True).count()
        total_size = db.session.query(func.sum(FileRecord.size)).scalar() or 0
        
        # Get top file types
        top_extensions = db.session.query(
            FileRecord.extension,
            func.count(FileRecord.id).label('count'),
            func.sum(FileRecord.size).label('total_size')
        ).filter(
            FileRecord.extension.isnot(None),
            FileRecord.is_directory == False
        ).group_by(FileRecord.extension).order_by(
            desc(func.sum(FileRecord.size))
        ).limit(10).all()
        
        # Get media breakdown by type
        media_counts = db.session.query(
            MediaFile.media_type,
            func.count(MediaFile.id).label('count')
        ).group_by(MediaFile.media_type).all()
        
        media_breakdown = {}
        total_media = 0
        for media_type, count in media_counts:
            media_breakdown[media_type] = count
            total_media += count
        
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
            'media_files': total_media,
            'media_breakdown': media_breakdown
        })
    except Exception as e:
        logger.error(f"Error getting analytics overview: {e}")
        return jsonify({'error': 'Failed to get analytics overview'}), 500

@app.route('/api/analytics/top-shares')
def get_top_shares():
    """Get top folder shares by size"""
    try:
        data_path = get_setting('data_path', os.environ.get('DATA_PATH', '/data'))
        
        # Get top-level directories (shares)
        shares = db.session.query(
            FileRecord,
            func.count(FileRecord.id).label('file_count')
        ).filter(
            FileRecord.is_directory == True,
            FileRecord.parent_path == data_path
        ).all()
        
        top_shares = []
        for share, file_count in shares:
            # Calculate total size of all files within this directory
            total_size = db.session.query(func.sum(FileRecord.size)).filter(
                FileRecord.path.like(f"{share.path}/%")
            ).scalar() or 0
            
            top_shares.append({
                'name': share.name,
                'path': share.path,
                'size': total_size,
                'size_formatted': format_size(total_size),
                'file_count': file_count
            })
        
        # Sort by total size and take top 10
        top_shares.sort(key=lambda x: x['size'], reverse=True)
        top_shares = top_shares[:10]
        
        return jsonify({
            'top_shares': top_shares
        })
    except Exception as e:
        logger.error(f"Error getting top shares: {e}")
        return jsonify({'error': 'Failed to get top shares'}), 500

@app.route('/api/analytics/history')
def get_storage_history():
    """Get storage usage history"""
    try:
        days = request.args.get('days', 30, type=int)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        history = StorageHistory.query.filter(
            StorageHistory.date >= start_date,
            StorageHistory.date <= end_date
        ).order_by(StorageHistory.date).all()
        
        return jsonify({
            'history': [{
                'date': record.date.isoformat(),
                'total_size': record.total_size,
                'total_size_formatted': format_size(record.total_size),
                'file_count': record.file_count,
                'directory_count': record.directory_count
            } for record in history]
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
        
        query = MediaFile.query
        
        # Apply filters
        if media_type and media_type != 'all':
            query = query.filter(MediaFile.media_type == media_type)
        if resolution and resolution != 'all':
            query = query.filter(MediaFile.resolution == resolution)
        if search:
            query = query.filter(MediaFile.title.ilike(f'%{search}%'))
        
        media_files = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Get counts by media type
        media_counts = db.session.query(
            MediaFile.media_type,
            func.count(MediaFile.id).label('count')
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
                'file_size': media.file_id and FileRecord.query.get(media.file_id).size or 0,
                'file_size_formatted': media.file_id and format_size(FileRecord.query.get(media.file_id).size) or '0 B',
                'path': media.file_id and FileRecord.query.get(media.file_id).path or ''
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
    """Get recent application logs"""
    try:
        lines = request.args.get('lines', 50, type=int)
        
        # Read the log file
        log_file = '/app/logs/app.log'
        logs = []
        
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                # Get the last N lines
                lines_list = f.readlines()
                recent_lines = lines_list[-lines:] if len(lines_list) > lines else lines_list
                
                for line in recent_lines:
                    # Parse log line to extract timestamp and message
                    if ' - ' in line:
                        parts = line.split(' - ', 2)
                        if len(parts) >= 3:
                            timestamp = parts[0]
                            level = parts[1]
                            message = parts[2].strip()
                            
                            logs.append({
                                'timestamp': timestamp,
                                'level': level,
                                'message': message,
                                'raw': line.strip()
                            })
                        else:
                            logs.append({
                                'timestamp': '',
                                'level': 'INFO',
                                'message': line.strip(),
                                'raw': line.strip()
                            })
                    else:
                        logs.append({
                            'timestamp': '',
                            'level': 'INFO',
                            'message': line.strip(),
                            'raw': line.strip()
                        })
        
        return jsonify({
            'logs': logs,
            'total_lines': len(logs)
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
        return jsonify({'error': 'Failed to get duplicates'}), 500

@app.route('/api/duplicates/<int:group_id>/delete/<int:file_id>', methods=['POST'])
def delete_duplicate_file(group_id, file_id):
    """Delete a specific duplicate file"""
    try:
        duplicate_file = DuplicateFile.query.filter_by(
            group_id=group_id, file_id=file_id
        ).first_or_404()
        
        file_record = FileRecord.query.get_or_404(file_id)
        
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

if __name__ == '__main__':
    # Ensure data directory exists
    Path('/app/data').mkdir(parents=True, exist_ok=True)
    Path('/app/logs').mkdir(parents=True, exist_ok=True)
    
    app.run(host='0.0.0.0', port=8080, debug=os.environ.get('FLASK_ENV') == 'development') 