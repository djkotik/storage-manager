import os
import logging
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
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

# Import routes and register them
from routes import register_routes
register_routes(app)

@app.route('/')
def index():
    """Serve the main application"""
    return app.send_static_file('index.html')

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
        'data_path': os.environ.get('DATA_PATH', '/data'),
        'scan_time': os.environ.get('SCAN_TIME', '01:00'),
        'max_scan_duration': int(os.environ.get('MAX_SCAN_DURATION', 6)),
        'themes': ['unraid', 'plex', 'dark', 'light']
    })

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Update application settings"""
    data = request.get_json()
    # In a real implementation, you'd save these to a config file or database
    return jsonify({'message': 'Settings updated successfully'})

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

if __name__ == '__main__':
    # Ensure data directory exists
    Path('/app/data').mkdir(parents=True, exist_ok=True)
    Path('/app/logs').mkdir(parents=True, exist_ok=True)
    
    app.run(host='0.0.0.0', port=8080, debug=os.environ.get('FLASK_ENV') == 'development') 