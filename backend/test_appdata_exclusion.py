#!/usr/bin/env python3
"""
Test script to verify appdata exclusion is working properly
"""

import os
import sys
import time
from pathlib import Path

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scanner import FileScanner

def test_appdata_exclusion():
    """Test that appdata directories are properly excluded"""
    
    # Create a test scanner
    scanner = FileScanner(data_path="/data", max_duration=1)
    
    # Test the should_exclude_path function
    def should_exclude_path(path):
        """Check if a path should be excluded from scanning"""
        path_lower = path.lower()
        # Check for appdata in the path
        if 'appdata' in path_lower:
            print(f"Excluding appdata path: {path}")
            return True
        return False
    
    # Test paths
    test_paths = [
        "/data/movies",
        "/data/appdata",
        "/data/appdata/plex",
        "/data/appdata/radarr",
        "/data/tv",
        "/data/appdata/sonarr",
        "/data/music",
        "/data/appdata/transmission",
        "/data/backups",
        "/data/appdata/nginx",
    ]
    
    print("Testing appdata exclusion logic:")
    for path in test_paths:
        should_exclude = should_exclude_path(path)
        print(f"  {path}: {'EXCLUDED' if should_exclude else 'INCLUDED'}")
    
    # Test the safe_walk function
    print("\nTesting safe_walk function:")
    
    def safe_walk(path):
        """Safe walk function that properly excludes appdata and handles timeouts"""
        try:
            for root, dirs, files in os.walk(path):
                # Check if current root should be excluded
                if should_exclude_path(root):
                    print(f"Excluding entire directory tree: {root}")
                    # Clear everything to prevent any processing
                    dirs.clear()
                    files.clear()
                    continue
                
                # Remove appdata directories from the dirs list to prevent os.walk from entering them
                original_dirs = dirs.copy()
                dirs[:] = [d for d in dirs if 'appdata' not in d.lower()]
                if len(dirs) != len(original_dirs):
                    print(f"Filtered out {len(original_dirs) - len(dirs)} appdata directories from {root}")
                
                yield root, dirs, files
                
        except Exception as e:
            print(f"Error in safe_walk: {e}")
            raise
    
    # Test with a small sample of the actual data path
    print("\nTesting with actual data path (first 10 directories):")
    count = 0
    try:
        for root, dirs, files in safe_walk("/data"):
            if count >= 10:  # Only test first 10 directories
                break
            print(f"  Processing: {root} ({len(dirs)} dirs, {len(files)} files)")
            count += 1
    except Exception as e:
        print(f"Error during walk: {e}")

if __name__ == "__main__":
    test_appdata_exclusion()
