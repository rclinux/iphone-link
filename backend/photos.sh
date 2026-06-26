#!/usr/bin/env bash
# photos.sh — read-only access to the iPhone camera roll (DCIM) over AFC.
#
# Usage:
#   photos.sh list                 summarise photos/videos on the device
#   photos.sh copy <dest> [--new]  copy DCIM files into <dest>/iPhone-Photos
#                                   --new skips files already present (size match)
#
# Mounts the device with ifuse, works under DCIM, and ALWAYS unmounts on exit.
# Originals on the phone are never modified or deleted.
# Honours $IDEVICE_UDID to target a specific device.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$HERE/_common.sh"

need ifuse libimobiledevice
need fusermount fuse

UDID="$(resolve_udid)"

MNT="$(mktemp -d /tmp/iphone-link-dcim.XXXXXX)"
cleanup() {
    if mountpoint -q "$MNT" 2>/dev/null; then
        fusermount -u "$MNT" 2>/dev/null || true
    fi
    rmdir "$MNT" 2>/dev/null || true
}
trap cleanup EXIT

step "Mounting camera roll (read-only)"
ifuse -o ro -u "$UDID" "$MNT" 2>/dev/null || ifuse -u "$UDID" "$MNT"

DCIM="$MNT/DCIM"
[[ -d "$DCIM" ]] || die "No DCIM folder on the device (is it unlocked and trusted?)."

# Collect the media files once.
mapfile -t FILES < <(find "$DCIM" -type f \
    \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.heic' -o -iname '*.png' \
       -o -iname '*.gif' -o -iname '*.mov' -o -iname '*.mp4' -o -iname '*.m4v' \
       -o -iname '*.aae' -o -iname '*.dng' \) 2>/dev/null | sort)
TOTAL="${#FILES[@]}"

action="${1:-list}"

if [[ "$action" == "list" ]]; then
    photos=$(printf '%s\n' "${FILES[@]}" | grep -icE '\.(jpg|jpeg|heic|png|gif|dng)$' || true)
    videos=$(printf '%s\n' "${FILES[@]}" | grep -icE '\.(mov|mp4|m4v)$' || true)
    bytes=$(printf '%s\0' "${FILES[@]}" | du -ch --files0-from=- 2>/dev/null | tail -1 | cut -f1 || echo "?")
    echo "TotalFiles: $TOTAL"
    echo "Photos: $photos"
    echo "Videos: $videos"
    echo "TotalSize: ${bytes:-?}"
    step "Done"
    exit 0
fi

if [[ "$action" == "copy" ]]; then
    dest="${2:-}"
    [[ -n "$dest" ]] || die "copy needs a destination folder."
    [[ -d "$dest" ]] || die "Destination folder does not exist: $dest"
    skip_existing=0
    [[ "${3:-}" == "--new" ]] && skip_existing=1

    outdir="$dest/iPhone-Photos"
    mkdir -p "$outdir"
    (( TOTAL > 0 )) || { echo "No media files found in DCIM."; step "Done"; exit 0; }

    step "Copying $TOTAL files to $outdir"
    copied=0; skipped=0; i=0
    for f in "${FILES[@]}"; do
        i=$((i+1))
        base="$(basename "$f")"
        target="$outdir/$base"
        if (( skip_existing )) && [[ -f "$target" ]] \
            && [[ "$(stat -c%s "$f" 2>/dev/null)" == "$(stat -c%s "$target" 2>/dev/null)" ]]; then
            skipped=$((skipped+1))
        else
            cp -p "$f" "$target" && copied=$((copied+1))
        fi
        # Progress as a percentage the GUI parses.
        printf '%d%%\n' $(( i * 100 / TOTAL ))
    done
    echo "Copied: $copied  Skipped: $skipped  Total: $TOTAL"
    step "Done — files in $outdir"
    exit 0
fi

die "Unknown action '$action' (use list|copy)."
