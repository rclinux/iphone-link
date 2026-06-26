#!/usr/bin/env python3
"""notes_export.py — turn an iOS NoteStore.sqlite into readable files.

Reads the Apple Notes database extracted from an *unencrypted* device backup and
writes one .txt per note (organised by folder) plus an index, or a single CSV.
Read-only on the input; never touches the device.

Usage:
    notes_export.py <NoteStore.sqlite> <out_dir> [--format txt|csv]

Modern Notes stores each note body in ZICNOTEDATA.ZDATA as a gzip- or zlib-
compressed protobuf. We decompress it and pull the note text out of the protobuf
(NoteStoreProto.document.note.note_text), the same shape of problem as the
Messages attributedBody decode.
"""

import csv
import datetime
import gzip
import json
import os
import re
import sqlite3
import sys
import zlib

# Notes timestamps are CFAbsoluteTime: seconds since 2001-01-01 UTC.
APPLE_EPOCH = datetime.datetime(2001, 1, 1, tzinfo=datetime.timezone.utc)


def apple_seconds(value) -> str:
    if not value:
        return ""
    try:
        local = (APPLE_EPOCH + datetime.timedelta(seconds=float(value))).astimezone()
        return local.strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return ""


def decompress(blob: bytes):
    """Apple Notes bodies are gzip or zlib (or raw deflate); try each."""
    for fn in (gzip.decompress,
               zlib.decompress,
               lambda b: zlib.decompress(b, -zlib.MAX_WBITS),
               lambda b: zlib.decompress(b, 16 + zlib.MAX_WBITS)):
        try:
            return fn(blob)
        except Exception:
            continue
    return None


def _read_varint(b, i):
    shift = 0
    val = 0
    while True:
        x = b[i]
        i += 1
        val |= (x & 0x7F) << shift
        if not (x & 0x80):
            break
        shift += 7
    return val, i


def _first_field(b, field_no):
    """Return the bytes of the first length-delimited field `field_no`, or None."""
    i, n = 0, len(b)
    while i < n:
        key, i = _read_varint(b, i)
        fn, wt = key >> 3, key & 7
        if wt == 0:
            _, i = _read_varint(b, i)
        elif wt == 2:
            ln, i = _read_varint(b, i)
            chunk = b[i:i + ln]
            i += ln
            if fn == field_no:
                return chunk
        elif wt == 5:
            i += 4
        elif wt == 1:
            i += 8
        else:
            break
    return None


def note_text(blob: bytes):
    """NoteStoreProto(2=document) -> Document(3=note) -> Note(2=note_text)."""
    dec = decompress(blob)
    if dec is None:
        return None
    doc = _first_field(dec, 2)
    if doc is None:
        return None
    note = _first_field(doc, 3)
    if note is None:
        return None
    txt = _first_field(note, 2)
    if txt is None:
        return None
    return txt.decode("utf-8", "replace")


def sanitize(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._+@ -]+", "_", name or "").strip().strip("_")
    return (name[:80] or "untitled")


def fetch_notes(con: sqlite3.Connection):
    """Return list of dicts: folder, title, created, modified, body (date-sorted)."""
    cur = con.cursor()
    # Only objects that are notes have ZNOTEDATA; skip ones marked for deletion.
    try:
        cur.execute("""
            SELECT n.ZTITLE1, n.ZCREATIONDATE1, n.ZMODIFICATIONDATE1,
                   f.ZTITLE2, d.ZDATA
            FROM ZICCLOUDSYNCINGOBJECT n
            JOIN ZICNOTEDATA d ON d.Z_PK = n.ZNOTEDATA
            LEFT JOIN ZICCLOUDSYNCINGOBJECT f ON f.Z_PK = n.ZFOLDER
            WHERE n.ZNOTEDATA IS NOT NULL
              AND (n.ZMARKEDFORDELETION IS NULL OR n.ZMARKEDFORDELETION = 0)
        """)
    except sqlite3.OperationalError:
        # Older schema without ZMARKEDFORDELETION.
        cur.execute("""
            SELECT n.ZTITLE1, n.ZCREATIONDATE1, n.ZMODIFICATIONDATE1,
                   f.ZTITLE2, d.ZDATA
            FROM ZICCLOUDSYNCINGOBJECT n
            JOIN ZICNOTEDATA d ON d.Z_PK = n.ZNOTEDATA
            LEFT JOIN ZICCLOUDSYNCINGOBJECT f ON f.Z_PK = n.ZFOLDER
            WHERE n.ZNOTEDATA IS NOT NULL
        """)
    notes = []
    for title, created, modified, folder, blob in cur.fetchall():
        body = note_text(bytes(blob)) if blob is not None else None
        notes.append({
            "folder": folder or "Notes",
            "title": (title or "").strip() or "Untitled",
            "created": apple_seconds(created),
            "modified": apple_seconds(modified),
            "modified_raw": modified or 0,
            "body": body if body is not None else "[note body could not be decoded]",
        })
    notes.sort(key=lambda x: x["modified_raw"], reverse=True)  # most recent first
    return notes


def export_txt(notes, out_dir):
    index = [f"# iPhone Notes export — {datetime.datetime.now():%Y-%m-%d %H:%M}",
             f"# {len(notes)} notes", ""]
    used = {}
    for note in notes:
        folder_dir = os.path.join(out_dir, sanitize(note["folder"]))
        os.makedirs(folder_dir, exist_ok=True)
        base = sanitize(note["title"])
        # Avoid collisions when two notes share a title.
        key = (folder_dir, base)
        used[key] = used.get(key, 0) + 1
        fname = f"{base}.txt" if used[key] == 1 else f"{base} ({used[key]}).txt"
        with open(os.path.join(folder_dir, fname), "w", encoding="utf-8") as fh:
            fh.write(f"Title:    {note['title']}\n")
            fh.write(f"Folder:   {note['folder']}\n")
            fh.write(f"Created:  {note['created']}\n")
            fh.write(f"Modified: {note['modified']}\n")
            fh.write("=" * 60 + "\n\n")
            fh.write(note["body"].rstrip() + "\n")
        index.append(f"{note['modified'][:10]}   {note['folder']}/{fname}")
    with open(os.path.join(out_dir, "INDEX.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(index) + "\n")


def export_csv(notes, out_dir):
    path = os.path.join(out_dir, "notes.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["folder", "title", "created", "modified", "body"])
        for note in notes:
            w.writerow([note["folder"], note["title"], note["created"],
                        note["modified"], note["body"]])


def main(argv):
    if len(argv) < 3:
        print("Usage: notes_export.py <NoteStore.sqlite> <out_dir> [--format txt|csv]",
              file=sys.stderr)
        return 2
    db_path, out_dir = argv[1], argv[2]
    fmt = argv[argv.index("--format") + 1] if "--format" in argv else "txt"
    if not os.path.isfile(db_path):
        print(f"ERROR: NoteStore.sqlite not found: {db_path}", file=sys.stderr)
        return 1

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        notes = fetch_notes(con)
    finally:
        con.close()

    # JSON mode feeds the in-app viewer: emit one compact line to stdout, no files.
    if fmt == "json":
        slim = [{k: n[k] for k in ("folder", "title", "created", "modified", "body")}
                for n in notes]
        print(json.dumps(slim, ensure_ascii=False))
        return 0

    os.makedirs(out_dir, exist_ok=True)
    decoded = sum(1 for n in notes if not n["body"].startswith("[note body"))
    print(f"==> Parsed {len(notes)} notes ({decoded} with text)")
    if fmt == "csv":
        export_csv(notes, out_dir)
    else:
        export_txt(notes, out_dir)
    print(f"Notes: {len(notes)}")
    print(f"==> Done — export in {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
