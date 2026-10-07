#!/bin/bash
# Step 7: assemble the final archive folder with README + SHA-256 checksums.
# Usage: ./assemble.sh [workdir] [archive-name]
#   produces: $WORK/<archive-name>/  ready to copy to your backup location
set -euo pipefail
WORK="${1:-.}"
NAME="${2:-iMessage-Archive-$(date +%Y-%m)}"
A="$WORK/$NAME"
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"

rm -rf "$A"
mkdir -p "$A/04_search" "$A/05_db"
cp -R "$WORK/output/txt"   "$A/01_txt"
cp -R "$WORK/output/html"  "$A/02_html"
cp -R "$WORK/universal"    "$A/03_universal"
cp "$WORK/imessage-archive.db" "$A/04_search/"
cp "$SCRIPTS/search.py"     "$A/04_search/"
cp "$SCRIPTS/SEARCH_README.md" "$A/04_search/README.md" 2>/dev/null || true
cp "$WORK/snapshot/chat.db" "$A/05_db/"
cp "$SCRIPTS/ARCHIVE_README.md" "$A/00_README.md" 2>/dev/null || true

cd "$A"
find . -type f ! -name "00_checksums.sha256" -exec shasum -a 256 {} + > 00_checksums.sha256
echo "archive -> $A ($(du -sh "$A" | awk '{print $1}'))"
