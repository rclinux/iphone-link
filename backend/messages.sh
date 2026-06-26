#!/usr/bin/env bash
# messages.sh — export iPhone text messages to readable files (one-way, phone ->
# this system; the device is never modified).
#
# Usage:
#   messages.sh check                         report whether messages are exportable
#   messages.sh backup <backup_dir>           make/refresh a device backup (FULL the
#                                             first time: large and slow)
#   messages.sh export <backup_dir> <out_dir> [--format txt|csv]
#                                             parse the backup's sms.db -> out_dir
#   messages.sh view <backup_dir>             print conversations as one JSON line
#                                             (for the in-app viewer; no files)
#
# Messages live only inside a device backup (no AFC access), so a backup is
# required first. This tool supports UNENCRYPTED backups (WillEncrypt=false);
# encrypted backups would need the password + decryption and are reported as such.
# Honours $IDEVICE_UDID to target a specific device.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$HERE/_common.sh"

need idevicebackup2 libimobiledevice
need ideviceinfo libimobiledevice

UDID="$(resolve_udid)"
SMS_FILEID="3d0d7e5fb2ce288813306e4d4636395e047a3d28"  # SHA1 HomeDomain-Library/SMS/sms.db

encrypted() {
    [[ "$(ideviceinfo -u "$UDID" -q com.apple.mobile.backup -k WillEncrypt 2>/dev/null)" == "true" ]]
}

# Find sms.db inside a backup dir (modern layout: <dir>/<UDID>/3d/<fileid>).
find_sms_db() {
    local root="$1"
    local p="$root/$UDID/${SMS_FILEID:0:2}/$SMS_FILEID"
    [[ -f "$p" ]] && { printf '%s\n' "$p"; return 0; }
    p="$root/$UDID/$SMS_FILEID"                       # flat (very old) layout
    [[ -f "$p" ]] && { printf '%s\n' "$p"; return 0; }
    # Last resort: search.
    find "$root" -type f -name "$SMS_FILEID" 2>/dev/null | head -1
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
        if encrypted; then
            die "Backup encryption is ON. This tool reads unencrypted backups only."
        fi
        step "Backing up device (first run is a FULL backup — large and slow)"
        # idevicebackup2 prints "Progress: NN.N%" which runner.py parses as NN%.
        idevicebackup2 -u "$UDID" backup "$dir"
        step "Backup complete"
        ;;

    export)
        backup_dir="${2:-}"
        out_dir="${3:-}"
        [[ -n "$backup_dir" && -n "$out_dir" ]] || die "export needs <backup_dir> <out_dir>."
        [[ -d "$backup_dir" ]] || die "Backup directory not found: $backup_dir"
        if encrypted; then
            die "Backup encryption is ON; cannot read sms.db without decryption."
        fi
        step "Locating sms.db in the backup"
        sms="$(find_sms_db "$backup_dir")"
        [[ -n "$sms" && -f "$sms" ]] || die "sms.db not found. Run 'backup' first (into the same directory)."
        mkdir -p "$out_dir"
        step "Exporting conversations"
        python3 "$HERE/messages_export.py" "$sms" "$out_dir" "${@:4}"
        ;;

    view)
        backup_dir="${2:-}"
        [[ -n "$backup_dir" ]] || die "view needs <backup_dir>."
        [[ -d "$backup_dir" ]] || die "Backup directory not found: $backup_dir"
        encrypted && die "Backup encryption is ON; cannot read sms.db without decryption."
        sms="$(find_sms_db "$backup_dir")"
        [[ -n "$sms" && -f "$sms" ]] || die "sms.db not found. Run 'backup' first."
        # Clean JSON only on stdout so the GUI can parse it directly.
        python3 "$HERE/messages_export.py" "$sms" - --format json
        ;;

    *)
        die "Unknown action '$action' (use check|backup|export|view)."
        ;;
esac
