#!/usr/bin/env bash
# notes.sh — export iPhone Notes to readable files (one-way, phone -> this system;
# the device is never modified).
#
# Usage:
#   notes.sh check                          report whether notes are exportable
#   notes.sh backup <backup_dir>            make/refresh a device backup (FULL the
#                                           first time: large and slow)
#   notes.sh export <backup_dir> <out_dir> [--format txt|csv]
#                                           parse the backup's NoteStore.sqlite
#   notes.sh view <backup_dir>              print notes as one JSON line (for the
#                                           in-app viewer; nothing written to disk)
#
# Notes live only inside a device backup (no AFC access). The SAME backup serves
# the Messages page, so if you've already backed up there you can export straight
# away. Unencrypted backups only.
# Honours $IDEVICE_UDID to target a specific device.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$HERE/_common.sh"

need idevicebackup2 libimobiledevice
need ideviceinfo libimobiledevice

UDID="$(resolve_udid)"
# SHA1 of AppDomainGroup-group.com.apple.notes-NoteStore.sqlite (modern Notes db).
NOTES_FILEID="4f98687d8ab0d6d1a371110e6b7300f6e465bef2"

encrypted() {
    [[ "$(ideviceinfo -u "$UDID" -q com.apple.mobile.backup -k WillEncrypt 2>/dev/null)" == "true" ]]
}

find_notestore() {
    local root="$1"
    local p="$root/$UDID/${NOTES_FILEID:0:2}/$NOTES_FILEID"
    [[ -f "$p" ]] && { printf '%s\n' "$p"; return 0; }
    p="$root/$UDID/$NOTES_FILEID"
    [[ -f "$p" ]] && { printf '%s\n' "$p"; return 0; }
    find "$root" -type f -name "$NOTES_FILEID" 2>/dev/null | head -1
}

action="${1:-check}"

case "$action" in
    check)
        if encrypted; then
            echo "Encrypted: yes"
            echo "Exportable: no (encrypted backups need the password + decryption)"
        else
            echo "Encrypted: no"
            echo "Exportable: yes"
        fi
        step "Done"
        ;;

    backup)
        dir="${2:-}"
        [[ -n "$dir" ]] || die "backup needs a target directory."
        mkdir -p "$dir"
        encrypted && die "Backup encryption is ON. This tool reads unencrypted backups only."
        step "Backing up device (first run is a FULL backup — large and slow)"
        idevicebackup2 -u "$UDID" backup "$dir"
        step "Backup complete"
        ;;

    export)
        backup_dir="${2:-}"
        out_dir="${3:-}"
        [[ -n "$backup_dir" && -n "$out_dir" ]] || die "export needs <backup_dir> <out_dir>."
        [[ -d "$backup_dir" ]] || die "Backup directory not found: $backup_dir"
        encrypted && die "Backup encryption is ON; cannot read NoteStore.sqlite without decryption."
        step "Locating NoteStore.sqlite in the backup"
        ns="$(find_notestore "$backup_dir")"
        [[ -n "$ns" && -f "$ns" ]] || die "NoteStore.sqlite not found. Run 'backup' first (into the same directory)."
        mkdir -p "$out_dir"
        step "Exporting notes"
        python3 "$HERE/notes_export.py" "$ns" "$out_dir" "${@:4}"
        ;;

    view)
        backup_dir="${2:-}"
        [[ -n "$backup_dir" ]] || die "view needs <backup_dir>."
        [[ -d "$backup_dir" ]] || die "Backup directory not found: $backup_dir"
        encrypted && die "Backup encryption is ON; cannot read NoteStore.sqlite without decryption."
        ns="$(find_notestore "$backup_dir")"
        [[ -n "$ns" && -f "$ns" ]] || die "NoteStore.sqlite not found. Run 'backup' first."
        # Clean JSON only on stdout (no step lines) so the GUI can parse it directly.
        python3 "$HERE/notes_export.py" "$ns" - --format json
        ;;

    *)
        die "Unknown action '$action' (use check|backup|export|view)."
        ;;
esac
