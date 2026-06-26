#!/usr/bin/env bash
# documents.sh — move files in and out of an iPhone app's File-Sharing folder.
#
# Usage:
#   documents.sh list                     list apps that enable File Sharing
#   documents.sh browse <bundle_id>       list the files in that app's folder
#   documents.sh pull   <bundle_id> <dest>     copy app files -> <dest>/<App>-Documents
#   documents.sh push   <bundle_id> <file...>  copy local file(s) -> app's folder
#
# Mounts a single app's documents container with `ifuse --documents` and ALWAYS
# unmounts on exit. Only the chosen app's sandbox is touched. `push` writes to the
# device; `list`/`browse`/`pull` are read-only.
# Honours $IDEVICE_UDID to target a specific device.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$HERE/_common.sh"

need ifuse libimobiledevice
need fusermount fuse

UDID="$(resolve_udid)"

# Map a bundle id -> display name from `ifuse --list-apps`, or echo the bundle id.
app_name() {
    local bundle="$1"
    ifuse --list-apps -u "$UDID" 2>/dev/null \
        | awk -F', ' -v b="$bundle" '$1==b {
            name=$3; gsub(/^"|"$/,"",name); print name; found=1; exit
          } END { if (!found) print "" }'
}

# Filesystem-safe folder name.
sanitize() { printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_'; }

mount_app() {
    local bundle="$1" mnt="$2" ro="${3:-}"
    if [[ "$ro" == "ro" ]]; then
        ifuse -o ro --documents "$bundle" -u "$UDID" "$mnt" 2>/dev/null \
            || ifuse --documents "$bundle" -u "$UDID" "$mnt"
    else
        ifuse --documents "$bundle" -u "$UDID" "$mnt"
    fi
}

action="${1:-list}"

# ---- list ------------------------------------------------------------------- #
if [[ "$action" == "list" ]]; then
    step "Listing apps with File Sharing enabled"
    # Emit "bundle_id<TAB>Display Name" so the GUI can parse it cleanly.
    ifuse --list-apps -u "$UDID" 2>/dev/null | while IFS= read -r line; do
        bundle="${line%%,*}"
        name="${line##*, }"; name="${name%\"}"; name="${name#\"}"
        [[ -n "$bundle" ]] && printf '%s\t%s\n' "$bundle" "$name"
    done
    step "Done"
    exit 0
fi

BUNDLE="${2:-}"
[[ -n "$BUNDLE" ]] || die "$action needs an app bundle id."

MNT="$(mktemp -d /tmp/iphone-link-docs.XXXXXX)"
cleanup() {
    if mountpoint -q "$MNT" 2>/dev/null; then
        # Lazy unmount as a fallback if a handle is briefly still busy.
        fusermount -u "$MNT" 2>/dev/null || fusermount -uz "$MNT" 2>/dev/null || true
    fi
    rmdir "$MNT" 2>/dev/null || true
}
trap cleanup EXIT

NAME="$(app_name "$BUNDLE")"; NAME="${NAME:-$BUNDLE}"

# ---- browse (read-only) ----------------------------------------------------- #
if [[ "$action" == "browse" ]]; then
    step "Reading $NAME documents"
    mount_app "$BUNDLE" "$MNT" ro
    count=0
    while IFS= read -r -d '' f; do
        rel="${f#"$MNT"/}"
        sz="$(stat -c%s "$f" 2>/dev/null || echo 0)"
        printf '%s\t%s\n' "$sz" "$rel"
        count=$((count+1))
    done < <(find "$MNT" -type f -print0 2>/dev/null | sort -z)
    echo "Files: $count"
    step "Done"
    exit 0
fi

# ---- pull (read-only copy device -> host) ----------------------------------- #
if [[ "$action" == "pull" ]]; then
    dest="${3:-}"
    [[ -n "$dest" ]] || die "pull needs a destination folder."
    [[ -d "$dest" ]] || die "Destination folder does not exist: $dest"
    step "Reading $NAME documents"
    mount_app "$BUNDLE" "$MNT" ro

    mapfile -t FILES < <(find "$MNT" -type f 2>/dev/null | sort)
    total="${#FILES[@]}"
    outdir="$dest/$(sanitize "$NAME")-Documents"
    mkdir -p "$outdir"
    (( total > 0 )) || { echo "No files in $NAME's folder."; step "Done"; exit 0; }

    step "Copying $total file(s) to $outdir"
    i=0
    for f in "${FILES[@]}"; do
        i=$((i+1))
        rel="${f#"$MNT"/}"
        mkdir -p "$outdir/$(dirname "$rel")"
        cp -p "$f" "$outdir/$rel"
        printf '%d%%\n' $(( i * 100 / total ))
    done
    echo "Copied: $total file(s)"
    step "Done — files in $outdir"
    exit 0
fi

# ---- push (write host -> device) -------------------------------------------- #
if [[ "$action" == "push" ]]; then
    shift 2  # drop "push" and bundle; the rest are local files
    (( $# > 0 )) || die "push needs at least one local file."
    for src in "$@"; do
        [[ -f "$src" ]] || die "Not a file: $src"
    done
    step "Opening $NAME documents (read-write)"
    mount_app "$BUNDLE" "$MNT"
    n=0; total=$#
    for src in "$@"; do
        n=$((n+1))
        base="$(basename "$src")"
        # Plain cp (no -p): AFC can't take ownership/timestamps, and -p would
        # return non-zero after copying the data, tripping `set -e`.
        cp "$src" "$MNT/$base"
        echo "Pushed: $base"
        printf '%d%%\n' $(( n * 100 / total ))
    done
    echo "Pushed: $total file(s) to $NAME"
    step "Done"
    exit 0
fi

die "Unknown action '$action' (use list|browse|pull|push)."
