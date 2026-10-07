#!/bin/bash
# Step 3: decode every message (incl. the new streamtyped attributedBody
# format) into flat JSONL using the Rust dumper (imessage-database crate).
# Requires: rustup/cargo.
# Usage: ./dump_jsonl.sh [workdir]
set -euo pipefail
WORK="${1:-.}"
cd "$(dirname "$0")/../dumper"
cargo build --release
cd "$WORK"
"$(dirname "$0")/../dumper/target/release/imessage-dumper" \
  "$WORK/snapshot/chat.db" "$WORK/jsonl"
echo "jsonl -> $WORK/jsonl/"
