# AGENTS.md

Instructions for AI agents (coding assistants) working with this repo.

**Mission:** when the user asks to "export / back up / archive my iMessages",
verify prerequisites → run the pipeline → verify the output → deliver the
archive to the location the user chooses. Do not skip verification steps.

## 0. Pre-flight checks (do all of these, in order)

1. **macOS only.** This repo works on the Mac that holds the Messages DB.
   If the agent is running elsewhere, stop and say so.
2. **DB exists:** `ls -la ~/Library/Messages/chat.db`
3. **Sync completeness — the most important check.** The DB is only as good
   as the iCloud sync. Query:
   ```sh
   sqlite3 ~/Library/Messages/chat.db \
     "SELECT MIN(date), MAX(date), COUNT(*) FROM message;"
   ```
   Dates are nanoseconds since **2001-01-01** (`unix = v/1e9 + 978307200`).
   Ask the user: does the oldest date match the oldest message they can
   scroll to on their iPhone? If the range looks partial, **stop** and walk
   them through enabling iCloud Messages sync (see README → Prerequisite).
   Do not export a known-partial history without the user explicitly
   accepting it.
4. **Disk space:** the final archive ≈ 2.5× the attachment data size
   (`du -sh ~/Library/Messages/Attachments`). Check free space first.
5. **Ask where the finished archive should go** (external drive, cloud sync
   folder, …). Don't assume.

## 1. Run the pipeline

```sh
./scripts/run.sh /path/to/workdir
```

or step-by-step (same order): `snapshot.sh` → `export.sh` → `dump_jsonl.sh`
→ `extract_names.py` → `make_year_html.py` → `build_archive_db.py` →
`assemble.sh`.

Timing expectations (tell the user): first `cargo build` a few minutes;
the per-year HTML step is the slowest (base64-embedding all media); a
~600 MB attachment set produces a ~1.5–2 GB archive.

## 2. Verify (do not skip)

- **Message count:** the dumper prints `messages: N (failed rows: F, empty
  text: E)`. N must equal the `COUNT(*)` from pre-flight. F must be 0.
  E should be tiny (tapbacks/reactions have no text by design).
- **Checksums:** `cd <archive> && sha256sum -c 00_checksums.sha256` — all OK.
- **Render check (optional, macOS):** `swift tests/domcheck.swift
  universal/<year>.html` — should report conversations, rows, images.
- **Spot-check:** open one txt transcript and one year HTML; compare a few
  messages against the Messages app.

## 3. Deliver

- Copy the assembled `iMessage-Archive-YYYY-MM/` folder to the user's
  chosen location. Cloud sync folders (pCloud, Dropbox, …) may be on a
  **separate volume**: use plain `cp -R`, not `cp -Rc` (clonefile fails
  cross-device).
- Report to the user: message count, date range, conversation count,
  attachments included, attachments missing (see below), total size,
  final location, and how to open the archive
  (`03_universal/index.html` → pick a year; `04_search/search.py` for search).

## Gotchas

- **Never touch the live DB.** All reads go through the
  `snapshot/chat.db` copy made by `snapshot.sh`.
- **Don't parse `attributedBody` yourself.** Recent macOS stores ~99% of
  message text in a new binary `streamtyped` format that even Apple's
  `NSKeyedUnarchiver` rejects. The Rust dumper (via the `imessage-database`
  crate) handles it. If the dumper fails to build, debug the build — don't
  fall back to `SELECT text` (it will silently drop most messages).
- **Contact names from the CLI are TCC-blocked** (`CNContactStore` is
  unavailable to command-line tools). The pipeline works around it by
  extracting names from transcripts + vCards. Handles that stay unresolved
  show phone numbers — that's expected, not a bug.
- **Missing attachments:** DB rows with `filename IS NULL` were never
  downloaded to this Mac (viewed on iPhone only). Report them as
  unrecoverable-from-this-machine; don't attempt "recovery".
- **New formats on request** (JSON, CSV, Signal-export, …): generate from
  `jsonl/` or `imessage-archive.db` — never re-decode the DB.
- **Per-year HTML files are big** (100–400 MB is normal). If a year file
  exceeds ~500 MB and the user finds it slow to load, offer to split that
  year further.
- **Search in the HTML apps** searches within one year file only — remind
  the user if they expect cross-year search (use `04_search/search.py` for
  that; it covers all years).

## Never

- Never upload, gist, commit, or sync message data anywhere without an
  explicit user instruction. This repo must stay data-free (`.gitignore`
  covers workdir artifacts — verify with `git status` before any commit).
- Never delete or overwrite the user's existing archives without asking.
- Never write to `~/Library/Messages/`.
