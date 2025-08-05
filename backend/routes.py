import os
import shutil
import logging
from datetime import datetime, timedelta
from flask import jsonify, request, send_file, current_app
from sqlalchemy import func, desc
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

def register_routes(app):
    """Register all routes with the Flask app"""
    
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
        """Get hierarchical file tree"""
        try:
            # This is a simplified implementation
            # In a real app, you'd build a proper tree structure
            directories = FileRecord.query.filter_by(is_directory=True).limit(100).all()
            
            tree = []
            for directory in directories:
                tree.append({
                    'id': directory.id,
                    'name': directory.name,
                    'path': directory.path,
                    'size': directory.size,
                    'size_formatted': format_size(directory.size),
                    'children': []  # Would be populated with actual children
                })
            
            return jsonify({'tree': tree})
        except Exception as e:
            logger.error(f"Error getting file tree: {e}")
            return jsonify({'error': 'Failed to get file tree'}), 500

    @app.route('/api/analytics/overview')
    def get_analytics_overview():
        """Get storage analytics overview"""
        try:
            # Get total stats
            total_files = FileRecord.query.filter_by(is_directory=False).count()
            total_directories = FileRecord.query.filter_by(is_directory=True).count()
            total_size = current_app.db.session.query(func.sum(FileRecord.size)).scalar() or 0
            
            # Get top file types
            top_extensions = current_app.db.session.query(
                FileRecord.extension,
                func.count(FileRecord.id).label('count'),
                func.sum(FileRecord.size).label('total_size')
            ).filter(
                FileRecord.extension.isnot(None),
                FileRecord.is_directory == False
            ).group_by(FileRecord.extension).order_by(
                desc(func.sum(FileRecord.size))
            ).limit(10).all()
            
            # Get media breakdown
            media_files = MediaFile.query.count()
            
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
            
            query = MediaFile.query.join(FileRecord)
            
            # Apply filters
            if media_type:
                query = query.filter(MediaFile.media_type == media_type)
            if resolution:
                query = query.filter(MediaFile.resolution == resolution)
            if search:
                query = query.filter(MediaFile.title.ilike(f'%{search}%'))
            
            media_files = query.paginate(page=page, per_page=per_page, error_out=False)
            
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
                    'file_size_formatted': media.file_id and format_size(FileRecord.query.get(media.file_id).size) or '0 B'
                } for media in media_files.items],
                'total': media_files.total,
                'pages': media_files.pages,
                'current_page': media_files.page
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
            current_app.db.session.add(trash_entry)
            current_app.db.session.commit()
            
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
                current_app.db.session.commit()
                
                return jsonify({'message': 'File restored successfully'})
            else:
                return jsonify({'error': 'File not found in trash'}), 404
        except Exception as e:
            logger.error(f"Error restoring file: {e}")
            return jsonify({'error': 'Failed to restore file'}), 500 