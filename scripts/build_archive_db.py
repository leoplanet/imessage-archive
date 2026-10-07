#!/usr/bin/env python3
"""Build the iMessage knowledge-source archive: a single SQLite file with
FTS5 full-text search over every decoded message.

Inputs:  jsonl/ (messages, chats, handles, attachments) + snapshot/chat.db
Output:  imessage-archive.db
"""
import json
import sqlite3
import sys
from pathlib import Path

BASE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
JSONL = BASE / "jsonl"
SNAPSHOT_DB = BASE / "snapshot" / "chat.db"
OUT_DB = BASE / "imessage-archive.db"

EPOCH_2001 = 978307200  # unix seconds for 2001-01-01


def load_jsonl(name):
    with open(JSONL / name) as f:
        for line in f:
            yield json.loads(line)


def main():
    handles = {h["rowid"]: h["id"] for h in load_jsonl("handles.jsonl")}
    chats = {c["rowid"]: c for c in load_jsonl("chats.jsonl")}

    # chat -> participants, from the snapshot
    src = sqlite3.connect(f"file:{SNAPSHOT_DB}?mode=ro", uri=True)
    chat_handles = {}
    for chat_id, handle_id in src.execute(
        "SELECT chat_id, handle_id FROM chat_handle_join"
    ):
        chat_handles.setdefault(chat_id, []).append(handle_id)
    src.close()

    if OUT_DB.exists():
        OUT_DB.unlink()
    db = sqlite3.connect(OUT_DB)
    db.executescript(
        """
        PRAGMA journal_mode = WAL;
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE conversations (
            chat_id INTEGER PRIMARY KEY,
            identifier TEXT,
            display_name TEXT,
            participants TEXT,
            service TEXT,
            message_count INTEGER DEFAULT 0,
            first_date TEXT,
            last_date TEXT
        );
        CREATE VIRTUAL TABLE messages_fts USING fts5(
            chat_id UNINDEXED, guid UNINDEXED, date UNINDEXED,
            sender UNINDEXED, is_from_me UNINDEXED, text
        );
        CREATE TABLE attachments (
            rowid INTEGER PRIMARY KEY,
            guid TEXT, message_id INTEGER, filename TEXT,
            transfer_name TEXT, mime_type TEXT, total_bytes INTEGER,
            is_sticker INTEGER
        );
        CREATE INDEX idx_att_message ON attachments(message_id);
        """
    )

    db.execute(
        "INSERT INTO meta VALUES ('source', ?), ('created', ?), "
        "('message_count', '0'), ('conversation_count', '0'), ('attachment_count', '0')",
        (str(SNAPSHOT_DB), "2026-10-07"),
    )

    # conversations
    for chat_id, ch in chat_handles.items():
        c = chats.get(chat_id, {})
        parts = ", ".join(sorted({handles.get(h, str(h)) for h in ch}))
        db.execute(
            "INSERT OR IGNORE INTO conversations "
            "(chat_id, identifier, display_name, participants, service) VALUES (?,?,?,?,?)",
            (chat_id, c.get("chat_identifier"), c.get("display_name"), parts,
             c.get("service_name")),
        )

    # messages -> FTS5
    n = 0
    buf = []
    for m in load_jsonl("messages.jsonl"):
        text = m.get("text") or ""
        sender = "Me" if m["is_from_me"] else handles.get(m["handle_id"], str(m["handle_id"]))
        buf.append((m["chat_id"], m["guid"], m["date"], sender,
                    1 if m["is_from_me"] else 0, text))
        if len(buf) >= 2000:
            db.executemany("INSERT INTO messages_fts VALUES (?,?,?,?,?,?)", buf)
            n += len(buf)
            buf.clear()
    if buf:
        db.executemany("INSERT INTO messages_fts VALUES (?,?,?,?,?,?)", buf)
        n += len(buf)

    # per-conversation stats
    db.execute(
        """
        UPDATE conversations SET
            message_count = (SELECT COUNT(*) FROM messages_fts WHERE messages_fts.chat_id = conversations.chat_id),
            first_date = (SELECT MIN(date) FROM messages_fts WHERE messages_fts.chat_id = conversations.chat_id),
            last_date = (SELECT MAX(date) FROM messages_fts WHERE messages_fts.chat_id = conversations.chat_id)
        """
    )

    # attachments
    atts = list(load_jsonl("attachments.jsonl"))
    db.executemany(
        "INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?)",
        [(a["rowid"], a["guid"], a["message_id"], a["filename"],
          a["transfer_name"], a["mime_type"], a["total_bytes"],
          1 if a["is_sticker"] else 0) for a in atts],
    )

    db.execute("UPDATE meta SET value=? WHERE key='message_count'", (str(n),))
    db.execute("UPDATE meta SET value=? WHERE key='conversation_count'",
               (str(db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]),))
    db.execute("UPDATE meta SET value=? WHERE key='attachment_count'", (str(len(atts)),))
    db.commit()
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db.close()
    print(f"OK: {n} messages, {len(atts)} attachments -> {OUT_DB}")


if __name__ == "__main__":
    sys.exit(main())
