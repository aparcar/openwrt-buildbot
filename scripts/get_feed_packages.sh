#!/bin/sh
#
# Get Feed Packages Script
#
# Lists all packages from a specific feed and outputs them as make targets.
# Used for incremental package building in OpenWrt buildbot phase2.
#
# Usage:
#   ./get_feed_packages.sh <feedname>
#
# Output:
#   One make target per line to stdout
#   Format: package/feeds/<feed>/<package>/compile
#
# Example:
#   ./get_feed_packages.sh packages
#   Output:
#     package/feeds/packages/curl/compile
#     package/feeds/packages/nginx/compile
#     ...

set -e

if [ $# -ne 1 ]; then
    echo "Usage: $0 <feedname>" >&2
    exit 1
fi

FEED_NAME="$1"

# Check if we're in an SDK directory
if [ ! -f "./scripts/feeds" ]; then
    echo "Error: Not in SDK directory (./scripts/feeds not found)" >&2
    exit 1
fi

# Get list of packages from the feed
# ./scripts/feeds list -r <feedname> outputs lines like:
#   curl
#   nginx
#   php
# We need to convert these to make target format

./scripts/feeds list -r "$FEED_NAME" 2>/dev/null | while read -r package; do
    # Skip empty lines
    if [ -z "$package" ]; then
        continue
    fi
    
    # Output make target format
    echo "package/feeds/${FEED_NAME}/${package}/compile"
done

# Exit successfully even if feed is empty or doesn't exist
exit 0