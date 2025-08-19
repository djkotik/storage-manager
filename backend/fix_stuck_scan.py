#!/usr/bin/env python3
"""
Fix stuck scan script - helps diagnose and fix scanner issues
"""

import os
import sys
import time
import logging
from datetime import datetime

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db, get_setting, set_setting
from models import ScanRecord, FileRecord
from scanner import FileScanner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_scanner_state():
    """Check the current state of the scanner"""
    with app.app_context():
        # Check for running scans
        running_scans = ScanRecord.query.filter_by(status='running').all()
        logger.info(f"Found {len(running_scans)} running scans")
        
        for scan in running_scans:
            logger.info(f"Scan ID: {scan.id}")
            logger.info(f"Start time: {scan.start_time}")
            logger.info(f"Status: {scan.status}")
            logger.info(f"Total files: {scan.total_files}")
            logger.info(f"Total directories: {scan.total_directories}")
            logger.info(f"Total size: {scan.total_size}")
            if scan.end_time:
                logger.info(f"End time: {scan.end_time}")
            if scan.error_message:
                logger.info(f"Error: {scan.error_message}")
        
        # Check appdata exclusion setting
        skip_appdata = get_setting('skip_appdata', 'true')
        logger.info(f"Appdata exclusion setting: {skip_appdata}")
        
        # Check data path
        data_path = get_setting('data_path', '/data')
        logger.info(f"Data path: {data_path}")
        
        return running_scans

def force_reset_scanner():
    """Force reset the scanner state"""
    with app.app_context():
        logger.info("Force resetting scanner...")
        
        # Mark all running scans as failed
        running_scans = ScanRecord.query.filter_by(status='running').all()
        for scan in running_scans:
            scan.status = 'failed'
            scan.error_message = 'Force reset by script'
            scan.end_time = datetime.utcnow()
        
        db.session.commit()
        logger.info(f"Marked {len(running_scans)} running scans as failed")
        
        # Create scanner instance and force reset
        scanner = FileScanner()
        scanner.force_reset()
        
        logger.info("Scanner force reset complete")

def test_appdata_exclusion():
    """Test the appdata exclusion logic"""
    with app.app_context():
        logger.info("Testing appdata exclusion...")
        
        data_path = get_setting('data_path', '/data')
        skip_appdata = get_setting('skip_appdata', 'true').lower() == 'true'
        
        logger.info(f"Data path: {data_path}")
        logger.info(f"Skip appdata: {skip_appdata}")
        
        if not os.path.exists(data_path):
            logger.error(f"Data path {data_path} does not exist")
            return
        
        # Test the exclusion function
        def should_exclude_path(path_str):
            if not skip_appdata:
                return False
            
            path_lower = path_str.lower()
            if 'appdata' in path_lower or 'app_data' in path_lower or 'app-data' in path_lower:
                return True
            
            problematic_dirs = ['cache', 'temp', 'tmp', 'logs', 'log', 'backup', 'backups']
            for problematic in problematic_dirs:
                if problematic in path_lower:
                    return True
            
            return False
        
        # Check for appdata directories
        appdata_found = []
        for root, dirs, files in os.walk(data_path):
            for dir_name in dirs:
                full_path = os.path.join(root, dir_name)
                if should_exclude_path(full_path):
                    appdata_found.append(full_path)
                    logger.info(f"Would exclude: {full_path}")
        
        logger.info(f"Found {len(appdata_found)} directories that would be excluded")

def check_database_health():
    """Check database health and connection status"""
    with app.app_context():
        logger.info("Checking database health...")
        
        try:
            # Test basic database operations
            logger.info("Testing database connection...")
            db.session.execute("SELECT 1")
            logger.info("✓ Database connection successful")
            
            # Check for locked database
            logger.info("Checking for database locks...")
            try:
                # Try to get a write lock
                db.session.execute("BEGIN IMMEDIATE")
                db.session.execute("COMMIT")
                logger.info("✓ Database is not locked")
            except Exception as e:
                if "database is locked" in str(e):
                    logger.error("✗ Database is locked!")
                else:
                    logger.warning(f"Database lock check failed: {e}")
            
            # Check connection pool status
            logger.info("Checking connection pool...")
            engine = db.engine
            logger.info(f"Pool size: {engine.pool.size()}")
            logger.info(f"Checked out connections: {engine.pool.checkedout()}")
            logger.info(f"Overflow: {engine.pool.overflow()}")
            
            # Test scan record operations
            logger.info("Testing scan record operations...")
            scan_count = ScanRecord.query.count()
            logger.info(f"✓ Found {scan_count} scan records")
            
            # Test file record operations
            logger.info("Testing file record operations...")
            file_count = FileRecord.query.count()
            logger.info(f"✓ Found {file_count} file records")
            
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            logger.error(f"Exception type: {type(e).__name__}")

def unlock_database():
    """Attempt to unlock the database by cleaning up connections"""
    with app.app_context():
        logger.info("Attempting to unlock database...")
        
        try:
            # Force cleanup of all database connections
            logger.info("Cleaning up database connections...")
            db.session.rollback()
            db.session.close()
            db.session.remove()
            
            # Force engine cleanup
            logger.info("Cleaning up database engine...")
            db.engine.dispose()
            
            # Wait a moment for cleanup
            time.sleep(2)
            
            # Test if database is now accessible
            logger.info("Testing database access after cleanup...")
            db.session.execute("SELECT 1")
            logger.info("✓ Database unlocked successfully")
            
        except Exception as e:
            logger.error(f"Failed to unlock database: {e}")
            logger.error(f"Exception type: {type(e).__name__}")

def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python fix_stuck_scan.py check     - Check scanner state")
        print("  python fix_stuck_scan.py reset     - Force reset scanner")
        print("  python fix_stuck_scan.py test      - Test appdata exclusion")
        print("  python fix_stuck_scan.py db-health - Check database health")
        print("  python fix_stuck_scan.py unlock    - Unlock database")
        return
    
    command = sys.argv[1]
    
    if command == 'check':
        check_scanner_state()
    elif command == 'reset':
        force_reset_scanner()
    elif command == 'test':
        test_appdata_exclusion()
    elif command == 'db-health':
        check_database_health()
    elif command == 'unlock':
        unlock_database()
    else:
        print(f"Unknown command: {command}")

if __name__ == '__main__':
    main()
