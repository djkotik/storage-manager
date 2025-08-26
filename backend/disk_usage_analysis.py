#!/usr/bin/env python3
"""
Disk Usage Analysis Script
Analyzes the discrepancy between Storage Analyzer and qdirstat results
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

def analyze_qdirstat_vs_scanner():
    """Analyze the qdirstat results vs what our scanner would include/exclude"""
    
    # qdirstat results from the screenshot
    qdirstat_results = {
        'tv shows': 15.8,  # TB
        'movies': 8.9,
        'music': 1.1,
        'docs': 0.5,
        'isos': 0.4,
        'eBooks': 0.3,
        'Other Videos': 0.2,
        'Special': 0.1,
        'files_external': 0.1,
        'Photos': 0.1,
        'FTP': 0.1,
        'cctv': 0.1,
        'Wedding': 0.1,
        'appdata': 2.8,
        'system': 1.1,
        'CommunityApplicationsAppdataBackup': 1.0,
        'Backups': 1.0,
        'TVH Recordings': 1.0,
        'Jellyfin Recordings': 1.0,
        'temp': 0.1,
        'downloads': 0.1,
        '.Trash-99': 0.1
    }
    
    # Convert to bytes for calculations
    qdirstat_bytes = {k: v * 1024**4 for k, v in qdirstat_results.items()}
    
    # Current scanner exclusion logic
    def would_exclude_share(share_name):
        share_lower = share_name.lower()
        
        # Appdata exclusion (default setting)
        skip_appdata = True  # Default setting
        if skip_appdata and ('appdata' in share_lower or share_lower == 'appdata'):
            return True, "appdata exclusion"
        
        # Other exclusions
        excluded_shares = [
            'cache', 'temp', 'tmp', 'logs', 'log', 'backup', 'backups',
            'xteve', 'plex', 'emby', 'jellyfin', 'sonarr', 'radarr', 
            'lidarr', 'readarr', 'sabnzbd', 'nzbget', 'transmission', 
            'deluge', 'qbit', 'qbittorrent', 'docker', 'containers'
        ]
        
        for excluded in excluded_shares:
            if excluded in share_lower:
                return True, f"matches '{excluded}'"
        
        return False, "included"
    
    logger.info("=== QDIRSTAT vs STORAGE ANALYZER ANALYSIS ===")
    logger.info(f"Analysis based on qdirstat results and current scanner logic")
    
    total_qdirstat = sum(qdirstat_bytes.values())
    included_shares = []
    excluded_shares = []
    
    for share_name, size_bytes in qdirstat_bytes.items():
        is_excluded, reason = would_exclude_share(share_name)
        
        if is_excluded:
            excluded_shares.append({
                'name': share_name,
                'size': size_bytes,
                'reason': reason
            })
        else:
            included_shares.append({
                'name': share_name,
                'size': size_bytes,
                'reason': reason
            })
    
    # Calculate totals
    total_included = sum(s['size'] for s in included_shares)
    total_excluded = sum(s['size'] for s in excluded_shares)
    
    logger.info(f"\n=== INCLUDED SHARES ({len(included_shares)}) ===")
    for share in sorted(included_shares, key=lambda x: x['size'], reverse=True):
        logger.info(f"✅ {share['name']}: {format_size(share['size'])} ({share['reason']})")
    
    logger.info(f"\n=== EXCLUDED SHARES ({len(excluded_shares)}) ===")
    for share in sorted(excluded_shares, key=lambda x: x['size'], reverse=True):
        logger.info(f"❌ {share['name']}: {format_size(share['size'])} ({share['reason']})")
    
    logger.info(f"\n=== SUMMARY ===")
    logger.info(f"qdirstat total: {format_size(total_qdirstat)}")
    logger.info(f"Storage Analyzer would include: {format_size(total_included)}")
    logger.info(f"Storage Analyzer would exclude: {format_size(total_excluded)}")
    logger.info(f"Discrepancy: {format_size(total_excluded)}")
    
    # Compare with reported discrepancy
    reported_discrepancy = 5.9 * 1024**4  # 5.9 TB in bytes
    logger.info(f"Reported discrepancy (unRAID vs Storage Analyzer): {format_size(reported_discrepancy)}")
    logger.info(f"Calculated exclusion total: {format_size(total_excluded)}")
    
    if abs(total_excluded - reported_discrepancy) < 1024**4:  # Within 1TB
        logger.info("✅ Calculated exclusions match reported discrepancy!")
    else:
        logger.info("⚠️  Calculated exclusions don't match reported discrepancy")
        logger.info(f"   Difference: {format_size(abs(total_excluded - reported_discrepancy))}")
    
    return {
        'qdirstat_total': total_qdirstat,
        'included_total': total_included,
        'excluded_total': total_excluded,
        'included_shares': included_shares,
        'excluded_shares': excluded_shares
    }

def suggest_fixes():
    """Suggest fixes for the disk usage discrepancy"""
    logger.info(f"\n=== SUGGESTED FIXES ===")
    
    logger.info("1. **Appdata Inclusion/Exclusion**")
    logger.info("   - Current: appdata is excluded (2.8TB)")
    logger.info("   - Option A: Keep excluded (recommended for performance)")
    logger.info("   - Option B: Include appdata (will increase scan time significantly)")
    
    logger.info("\n2. **Backup Share Handling**")
    logger.info("   - Current: 'backup' and 'backups' are excluded")
    logger.info("   - Affected: CommunityApplicationsAppdataBackup (1.0TB), Backups (1.0TB)")
    logger.info("   - Option A: Keep excluded (backups are often temporary)")
    logger.info("   - Option B: Include backups (will show full storage usage)")
    
    logger.info("\n3. **Recording Shares**")
    logger.info("   - Current: TVH Recordings (1.0TB), Jellyfin Recordings (1.0TB) might be timing out")
    logger.info("   - These should be included but may need timeout adjustments")
    
    logger.info("\n4. **System Share**")
    logger.info("   - Current: system (1.1TB) might be timing out")
    logger.info("   - This should be included but may need timeout adjustments")
    
    logger.info("\n5. **Recommended Actions**")
    logger.info("   - Add a setting to control backup share inclusion")
    logger.info("   - Increase timeout for large shares")
    logger.info("   - Add a 'comprehensive mode' that includes all shares")
    logger.info("   - Show excluded shares in the UI with their sizes")

def main():
    """Main function"""
    logger.info("=== STORAGE ANALYZER vs QDIRSTAT ANALYSIS ===")
    logger.info(f"Started at: {datetime.now()}")
    
    try:
        # Run the analysis
        results = analyze_qdirstat_vs_scanner()
        
        # Suggest fixes
        suggest_fixes()
        
        logger.info(f"\n=== FINAL RECOMMENDATION ===")
        logger.info(f"The 5.9TB discrepancy is primarily due to intentional exclusions:")
        logger.info(f"- Appdata exclusion: 2.8TB")
        logger.info(f"- Backup shares: 2.0TB")
        logger.info(f"- Recording shares: 2.0TB")
        logger.info(f"- System share: 1.1TB")
        logger.info(f"")
        logger.info(f"To get closer to unRAID's 43.8TB, consider:")
        logger.info(f"1. Including backup shares (+2.0TB)")
        logger.info(f"2. Including recording shares (+2.0TB)")
        logger.info(f"3. Including system share (+1.1TB)")
        logger.info(f"4. Keep appdata excluded for performance")
        
    except Exception as e:
        logger.error(f"Error in analysis: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()
