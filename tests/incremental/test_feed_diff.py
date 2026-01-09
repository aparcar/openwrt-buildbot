#!/usr/bin/env python3
"""
Unit tests for feed_diff.py script.

Tests various scenarios for feed comparison and change detection.
"""

import unittest
import tempfile
import os
import sys
import subprocess
from pathlib import Path


class TestFeedDiff(unittest.TestCase):
    """Test cases for feed_diff.py functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.script_path = Path(__file__).parent.parent.parent / "scripts" / "feed_diff.py"
        self.assertTrue(self.script_path.exists(), f"Script not found: {self.script_path}")
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def write_feeds_conf(self, filename, feeds):
        """Helper to write a feeds.conf file."""
        path = os.path.join(self.temp_dir, filename)
        with open(path, 'w') as f:
            for feed_name, commit_hash in feeds.items():
                f.write(f"src-git {feed_name} https://git.openwrt.org/feed/{feed_name}.git^{commit_hash}\n")
        return path
    
    def run_feed_diff(self, old_path, new_path):
        """Helper to run feed_diff.py and return exit code and output."""
        result = subprocess.run(
            [str(self.script_path), old_path, new_path],
            capture_output=True,
            text=True
        )
        return result.returncode, result.stdout, result.stderr
    
    def test_identical_feeds(self):
        """Test with identical feeds - should exit 0 with no output."""
        feeds = {
            'packages': 'abc1234567890abcdef1234567890abcdef12345',
            'luci': 'def4567890abcdef1234567890abcdef12345678',
            'routing': 'fed9876543210fedcba9876543210fedcba98765'
        }
        old_path = self.write_feeds_conf('old.conf', feeds)
        new_path = self.write_feeds_conf('new.conf', feeds)
        
        exit_code, stdout, stderr = self.run_feed_diff(old_path, new_path)
        
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.strip(), '')
        self.assertIn("No feed changes detected", stderr)
    
    def test_single_feed_changed(self):
        """Test with one feed changed - should exit 0 and output feed name."""
        old_feeds = {
            'packages': 'abc1234567890abcdef1234567890abcdef12345',
            'luci': 'def4567890abcdef1234567890abcdef12345678',
            'routing': 'fed9876543210fedcba9876543210fedcba98765'
        }
        new_feeds = {
            'packages': 'fff9999999999999999999999999999999999999',  # Changed
            'luci': 'def4567890abcdef1234567890abcdef12345678',
            'routing': 'fed9876543210fedcba9876543210fedcba98765'
        }
        old_path = self.write_feeds_conf('old.conf', old_feeds)
        new_path = self.write_feeds_conf('new.conf', new_feeds)
        
        exit_code, stdout, stderr = self.run_feed_diff(old_path, new_path)
        
        self.assertEqual(exit_code, 0)
        self.assertIn('packages', stdout)
        self.assertNotIn('luci', stdout)
        self.assertNotIn('routing', stdout)
    
    def test_multiple_feeds_changed(self):
        """Test with multiple feeds changed - should exit 0 and list all."""
        old_feeds = {
            'packages': 'abc1234567890abcdef1234567890abcdef12345',
            'luci': 'def4567890abcdef1234567890abcdef12345678',
            'routing': 'fed9876543210fedcba9876543210fedcba98765'
        }
        new_feeds = {
            'packages': 'fff9999999999999999999999999999999999999',  # Changed
            'luci': 'eee8888888888888888888888888888888888888',      # Changed
            'routing': 'fed9876543210fedcba9876543210fedcba98765'
        }
        old_path = self.write_feeds_conf('old.conf', old_feeds)
        new_path = self.write_feeds_conf('new.conf', new_feeds)
        
        exit_code, stdout, stderr = self.run_feed_diff(old_path, new_path)
        
        self.assertEqual(exit_code, 0)
        self.assertIn('packages', stdout)
        self.assertIn('luci', stdout)
        self.assertNotIn('routing', stdout)
    
    def test_base_feed_changed(self):
        """Test with base feed changed - should exit 3 and output ALL."""
        old_feeds = {
            'base': '1111111111111111111111111111111111111111',
            'packages': 'abc1234567890abcdef1234567890abcdef12345',
            'luci': 'def4567890abcdef1234567890abcdef12345678'
        }
        new_feeds = {
            'base': '9999999999999999999999999999999999999999',  # Base changed
            'packages': 'abc1234567890abcdef1234567890abcdef12345',
            'luci': 'def4567890abcdef1234567890abcdef12345678'
        }
        old_path = self.write_feeds_conf('old.conf', old_feeds)
        new_path = self.write_feeds_conf('new.conf', new_feeds)
        
        exit_code, stdout, stderr = self.run_feed_diff(old_path, new_path)
        
        self.assertEqual(exit_code, 3)
        self.assertIn('ALL', stdout)
        self.assertIn('Base feed changed', stderr)
    
    def test_missing_old_file(self):
        """Test with missing old file - should exit 2 and output ALL."""
        new_feeds = {
            'packages': 'abc1234567890abcdef1234567890abcdef12345',
            'luci': 'def4567890abcdef1234567890abcdef12345678'
        }
        old_path = os.path.join(self.temp_dir, 'nonexistent.conf')
        new_path = self.write_feeds_conf('new.conf', new_feeds)
        
        exit_code, stdout, stderr = self.run_feed_diff(old_path, new_path)
        
        self.assertEqual(exit_code, 2)
        self.assertIn('ALL', stdout)
        self.assertIn('not found', stderr)
    
    def test_all_feeds_changed(self):
        """Test with all feeds changed - should exit 3 and output ALL."""
        old_feeds = {
            'packages': 'abc1234567890abcdef1234567890abcdef12345',
            'luci': 'def4567890abcdef1234567890abcdef12345678',
            'routing': 'fed9876543210fedcba9876543210fedcba98765',
            'telephony': '1234567890abcdef1234567890abcdef12345678'
        }
        new_feeds = {
            'packages': 'fff9999999999999999999999999999999999999',
            'luci': 'eee8888888888888888888888888888888888888',
            'routing': 'ddd7777777777777777777777777777777777777',
            'telephony': 'ccc6666666666666666666666666666666666666'
        }
        old_path = self.write_feeds_conf('old.conf', old_feeds)
        new_path = self.write_feeds_conf('new.conf', new_feeds)
        
        exit_code, stdout, stderr = self.run_feed_diff(old_path, new_path)
        
        self.assertEqual(exit_code, 3)
        self.assertIn('ALL', stdout)
    
    def test_new_feed_added(self):
        """Test with new feed added - should exit 0 and include new feed."""
        old_feeds = {
            'packages': 'abc1234567890abcdef1234567890abcdef12345',
            'luci': 'def4567890abcdef1234567890abcdef12345678'
        }
        new_feeds = {
            'packages': 'abc1234567890abcdef1234567890abcdef12345',
            'luci': 'def4567890abcdef1234567890abcdef12345678',
            'routing': 'fed9876543210fedcba9876543210fedcba98765'  # New feed
        }
        old_path = self.write_feeds_conf('old.conf', old_feeds)
        new_path = self.write_feeds_conf('new.conf', new_feeds)
        
        exit_code, stdout, stderr = self.run_feed_diff(old_path, new_path)
        
        self.assertEqual(exit_code, 0)
        self.assertIn('routing', stdout)
        self.assertIn('New feeds', stderr)
    
    def test_feed_removed(self):
        """Test with feed removed - should not be in changed list."""
        old_feeds = {
            'packages': 'abc1234567890abcdef1234567890abcdef12345',
            'luci': 'def4567890abcdef1234567890abcdef12345678',
            'routing': 'fed9876543210fedcba9876543210fedcba98765'
        }
        new_feeds = {
            'packages': 'abc1234567890abcdef1234567890abcdef12345',
            'luci': 'def4567890abcdef1234567890abcdef12345678'
            # routing removed
        }
        old_path = self.write_feeds_conf('old.conf', old_feeds)
        new_path = self.write_feeds_conf('new.conf', new_feeds)
        
        exit_code, stdout, stderr = self.run_feed_diff(old_path, new_path)
        
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.strip(), '')
        self.assertIn('Removed feeds', stderr)
    
    def test_src_git_full_format(self):
        """Test with src-git-full format (base feed)."""
        old_feeds = {}
        new_feeds = {}
        
        old_path = os.path.join(self.temp_dir, 'old.conf')
        new_path = os.path.join(self.temp_dir, 'new.conf')
        
        with open(old_path, 'w') as f:
            f.write("src-git-full base https://git.openwrt.org/openwrt/openwrt.git^abc1234567890abcdef1234567890abcdef12345\n")
            f.write("src-git packages https://git.openwrt.org/feed/packages.git^def4567890abcdef1234567890abcdef12345678\n")
        
        with open(new_path, 'w') as f:
            f.write("src-git-full base https://git.openwrt.org/openwrt/openwrt.git^fedcba9876543210fedcba9876543210fedcba98\n")
            f.write("src-git packages https://git.openwrt.org/feed/packages.git^def4567890abcdef1234567890abcdef12345678\n")
        
        exit_code, stdout, stderr = self.run_feed_diff(old_path, new_path)
        
        # Base feed changed, should trigger full rebuild
        self.assertEqual(exit_code, 3)
        self.assertIn('ALL', stdout)
    
    def test_malformed_line_handling(self):
        """Test that malformed lines are handled gracefully."""
        old_path = os.path.join(self.temp_dir, 'old.conf')
        new_path = os.path.join(self.temp_dir, 'new.conf')
        
        with open(old_path, 'w') as f:
            f.write("src-git packages https://git.openwrt.org/feed/packages.git^abc1234567890abcdef1234567890abcdef12345\n")
            f.write("# This is a comment\n")
            f.write("\n")  # Empty line
            f.write("malformed line without caret\n")
        
        with open(new_path, 'w') as f:
            f.write("src-git packages https://git.openwrt.org/feed/packages.git^abc1234567890abcdef1234567890abcdef12345\n")
        
        exit_code, stdout, stderr = self.run_feed_diff(old_path, new_path)
        
        # Should not crash, should handle gracefully
        self.assertIn(exit_code, [0, 1])  # 0 for no changes, 1 for error
    
    def test_80_percent_threshold(self):
        """Test that changing 80%+ of feeds triggers full rebuild."""
        old_feeds = {
            'feed1': 'abc1111111111111111111111111111111111111',
            'feed2': 'def2222222222222222222222222222222222222',
            'feed3': 'fed3333333333333333333333333333333333333',
            'feed4': 'bcd4444444444444444444444444444444444444',
            'feed5': 'cde5555555555555555555555555555555555555'
        }
        new_feeds = {
            'feed1': 'fff9999999999999999999999999999999999999',  # Changed
            'feed2': 'eee8888888888888888888888888888888888888',  # Changed
            'feed3': 'ddd7777777777777777777777777777777777777',  # Changed
            'feed4': 'ccc6666666666666666666666666666666666666',  # Changed
            'feed5': 'cde5555555555555555555555555555555555555'   # Unchanged (80% changed)
        }
        old_path = self.write_feeds_conf('old.conf', old_feeds)
        new_path = self.write_feeds_conf('new.conf', new_feeds)
        
        exit_code, stdout, stderr = self.run_feed_diff(old_path, new_path)
        
        # 80% changed should trigger full rebuild
        self.assertEqual(exit_code, 3)
        self.assertIn('ALL', stdout)


if __name__ == '__main__':
    unittest.main()