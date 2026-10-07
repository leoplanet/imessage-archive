# iMessage Archive Toolkit

Salvage your complete iMessage history from a Mac into portable, searchable,
self-contained archives.

Built from a real-world export: 14,368 messages, 715 conversations, 791
attachments (2023–2026), macOS 26, exported 2026-10.

## What you get

Run the pipeline once and you get, in a workdir of your choice:

| Output | Description |
|---|---|
| `output/txt/` | Plain-text transcript per conversation + attachments |
| `output/html/` | iMessage-styled HTML per conversation + attachments |
| `universal/` | **Per-year self-contained HTML apps** — one file per year, all media embedded, iMessage-style conversation list + thread view + full-text search. Opens on any device, zero dependencies. |
| `imessage-archive.db` | Single-file SQLite with FTS5 full-text search over every decoded message |
| `jsonl/` | Every message decoded to flat JSONL (the canonical data layer — generate any future format from it) |
| `iMessage-Archive-YYYY-MM/` | Assembled, checksummed archive folder, ready for backup |

## Quick start (macOS)

```sh
git clone <this repo>
./scripts/run.sh /path/to/workdir
```

Requirements: `sqlite3` (system), Python 3 (stdlib only), Rust (`rustup`) for
the dumper, network access to download `imessage-exporter`.

Individual steps are in `scripts/` and can be run separately.

## Prerequisite: iMessage must be synced to iCloud (read this first!)

The pipeline exports `~/Library/Messages/chat.db` — the Mac's **local copy**
of your message history. That copy is only complete if iMessage is synced
through iCloud. **If sync is off, the pipeline will happily export a partial
history** (only what was sent/received on the Mac itself) and nothing will
tell you it's incomplete.

### Enable it

**iPhone:** Settings → *Messages* → *Send & Receive* — make sure your number
and email are listed. Then Settings → *[your name]* → *iCloud* → *Show All*
→ *Messages* → **On**.

**Mac:** System Settings → *Apple Account* → *iCloud* → *Show All* →
*Messages* → **On**. In the Messages app: Messages → Settings → *iMessage*
tab — signed in with the **same Apple ID** as your iPhone.

If you're turning this on for the first time, give the initial sync time
(large histories can take hours to a day), and keep both devices online and
idle while it runs.

### Verify completeness before exporting

```sh
# oldest + newest message in the Mac's DB (local time)
sqlite3 ~/Library/Messages/chat.db \
  "SELECT MIN(date), MAX(date), COUNT(*) FROM message;"
```

- Convert the raw nanosecond values: `unix = value/1e9 + 978307200`
  (epoch is 2001-01-01, not 1970).
- The **oldest** date should match the oldest message you can scroll to on
  your iPhone's Messages app. If the Mac's range starts much later, sync is
  incomplete (or was recently turned on).
- Sanity-check the count against your usage — a phone that's been active for
  years should have tens of thousands of messages, not a few hundred.

## Where iMessage lives on macOS

```
~/Library/Messages/
├── chat.db              # THE database: messages, chats, handles, attachments
├── chat.db-wal/-shm     # WAL files — use sqlite3 .backup for a consistent copy
├── Sync/sync.db         # CloudKit sync state
└── Attachments/         # 256 hex dirs of media files
```

`chat.db` is the Mac's local copy of your iCloud-synced history. If Messages
sync is on, it contains everything your iPhone has — verified by date range
and per-year message counts.

## Key findings (the hard-won part)

### 1. The `text` column is mostly empty — the new `streamtyped` format

On current macOS, ~99% of messages have an **empty `text` column**. The body
lives in `attributedBody` as a new binary format:

```
5e 44 5e 4b  "streamtyped"  ...   # magic ~D~k + "streamtyped"
```

- It is **not** LZFSE, **not** the classic `04 0b "streamtyped"` NSKeyedArchiver
  stream — Apple's own `NSKeyedUnarchiver` rejects it ("incomprehensible archive").
- It is a compact typed-stream (opcodes `~C`, `~A`, `~Y`, varint lengths,
  UTF-8 strings) introduced around iOS 17 / macOS 14.
- **Solution:** don't parse it yourself. The
  [`imessage-database`](https://crates.io/crates/imessage-database) crate
  (from [ReagentX/imessage-exporter](https://github.com/ReagentX/imessage-exporter))
  decodes it. Our `dumper/` is a ~120-line Rust program on top of it that
  emits JSONL. Result: **14,368/14,368 messages decoded, 0 failures**
  (13 empty by design — tapbacks/reactions).

### 2. New chat `style` values

Old DBs use `style` 0/1/2 (SMS / 1:1 / group). Current DBs use:

| style | meaning |
|---|---|
| 43 | group chat (`chat_identifier` = `chat<group-id>`) |
| 45 | 1:1 chat (`chat_identifier` = phone/email) |

### 3. Dates

`message.date` = **nanoseconds since 2001-01-01 00:00:00 UTC**.
Convert: `unix = date/1e9 + 978307200`, then render in local time.

### 4. Attachment export naming

`imessage-exporter` writes attachments as
`attachments/<deduped-chatroom-id>/<attachment-rowid>.<ext>`.
The directory is a *deduplicated* chatroom id, **not** the raw `chat.rowid` —
don't try to derive it. The **filename stem is the attachment `rowid`**, which
is what you want: map files back to messages via `message_attachment_join`.

### 5. Contact names from the CLI are blocked (TCC)

`CNContactStore` is compile-time unavailable for command-line tools
(`init()` is `NS_UNAVAILABLE` in the SDK; `alloc()` is banned in Swift).
Workarounds, in order of preference:

1. Let `imessage-exporter` do it — it resolves handles to names in the
   transcripts (it read 143/704 handles on our machine).
2. Extract names from the transcripts: 1:1 files give a direct
   participant→name mapping; group files can be aligned to the DB message
   sequence (same order, same count) to attribute sender names to `handle_id`s.
3. Mine `.vcf` attachments (shared contacts) for `FN:`/`TEL:` pairs.

Our `extract_names.py` combines all three → **270 named handles**.

### 6. Some attachments simply don't exist on the Mac

Rows with `attachment.filename IS NULL` were never downloaded to this
machine (viewed on iPhone only). Nothing to salvage — the export tools mark
them as missing. Ours: 38 of 791.

### 7. Single-file HTML size budget

Base64 inflates media ~33%. Our total was 577 MB raw → ~770 MB embedded.
A single 770 MB HTML is too much for browsers; **one file per year**
(82/304/369/14 MB) loads fine. The per-year files are complete apps:
conversation list, thread rendering (lazy — only the open thread is in the
DOM), tapbacks, and client-side full-text search.

## The `universal/` HTML apps

- `index.html` → pick a year
- Sidebar: contact names, avatar initials, last-message preview, timestamps
- Thread: iMessage bubbles (blue/gray), date separators, group sender names,
  tapback emoji badges, inline images/videos/audio, PDF/vCard links
- Search: name filter (1 char), full-text + sender-name search with
  match-context snippets (2+ chars), no-results state
- Everything embedded — email a year file to yourself and it just works

## Knowledge source: `imessage-archive.db`

Single-file SQLite (FTS5), built from `jsonl/`:

```sh
python3 scripts/search.py imessage-archive.db "roof"     # full-text, snippets
python3 scripts/search.py imessage-archive.db --list     # all conversations
python3 scripts/search.py imessage-archive.db --show 98  # dump a conversation
python3 scripts/search.py imessage-archive.db "roof" -c "+614..."  # one chat
```

Schema: `conversations`, `messages_fts` (chat_id, guid, date, sender,
is_from_me, text), `attachments`, `meta`. Because the decoded text lives
here, **any future format (JSON, CSV, Signal-export, …) is a trivial query** —
no re-decoding ever needed.

## Testing without a browser

macOS ships WebKit; these headless scripts load a generated year file and
verify rendering/function (used to catch a search-results bug):

```sh
swift tests/domcheck.swift   universal/2025.html    # counts convs/rows/imgs
swift tests/searchtest.swift universal/2025.html    # search flow, click, clear
swift tests/shot.swift       universal/2026.html /tmp/shot.png  # screenshot
```

## Repo layout

```
AGENTS.md  runbook for AI agents running this pipeline
dumper/    Rust JSONL dumper (imessage-database crate)
scripts/   pipeline (run.sh + steps) and Python tools
tests/     headless WebKit verification scripts
```

**Using an AI coding agent?** Point it at `AGENTS.md` — it covers
pre-flight checks (including the iCloud sync verification), execution,
verification, delivery, and the pitfalls.

## Refreshing

Re-run `./scripts/run.sh <workdir>` whenever you want a new snapshot
(e.g. yearly). The old archive folder is a point-in-time export; keep or
delete at will.

## Credits & license

- [ReagentX/imessage-exporter](https://github.com/ReagentX/imessage-exporter)
  (GPL-3.0) — the workhorse for txt/html export and the `imessage-database`
  crate used by the dumper.
- This repo: GPL-3.0-or-later (dumper links a GPL library).

Your message data never leaves your machine — this repo contains no personal
data.
