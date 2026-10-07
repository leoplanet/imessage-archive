#!/bin/bash
# Step 2: export txt + html transcripts with attachments, using
# ReagentX/imessage-exporter (prebuilt binary, GPL-3.0).
# Usage: ./export.sh [workdir] [version]   (default version: 4.3.0)
set -euo pipefail
WORK="${1:-.}"
VER="${2:-4.3.0}"
BIN="$WORK/bin/imessage-exporter"

if [ ! -x "$BIN" ]; then
  mkdir -p "$WORK/bin"
  ARCH=$(uname -m)
  echo "downloading imessage-exporter $VER ($ARCH)..."
  curl -sL -o "$BIN" \
    "https://github.com/ReagentX/imessage-exporter/releases/download/$VER/imessage-exporter-$([ "$ARCH" = arm64 ] && echo aarch64 || echo x86_64)-apple-darwin"
  chmod +x "$BIN"
  xattr -d com.apple.quarantine "$BIN" 2>/dev/null || true
fi

"$BIN" -p "$WORK/snapshot/chat.db" -f txt  -c full -o "$WORK/output/txt"  --use-message-times
"$BIN" -p "$WORK/snapshot/chat.db" -f html -c full -o "$WORK/output/html" --use-message-times
echo "exports -> $WORK/output/{txt,html}"
