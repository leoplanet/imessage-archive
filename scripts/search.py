#!/usr/bin/env python3
"""Search the iMessage archive.

DB location: IMSG_DB env var (default ./imessage-archive.db)

Usage:
  search.py <query>              full-text search, top 20 hits
  search.py <query> -n 50        more hits
  search.py <query> -c "+614..." limit results to a conversation
  search.py --list               list conversations sorted by last activity
  search.py --show <chat_id>     dump a whole conversation
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

DB = Path(os.environ.get("IMSG_DB", "imessage-archive.db")).resolve()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="*")
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("-c", "--chat", help="filter by chat_id or participant substring")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--show", type=int, metavar="CHAT_ID")
    args = ap.parse_args()

    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row

    if args.list:
        for r in db.execute(
            "SELECT chat_id, identifier, display_name, participants, message_count, last_date "
            "FROM conversations ORDER BY last_date DESC"
        ):
            name = r["display_name"] or r["identifier"]
            print(f"[{r['chat_id']}] {name}  ({r['message_count']} msgs, last {r['last_date'][:10]})")
            print(f"      {r['participants']}")
        return

    if args.show:
        for r in db.execute(
            "SELECT date, sender, is_from_me, text FROM messages_fts "
            "WHERE chat_id = ? ORDER BY date", (args.show,)
        ):
            who = "Me" if r["is_from_me"] else r["sender"]
            print(f"{r['date'][:16].replace('T', ' ')}  {who}: {r['text']}")
        return

    if not args.query:
        ap.print_help()
        return
    q = " ".join(args.query)

    chat_filter = ""
    params = [q]
    if args.chat:
        if args.chat.isdigit():
            chat_filter = "AND chat_id = ?"
            params.append(int(args.chat))
        else:
            chat_filter = "AND chat_id IN (SELECT chat_id FROM conversations WHERE participants LIKE ?)"
            params.append(f"%{args.chat}%")

    rows = db.execute(
        f"""
        SELECT m.chat_id, m.date, m.sender, m.is_from_me,
               snippet(messages_fts, 5, '>>>', '<<<', ' … ', 40) AS snip,
               c.participants
        FROM messages_fts m
        LEFT JOIN conversations c ON c.chat_id = m.chat_id
        WHERE messages_fts MATCH ? {chat_filter}
        ORDER BY rank LIMIT ?
        """,
        (*params, args.n),
    ).fetchall()

    if not rows:
        print("no matches")
        return
    for r in rows:
        who = "Me" if r["is_from_me"] else r["sender"]
        print(f"[{r['date'][:16].replace('T',' ')}] chat {r['chat_id']} ({r['participants']}) {who}:")
        print(f"    {r['snip']}\n")


if __name__ == "__main__":
    main()
