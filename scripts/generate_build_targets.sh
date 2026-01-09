#!/bin/sh
#
# Generate Build Targets Script
#
# Reads a list of changed feeds and generates make targets for all packages
# in those feeds. Used for incremental package building in OpenWrt buildbot phase2.
#
# Usage:
#   ./generate_build_targets.sh <changed-feeds-file>
#
# Input File Format:
#   One feed name per line, or "ALL" to indicate full build
#
# Output:
#   Space-separated list of make targets to stdout
#   Or empty output if "ALL" or no changes
#
# Example:
#   Input file contains:
#     packages
#     luci
#   Output:
#     package/feeds/packages/curl/compile package/feeds/packages/nginx/compile ... package/feeds/luci/base/compile ...

set -e

if [ $# -ne 1 ]; then
    echo "Usage: $0 <changed-feeds-file>" >&2
    exit 1
fi

CHANGED_FEEDS_FILE="$1"

# Check if changed feeds file exists
if [ ! -f "$CHANGED_FEEDS_FILE" ]; then
    echo "Error: Changed feeds file not found: $CHANGED_FEEDS_FILE" >&2
    exit 1
fi

# Read the changed feeds file
CHANGED_FEEDS=$(cat "$CHANGED_FEEDS_FILE" | tr '\n' ' ' | tr -s ' ')

# Check if it contains "ALL" marker
if echo "$CHANGED_FEEDS" | grep -q "ALL"; then
    echo "Info: ALL marker detected - full build required" >&2
    # Output nothing (empty targets means full build)
    exit 0
fi

# Check if empty
if [ -z "$CHANGED_FEEDS" ]; then
    echo "Info: No changed feeds - minimal build" >&2
    # Output nothing
    exit 0
fi

# Get the directory where this script is located
SCRIPT_DIR=$(dirname "$0")

# Check if get_feed_packages.sh exists
if [ ! -f "$SCRIPT_DIR/get_feed_packages.sh" ]; then
    echo "Error: get_feed_packages.sh not found in $SCRIPT_DIR" >&2
    exit 1
fi

# Make sure it's executable
chmod +x "$SCRIPT_DIR/get_feed_packages.sh"

# Collect all targets
ALL_TARGETS=""

echo "Info: Processing changed feeds: $CHANGED_FEEDS" >&2

# Process each feed
for feed in $CHANGED_FEEDS; do
    # Skip empty feed names
    if [ -z "$feed" ]; then
        continue
    fi
    
    echo "Info: Getting packages for feed: $feed" >&2
    
    # Get targets for this feed
    FEED_TARGETS=$("$SCRIPT_DIR/get_feed_packages.sh" "$feed" | tr '\n' ' ')
    
    if [ -n "$FEED_TARGETS" ]; then
        # Count packages (approximate)
        PKG_COUNT=$(echo "$FEED_TARGETS" | wc -w)
        echo "Info: Found $PKG_COUNT package(s) in feed $feed" >&2
        
        # Append to all targets
        ALL_TARGETS="$ALL_TARGETS $FEED_TARGETS"
    else
        echo "Warning: No packages found for feed: $feed" >&2
    fi
done

# Trim leading/trailing spaces
ALL_TARGETS=$(echo "$ALL_TARGETS" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

# Output the targets
if [ -n "$ALL_TARGETS" ]; then
    # Count total targets
    TOTAL_COUNT=$(echo "$ALL_TARGETS" | wc -w)
    echo "Info: Generated $TOTAL_COUNT total build target(s)" >&2
    echo "$ALL_TARGETS"
else
    echo "Warning: No build targets generated" >&2
fi

exit 0