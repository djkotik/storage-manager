import os
import hashlib
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re
from mutagen import File as MutagenFile
from mutagen.mp4 import MP4
from mutagen.avi import AVI
from mutagen.asf import ASF
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.oggvorbis import OggVorbis

from app import db
from models import FileRecord, ScanRecord, MediaFile, StorageHistory

logger = logging.getLogger(__name__)

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
        scan_thread = threading.Thread(target=self._scan_filesystem)
        scan_thread.daemon = True
        scan_thread.start()
        
        logger.info(f"Started scan session {self.current_scan.id}")
        return self.current_scan.id

    def stop_current_scan(self):
        """Stop the current scan"""
        self.stop_scan = True
        logger.info("Scan stop requested")

    def get_scan_status(self) -> Dict:
        """Get current scan status"""
        if not self.current_scan:
            return {'status': 'idle'}
            
        return {
            'scan_id': self.current_scan.id,
            'status': self.current_scan.status,
            'start_time': self.current_scan.start_time.isoformat(),
            'end_time': self.current_scan.end_time.isoformat() if self.current_scan.end_time else None,
            'total_files': self.current_scan.total_files,
            'total_directories': self.current_scan.total_directories,
            'total_size': self.current_scan.total_size,
            'scanning': self.scanning
        }

    def _scan_filesystem(self):
        """Main scanning method"""
        try:
            logger.info(f"Starting filesystem scan of {self.data_path}")
            
            total_files = 0
            total_directories = 0
            total_size = 0
            
            # Get max shares to scan setting
            max_shares_to_scan = int(get_setting('max_shares_to_scan', '0'))
            shares_scanned = 0
            
            # Clear old file records for this scan
            FileRecord.query.filter_by(scan_id=self.current_scan.id).delete()
            
            for root, dirs, files in os.walk(self.data_path):
                if self.stop_scan:
                    logger.info("Scan stopped by user request")
                    break
                    
                # Check if we've exceeded max duration
                if time.time() - self.scan_start_time > self.max_duration:
                    logger.warning("Scan stopped due to max duration limit")
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
                        
                        # Extract media metadata if it's a media file
                        if extension in self.video_extensions or extension in self.audio_extensions:
                            self._extract_media_metadata(file_record, file_path)
                        
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Error accessing file {file_path}: {e}")
                
                # Commit in batches
                if total_files % 1000 == 0:
                    db.session.commit()
                    logger.info(f"Processed {total_files} files, {total_directories} directories")
            
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
            if self.current_scan:
                self.current_scan.status = 'failed'
                self.current_scan.error_message = str(e)
                self.current_scan.end_time = datetime.utcnow()
                db.session.commit()
        finally:
            self.scanning = False

    def _extract_media_metadata(self, file_record: FileRecord, file_path: Path):
        """Extract metadata from media files"""
        try:
            # Try to extract metadata using mutagen
            media_file = MutagenFile(str(file_path))
            if not media_file:
                return
                
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
            if hasattr(media_file, 'info') and hasattr(media_file.info, 'length'):
                runtime = int(media_file.info.length / 60)  # Convert to minutes
            
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