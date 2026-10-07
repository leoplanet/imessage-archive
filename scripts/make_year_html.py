#!/usr/bin/env python3
"""Generate per-year, fully self-contained iMessage-style HTML archives.

Each year file is a single .html with:
- conversation list sidebar (contact names, previews, timestamps)
- thread view (iMessage bubbles, date separators, group sender names,
  tapbacks, inline images/videos/audio, pdf/vcf links)
- all attachments embedded as base64 data URIs
- client-side search (conversations + full text)
"""
import base64
import datetime
import json
import mimetypes
import sqlite3
import sys
from pathlib import Path

BASE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
JSONL = BASE / "jsonl"
SNAP = BASE / "snapshot" / "chat.db"
ATT_SRC = BASE / "output" / "html" / "attachments"
OUT = BASE / "universal"
EPOCH = 978307200

EXTRA_MIME = {
    ".heic": "image/heic", ".heif": "image/heif", ".caf": "audio/x-caf",
    ".vcf": "text/vcard", ".mov": "video/quicktime", ".m4a": "audio/mp4",
    ".mp4": "video/mp4", ".jpeg": "image/jpeg", ".jpg": "image/jpeg",
}


def mime(p: Path) -> str:
    e = p.suffix.lower()
    if e in EXTRA_MIME:
        return EXTRA_MIME[e]
    m, _ = mimetypes.guess_type(p.name)
    return m or "application/octet-stream"


def load_jsonl(name):
    with open(JSONL / name) as f:
        for line in f:
            yield json.loads(line)


def main():
    OUT.mkdir(exist_ok=True)
    names = json.loads((BASE / "names.json").read_text())
    handles = {h["rowid"]: h["id"] for h in load_jsonl("handles.jsonl")}
    chats = {c["rowid"]: c for c in load_jsonl("chats.jsonl")}

    src = sqlite3.connect(f"file:{SNAP}?mode=ro", uri=True)
    chat_parts = {}
    for cid, hid in src.execute("SELECT chat_id, handle_id FROM chat_handle_join"):
        chat_parts.setdefault(cid, []).append(hid)

    # message rowid -> [attachment rowids]
    msg_atts = {}
    for a, m in src.execute(
            "SELECT attachment_id, message_id FROM message_attachment_join"):
        msg_atts.setdefault(m, []).append(a)
    msg_guid = {r: g for r, g in src.execute("SELECT rowid, guid FROM message")}

    # tapbacks: target guid -> list of "emoji|sender"
    taps = {}
    for guid, target, emoji, hid, me in src.execute(
            "SELECT guid, associated_message_guid, associated_message_emoji, "
            "handle_id, is_from_me FROM message "
            "WHERE item_type=1 AND associated_message_emoji IS NOT NULL"):
        sender = "Me" if me else names.get(str(hid), handles.get(hid, "?"))
        taps.setdefault(target, []).append(f"{emoji}|{sender}")

    # attachment files on disk: rowid -> data uri
    atts = {}
    for sub in ATT_SRC.iterdir():
        if not sub.is_dir():
            continue
        for f in sub.iterdir():
            try:
                rowid = int(f.stem)
            except ValueError:
                continue
            b64 = base64.b64encode(f.read_bytes()).decode("ascii")
            atts[rowid] = f"data:{mime(f)};base64,{b64}"
    print(f"attachments loaded: {len(atts)}")

    # messages grouped by chat and year
    by_year = {}
    for m in load_jsonl("messages.jsonl"):
        if not m["date"]:
            continue
        year = int(m["date"][:4])
        chat_id = m["chat_id"]
        if chat_id is None:
            continue
        sender = "Me" if m["is_from_me"] else names.get(
            str(m["handle_id"]), handles.get(m["handle_id"], str(m["handle_id"])))
        att_idx = [a for a in msg_atts.get(m["rowid"], []) if a in atts]
        entry = [m["date"], sender, (m["text"] or "").replace("\ufffc", ""), att_idx,
                 taps.get(m["guid"], [])]
        by_year.setdefault(year, {}).setdefault(chat_id, []).append(
            (m["rowid"], entry, att_idx))

    # conversation display names
    def conv_name(cid):
        c = chats.get(cid, {})
        if c.get("display_name"):
            return c["display_name"]
        parts = chat_parts.get(cid, [])
        if len(parts) == 1:
            return names.get(str(parts[0]), handles.get(parts[0], c.get("chat_identifier", "?")))
        named = [names.get(str(p), handles.get(p, "")) for p in parts]
        named = [n for n in named if n]
        if named:
            return ", ".join(sorted(named)[:3]) + (f" +{len(parts)-3}" if len(parts) > 3 else "")
        return c.get("chat_identifier", f"chat {cid}")

    def conv_participants(cid):
        return [names.get(str(p), handles.get(p, str(p))) for p in chat_parts.get(cid, [])]

    years = sorted(by_year)
    for year in years:
        data = by_year[year]
        # global attachment list for this year
        att_list = []
        att_pos = {}
        convs = []
        msgs = {}
        for cid, entries in data.items():
            entries.sort(key=lambda e: e[0])
            atts_used = []
            for _, entry, att_idx in entries:
                for a in att_idx:
                    if a not in att_pos:
                        att_pos[a] = len(att_list)
                        att_list.append(atts[a])
                    atts_used.append(att_pos[a])
            # compact message rows: [date, sender, text, [attPos], taps]
            rows = []
            for _, entry, att_idx in entries:
                rows.append([entry[0], entry[1], entry[2],
                             [att_pos[a] for a in att_idx], entry[4]])
            msgs[str(cid)] = rows
            last = entries[-1][1]
            preview = last[2]
            if not preview and last[3]:
                first_att = att_list[att_pos[last[3][0]]]
                kind = first_att.split(";")[0].split(":")[1]
                preview = {"image": "Photo", "video": "Video",
                           "audio": "Audio message"}.get(kind, "Attachment")
            convs.append({
                "id": cid,
                "name": conv_name(cid),
                "parts": conv_participants(cid),
                "last": last[0],
                "preview": preview,
                "count": len(rows),
            })
        convs.sort(key=lambda c: c["last"], reverse=True)
        payload = {"conversations": convs, "messages": msgs, "attachments": att_list}
        js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        js = js.replace("</", "<\\/")
        html = TEMPLATE.replace("__PAYLOAD__", js).replace("__YEAR__", str(year))
        out = OUT / f"{year}.html"
        out.write_text(html, encoding="utf-8")
        print(f"{year}: {len(convs)} conversations, {len(att_list)} attachments -> {out.stat().st_size/1024/1024:.0f} MB")

    # index page
    links = []
    for year in years:
        n_conv = len(by_year[year])
        n_msg = sum(len(v) for v in by_year[year].values())
        links.append(f'<a class="card" href="{year}.html"><div class="y">{year}</div>'
                     f'<div class="s">{n_msg:,} messages &middot; {n_conv} conversations</div></a>')
    idx = TEMPLATE_INDEX.replace("__CARDS__", "\n".join(links))
    (OUT / "index.html").write_text(idx, encoding="utf-8")
    print("index.html written")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>iMessage Archive __YEAR__</title>
<style>
:root {
  --blue: #0A84FF; --blue-dark: #007AFF;
  --gray-bubble: #E9E9EB; --sidebar-w: 340px;
  --border: #E5E5EA; --muted: #8E8E93;
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  display: flex; height: 100vh; overflow: hidden; background: #fff; color: #000;
}
/* ---------- sidebar ---------- */
#sidebar {
  width: var(--sidebar-w); min-width: 260px; border-right: 1px solid var(--border);
  display: flex; flex-direction: column; background: #fff;
}
#searchwrap { padding: 10px 12px 6px; }
#search {
  width: 100%; border: none; outline: none; border-radius: 8px;
  background: #E9E9EB; padding: 6px 10px; font-size: 14px;
}
#convlist { flex: 1; overflow-y: auto; }
.conv {
  display: flex; gap: 10px; padding: 9px 12px; cursor: pointer;
  border-bottom: 1px solid #F2F2F7; align-items: center;
}
.conv:hover { background: #F5F5F7; }
.conv.sel { background: var(--blue); color: #fff; }
.conv.sel .prev, .conv.sel .when { color: rgba(255,255,255,.75); }
.avatar {
  width: 42px; height: 42px; border-radius: 50%; flex: 0 0 42px;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 16px; font-weight: 600;
}
.cbody { flex: 1; min-width: 0; }
.cname { font-size: 15px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.prev { font-size: 13px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 1px; }
.when { font-size: 12px; color: var(--muted); flex: 0 0 auto; }
/* ---------- thread ---------- */
#main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
#theader {
  height: 56px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: center; flex-direction: column;
  padding: 0 40px;
}
#tname { font-size: 15px; font-weight: 600; }
#tparts { font-size: 12px; color: var(--muted); margin-top: 1px; }
#back {
  position: absolute; left: 12px; top: 14px; display: none;
  border: none; background: none; font-size: 20px; color: var(--blue); cursor: pointer;
}
#msgs { flex: 1; overflow-y: auto; padding: 16px 8%; display: flex; flex-direction: column; }
.day { text-align: center; font-size: 12px; color: var(--muted); margin: 14px 0 8px; }
.day b { font-weight: 600; }
.mrow { display: flex; flex-direction: column; margin-bottom: 3px; }
.mrow.me { align-items: flex-end; }
.mrow.them { align-items: flex-start; }
.sname { font-size: 11px; color: var(--muted); margin: 0 8px 2px; }
.bubble {
  max-width: 75%; padding: 7px 11px; border-radius: 18px;
  font-size: 15px; line-height: 1.3; white-space: pre-wrap; word-wrap: break-word;
  position: relative;
}
.mrow.me .bubble { background: var(--blue); color: #fff; border-bottom-right-radius: 5px; }
.mrow.them .bubble { background: var(--gray-bubble); color: #000; border-bottom-left-radius: 5px; }
.bubble:empty { display: none; }
.bubble img { max-width: 320px; width: 100%; border-radius: 12px; display: block; }
.bubble video { max-width: 320px; width: 100%; border-radius: 12px; display: block; }
.bubble audio { width: 260px; display: block; }
.bubble a.file { display: flex; align-items: center; gap: 8px; text-decoration: none; color: inherit; background: rgba(255,255,255,.25); border-radius: 10px; padding: 8px 12px; font-size: 14px; }
.mrow.them .bubble a.file { background: rgba(0,0,0,.06); color: #000; }
.taps {
  position: absolute; top: -10px; font-size: 13px;
  background: #fff; border-radius: 10px; padding: 0 6px;
  box-shadow: 0 1px 3px rgba(0,0,0,.2); white-space: nowrap;
}
.mrow.me .taps { left: -8px; }
.mrow.them .taps { right: -8px; }
#empty { flex: 1; display: flex; align-items: center; justify-content: center; color: var(--muted); font-size: 15px; }
@media (max-width: 700px) {
  #sidebar { width: 100%; min-width: 0; }
  body.thread-open #sidebar { display: none; }
  body.thread-open #main { display: flex; }
  #main { display: none; }
  #back { display: block; }
  #msgs { padding: 12px 4%; }
}
</style>
</head>
<body>
<div id="sidebar">
  <div id="searchwrap"><input id="search" type="search" placeholder="Search" autocomplete="off"></div>
  <div id="convlist"></div>
</div>
<div id="main">
  <button id="back" onclick="closeThread()">&#8249;</button>
  <div id="theader"><div id="tname"></div><div id="tparts"></div></div>
  <div id="msgs"><div id="empty">Select a conversation</div></div>
</div>
<script>
const DATA = __PAYLOAD__;
const AV_COLORS = ["#E94F4F","#F27D2E","#E8B518","#5BB661","#2E9E6B","#0A84FF","#5E5CE6","#B052D6","#D6528E"];
function avColor(name){let h=0;for(const c of name)h=(h*31+c.charCodeAt(0))>>>0;return AV_COLORS[h%AV_COLORS.length];}
function initials(name){
  const w=name.replace(/[^\p{L}\p{N} ]/gu,"").trim().split(/\s+/).filter(Boolean);
  if(!w.length)return "?";
  if(w.length===1)return w[0].slice(0,2).toUpperCase();
  return (w[0][0]+w[w.length-1][0]).toUpperCase();
}
function esc(s){const d=document.createElement("div");d.textContent=s;return d.innerHTML;}
const MONTHS=["January","February","March","April","May","June","July","August","September","October","November","December"];
const DAYS=["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
function dayLabel(iso){
  const d=new Date(iso);
  return `${DAYS[d.getDay()]}, ${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}
function whenLabel(iso){
  const d=new Date(iso); const now=new Date();
  const sameYear=d.getFullYear()===now.getFullYear();
  return sameYear?`${d.getMonth()+1}/${d.getDate()}`:`${d.getMonth()+1}/${d.getDate()}/${String(d.getFullYear()).slice(2)}`;
}
let sel=null, query="";
function searchItems(){
  const q=query.trim().toLowerCase();
  if(q.length<2){
    return DATA.conversations
      .map(c=>({c,snip:null}))
      .filter(x=>!q||(x.c.name+" "+x.c.parts.join(" ")).toLowerCase().includes(q));
  }
  const items=[];
  for(const c of DATA.conversations){
    const msgs=DATA.messages[String(c.id)]||[];
    let snip=null;
    for(const r of msgs){
      const t=r[2];
      if(t){
        const i=t.toLowerCase().indexOf(q);
        if(i>=0){
          snip=(i>25?"…":"")+t.slice(Math.max(0,i-25),i+q.length+45)+(i+q.length+45<t.length?"…":"");
          break;
        }
      }
      if(r[1].toLowerCase().includes(q)){snip="sent by "+r[1];break;}
    }
    if(snip)items.push({c,snip});
  }
  return items;
}
function renderConvList(){
  const list=document.getElementById("convlist");
  list.innerHTML="";
  const items=searchItems();
  if(!items.length){
    const el=document.createElement("div");
    el.className="prev";
    el.style.padding="16px 14px";
    el.textContent="No results for “"+query.trim()+"”";
    list.appendChild(el);
    return;
  }
  const frag=document.createDocumentFragment();
  for(const {c,snip} of items){
    const el=document.createElement("div");
    el.className="conv"+(sel===c.id?" sel":"");
    el.innerHTML=`<div class="avatar" style="background:${avColor(c.name)}">${esc(initials(c.name))}</div>
      <div class="cbody"><div class="cname">${esc(c.name)}</div><div class="prev">${esc(snip||c.preview||"")}</div></div>
      <div class="when">${whenLabel(c.last)}</div>`;
    el.onclick=()=>openThread(c);
    frag.appendChild(el);
  }
  list.appendChild(frag);
}
function openThread(c){
  sel=c.id;
  document.body.classList.add("thread-open");
  document.getElementById("tname").textContent=c.name;
  document.getElementById("tparts").textContent=c.parts.length>1?c.parts.join(", "):"";
  renderConvList();
  const box=document.getElementById("msgs");
  box.innerHTML="";
  const rows=DATA.messages[String(c.id)]||[];
  const frag=document.createDocumentFragment();
  let lastDay="";
  for(const r of rows){
    const day=r[0].slice(0,10);
    if(day!==lastDay){
      lastDay=day;
      const d=document.createElement("div");
      d.className="day";
      d.innerHTML=`<b>${dayLabel(r[0])}</b>`;
      frag.appendChild(d);
    }
    const me=r[1]==="Me";
    const row=document.createElement("div");
    row.className="mrow "+(me?"me":"them");
    let html="";
    if(!me&&c.parts.length>1)html+=`<div class="sname">${esc(r[1])}</div>`;
    html+=`<div class="bubble">`;
    if(r[2])html+=esc(r[2]);
    for(const ai of r[3]){
      const uri=DATA.attachments[ai];
      if(!uri)continue;
      const m=uri.split(";")[0].split(":")[1];
      if(m.startsWith("image/"))html+=`<img src="${uri}" loading="lazy" alt="">`;
      else if(m.startsWith("video/"))html+=`<video src="${uri}" controls preload="metadata"></video>`;
      else if(m.startsWith("audio/"))html+=`<audio src="${uri}" controls></audio>`;
      else html+=`<a class="file" href="${uri}" download>&#128196; file</a>`;
    }
    if(r[4]&&r[4].length)html+=`<span class="taps">${esc(r[4].map(t=>t.split("|")[0]).join(" "))}</span>`;
    html+=`</div>`;
    row.innerHTML=html;
    frag.appendChild(row);
  }
  box.appendChild(frag);
  box.scrollTop=box.scrollHeight;
}
function closeThread(){
  document.body.classList.remove("thread-open");
  sel=null;
  renderConvList();
}
let sT;
document.getElementById("search").addEventListener("input",e=>{
  clearTimeout(sT);
  sT=setTimeout(()=>{query=e.target.value;renderConvList();},200);
});
renderConvList();
</script>
</body>
</html>
"""

TEMPLATE_INDEX = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>iMessage Archive</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: #F5F5F7; margin: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; min-height: 100vh; }
h1 { font-size: 28px; margin-bottom: 4px; }
p.sub { color: #8E8E93; margin-top: 0; }
.grid { display: flex; gap: 16px; flex-wrap: wrap; justify-content: center; margin-top: 28px; }
.card { background: #fff; border-radius: 16px; padding: 24px 36px; text-align: center;
  text-decoration: none; color: #000; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.card:hover { box-shadow: 0 4px 14px rgba(0,0,0,.15); }
.y { font-size: 34px; font-weight: 700; color: #0A84FF; }
.s { font-size: 13px; color: #8E8E93; margin-top: 6px; }
</style>
</head>
<body>
<h1>&#128172; iMessage Archive</h1>
<p class="sub">Choose a year to open the conversation list</p>
<div class="grid">
__CARDS__
</div>
</body>
</html>
"""

if __name__ == "__main__":
    main()
