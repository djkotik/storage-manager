#!/usr/bin/env python3
"""
Disk Usage Diagnostic Script
Helps identify discrepancies between Storage Analyzer and unRAID disk usage
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_directory_size_manual(path):
    """Calculate directory size manually (similar to our scanner)"""
    total_size = 0
    file_count = 0
    dir_count = 0
    
    try:
        for root, dirs, files in os.walk(path):
            # Skip appdata directories if they exist
            dirs[:] = [d for d in dirs if 'appdata' not in d.lower()]
            
            dir_count += len(dirs)
            
            for file in files:
                try:
                    file_path = os.path.join(root, file)
                    if os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                        total_size += file_size
                        file_count += 1
                except (OSError, PermissionError) as e:
                    logger.warning(f"Error accessing file {file_path}: {e}")
                    continue
    except Exception as e:
        logger.error(f"Error walking directory {path}: {e}")
    
    return total_size, file_count, dir_count

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

def analyze_share_exclusions(data_path):
    """Analyze what shares are being excluded and their potential size"""
    logger.info(f"=== SHARE EXCLUSION ANALYSIS ===")
    logger.info(f"Data path: {data_path}")
    
    if not os.path.exists(data_path):
        logger.error(f"Data path does not exist: {data_path}")
        return
    
    # Get all top-level items
    try:
        top_level_items = os.listdir(data_path)
        logger.info(f"Found {len(top_level_items)} top-level items")
    except Exception as e:
        logger.error(f"Error listing top-level items: {e}")
        return
    
    # Define excluded shares (same as in scanner)
    excluded_shares = [
        'cache', 'temp', 'tmp', 'logs', 'log', 'backup', 'backups',
        'xteve', 'plex', 'emby', 'jellyfin', 'sonarr', 'radarr', 
        'lidarr', 'readarr', 'sabnzbd', 'nzbget', 'transmission', 
        'deluge', 'qbit', 'qbittorrent', 'docker', 'containers'
    ]
    
    total_excluded_size = 0
    total_included_size = 0
    excluded_shares_found = []
    included_shares_found = []
    
    for item in top_level_items:
        item_path = os.path.join(data_path, item)
        
        if not os.path.isdir(item_path):
            logger.info(f"Skipping non-directory: {item}")
            continue
        
        # Check if this share would be excluded
        item_lower = item.lower()
        is_excluded = False
        
        # Check appdata exclusion
        if 'appdata' in item_lower or item_lower == 'appdata':
            is_excluded = True
            logger.info(f"Would exclude appdata share: {item}")
        
        # Check other exclusions
        for excluded in excluded_shares:
            if excluded in item_lower:
                is_excluded = True
                logger.info(f"Would exclude share: {item} (matches '{excluded}')")
                break
        
        # Calculate size for this share
        try:
            size, files, dirs = get_directory_size_manual(item_path)
            logger.info(f"Share '{item}': {format_size(size)} ({files:,} files, {dirs:,} dirs)")
            
            if is_excluded:
                excluded_shares_found.append({
                    'name': item,
                    'size': size,
                    'files': files,
                    'dirs': dirs
                })
                total_excluded_size += size
            else:
                included_shares_found.append({
                    'name': item,
                    'size': size,
                    'files': files,
                    'dirs': dirs
                })
                total_included_size += size
                
        except Exception as e:
            logger.error(f"Error calculating size for {item}: {e}")
    
    # Summary
    logger.info(f"\n=== SUMMARY ===")
    logger.info(f"Included shares ({len(included_shares_found)}): {format_size(total_included_size)}")
    for share in included_shares_found:
        logger.info(f"  - {share['name']}: {format_size(share['size'])} ({share['files']:,} files)")
    
    logger.info(f"\nExcluded shares ({len(excluded_shares_found)}): {format_size(total_excluded_size)}")
    for share in excluded_shares_found:
        logger.info(f"  - {share['name']}: {format_size(share['size'])} ({share['files']:,} files)")
    
    logger.info(f"\nTotal scanned: {format_size(total_included_size)}")
    logger.info(f"Total excluded: {format_size(total_excluded_size)}")
    logger.info(f"Total available: {format_size(total_included_size + total_excluded_size)}")
    
    return {
        'included': included_shares_found,
        'excluded': excluded_shares_found,
        'total_included': total_included_size,
        'total_excluded': total_excluded_size,
        'total_available': total_included_size + total_excluded_size
    }

def check_hidden_files(data_path):
    """Check for hidden files and directories that might be missed"""
    logger.info(f"\n=== HIDDEN FILES ANALYSIS ===")
    
    hidden_files_size = 0
    hidden_files_count = 0
    
    try:
        for root, dirs, files in os.walk(data_path):
            # Check hidden directories
            for dir_name in dirs:
                if dir_name.startswith('.'):
                    dir_path = os.path.join(root, dir_name)
                    try:
                        size, files, dirs_count = get_directory_size_manual(dir_path)
                        hidden_files_size += size
                        hidden_files_count += files
                        logger.info(f"Hidden directory: {dir_path} - {format_size(size)} ({files:,} files)")
                    except Exception as e:
                        logger.warning(f"Error accessing hidden directory {dir_path}: {e}")
            
            # Check hidden files
            for file_name in files:
                if file_name.startswith('.'):
                    file_path = os.path.join(root, file_name)
                    try:
                        if os.path.exists(file_path):
                            file_size = os.path.getsize(file_path)
                            hidden_files_size += file_size
                            hidden_files_count += 1
                            logger.info(f"Hidden file: {file_path} - {format_size(file_size)}")
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Error accessing hidden file {file_path}: {e}")
                        
    except Exception as e:
        logger.error(f"Error checking hidden files: {e}")
    
    logger.info(f"Total hidden files size: {format_size(hidden_files_size)} ({hidden_files_count:,} files)")
    return hidden_files_size, hidden_files_count

def check_symlinks(data_path):
    """Check for symlinks that might affect size calculations"""
    logger.info(f"\n=== SYMLINK ANALYSIS ===")
    
    symlink_count = 0
    broken_symlink_count = 0
    
    try:
        for root, dirs, files in os.walk(data_path):
            # Check directories for symlinks
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                if os.path.islink(dir_path):
                    symlink_count += 1
                    target = os.readlink(dir_path)
                    if not os.path.exists(dir_path):
                        broken_symlink_count += 1
                        logger.warning(f"Broken symlink (dir): {dir_path} -> {target}")
                    else:
                        logger.info(f"Symlink (dir): {dir_path} -> {target}")
            
            # Check files for symlinks
            for file_name in files:
                file_path = os.path.join(root, file_name)
                if os.path.islink(file_path):
                    symlink_count += 1
                    target = os.readlink(file_path)
                    if not os.path.exists(file_path):
                        broken_symlink_count += 1
                        logger.warning(f"Broken symlink (file): {file_path} -> {target}")
                    else:
                        logger.info(f"Symlink (file): {file_path} -> {target}")
                        
    except Exception as e:
        logger.error(f"Error checking symlinks: {e}")
    
    logger.info(f"Total symlinks: {symlink_count}")
    logger.info(f"Broken symlinks: {broken_symlink_count}")
    return symlink_count, broken_symlink_count

def main():
    """Main diagnostic function"""
    logger.info("=== STORAGE ANALYZER DISK USAGE DIAGNOSTIC ===")
    logger.info(f"Started at: {datetime.now()}")
    
    # Get data path from environment or use default
    data_path = os.environ.get('DATA_PATH', '/data')
    logger.info(f"Using data path: {data_path}")
    
    if not os.path.exists(data_path):
        logger.error(f"Data path does not exist: {data_path}")
        sys.exit(1)
    
    # Run diagnostics
    try:
        # 1. Analyze share exclusions
        exclusion_analysis = analyze_share_exclusions(data_path)
        
        # 2. Check hidden files
        hidden_size, hidden_count = check_hidden_files(data_path)
        
        # 3. Check symlinks
        symlink_count, broken_symlinks = check_symlinks(data_path)
        
        # Final summary
        logger.info(f"\n=== FINAL DIAGNOSTIC SUMMARY ===")
        logger.info(f"Data path: {data_path}")
        logger.info(f"Total included by scanner: {format_size(exclusion_analysis['total_included'])}")
        logger.info(f"Total excluded by scanner: {format_size(exclusion_analysis['total_excluded'])}")
        logger.info(f"Hidden files size: {format_size(hidden_size)}")
        logger.info(f"Total available on disk: {format_size(exclusion_analysis['total_available'] + hidden_size)}")
        logger.info(f"Symlinks found: {symlink_count} (broken: {broken_symlinks})")
        
        # Potential sources of discrepancy
        logger.info(f"\n=== POTENTIAL DISCREPANCY SOURCES ===")
        logger.info(f"1. Excluded shares: {format_size(exclusion_analysis['total_excluded'])}")
        logger.info(f"2. Hidden files: {format_size(hidden_size)}")
        logger.info(f"3. Broken symlinks: {broken_symlinks}")
        logger.info(f"4. Permission errors (not calculated)")
        logger.info(f"5. unRAID system files (not in /data)")
        logger.info(f"6. Docker/container overhead")
        
    except Exception as e:
        logger.error(f"Error during diagnostic: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()
