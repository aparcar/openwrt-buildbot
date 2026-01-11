#!/usr/bin/env python3
"""
Feed Difference Detection Script

Compares two feeds.conf files and determines which feeds have changed.
Used for incremental package building in OpenWrt buildbot phase2.

Exit Codes:
    0: Some feeds changed (outputs list to stdout)
    1: Error occurred
    2: Old file doesn't exist (should trigger full build)
    3: Base feed changed OR all feeds changed (should trigger full build)

Output Format:
    One feed name per line to stdout
    Or "ALL" if all feeds changed or base changed
    
Usage:
    ./feed_diff.py <old-feeds.conf> <new-feeds.conf>
"""

import sys
import os
import re
from typing import Dict, Set, Tuple


def parse_feeds_conf(filepath: str) -> Dict[str, str]:
    """
    Parse a feeds.conf file and extract feed names and commit hashes.
    
    Args:
        filepath: Path to feeds.conf file
        
    Returns:
        Dictionary mapping feed_name -> commit_hash
        
    Format examples:
        src-git packages https://git.openwrt.org/feed/packages.git^835d8c3409d200e41fd1f67718c4a01ae4229f82
        src-git-full base https://git.openwrt.org/openwrt/openwrt.git^dcf11c832a95595e6b919b88d6cd649bd9343a1f
    """
    feeds = {}
    
    if not os.path.exists(filepath):
        return feeds
    
    # Pattern to match feed lines with commit hashes
    # Matches: src-git(-full) <name> <url>^<commit>
    pattern = re.compile(r'^src-git(-full)?\s+(\S+)\s+\S+\^([0-9a-f]+)', re.IGNORECASE)
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                match = pattern.match(line)
                if match:
                    feed_type = match.group(1)  # -full or None
                    feed_name = match.group(2)
                    commit_hash = match.group(3)
                    feeds[feed_name] = commit_hash
                else:
                    # Log malformed lines to stderr but don't fail
                    print(f"Warning: Could not parse line {line_num} in {filepath}: {line}", 
                          file=sys.stderr)
    
    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
        raise
    
    return feeds


def compare_feeds(old_feeds: Dict[str, str], new_feeds: Dict[str, str]) -> Tuple[Set[str], Set[str], Set[str]]:
    """
    Compare two feed dictionaries and identify changes.
    
    Args:
        old_feeds: Dictionary of old feed_name -> commit_hash
        new_feeds: Dictionary of new feed_name -> commit_hash
        
    Returns:
        Tuple of (changed_feeds, new_feeds, removed_feeds)
    """
    old_names = set(old_feeds.keys())
    new_names = set(new_feeds.keys())
    
    # Feeds that exist in both but have different commits
    changed = {name for name in old_names & new_names 
               if old_feeds[name] != new_feeds[name]}
    
    # Feeds that are new (not in old)
    new = new_names - old_names
    
    # Feeds that were removed (not in new)
    removed = old_names - new_names
    
    return changed, new, removed


def main():
    """Main entry point for feed_diff.py"""
    
    if len(sys.argv) != 3:
        print("Usage: feed_diff.py <old-feeds.conf> <new-feeds.conf>", file=sys.stderr)
        sys.exit(1)
    
    old_path = sys.argv[1]
    new_path = sys.argv[2]
    
    # Check if new file exists (should always exist)
    if not os.path.exists(new_path):
        print(f"Error: New feeds.conf not found: {new_path}", file=sys.stderr)
        sys.exit(1)
    
    # Check if old file exists
    if not os.path.exists(old_path):
        print(f"Info: Old feeds.conf not found: {old_path} (first build)", file=sys.stderr)
        print("ALL")
        sys.exit(2)
    
    # Parse both files
    try:
        old_feeds = parse_feeds_conf(old_path)
        new_feeds = parse_feeds_conf(new_path)
    except Exception as e:
        print(f"Error parsing feeds.conf files: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Debug output
    print(f"Old feeds: {len(old_feeds)} feeds", file=sys.stderr)
    print(f"New feeds: {len(new_feeds)} feeds", file=sys.stderr)
    
    # Compare feeds
    changed, new, removed = compare_feeds(old_feeds, new_feeds)
    
    # Collect all affected feeds
    affected = changed | new
    
    print(f"Changed feeds: {changed}", file=sys.stderr)
    print(f"New feeds: {new}", file=sys.stderr)
    print(f"Removed feeds: {removed}", file=sys.stderr)
    
    # Base feed changes are treated like any other feed change
    # A smarter dependency model will be implemented later
    # if 'base' in changed or 'base' in new:
    #     print("Info: Base feed changed - triggering full rebuild", file=sys.stderr)
    #     print("ALL")
    #     sys.exit(3)
    
    # Check if no changes
    if not affected:
        print("Info: No feed changes detected", file=sys.stderr)
        # No output to stdout means no packages to build
        sys.exit(0)
    
    # Check if all (or most) feeds changed (likely indicates major update)
    # If more than 80% of feeds changed, trigger full rebuild
    if len(new_feeds) > 0:
        change_ratio = len(affected) / len(new_feeds)
        if change_ratio >= 0.8:
            print(f"Info: {len(affected)}/{len(new_feeds)} feeds changed ({change_ratio:.0%}) - triggering full rebuild", 
                  file=sys.stderr)
            print("ALL")
            sys.exit(3)
    
    # Output changed and new feeds (one per line)
    for feed in sorted(affected):
        print(feed)
    
    print(f"Info: {len(affected)} feed(s) require rebuilding", file=sys.stderr)
    sys.exit(0)


if __name__ == '__main__':
    main()