# iMessage search (knowledge source)

Single-file SQLite database with FTS5 full-text search over all 14,368 decoded
messages. No dependencies beyond Python 3 (stdlib only).

## Usage

```sh
# Full-text search (top 20 hits, with context snippets)
python3 search.py "roof"
python3 search.py "interview" -n 50

# Limit to one conversation (by chat_id or participant substring)
python3 search.py "roof" -c "+15551234567"

# List all conversations (most recent activity first)
python3 search.py --list

# Dump an entire conversation
python3 search.py --show 98
```

## Schema

- `conversations` — chat_id, identifier, display_name, participants, message_count, first/last date
- `messages_fts` — FTS5: chat_id, guid, date (ISO-8601 local), sender, is_from_me, text
- `attachments` — rowid, guid, message_id, filename, mime_type, total_bytes, is_sticker
- `meta` — source, created, counts

## Generating JSON later

The decoded message text lives in `messages_fts`, so a JSON export is a
trivial query, e.g.:

```sh
python3 - <<'EOF'
import json, sqlite3
db = sqlite3.connect("imessage-archive.db")
for row in db.execute("SELECT chat_id, guid, date, sender, is_from_me, text FROM messages_fts ORDER BY date"):
    print(json.dumps(dict(zip(("chat_id","guid","date","sender","is_from_me","text"), row))))
EOF
```
