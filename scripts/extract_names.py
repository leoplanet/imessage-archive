#!/usr/bin/env python3
"""Build handle_id -> display name map from the txt transcripts + vcf attachments.

1:1 files: filename participant gets the (non-Me) name found in the file.
Group files: align the sequence of (name, text) pairs in the txt with the DB
message sequence for that chat to attribute names to handle_ids.
vcf attachments: phone/email -> FN.
"""
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
TXT = BASE / "output" / "txt"
SNAP = BASE / "snapshot" / "chat.db"
OUT = BASE / "names.json"

DATE_RE = re.compile(r"^[A-Z][a-z]{2} \d{1,2}, \d{4}\s+\d{1,2}:\d{2}:\d{2} (AM|PM)")


def parse_txt(path: Path):
    """Yield (name, first_text_line) pairs in order."""
    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        if DATE_RE.match(lines[i]):
            # next non-empty line is the sender name
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                name = lines[j].strip()
                k = j + 1
                text = ""
                while k < len(lines) and lines[k].strip() and not DATE_RE.match(lines[k]) and lines[k].strip() != "Tapbacks:":
                    text += lines[k] + "\n"
                    k += 1
                yield name, text.strip()
            i = j + 1
        else:
            i += 1


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def main():
    src = sqlite3.connect(f"file:{SNAP}?mode=ro", uri=True)
    handles = {r[0]: r[1] for r in src.execute("SELECT rowid, id FROM handle")}

    # chat rowid -> list of participant handle ids
    chat_parts = {}
    for cid, hid in src.execute("SELECT chat_id, handle_id FROM chat_handle_join"):
        chat_parts.setdefault(cid, []).append(hid)

    # chat rowid -> ordered messages [(handle_id, is_from_me, text)]
    chat_msgs = {}
    for cid, hid, me, text in src.execute(
        "SELECT c.chat_id, m.handle_id, m.is_from_me, coalesce(m.text,'') "
        "FROM message m JOIN chat_message_join c ON c.message_id = m.rowid "
        "ORDER BY m.date, m.rowid"
    ):
        chat_msgs.setdefault(cid, []).append((hid, me, text))

    name_votes = defaultdict(Counter)  # handle_id -> Counter(names)

    txt_files = sorted(TXT.glob("*.txt"))
    for f in txt_files:
        participants = f.stem.split(", ")
        pairs = list(parse_txt(f))
        if not pairs:
            continue
        non_me = [p[0] for p in pairs if p[0] != "Me"]
        if len(participants) == 1:
            h = handles.get(0)
            # find the handle rowid for this participant id
            for hid, pid in handles.items():
                if pid == participants[0]:
                    for n in non_me:
                        name_votes[hid][n] += 1
                    break
        else:
            # group: align by sequence
            cid = None
            for c, parts in chat_parts.items():
                if sorted(handles.get(p, str(p)) for p in parts) == sorted(
                    handles.get(p, str(p)) for p in participants
                ) and len(parts) == len(participants):
                    cid = c
                    break
            if cid is None:
                continue
            msgs = chat_msgs.get(cid, [])
            # pairs include Me entries; align non-empty-text messages
            idx = 0
            for name, text in pairs:
                while idx < len(msgs):
                    hid, me, mtext = msgs[idx]
                    idx += 1
                    if me and name == "Me":
                        continue
                    if not me and name != "Me":
                        # match if first text lines are similar
                        if norm(text)[:40] == norm(mtext)[:40] or (not mtext and not text):
                            name_votes[hid][name] += 1
                        break

    # vcf attachments
    vcf_dir = TXT / "attachments"
    for vcf in vcf_dir.rglob("*.vcf"):
        try:
            content = vcf.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        fn = re.search(r"^FN:(.+)$", content, re.M)
        tel = re.findall(r"^TEL[^:]*:(.+)$", content, re.M)
        email = re.findall(r"^EMAIL[^:]*:(.+)$", content, re.M)
        if not fn:
            continue
        name = fn.group(1).strip()
        ids = [t.strip() for t in tel] + [e.strip().lower() for e in email]
        for hid, pid in handles.items():
            if any(pid == i or pid == i.lstrip("+") for i in ids if i):
                name_votes[hid][name] += 2  # weight vcfs

    result = {}
    for hid, votes in name_votes.items():
        result[str(hid)] = votes.most_common(1)[0][0]
    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(f"mapped {len(result)} handles -> {OUT}")
    for hid, n in list(result.items())[:10]:
        print(f"  {handles.get(int(hid), '?')}: {n}")


if __name__ == "__main__":
    main()
