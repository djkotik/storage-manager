#!/usr/bin/env python3
"""
Database Lock Fix Script

This script helps resolve SQLite database lock issues by:
1. Stopping any running scans
2. Unlocking the database
3. Checking database status
"""

import sqlite3
import os
import sys
import time
from datetime import datetime

# Database path
DB_PATH = '/app/data/storage_analyzer.db'

def check_database_status():
    """Check if database is accessible and get status"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cursor = conn.cursor()
        
        # Check if database is accessible
        cursor.execute("SELECT COUNT(*) FROM sqlite_master")
        table_count = cursor.fetchone()[0]
        
        # Check for running scans
        cursor.execute("SELECT COUNT(*) FROM scans WHERE status = 'running'")
        running_scans = cursor.fetchone()[0]
        
        # Check WAL mode
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        
        # Check busy timeout
        cursor.execute("PRAGMA busy_timeout")
        busy_timeout = cursor.fetchone()[0]
        
        conn.close()
        
        print(f"Database Status:")
        print(f"  - Accessible: Yes")
        print(f"  - Tables: {table_count}")
        print(f"  - Running scans: {running_scans}")
        print(f"  - Journal mode: {journal_mode}")
        print(f"  - Busy timeout: {busy_timeout}ms")
        
        return True, running_scans
        
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e).lower():
            print(f"Database is locked: {e}")
            return False, 0
        else:
            print(f"Database error: {e}")
            return False, 0
    except Exception as e:
        print(f"Error checking database: {e}")
        return False, 0

def stop_running_scans():
    """Stop any running scans in the database"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cursor = conn.cursor()
        
        # Get running scans
        cursor.execute("SELECT id, start_time FROM scans WHERE status = 'running'")
        running_scans = cursor.fetchall()
        
        if running_scans:
            print(f"Found {len(running_scans)} running scans:")
            for scan_id, start_time in running_scans:
                print(f"  - Scan {scan_id} started at {start_time}")
            
            # Update running scans to stopped
            cursor.execute("""
                UPDATE scans 
                SET status = 'stopped', 
                    end_time = ?, 
                    error_message = 'Scan stopped by database fix script'
                WHERE status = 'running'
            """, (datetime.now().isoformat(),))
            
            conn.commit()
            print(f"Stopped {len(running_scans)} running scans")
        else:
            print("No running scans found")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error stopping scans: {e}")
        return False

def unlock_database():
    """Attempt to unlock the database"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cursor = conn.cursor()
        
        # Force a checkpoint to release locks
        cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        
        # Set better timeout and WAL settings
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=10000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        
        conn.commit()
        conn.close()
        
        print("Database unlocked and optimized")
        return True
        
    except Exception as e:
        print(f"Error unlocking database: {e}")
        return False

def main():
    print("=== Database Lock Fix Script ===")
    print(f"Database path: {DB_PATH}")
    print()
    
    # Check if database file exists
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file not found at {DB_PATH}")
        sys.exit(1)
    
    # Check initial status
    print("1. Checking database status...")
    accessible, running_scans = check_database_status()
    
    if not accessible:
        print("\n2. Database is locked, attempting to unlock...")
        if unlock_database():
            print("Database unlocked successfully")
        else:
            print("Failed to unlock database")
            sys.exit(1)
    
    # Stop running scans
    print("\n3. Stopping any running scans...")
    stop_running_scans()
    
    # Unlock database again
    print("\n4. Optimizing database settings...")
    unlock_database()
    
    # Final status check
    print("\n5. Final status check...")
    accessible, running_scans = check_database_status()
    
    if accessible and running_scans == 0:
        print("\n✅ Database is now accessible and no scans are running!")
        print("You can now restart your application.")
    else:
        print("\n❌ Database issues remain. You may need to restart the application.")
    
    print("\nTo restart the application, run:")
    print("docker-compose restart")

if __name__ == "__main__":
    main()
