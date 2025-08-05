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

# Import models
from models import FileRecord, ScanRecord, MediaFile, DuplicateGroup, DuplicateFile, StorageHistory, TrashBin

# Create database tables within application context
with app.app_context():
    # Register models with SQLAlchemy
    db.Model = FileRecord.__bases__[0]
    FileRecord.__table__.create(db.engine, checkfirst=True)
    ScanRecord.__table__.create(db.engine, checkfirst=True)
    MediaFile.__table__.create(db.engine, checkfirst=True)
    DuplicateGroup.__table__.create(db.engine, checkfirst=True)
    DuplicateFile.__table__.create(db.engine, checkfirst=True)
    StorageHistory.__table__.create(db.engine, checkfirst=True)
    TrashBin.__table__.create(db.engine, checkfirst=True)
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