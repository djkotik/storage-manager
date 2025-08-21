#!/usr/bin/env python3
"""
Script to fix stuck scan and restart with optimized folder calculation
"""

import os
import sys
import sqlite3
import time
from datetime import datetime

def fix_stuck_scan():
    """Stop the current scan and prepare for restart with optimized calculation"""
    
    # Database path
    db_path = os.environ.get('DATABASE_PATH', '/app/storage_manager.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check current scan status
        cursor.execute("""
            SELECT id, status, start_time, end_time 
            FROM scan_records 
            ORDER BY start_time DESC 
            LIMIT 1
        """)
        
        current_scan = cursor.fetchone()
        
        if not current_scan:
            print("No scan records found")
            return False
        
        scan_id, status, start_time, end_time = current_scan
        
        print(f"Current scan: ID={scan_id}, Status={status}, Start={start_time}")
        
        if status == 'in_progress':
            print("Stopping current scan...")
            
            # Update scan status to failed
            cursor.execute("""
                UPDATE scan_records 
                SET status = 'failed', 
                    end_time = ?, 
                    error_message = 'Stopped due to performance optimization'
                WHERE id = ?
            """, (datetime.now().isoformat(), scan_id))
            
            # Clear any partial folder calculations
            cursor.execute("DELETE FROM folder_info WHERE scan_id = ?", (scan_id,))
            
            conn.commit()
            print(f"Scan {scan_id} stopped and marked as failed")
            
        elif status == 'completed':
            print("Last scan was completed successfully")
            
        elif status == 'failed':
            print("Last scan failed, ready for restart")
            
        # Clear any scanner state
        cursor.execute("DELETE FROM scanner_state")
        conn.commit()
        
        conn.close()
        print("Database cleaned up successfully")
        return True
        
    except Exception as e:
        print(f"Error fixing stuck scan: {e}")
        return False

if __name__ == "__main__":
    print("=== Storage Manager Scan Fix ===")
    print(f"Time: {datetime.now()}")
    
    if fix_stuck_scan():
        print("Scan fix completed successfully")
        print("You can now restart the application to begin a new optimized scan")
    else:
        print("Scan fix failed")
        sys.exit(1)
