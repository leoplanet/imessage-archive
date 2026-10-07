# iMessage Archive — 2026-10

Complete export of all iMessage/SMS history synced to this Mac via iCloud.

- **Exported:** 2026-10-07
- **Message range:** 2023-08-07 → 2026-03-23
- **Messages:** 14,368 (iMessage + SMS)
- **Conversations:** 700 exported (715 in DB, incl. 5 duplicates)
- **Attachments:** 791 referenced, 361 present on disk and included
  (38 were never downloaded to this Mac and cannot be recovered from it)

## Contents

| Folder | What it is |
|---|---|
| `01_txt/` | Plain-text transcript per conversation. Grep-able, LLM-friendly, works everywhere. |
| `02_html/` | iMessage-styled HTML per conversation + `attachments/` folder. Open `index` from any browser. Thread view: date separators, sender labels, tapbacks, replies. |
| `03_universal/` | **Self-contained single-file HTML per conversation** — all attachments embedded (base64). Each file opens on any device with zero dependencies; email it, archive it, print it. |
| `04_search/` | Knowledge source: single SQLite file with FTS5 full-text search over every message. See its README. |
| `05_db/` | Raw `chat.db` snapshot (consistent copy taken at export time). Source of truth for re-exports. |

## Quick start

- **Browse casually:** open any file in `03_universal/` (one file = one complete
  conversation with all media), or the matching file in `02_html/`.
- **Search everything:**
  ```sh
  python3 04_search/search.py "roof"
  python3 04_search/search.py --list
  ```
- **Bulk text processing:** files in `01_txt/`.

## Provenance

- Source: `~/Library/Messages/chat.db` on macOS (Apple Messages, iCloud-synced)
- Tooling: [ReagentX/imessage-exporter](https://github.com/ReagentX/imessage-exporter) v4.3.0
  (GPL-3.0) for txt/html; custom Rust dumper using the `imessage-database` crate
  for the search DB.
- Message bodies in the new `streamtyped` binary format were fully decoded
  (0 of 14,368 failed; 13 are tapbacks/reactions with no text by design).

## Refreshing this archive

Re-run the export pipeline (kept in `~/imessage-export/`) and replace this
folder. The search DB and JSON can be regenerated from `05_db/chat.db` at any
time — the decoded message text lives in `04_search/imessage-archive.db`.

## Integrity

SHA-256 checksums for every file: `00_checksums.sha256`
Verify with: `sha256sum -c 00_checksums.sha256` (from this folder)
