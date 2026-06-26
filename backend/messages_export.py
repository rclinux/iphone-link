#!/usr/bin/env python3
"""messages_export.py — turn an iOS sms.db into readable per-conversation files.

Reads the Messages database (sms.db) extracted from an *unencrypted* device
backup and writes one .txt file per conversation plus an index. Read-only on the
input; never touches the device.

Usage:
    messages_export.py <sms.db> <out_dir> [--format txt|csv]

Modern iOS often stores the message text in the binary `attributedBody`
(a typedstream archive) instead of the plain `text` column; we extract it with a
well-known heuristic and fall back gracefully when a body can't be decoded.
"""

import csv
import datetime
import json
import os
import re
import sqlite3
import sys

# Messages timestamps are nanoseconds (modern) or seconds (legacy) since this.
APPLE_EPOCH = datetime.datetime(2001, 1, 1, tzinfo=datetime.timezone.utc)


def apple_time(value) -> str:
    if not value:
        return ""
    secs = value / 1e9 if value > 1e11 else value
    try:
        local = (APPLE_EPOCH + datetime.timedelta(seconds=secs)).astimezone()
        return local.strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return str(value)


def decode_attributed_body(data: bytes):
    """Best-effort text extraction from a typedstream attributedBody blob."""
    if not data:
        return None
    idx = data.find(b"NSString")
    if idx == -1:
        return None
    p = data.find(b"+", idx)
    if p == -1:
        return None
    p += 1
    if p >= len(data):
        return None
    marker = data[p]
    if marker == 0x81:            # 2-byte little-endian length
        length = int.from_bytes(data[p + 1:p + 3], "little"); start = p + 3
    elif marker == 0x82:          # 4-byte little-endian length
        length = int.from_bytes(data[p + 1:p + 5], "little"); start = p + 5
    else:                          # single-byte length
        length = marker; start = p + 1
    text = data[start:start + length].decode("utf-8", errors="replace").strip()
    return text or None


def sanitize(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._+@-]+", "_", name).strip("_")
    return name[:80] or "conversation"


def fetch_conversations(con: sqlite3.Connection):
    """Return [(chat_rowid, title, [message dicts])] ordered by latest activity."""
    cur = con.cursor()
    # Chats and their display identity.
    cur.execute("""
        SELECT ROWID,
               COALESCE(NULLIF(display_name,''), chat_identifier) AS title,
               chat_identifier
        FROM chat
    """)
    chats = {row[0]: {"title": row[1] or row[2] or "Unknown", "msgs": []}
             for row in cur.fetchall()}

    # All messages, with handle (other party) and chat membership.
    cur.execute("""
        SELECT cmj.chat_id, m.date, m.is_from_me, h.id AS handle, m.text,
               m.attributedBody, m.cache_has_attachments, m.service
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        LEFT JOIN handle h ON h.ROWID = m.handle_id
        ORDER BY m.date ASC
    """)
    for chat_id, date, is_from_me, handle, text, abody, has_att, service in cur.fetchall():
        if chat_id not in chats:
            continue
        body = text if (text and text.strip()) else decode_attributed_body(abody)
        chats[chat_id]["msgs"].append({
            "ts": apple_time(date),
            "raw": date or 0,
            "sender": "Me" if is_from_me else (handle or "Unknown"),
            "body": body or ("[attachment]" if has_att else "[no text]"),
            "attachment": bool(has_att),
            "service": service or "",
        })

    convos = [(cid, c["title"], c["msgs"]) for cid, c in chats.items() if c["msgs"]]
    convos.sort(key=lambda t: t[2][-1]["raw"], reverse=True)  # latest first
    return convos


def export_txt(convos, out_dir):
    index_lines = [f"# iPhone Messages export — {datetime.datetime.now():%Y-%m-%d %H:%M}",
                   f"# {len(convos)} conversations", ""]
    for cid, title, msgs in convos:
        fname = f"{sanitize(title)}.txt"
        index_lines.append(f"{len(msgs):>6} messages   {title}   -> {fname}")
        with open(os.path.join(out_dir, fname), "w", encoding="utf-8") as fh:
            fh.write(f"Conversation: {title}\n")
            fh.write(f"Messages: {len(msgs)}\n")
            fh.write("=" * 60 + "\n\n")
            for m in msgs:
                fh.write(f"[{m['ts']}] {m['sender']}: {m['body']}\n")
    with open(os.path.join(out_dir, "INDEX.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(index_lines) + "\n")


def export_csv(convos, out_dir):
    path = os.path.join(out_dir, "messages.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["conversation", "timestamp", "sender", "service",
                    "has_attachment", "body"])
        for cid, title, msgs in convos:
            for m in msgs:
                w.writerow([title, m["ts"], m["sender"], m["service"],
                            "yes" if m["attachment"] else "", m["body"]])


def main(argv):
    if len(argv) < 3:
        print("Usage: messages_export.py <sms.db> <out_dir> [--format txt|csv]",
              file=sys.stderr)
        return 2
    db_path, out_dir = argv[1], argv[2]
    fmt = "txt"
    if "--format" in argv:
        fmt = argv[argv.index("--format") + 1]
    if not os.path.isfile(db_path):
        print(f"ERROR: sms.db not found: {db_path}", file=sys.stderr)
        return 1

    # Open read-only so we can never alter the source database.
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        convos = fetch_conversations(con)
    finally:
        con.close()

    # JSON mode feeds the in-app viewer: one compact line to stdout, no files.
    if fmt == "json":
        out = []
        for _cid, title, msgs in convos:
            out.append({
                "title": title,
                "count": len(msgs),
                "last": msgs[-1]["ts"] if msgs else "",
                "messages": [{"ts": m["ts"], "sender": m["sender"],
                              "body": m["body"]} for m in msgs],
            })
        print(json.dumps(out, ensure_ascii=False))
        return 0

    os.makedirs(out_dir, exist_ok=True)
    total_msgs = sum(len(m) for _, _, m in convos)
    print(f"==> Parsed {total_msgs} messages in {len(convos)} conversations")
    if fmt == "csv":
        export_csv(convos, out_dir)
    else:
        export_txt(convos, out_dir)
    print(f"Conversations: {len(convos)}")
    print(f"Messages: {total_msgs}")
    print(f"==> Done — export in {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
