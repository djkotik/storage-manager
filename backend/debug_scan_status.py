#!/usr/bin/env python3
"""
Debug script to check scan status and identify issues
"""

import os
import sys
import sqlite3
from datetime import datetime

def debug_scan_status():
    """Debug the current scan status"""
    
    # Database path
    db_path = os.environ.get('DATABASE_PATH', '/app/storage_manager.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("=== SCAN STATUS DEBUG ===")
        print(f"Time: {datetime.now()}")
        print()
        
        # Check scan records
        cursor.execute("""
            SELECT id, status, start_time, end_time, total_files, total_directories, total_size, error_message
            FROM scan_records 
            ORDER BY start_time DESC 
            LIMIT 5
        """)
        
        scans = cursor.fetchall()
        print(f"Found {len(scans)} scan records:")
        
        for scan in scans:
            scan_id, status, start_time, end_time, total_files, total_directories, total_size, error_message = scan
            print(f"  Scan {scan_id}: {status}")
            print(f"    Start: {start_time}")
            print(f"    End: {end_time}")
            print(f"    Files: {total_files:,}")
            print(f"    Directories: {total_directories:,}")
            print(f"    Size: {total_size:,} bytes")
            if error_message:
                print(f"    Error: {error_message}")
            print()
        
        # Check for running scans
        cursor.execute("SELECT COUNT(*) FROM scan_records WHERE status = 'running'")
        running_count = cursor.fetchone()[0]
        print(f"Running scans: {running_count}")
        
        if running_count > 0:
            cursor.execute("""
                SELECT id, start_time, total_files, total_directories, total_size
                FROM scan_records 
                WHERE status = 'running'
            """)
            running_scans = cursor.fetchall()
            
            for scan in running_scans:
                scan_id, start_time, total_files, total_directories, total_size = scan
                print(f"  Running scan {scan_id}:")
                print(f"    Started: {start_time}")
                print(f"    Files: {total_files:,}")
                print(f"    Directories: {total_directories:,}")
                print(f"    Size: {total_size:,} bytes")
                
                # Calculate duration
                if start_time:
                    start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    elapsed = datetime.now() - start_dt.replace(tzinfo=None)
                    print(f"    Duration: {elapsed}")
                print()
        
        # Check scanner state table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scanner_state'")
        if cursor.fetchone():
            cursor.execute("SELECT * FROM scanner_state")
            scanner_state = cursor.fetchall()
            print(f"Scanner state table entries: {len(scanner_state)}")
            for state in scanner_state:
                print(f"  {state}")
        else:
            print("No scanner_state table found")
        
        # Check file records
        cursor.execute("SELECT COUNT(*) FROM files")
        file_count = cursor.fetchone()[0]
        print(f"Total file records: {file_count:,}")
        
        # Check folder info
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='folder_info'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*) FROM folder_info")
            folder_count = cursor.fetchone()[0]
            print(f"Total folder info records: {folder_count:,}")
        else:
            print("No folder_info table found")
        
        conn.close()
        print("=== DEBUG COMPLETE ===")
        return True
        
    except Exception as e:
        print(f"Error debugging scan status: {e}")
        return False

if __name__ == "__main__":
    debug_scan_status()
