import os
import shutil
import logging
from datetime import datetime, timedelta
from flask import jsonify, request, send_file
from sqlalchemy import func, desc
from app import app, db
from models import FileRecord, ScanRecord, MediaFile, DuplicateGroup, DuplicateFile, StorageHistory, TrashBin
from scanner import FileScanner

logger = logging.getLogger(__name__)

# Initialize scanner
scanner = FileScanner(
    data_path=os.environ.get('DATA_PATH', '/data'),
    max_duration=int(os.environ.get('MAX_SCAN_DURATION', 6))
)

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

def get_directory_size(path):
    """Calculate total size of a directory"""
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
    except (OSError, PermissionError):
        pass
    return total_size

# API Routes

@app.route('/api/scan/start', methods=['POST'])
def start_scan():
    """Start a new scan"""
    try:
        scan_id = scanner.start_scan()
        if scan_id:
            return jsonify({
                'message': 'Scan started successfully',
                'scan_id': scan_id
            })
        else:
            return jsonify({'error': 'Scan already in progress'}), 400
    except Exception as e:
        logger.error(f"Error starting scan: {e}")
        return jsonify({'error': 'Failed to start scan'}), 500

@app.route('/api/scan/stop', methods=['POST'])
def stop_scan():
    """Stop the current scan"""
    try:
        scanner.stop_current_scan()
        return jsonify({'message': 'Scan stop requested'})
    except Exception as e:
        logger.error(f"Error stopping scan: {e}")
        return jsonify({'error': 'Failed to stop scan'}), 500

@app.route('/api/scan/status')
def get_scan_status():
    """Get current scan status"""
    try:
        return jsonify(scanner.get_scan_status())
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
                'total_size_formatted': format_size(scan.total_size) if scan.total_size else None,
                'error_message': scan.error_message
            } for scan in scans.items],
            'total': scans.total,
            'pages': scans.pages,
            'current_page': page
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
        path = request.args.get('path', '')
        search = request.args.get('search', '')
        extension = request.args.get('extension', '')
        min_size = request.args.get('min_size', 0, type=int)
        max_size = request.args.get('max_size', type=int)
        sort_by = request.args.get('sort_by', 'size')
        sort_order = request.args.get('sort_order', 'desc')
        
        query = FileRecord.query
        
        # Apply filters
        if path:
            query = query.filter(FileRecord.path.like(f"{path}%"))
        if search:
            query = query.filter(FileRecord.name.like(f"%{search}%"))
        if extension:
            query = query.filter(FileRecord.extension == extension)
        if min_size > 0:
            query = query.filter(FileRecord.size >= min_size)
        if max_size:
            query = query.filter(FileRecord.size <= max_size)
        
        # Apply sorting
        if sort_by == 'size':
            order_col = FileRecord.size
        elif sort_by == 'name':
            order_col = FileRecord.name
        elif sort_by == 'modified':
            order_col = FileRecord.modified_time
        else:
            order_col = FileRecord.size
        
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
            'current_page': page
        })
    except Exception as e:
        logger.error(f"Error getting files: {e}")
        return jsonify({'error': 'Failed to get files'}), 500

@app.route('/api/files/tree')
def get_file_tree():
    """Get file tree structure"""
    try:
        path = request.args.get('path', '/data')
        max_depth = request.args.get('max_depth', 3, type=int)
        
        # Get all files and directories under the path
        files = FileRecord.query.filter(
            FileRecord.path.like(f"{path}%")
        ).all()
        
        # Build tree structure
        tree = {}
        for file in files:
            if file.path == path:
                continue
                
            rel_path = file.path[len(path):].lstrip('/')
            parts = rel_path.split('/')
            
            if len(parts) <= max_depth:
                current = tree
                for i, part in enumerate(parts[:-1]):
                    if part not in current:
                        current[part] = {'type': 'directory', 'children': {}}
                    current = current[part]['children']
                
                if parts[-1] not in current:
                    current[parts[-1]] = {
                        'type': 'directory' if file.is_directory else 'file',
                        'size': file.size,
                        'size_formatted': format_size(file.size),
                        'modified_time': file.modified_time.isoformat() if file.modified_time else None
                    }
        
        return jsonify(tree)
    except Exception as e:
        logger.error(f"Error getting file tree: {e}")
        return jsonify({'error': 'Failed to get file tree'}), 500

@app.route('/api/analytics/overview')
def get_analytics_overview():
    """Get storage analytics overview"""
    try:
        # Get latest scan
        latest_scan = ScanRecord.query.filter_by(status='completed').order_by(desc(ScanRecord.end_time)).first()
        
        if not latest_scan:
            return jsonify({'error': 'No completed scans found'}), 404
        
        # Get file type statistics
        file_types = db.session.query(
            FileRecord.extension,
            func.count(FileRecord.id).label('count'),
            func.sum(FileRecord.size).label('total_size')
        ).filter(
            FileRecord.extension.isnot(None),
            FileRecord.is_directory == False
        ).group_by(FileRecord.extension).order_by(desc(func.sum(FileRecord.size))).limit(10).all()
        
        # Get media statistics
        media_stats = db.session.query(
            MediaFile.media_type,
            func.count(MediaFile.id).label('count'),
            func.sum(FileRecord.size).label('total_size')
        ).join(FileRecord).group_by(MediaFile.media_type).all()
        
        return jsonify({
            'latest_scan': {
                'id': latest_scan.id,
                'end_time': latest_scan.end_time.isoformat(),
                'total_files': latest_scan.total_files,
                'total_directories': latest_scan.total_directories,
                'total_size': latest_scan.total_size,
                'total_size_formatted': format_size(latest_scan.total_size)
            },
            'file_types': [{
                'extension': ft.extension,
                'count': ft.count,
                'total_size': ft.total_size,
                'total_size_formatted': format_size(ft.total_size)
            } for ft in file_types],
            'media_stats': [{
                'type': ms.media_type,
                'count': ms.count,
                'total_size': ms.total_size,
                'total_size_formatted': format_size(ms.total_size)
            } for ms in media_stats]
        })
    except Exception as e:
        logger.error(f"Error getting analytics overview: {e}")
        return jsonify({'error': 'Failed to get analytics overview'}), 500

@app.route('/api/analytics/history')
def get_storage_history():
    """Get storage usage history"""
    try:
        days = request.args.get('days', 30, type=int)
        start_date = datetime.utcnow() - timedelta(days=days)
        
        history = StorageHistory.query.filter(
            StorageHistory.date >= start_date
        ).order_by(StorageHistory.date).all()
        
        return jsonify({
            'history': [{
                'date': h.date.isoformat(),
                'total_size': h.total_size,
                'total_size_formatted': format_size(h.total_size),
                'file_count': h.file_count,
                'directory_count': h.directory_count
            } for h in history]
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
        title = request.args.get('title', '')
        resolution = request.args.get('resolution', '')
        
        query = MediaFile.query.join(FileRecord)
        
        # Apply filters
        if media_type:
            query = query.filter(MediaFile.media_type == media_type)
        if title:
            query = query.filter(MediaFile.title.like(f"%{title}%"))
        if resolution:
            query = query.filter(MediaFile.resolution == resolution)
        
        media_files = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            'media_files': [{
                'id': mf.id,
                'file_id': mf.file_id,
                'path': mf.file.path,
                'name': mf.file.name,
                'size': mf.file.size,
                'size_formatted': format_size(mf.file.size),
                'media_type': mf.media_type,
                'title': mf.title,
                'year': mf.year,
                'season': mf.season,
                'episode': mf.episode,
                'resolution': mf.resolution,
                'video_codec': mf.video_codec,
                'audio_codec': mf.audio_codec,
                'runtime': mf.runtime,
                'file_format': mf.file_format
            } for mf in media_files.items],
            'total': media_files.total,
            'pages': media_files.pages,
            'current_page': page
        })
    except Exception as e:
        logger.error(f"Error getting media files: {e}")
        return jsonify({'error': 'Failed to get media files'}), 500

@app.route('/api/files/<int:file_id>', methods=['DELETE'])
def delete_file(file_id):
    """Delete a file or directory"""
    try:
        file_record = FileRecord.query.get_or_404(file_id)
        
        # Check if file exists
        if not os.path.exists(file_record.path):
            return jsonify({'error': 'File not found on disk'}), 404
        
        # Move to trash bin instead of permanent deletion
        trash_path = f"/app/data/trash/{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{file_record.name}"
        
        try:
            # Create trash directory if it doesn't exist
            os.makedirs(os.path.dirname(trash_path), exist_ok=True)
            
            # Move file to trash
            shutil.move(file_record.path, trash_path)
            
            # Record in trash bin
            trash_record = TrashBin(
                original_path=file_record.path,
                original_size=file_record.size,
                expires_at=datetime.utcnow() + timedelta(hours=48)
            )
            db.session.add(trash_record)
            
            # Mark file as deleted
            file_record.path = trash_path
            db.session.commit()
            
            return jsonify({'message': 'File moved to trash bin'})
            
        except Exception as e:
            logger.error(f"Error moving file to trash: {e}")
            return jsonify({'error': 'Failed to delete file'}), 500
            
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        return jsonify({'error': 'Failed to delete file'}), 500

@app.route('/api/trash')
def get_trash_bin():
    """Get trash bin contents"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        trash_items = TrashBin.query.filter_by(restored=False).order_by(desc(TrashBin.deleted_time)).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            'items': [{
                'id': item.id,
                'original_path': item.original_path,
                'original_size': item.original_size,
                'original_size_formatted': format_size(item.original_size),
                'deleted_time': item.deleted_time.isoformat(),
                'expires_at': item.expires_at.isoformat() if item.expires_at else None
            } for item in trash_items.items],
            'total': trash_items.total,
            'pages': trash_items.pages,
            'current_page': page
        })
    except Exception as e:
        logger.error(f"Error getting trash bin: {e}")
        return jsonify({'error': 'Failed to get trash bin'}), 500

@app.route('/api/trash/<int:item_id>/restore', methods=['POST'])
def restore_file(item_id):
    """Restore a file from trash"""
    try:
        trash_item = TrashBin.query.get_or_404(item_id)
        
        if trash_item.restored:
            return jsonify({'error': 'File already restored'}), 400
        
        # Check if original location is available
        if os.path.exists(trash_item.original_path):
            return jsonify({'error': 'Original location is occupied'}), 400
        
        # Restore file
        try:
            shutil.move(trash_item.original_path, trash_item.original_path)
            trash_item.restored = True
            db.session.commit()
            return jsonify({'message': 'File restored successfully'})
        except Exception as e:
            logger.error(f"Error restoring file: {e}")
            return jsonify({'error': 'Failed to restore file'}), 500
            
    except Exception as e:
        logger.error(f"Error restoring file: {e}")
        return jsonify({'error': 'Failed to restore file'}), 500 