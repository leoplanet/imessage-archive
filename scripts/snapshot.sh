#!/bin/bash
# Step 1: take a consistent snapshot of the live iMessage database.
# Usage: ./snapshot.sh [workdir]   (default: current directory)
set -euo pipefail
WORK="${1:-.}"
mkdir -p "$WORK/snapshot"
sqlite3 "$HOME/Library/Messages/chat.db" ".backup '$WORK/snapshot/chat.db'"
echo "snapshot -> $WORK/snapshot/chat.db"
