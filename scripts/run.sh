#!/bin/bash
# Full iMessage archive pipeline.
# Usage: ./run.sh [workdir]
#
# Produces in the workdir:
#   snapshot/chat.db        consistent DB copy
#   output/{txt,html}/      transcripts + attachments (imessage-exporter)
#   jsonl/                  every message decoded (Rust dumper)
#   names.json              handle -> contact name map
#   universal/              per-year self-contained iMessage-style HTML
#   imessage-archive.db     FTS5 full-text search DB
#   iMessage-Archive-YYYY-MM/  final assembled archive (checksummed)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${1:-.}"

"$HERE/snapshot.sh"    "$WORK"
"$HERE/export.sh"      "$WORK"
"$HERE/dump_jsonl.sh"  "$WORK"
python3 "$HERE/extract_names.py"   "$WORK"
python3 "$HERE/make_year_html.py"  "$WORK"
python3 "$HERE/build_archive_db.py" "$WORK"
"$HERE/assemble.sh"    "$WORK"
echo "done. archive: $WORK/iMessage-Archive-*/"
