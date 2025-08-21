#!/usr/bin/env python3
"""
Test script to verify share-level exclusion is working properly
"""

import os
import sys

def is_excluded_share(share_name):
    """Check if a share should be excluded"""
    share_lower = share_name.lower()
    
    # CRITICAL: Exclude appdata share completely
    if share_lower == 'appdata':
        print(f"EXCLUDING appdata share: {share_name}")
        return True
    
    # Also exclude other problematic shares
    excluded_shares = [
        'cache', 'temp', 'tmp', 'logs', 'log', 'backup', 'backups',
        'xteve', 'plex', 'emby', 'jellyfin', 'sonarr', 'radarr', 
        'lidarr', 'readarr', 'sabnzbd', 'nzbget', 'transmission', 
        'deluge', 'qbit', 'qbittorrent', 'docker', 'containers'
    ]
    
    for excluded in excluded_shares:
        if excluded in share_lower:
            print(f"EXCLUDING problematic share: {share_name}")
            return True
    
    return False

def test_share_exclusion():
    """Test the share exclusion logic"""
    print("=== TESTING SHARE EXCLUSION LOGIC ===")
    
    # Test data path
    data_path = "/data"
    
    if not os.path.exists(data_path):
        print(f"ERROR: {data_path} does not exist on this system")
        return
    
    # Get all top-level shares/directories
    try:
        top_level_items = os.listdir(data_path)
        print(f"Found {len(top_level_items)} top-level items in {data_path}")
        print(f"Top-level items: {top_level_items}")
    except Exception as e:
        print(f"Error listing top-level directories: {e}")
        return
    
    # Test each share
    excluded_count = 0
    included_count = 0
    
    for share_name in top_level_items:
        share_path = os.path.join(data_path, share_name)
        
        if is_excluded_share(share_name):
            print(f"❌ SKIPPING excluded share: {share_name} at {share_path}")
            excluded_count += 1
        else:
            print(f"✅ PROCESSING share: {share_name} at {share_path}")
            included_count += 1
    
    print(f"\n=== SUMMARY ===")
    print(f"Total shares found: {len(top_level_items)}")
    print(f"Shares to EXCLUDE: {excluded_count}")
    print(f"Shares to PROCESS: {included_count}")
    
    # Check if appdata is being excluded
    if 'appdata' in top_level_items:
        if is_excluded_share('appdata'):
            print("✅ appdata share is correctly marked for exclusion")
        else:
            print("❌ ERROR: appdata share is NOT being excluded!")
    else:
        print("ℹ️  appdata share not found in top-level items")

if __name__ == "__main__":
    test_share_exclusion()
