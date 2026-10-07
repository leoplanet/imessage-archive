//! Dumps the iMessage chat.db into flat JSONL files with all message bodies
//! decoded (including the new streamtyped attributedBody format).

use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::PathBuf;

use imessage_database::{
    tables::{messages::Message, table::{get_connection, Table}},
    util::dates::{get_local_time, get_offset},
};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    assert!(args.len() == 3, "usage: imessage-dumper <chat.db> <out_dir>");
    let db_path = PathBuf::from(&args[1]);
    let out_dir = PathBuf::from(&args[2]);
    std::fs::create_dir_all(&out_dir).unwrap();

    let conn = get_connection(&db_path).expect("cannot connect to database");
    let offset = get_offset();

    // ---- messages ----
    let mut stmt = Message::get(&conn).expect("prepare message query");
    let mut w = BufWriter::new(File::create(out_dir.join("messages.jsonl")).unwrap());
    let mut count = 0u64;
    let mut failed = 0u64;
    let mut empty_text = 0u64;
    for m_res in Message::rows(&mut stmt, []).expect("iterate messages") {
        let mut m = match m_res {
            Ok(m) => m,
            Err(e) => {
                failed += 1;
                eprintln!("row error: {e:?}");
                continue;
            }
        };
        // Decode attributedBody (new streamtyped format) into plain text
        if m.text.as_deref().unwrap_or("").is_empty() {
            if let Ok(body) = m.parse_body(&conn) {
                m.apply_body(body);
            }
        }
        if m.text.as_deref().unwrap_or("").is_empty() {
            empty_text += 1;
        }
        let date = if m.date > 0 {
            get_local_time(m.date, offset)
                .map(|d| d.to_rfc3339())
                .unwrap_or_default()
        } else {
            String::new()
        };
        let obj = serde_json::json!({
            "rowid": m.rowid,
            "guid": m.guid,
            "chat_id": m.chat_id,
            "handle_id": m.handle_id,
            "is_from_me": m.is_from_me,
            "date_raw": m.date,
            "date": date,
            "text": m.text,
            "num_attachments": m.num_attachments,
            "edited": m.edited_parts.is_some(),
            "service": m.service,
        });
        writeln!(w, "{obj}").unwrap();
        count += 1;
    }
    w.flush().unwrap();
    println!("messages: {count} (failed rows: {failed}, empty text: {empty_text})");

    // ---- chats ----
    let mut w = BufWriter::new(File::create(out_dir.join("chats.jsonl")).unwrap());
    let mut rows = conn
        .prepare("SELECT rowid, chat_identifier, display_name, service_name FROM chat")
        .unwrap();
    let mut count = 0;
    for r in rows
        .query_map([], |r| {
            Ok(serde_json::json!({
                "rowid": r.get::<_, i32>(0)?,
                "chat_identifier": r.get::<_, String>(1)?,
                "display_name": r.get::<_, Option<String>>(2)?,
                "service_name": r.get::<_, Option<String>>(3)?,
            }))
        })
        .unwrap()
    {
        writeln!(w, "{}", r.unwrap()).unwrap();
        count += 1;
    }
    w.flush().unwrap();
    println!("chats: {count}");

    // ---- handles ----
    let mut w = BufWriter::new(File::create(out_dir.join("handles.jsonl")).unwrap());
    let mut rows = conn.prepare("SELECT rowid, id FROM handle").unwrap();
    let mut count = 0;
    for r in rows
        .query_map([], |r| {
            Ok(serde_json::json!({
                "rowid": r.get::<_, i32>(0)?,
                "id": r.get::<_, String>(1)?,
            }))
        })
        .unwrap()
    {
        writeln!(w, "{}", r.unwrap()).unwrap();
        count += 1;
    }
    w.flush().unwrap();
    println!("handles: {count}");

    // ---- attachments ----
    let mut w = BufWriter::new(File::create(out_dir.join("attachments.jsonl")).unwrap());
    let mut rows = conn
        .prepare(
            "SELECT a.rowid, a.guid, a.filename, a.transfer_name, a.mime_type,
                    a.total_bytes, a.is_sticker, j.message_id
             FROM attachment a
             LEFT JOIN message_attachment_join j ON j.attachment_id = a.rowid",
        )
        .unwrap();
    let mut count = 0;
    for r in rows
        .query_map([], |r| {
            Ok(serde_json::json!({
                "rowid": r.get::<_, i32>(0)?,
                "guid": r.get::<_, String>(1)?,
                "filename": r.get::<_, Option<String>>(2)?,
                "transfer_name": r.get::<_, Option<String>>(3)?,
                "mime_type": r.get::<_, Option<String>>(4)?,
                "total_bytes": r.get::<_, i64>(5)?,
                "is_sticker": r.get::<_, i64>(6)? != 0,
                "message_id": r.get::<_, Option<i32>>(7)?,
            }))
        })
        .unwrap()
    {
        writeln!(w, "{}", r.unwrap()).unwrap();
        count += 1;
    }
    w.flush().unwrap();
    println!("attachments: {count}");
}
