#!/usr/bin/env python3
"""
Test script to verify appdata exclusion is working properly
"""

import os
import sys
from pathlib import Path

def is_appdata_path(path_str):
    """Simple check if path contains appdata - EXTREMELY AGGRESSIVE"""
    path_lower = path_str.lower()
    
    # Check for ANY occurrence of appdata in the path
    if 'appdata' in path_lower:
        print(f"EXCLUDING appdata path: {path_str}")
        return True
    
    # Also exclude other problematic directories that might cause delays
    problematic_patterns = [
        'cache', 'temp', 'tmp', 'logs', 'log', 'backup', 'backups',
        'xteve', 'plex', 'emby', 'jellyfin', 'sonarr', 'radarr', 
        'lidarr', 'readarr', 'sabnzbd', 'nzbget', 'transmission', 
        'deluge', 'qbit', 'qbittorrent', 'docker', 'containers'
    ]
    
    for pattern in problematic_patterns:
        if pattern in path_lower:
            print(f"EXCLUDING problematic directory: {path_str}")
            return True
    
    return False

def test_appdata_exclusion():
    """Test the appdata exclusion function with various paths"""
    
    test_paths = [
        "/data/movies",
        "/data/tv",
        "/data/appdata",
        "/data/appdata/plex",
        "/data/appdata/sonarr",
        "/data/appdata/radarr",
        "/data/appdata/emby",
        "/data/appdata/jellyfin",
        "/data/appdata/xteve",
        "/data/appdata/sabnzbd",
        "/data/appdata/nzbget",
        "/data/appdata/transmission",
        "/data/appdata/deluge",
        "/data/appdata/qbittorrent",
        "/data/appdata/docker",
        "/data/appdata/containers",
        "/data/appdata/cache",
        "/data/appdata/temp",
        "/data/appdata/tmp",
        "/data/appdata/logs",
        "/data/appdata/log",
        "/data/appdata/backup",
        "/data/appdata/backups",
        "/data/movies/appdata",
        "/data/tv/appdata",
        "/data/movies/plex",
        "/data/tv/sonarr",
        "/data/movies/radarr",
        "/data/tv/emby",
        "/data/movies/jellyfin",
        "/data/tv/xteve",
        "/data/movies/sabnzbd",
        "/data/tv/nzbget",
        "/data/movies/transmission",
        "/data/tv/deluge",
        "/data/movies/qbittorrent",
        "/data/tv/docker",
        "/data/movies/containers",
        "/data/tv/cache",
        "/data/movies/temp",
        "/data/tv/tmp",
        "/data/movies/logs",
        "/data/tv/log",
        "/data/movies/backup",
        "/data/tv/backups",
    ]
    
    print("=== TESTING APPDATA EXCLUSION ===")
    print()
    
    excluded_count = 0
    included_count = 0
    
    for path in test_paths:
        if is_appdata_path(path):
            excluded_count += 1
            print(f"❌ EXCLUDED: {path}")
        else:
            included_count += 1
            print(f"✅ INCLUDED: {path}")
    
    print()
    print("=== SUMMARY ===")
    print(f"Total paths tested: {len(test_paths)}")
    print(f"Excluded: {excluded_count}")
    print(f"Included: {included_count}")
    print()
    
    # Test with actual data path
    data_path = os.environ.get('DATA_PATH', '/data')
    print(f"=== TESTING ACTUAL DATA PATH ===")
    print(f"Data path: {data_path}")
    
    if is_appdata_path(data_path):
        print(f"❌ WARNING: Data path {data_path} would be excluded!")
        print("This would prevent scanning entirely.")
        return False
    else:
        print(f"✅ Data path {data_path} would be included for scanning.")
        return True

if __name__ == "__main__":
    success = test_appdata_exclusion()
    sys.exit(0 if success else 1)
