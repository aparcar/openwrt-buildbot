#!/bin/bash
#
# Detect Changed Packages Script
#
# Compares feed commit hashes and detects which packages have changed Makefiles.
# Only packages with modified Makefiles will be rebuilt.
#
# Usage:
#   ./detect_changed_packages.sh <old-feeds.conf> <new-feeds.conf>
#
# Output:
#   One make target per line to stdout
#   Format: package/feeds/<feed>/<package>/compile
#   Or "ALL" if full build is required
#
# Exit Codes:
#   0: Some packages changed (outputs list to stdout)
#   1: Error occurred
#   2: Old file doesn't exist (should trigger full build)
#   3: All feeds changed significantly (should trigger full build)

set -e

if [ $# -ne 2 ]; then
    echo "Usage: $0 <old-feeds.conf> <new-feeds.conf>" >&2
    exit 1
fi

OLD_FEEDS="$1"
NEW_FEEDS="$2"

# Check if new file exists
if [ ! -f "$NEW_FEEDS" ]; then
    echo "Error: New feeds.conf not found: $NEW_FEEDS" >&2
    exit 1
fi

# Check if old file exists
if [ ! -f "$OLD_FEEDS" ]; then
    echo "Info: Old feeds.conf not found (first build)" >&2
    echo "ALL"
    exit 2
fi

# Temporary directory for git operations
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Parse feeds.conf files
# Format: src-git(-full) <name> <url>^<commit>
parse_feed() {
    local FEEDS_FILE="$1"
    grep -E '^src-git(-full)?\s+' "$FEEDS_FILE" | while read -r line; do
        # Extract feed name, URL, and commit
        FEED_NAME=$(echo "$line" | awk '{print $2}')
        URL_AND_COMMIT=$(echo "$line" | awk '{print $3}')
        
        # Split URL and commit (separated by ^)
        FEED_URL=$(echo "$URL_AND_COMMIT" | cut -d'^' -f1)
        COMMIT_HASH=$(echo "$URL_AND_COMMIT" | cut -d'^' -f2)
        
        echo "$FEED_NAME|$FEED_URL|$COMMIT_HASH"
    done
}

echo "Info: Parsing feeds..." >&2

# Parse old and new feeds
parse_feed "$OLD_FEEDS" | sort > "$TEMP_DIR/old_feeds.txt"
parse_feed "$NEW_FEEDS" | sort > "$TEMP_DIR/new_feeds.txt"

OLD_COUNT=$(wc -l < "$TEMP_DIR/old_feeds.txt")
NEW_COUNT=$(wc -l < "$TEMP_DIR/new_feeds.txt")

echo "Info: Old feeds: $OLD_COUNT, New feeds: $NEW_COUNT" >&2

# Track all build targets
ALL_TARGETS=""
CHANGED_FEEDS_COUNT=0
TOTAL_PACKAGES=0

# Process each feed from new feeds.conf
while IFS='|' read -r FEED_NAME FEED_URL COMMIT_NEW; do
    # Skip base feed - always do full build when base changes
    if [ "$FEED_NAME" = "base" ]; then
        echo "Info: Skipping base feed (base changes trigger full rebuild)" >&2
        continue
    fi
    
    # Find corresponding entry in old feeds
    OLD_LINE=$(grep "^${FEED_NAME}|" "$TEMP_DIR/old_feeds.txt" || true)
    
    if [ -z "$OLD_LINE" ]; then
        echo "Info: Feed '$FEED_NAME' is new - building all packages" >&2
        # New feed - build all packages from it
        if [ -d "feeds/$FEED_NAME" ]; then
            find "feeds/$FEED_NAME" -name Makefile -type f | while read makefile; do
                # Extract package name from path like feeds/packages/net/curl/Makefile
                PKG_DIR=$(dirname "$makefile")
                PKG_NAME=$(basename "$PKG_DIR")
                echo "package/feeds/${FEED_NAME}/${PKG_NAME}/compile"
            done
        fi
        CHANGED_FEEDS_COUNT=$((CHANGED_FEEDS_COUNT + 1))
        continue
    fi
    
    # Extract old commit
    COMMIT_OLD=$(echo "$OLD_LINE" | cut -d'|' -f3)
    
    # Skip if commits are the same
    if [ "$COMMIT_OLD" = "$COMMIT_NEW" ]; then
        echo "Info: Feed '$FEED_NAME' unchanged (${COMMIT_NEW:0:8})" >&2
        continue
    fi
    
    echo "Info: Feed '$FEED_NAME' changed: ${COMMIT_OLD:0:8} -> ${COMMIT_NEW:0:8}" >&2
    CHANGED_FEEDS_COUNT=$((CHANGED_FEEDS_COUNT + 1))
    
    # Clone/fetch the feed repository to check for changed files
    FEED_DIR="$TEMP_DIR/$FEED_NAME"
    
    if [ ! -d "$FEED_DIR/.git" ]; then
        echo "  Cloning feed repository..." >&2
        git clone -q "$FEED_URL" "$FEED_DIR" 2>&1 | sed 's/^/    /' >&2 || {
            echo "  Warning: Failed to clone $FEED_URL, skipping diff" >&2
            continue
        }
    fi
    
    cd "$FEED_DIR"
    
    # Fetch if needed
    if ! git cat-file -e "$COMMIT_NEW" 2>/dev/null; then
        echo "  Fetching new commits..." >&2
        git fetch -q origin 2>&1 | sed 's/^/    /' >&2 || {
            echo "  Warning: Failed to fetch, skipping diff" >&2
            cd - > /dev/null
            continue
        }
    fi
    
    # Get list of changed files between commits
    CHANGED_FILES=$(git diff --name-only "$COMMIT_OLD" "$COMMIT_NEW" 2>/dev/null || {
        echo "  Warning: Failed to diff commits, building all packages from feed" >&2
        cd - > /dev/null
        # Build all packages from this feed
        if [ -d "$FEED_DIR" ]; then
            find "$FEED_DIR" -name Makefile -type f | while read makefile; do
                PKG_DIR=$(dirname "$makefile")
                PKG_NAME=$(basename "$PKG_DIR")
                echo "package/feeds/${FEED_NAME}/${PKG_NAME}/compile"
            done
        fi
        continue
    })
    
    cd - > /dev/null
    
    # Filter for Makefile changes
    CHANGED_MAKEFILES=$(echo "$CHANGED_FILES" | grep '/Makefile$' || true)
    
    if [ -z "$CHANGED_MAKEFILES" ]; then
        echo "  No Makefile changes detected" >&2
        continue
    fi
    
    # Extract package names and generate build targets
    echo "  Changed packages:" >&2
    echo "$CHANGED_MAKEFILES" | while read -r makefile_path; do
        # Extract package name from path like net/curl/Makefile
        PKG_DIR=$(dirname "$makefile_path")
        PKG_NAME=$(basename "$PKG_DIR")
        
        # Skip if it's a top-level Makefile (not a package)
        if [ "$PKG_DIR" = "." ] || [ -z "$PKG_NAME" ]; then
            continue
        fi
        
        echo "    - $PKG_NAME" >&2
        echo "package/feeds/${FEED_NAME}/${PKG_NAME}/compile"
        TOTAL_PACKAGES=$((TOTAL_PACKAGES + 1))
    done
    
done < "$TEMP_DIR/new_feeds.txt" > "$TEMP_DIR/build_targets.txt"

# Check results
if [ $CHANGED_FEEDS_COUNT -eq 0 ]; then
    echo "Info: No feed changes detected" >&2
    exit 0
fi

# Check if too many feeds changed (>80%)
if [ $NEW_COUNT -gt 0 ]; then
    CHANGE_RATIO=$((CHANGED_FEEDS_COUNT * 100 / NEW_COUNT))
    if [ $CHANGE_RATIO -ge 80 ]; then
        echo "Info: $CHANGED_FEEDS_COUNT/$NEW_COUNT feeds changed (${CHANGE_RATIO}%) - triggering full build" >&2
        echo "ALL"
        exit 3
    fi
fi

# Output build targets
if [ -s "$TEMP_DIR/build_targets.txt" ]; then
    TOTAL_PACKAGES=$(wc -l < "$TEMP_DIR/build_targets.txt")
    echo "Info: $TOTAL_PACKAGES package(s) with changed Makefiles detected" >&2
    cat "$TEMP_DIR/build_targets.txt"
else
    echo "Info: No packages with changed Makefiles" >&2
fi

exit 0
