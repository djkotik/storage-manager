from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float, Text, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class FileRecord(Base):
    """Model for storing file information"""
    __tablename__ = 'files'
    
    id = Column(Integer, primary_key=True)
    path = Column(String(2000), nullable=False, unique=True)
    name = Column(String(500), nullable=False)
    size = Column(Integer, nullable=False)  # Size in bytes
    is_directory = Column(Boolean, default=False)
    parent_path = Column(String(2000))
    extension = Column(String(50))
    created_time = Column(DateTime)
    modified_time = Column(DateTime)
    accessed_time = Column(DateTime)
    permissions = Column(String(20))
    scan_id = Column(Integer)
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_path', 'path'),
        Index('idx_parent_path', 'parent_path'),
        Index('idx_extension', 'extension'),
        Index('idx_size', 'size'),
        Index('idx_scan_id', 'scan_id'),
    )

class ScanRecord(Base):
    """Model for storing scan sessions"""
    __tablename__ = 'scans'
    
    id = Column(Integer, primary_key=True)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime)
    total_files = Column(Integer, default=0)
    total_directories = Column(Integer, default=0)
    total_size = Column(Integer, default=0)  # Total size in bytes
    status = Column(String(20), default='running')  # running, completed, failed
    error_message = Column(Text)
    
    # Indexes
    __table_args__ = (
        Index('idx_start_time', 'start_time'),
        Index('idx_status', 'status'),
    )

class MediaFile(Base):
    """Model for storing media file metadata"""
    __tablename__ = 'media_files'
    
    id = Column(Integer, primary_key=True)
    file_id = Column(Integer)
    media_type = Column(String(20))  # movie, tv_show, music, other
    title = Column(String(500))
    year = Column(Integer)
    season = Column(Integer)
    episode = Column(Integer)
    episode_title = Column(String(500))
    resolution = Column(String(20))  # 480p, 720p, 1080p, 4K, etc.
    video_codec = Column(String(50))
    audio_codec = Column(String(50))
    audio_channels = Column(String(20))
    runtime = Column(Integer)  # Runtime in minutes
    bitrate = Column(Integer)
    frame_rate = Column(Float)
    file_format = Column(String(20))
    
    # Indexes
    __table_args__ = (
        Index('idx_media_type', 'media_type'),
        Index('idx_title', 'title'),
        Index('idx_year', 'year'),
        Index('idx_resolution', 'resolution'),
    )

class DuplicateGroup(Base):
    """Model for storing duplicate file groups"""
    __tablename__ = 'duplicate_groups'
    
    id = Column(Integer, primary_key=True)
    hash_value = Column(String(64), nullable=False)
    size = Column(Integer, nullable=False)
    file_count = Column(Integer, default=0)
    created_time = Column(DateTime, default=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_hash', 'hash_value'),
        Index('idx_size', 'size'),
    )

class DuplicateFile(Base):
    """Model for storing individual duplicate files"""
    __tablename__ = 'duplicate_files'
    
    id = Column(Integer, primary_key=True)
    file_id = Column(Integer)
    group_id = Column(Integer)
    hash_value = Column(String(64), nullable=False)
    is_primary = Column(Boolean, default=False)  # Marked as keep
    is_deleted = Column(Boolean, default=False)
    
    # Indexes
    __table_args__ = (
        Index('idx_file_id', 'file_id'),
        Index('idx_group_id', 'group_id'),
        Index('idx_hash', 'hash_value'),
    )

class StorageHistory(Base):
    """Model for storing storage usage over time"""
    __tablename__ = 'storage_history'
    
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=False)
    total_size = Column(Integer, nullable=False)  # Total size in bytes
    file_count = Column(Integer, default=0)
    directory_count = Column(Integer, default=0)
    
    # Indexes
    __table_args__ = (
        Index('idx_date', 'date'),
    )

class TrashBin(Base):
    """Model for storing deleted files (for undo functionality)"""
    __tablename__ = 'trash_bin'
    
    id = Column(Integer, primary_key=True)
    original_path = Column(String(2000), nullable=False)
    original_size = Column(Integer, nullable=False)
    deleted_time = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)  # When the file will be permanently deleted
    restored = Column(Boolean, default=False)
    
    # Indexes
    __table_args__ = (
        Index('idx_deleted_time', 'deleted_time'),
        Index('idx_expires_at', 'expires_at'),
    ) 