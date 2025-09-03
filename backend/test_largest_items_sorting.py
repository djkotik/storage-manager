#!/usr/bin/env python3
"""
Test script to verify that the largest items sorting fix works correctly.
This script simulates the logic used in get_directory_children to ensure
we're getting the top N largest items after calculating total sizes.
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import FileRecord, FolderInfo, ScanRecord
from sqlalchemy import func, desc

def test_largest_items_sorting():
    """Test that we get the largest items after calculating total sizes"""
    
    with app.app_context():
        # Get the latest scan
        latest_scan = db.session.query(ScanRecord).order_by(desc(ScanRecord.start_time)).first()
        
        if not latest_scan:
            print("No scans found. Please run a scan first.")
            return
        
        print(f"Testing with scan ID: {latest_scan.id}")
        
        # Simulate the old (broken) approach
        print("\n=== OLD APPROACH (BROKEN) ===")
        print("1. Query with limit first, then calculate sizes")
        
        # This is what was happening before - limiting before knowing total sizes
        children_old = db.session.query(
            FileRecord.name,
            FileRecord.path,
            FileRecord.id,
            FileRecord.is_directory,
            FileRecord.size,
            FileRecord.extension,
            FileRecord.modified_time
        ).filter(
            FileRecord.parent_path == '/data',  # Assuming /data is the root
            FileRecord.scan_id == latest_scan.id
        ).order_by(FileRecord.size.desc()).limit(5).all()  # Limit to 5 for demo
        
        print(f"Found {len(children_old)} children with old approach")
        for i, child in enumerate(children_old):
            print(f"  {i+1}. {child.name} (direct size: {child.size})")
        
        # Simulate the new (fixed) approach
        print("\n=== NEW APPROACH (FIXED) ===")
        print("1. Get all children")
        print("2. Calculate total sizes")
        print("3. Sort by total size")
        print("4. Limit to top N")
        
        # Get all children without limit
        all_children = db.session.query(
            FileRecord.name,
            FileRecord.path,
            FileRecord.id,
            FileRecord.is_directory,
            FileRecord.size,
            FileRecord.extension,
            FileRecord.modified_time
        ).filter(
            FileRecord.parent_path == '/data',  # Assuming /data is the root
            FileRecord.scan_id == latest_scan.id
        ).all()
        
        print(f"Found {len(all_children)} total children")
        
        # Calculate total sizes for each
        children_with_totals = []
        for child in all_children:
            if child.is_directory:
                # Get folder info or calculate
                folder_info = FolderInfo.query.filter(
                    FolderInfo.path == child.path,
                    FolderInfo.scan_id == latest_scan.id
                ).first()
                
                if folder_info and folder_info.total_size > 0:
                    total_size = folder_info.total_size
                else:
                    # Fallback calculation
                    child_totals = db.session.query(
                        func.sum(FileRecord.size).label('total_size')
                    ).filter(
                        FileRecord.path.like(f"{child.path}/%"),
                        FileRecord.scan_id == latest_scan.id
                    ).first()
                    total_size = child_totals.total_size or 0
                
                children_with_totals.append({
                    'name': child.name,
                    'path': child.path,
                    'is_directory': True,
                    'direct_size': child.size,
                    'total_size': total_size
                })
            else:
                children_with_totals.append({
                    'name': child.name,
                    'path': child.path,
                    'is_directory': False,
                    'direct_size': child.size,
                    'total_size': child.size
                })
        
        # Sort by total size and take top 5
        children_with_totals.sort(key=lambda x: x['total_size'], reverse=True)
        top_5_new = children_with_totals[:5]
        
        print(f"Top 5 largest items with new approach:")
        for i, child in enumerate(top_5_new):
            size_diff = child['total_size'] - child['direct_size']
            size_diff_str = f" (+{size_diff})" if size_diff > 0 else ""
            print(f"  {i+1}. {child['name']} (total: {child['total_size']}, direct: {child['direct_size']}{size_diff_str})")
        
        # Show the difference
        print("\n=== COMPARISON ===")
        print("Old approach might miss larger items because it limits before calculating totals.")
        print("New approach ensures we get the truly largest items by total size.")
        
        # Check if there are significant differences
        old_names = {child.name for child in children_old}
        new_names = {child['name'] for child in top_5_new}
        
        if old_names != new_names:
            print(f"\nDIFFERENCE DETECTED!")
            print(f"Old approach top 5: {old_names}")
            print(f"New approach top 5: {new_names}")
            print(f"Items in new but not old: {new_names - old_names}")
            print(f"Items in old but not new: {old_names - new_names}")
        else:
            print("\nNo difference detected in this test case.")

if __name__ == "__main__":
    test_largest_items_sorting()
