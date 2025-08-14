#!/usr/bin/env python3
"""
Script to force stop stuck scan and restart with improved logic
"""

import os
import sys
import time
import requests
import json

# Configuration
API_BASE_URL = "http://localhost:5000/api"

def force_stop_and_restart():
    """Force stop the stuck scan and restart it"""
    
    print("=== Storage Manager Scan Fix ===")
    print("This script will force stop any stuck scans and restart with improved logic")
    print()
    
    # Step 1: Check current scan status
    print("1. Checking current scan status...")
    try:
        response = requests.get(f"{API_BASE_URL}/scan/status")
        if response.status_code == 200:
            status = response.json()
            print(f"   Current status: {status.get('status', 'unknown')}")
            if status.get('scanning'):
                print(f"   Current path: {status.get('current_path', 'unknown')}")
                print(f"   Files processed: {status.get('total_files', 0):,}")
                print(f"   Directories processed: {status.get('total_directories', 0):,}")
        else:
            print(f"   Error getting status: {response.status_code}")
    except Exception as e:
        print(f"   Error connecting to API: {e}")
        return
    
    # Step 2: Force stop any running scans
    print("\n2. Force stopping any running scans...")
    try:
        response = requests.post(f"{API_BASE_URL}/scan/force-reset")
        if response.status_code == 200:
            print("   ✓ Force reset completed")
        else:
            print(f"   Error force resetting: {response.status_code}")
    except Exception as e:
        print(f"   Error force resetting: {e}")
    
    # Step 3: Wait a moment for cleanup
    print("\n3. Waiting for cleanup...")
    time.sleep(2)
    
    # Step 4: Check status again
    print("\n4. Checking status after reset...")
    try:
        response = requests.get(f"{API_BASE_URL}/scan/status")
        if response.status_code == 200:
            status = response.json()
            print(f"   Status after reset: {status.get('status', 'unknown')}")
        else:
            print(f"   Error getting status: {response.status_code}")
    except Exception as e:
        print(f"   Error connecting to API: {e}")
    
    # Step 5: Start new scan
    print("\n5. Starting new scan with improved logic...")
    try:
        response = requests.post(f"{API_BASE_URL}/scan/start")
        if response.status_code == 200:
            result = response.json()
            print(f"   ✓ New scan started: {result.get('scan_id', 'unknown')}")
        else:
            print(f"   Error starting scan: {response.status_code}")
    except Exception as e:
        print(f"   Error starting scan: {e}")
    
    # Step 6: Monitor the new scan
    print("\n6. Monitoring new scan (press Ctrl+C to stop monitoring)...")
    try:
        while True:
            response = requests.get(f"{API_BASE_URL}/scan/status")
            if response.status_code == 200:
                status = response.json()
                if status.get('scanning'):
                    print(f"   Scanning: {status.get('current_path', 'unknown')} - "
                          f"Files: {status.get('total_files', 0):,}, "
                          f"Dirs: {status.get('total_directories', 0):,}, "
                          f"Size: {status.get('total_size_formatted', '0 B')}")
                else:
                    print(f"   Scan status: {status.get('status', 'unknown')}")
                    if status.get('status') == 'completed':
                        print("   ✓ Scan completed successfully!")
                        break
                    elif status.get('status') == 'failed':
                        print(f"   ✗ Scan failed: {status.get('error_message', 'Unknown error')}")
                        break
            else:
                print(f"   Error getting status: {response.status_code}")
            
            time.sleep(5)  # Check every 5 seconds
            
    except KeyboardInterrupt:
        print("\n   Monitoring stopped by user")
    except Exception as e:
        print(f"   Error monitoring scan: {e}")
    
    print("\n=== Fix Complete ===")

if __name__ == "__main__":
    force_stop_and_restart()
