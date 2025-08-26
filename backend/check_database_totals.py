#!/usr/bin/env python3
"""
Check Database Totals Script
Shows what the current Storage Analyzer database contains
"""

import os
import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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

def check_database_totals():
    """Check what totals are stored in the database"""
    try:
        # Import database models
        from app import db, FileRecord, ScanRecord, FolderInfo
        from sqlalchemy import func, desc, case
        
        logger.info("=== DATABASE TOTALS ANALYSIS ===")
        
        # Get the most recent scan
        latest_scan = db.session.query(ScanRecord).order_by(desc(ScanRecord.start_time)).first()
        
        if not latest_scan:
            logger.error("No scans found in database")
            return
        
        logger.info(f"Latest scan ID: {latest_scan.id}")
        logger.info(f"Scan status: {latest_scan.status}")
        logger.info(f"Start time: {latest_scan.start_time}")
        logger.info(f"End time: {latest_scan.end_time}")
        
        # Get totals from scan record
        logger.info(f"\n=== SCAN RECORD TOTALS ===")
        logger.info(f"Total files: {latest_scan.total_files:,}")
        logger.info(f"Total directories: {latest_scan.total_directories:,}")
        logger.info(f"Total size: {format_size(latest_scan.total_size)}")
        
        # Get totals from FileRecord table
        logger.info(f"\n=== FILERECORD TABLE TOTALS ===")
        file_stats = db.session.query(
            func.count(FileRecord.id).label('total_count'),
            func.sum(case((FileRecord.is_directory == False, 1), else_=0)).label('file_count'),
            func.sum(case((FileRecord.is_directory == True, 1), else_=0)).label('directory_count'),
            func.sum(FileRecord.size).label('total_size')
        ).filter(FileRecord.scan_id == latest_scan.id).first()
        
        logger.info(f"Total records: {file_stats.total_count:,}")
        logger.info(f"File records: {file_stats.file_count:,}")
        logger.info(f"Directory records: {file_stats.directory_count:,}")
        logger.info(f"Total size: {format_size(file_stats.total_size)}")
        
        # Get top-level shares from FolderInfo
        logger.info(f"\n=== TOP-LEVEL SHARES (FOLDERINFO) ===")
        top_shares = db.session.query(
            FolderInfo.name,
            FolderInfo.total_size,
            FolderInfo.file_count,
            FolderInfo.directory_count
        ).filter(
            FolderInfo.scan_id == latest_scan.id,
            FolderInfo.depth == 1
        ).order_by(desc(FolderInfo.total_size)).all()
        
        total_folderinfo_size = 0
        for share in top_shares:
            logger.info(f"{share.name}: {format_size(share.total_size)} ({share.file_count:,} files, {share.directory_count:,} dirs)")
            total_folderinfo_size += share.total_size
        
        logger.info(f"Total from FolderInfo: {format_size(total_folderinfo_size)}")
        
        # Check for any discrepancies
        logger.info(f"\n=== DISCREPANCY ANALYSIS ===")
        scan_size = latest_scan.total_size or 0
        filerecord_size = file_stats.total_size or 0
        folderinfo_size = total_folderinfo_size
        
        logger.info(f"ScanRecord total: {format_size(scan_size)}")
        logger.info(f"FileRecord total: {format_size(filerecord_size)}")
        logger.info(f"FolderInfo total: {format_size(folderinfo_size)}")
        
        if scan_size != filerecord_size:
            logger.warning(f"⚠️  ScanRecord vs FileRecord mismatch: {format_size(abs(scan_size - filerecord_size))}")
        
        if filerecord_size != folderinfo_size:
            logger.warning(f"⚠️  FileRecord vs FolderInfo mismatch: {format_size(abs(filerecord_size - folderinfo_size))}")
        
        # Get all scans for comparison
        logger.info(f"\n=== ALL SCANS ===")
        all_scans = db.session.query(ScanRecord).order_by(desc(ScanRecord.start_time)).limit(5).all()
        
        for scan in all_scans:
            status_icon = "✅" if scan.status == "completed" else "❌" if scan.status == "failed" else "🔄"
            logger.info(f"{status_icon} Scan {scan.id}: {format_size(scan.total_size)} ({scan.total_files:,} files) - {scan.status}")
        
        return {
            'scan_size': scan_size,
            'filerecord_size': filerecord_size,
            'folderinfo_size': folderinfo_size,
            'total_files': latest_scan.total_files,
            'total_directories': latest_scan.total_directories
        }
        
    except Exception as e:
        logger.error(f"Error checking database totals: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

def main():
    """Main function"""
    logger.info("=== STORAGE ANALYZER DATABASE TOTALS CHECK ===")
    logger.info(f"Started at: {datetime.now()}")
    
    try:
        # Check if we're in the right directory
        if not os.path.exists('app.py'):
            logger.error("app.py not found. Please run this script from the backend directory.")
            sys.exit(1)
        
        # Run the check
        results = check_database_totals()
        
        if results:
            logger.info(f"\n=== SUMMARY ===")
            logger.info(f"Storage Analyzer shows: {format_size(results['scan_size'])}")
            logger.info(f"FileRecord total: {format_size(results['filerecord_size'])}")
            logger.info(f"FolderInfo total: {format_size(results['folderinfo_size'])}")
            logger.info(f"Files: {results['total_files']:,}")
            logger.info(f"Directories: {results['total_directories']:,}")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()
