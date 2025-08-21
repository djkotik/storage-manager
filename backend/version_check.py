#!/usr/bin/env python3
"""
Simple script to verify which version of the scanner code is running
"""

import os
import sys

def main():
    print("=== CONTAINER VERSION CHECK ===")
    
    # Check VERSION file
    try:
        with open('./VERSION', 'r') as f:
            version = f.read().strip()
        print(f"VERSION file: {version}")
    except Exception as e:
        print(f"Error reading VERSION file: {e}")
    
    # Check if scanner.py has the bulletproof messages
    try:
        with open('./scanner.py', 'r') as f:
            content = f.read()
        
        if "🚨 STARTING BULLETPROOF SCAN" in content:
            print("✅ Scanner has bulletproof exclusion code")
        else:
            print("❌ Scanner does NOT have bulletproof exclusion code")
            
        if "EMERGENCY CRASH PROTECTION" in content:
            print("✅ Scanner has crash protection")
        else:
            print("❌ Scanner does NOT have crash protection")
            
    except Exception as e:
        print(f"Error checking scanner.py: {e}")
    
    print("=== END VERSION CHECK ===")

if __name__ == "__main__":
    main()
