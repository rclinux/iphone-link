#!/usr/bin/env bash
# media.sh — receive the iPhone's AirPlay (screen + audio) on this PC via UxPlay.
#
# Usage:
#   media.sh check                 verify uxplay + mDNS + gstreamer are ready
#   media.sh start [options]       run the AirPlay receiver (until stopped)
#       --name "NAME"   receiver name shown in the iPhone's AirPlay menu
#       --fullscreen    start the mirror window full-screen
#       --pin [NNNN]    require a PIN to connect (random if NNNN omitted)
#   media.sh list-videos           list camera-roll videos (bytes<TAB>name)
#   media.sh play <name>           play one camera-roll video locally (gst-play)
#
# `start` runs the AirPlay receiver (iPhone -> this PC). `list-videos`/`play`
# read the camera roll over a read-only ifuse mount and never modify the device.
# Long-running actions stream their log; the GUI's Stop/Cancel sends SIGTERM.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$HERE/_common.sh"

action="${1:-check}"; shift || true

avahi_up() {
    pgrep -x avahi-daemon >/dev/null 2>&1 \
        || systemctl is-active --quiet avahi-daemon 2>/dev/null
}

if [[ "$action" == "check" ]]; then
    ok=1
    if command -v uxplay >/dev/null 2>&1; then
        echo "UxPlay: $(uxplay -v 2>&1 | head -1)"
    else
        echo "UxPlay: MISSING (install the 'uxplay' package)"; ok=0
    fi
    if command -v gst-launch-1.0 >/dev/null 2>&1; then
        echo "GStreamer: $(gst-launch-1.0 --version | head -1 | awk '{print $NF}')"
    else
        echo "GStreamer: MISSING (install gstreamer1.0 plugins)"; ok=0
    fi
    if avahi_up; then
        echo "mDNS (avahi): running"
    else
        echo "mDNS (avahi): NOT running (start avahi-daemon so the iPhone can discover this PC)"; ok=0
    fi
    [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] && echo "Display: yes" || { echo "Display: none"; ok=0; }
    if (( ok )); then echo "Ready: yes"; else echo "Ready: no"; fi
    step "Done"
    exit 0
fi

if [[ "$action" == "start" ]]; then
    need uxplay uxplay
    avahi_up || die "avahi-daemon is not running; the iPhone can't discover this receiver."

    name="iPhone Link @ $(hostname)"
    args=()
    while (( $# )); do
        case "$1" in
            --name)       name="${2:-$name}"; shift 2 ;;
            --fullscreen) args+=("-fs"); shift ;;
            --pin)        # optional 4-digit code follows; else random pin
                if [[ "${2:-}" =~ ^[0-9]{4}$ ]]; then args+=("-pin${2}"); shift 2
                else args+=("-pin"); shift; fi ;;
            *) die "Unknown option: $1" ;;
        esac
    done

    step "Starting AirPlay receiver \"$name\""
    echo "On the iPhone: open Control Center, tap Screen Mirroring, and pick \"$name\"."
    echo "Press Stop (or close this) to shut the receiver down."
    # stdbuf forces line-buffering so UxPlay's log streams live to the GUI (it
    # block-buffers stdout when it's a pipe). exec so SIGTERM reaches uxplay.
    if command -v stdbuf >/dev/null 2>&1; then
        exec stdbuf -oL -eL uxplay -n "$name" "${args[@]}"
    fi
    exec uxplay -n "$name" "${args[@]}"
fi

# -- camera-roll video browse & play ----------------------------------------- #
VIDEO_EXTS='-iname *.mov -o -iname *.mp4 -o -iname *.m4v'

mount_dcim() {
    local mnt="$1"
    ifuse -o ro "$mnt" 2>/dev/null || ifuse "$mnt"
}

if [[ "$action" == "list-videos" ]]; then
    need ifuse libimobiledevice
    need fusermount fuse
    MNT="$(mktemp -d /tmp/iphone-link-vid.XXXXXX)"
    trap 'mountpoint -q "$MNT" && { fusermount -u "$MNT" 2>/dev/null || fusermount -uz "$MNT" 2>/dev/null; }; rmdir "$MNT" 2>/dev/null || true' EXIT
    mount_dcim "$MNT"
    [[ -d "$MNT/DCIM" ]] || die "No DCIM folder (is the phone unlocked and trusted?)."
    count=0
    while IFS= read -r -d '' f; do
        printf '%s\t%s\n' "$(stat -c%s "$f" 2>/dev/null || echo 0)" "$(basename "$f")"
        count=$((count+1))
    done < <(find "$MNT/DCIM" -type f \( -iname '*.mov' -o -iname '*.mp4' -o -iname '*.m4v' \) -print0 2>/dev/null | sort -z)
    echo "Videos: $count"
    exit 0
fi

if [[ "$action" == "play" ]]; then
    name="${1:-}"
    [[ -n "$name" ]] || die "play needs a video file name."
    need ifuse libimobiledevice
    need fusermount fuse
    command -v gst-play-1.0 >/dev/null 2>&1 || command -v xdg-open >/dev/null 2>&1 \
        || die "No player found (need gst-play-1.0 or xdg-open)."
    MNT="$(mktemp -d /tmp/iphone-link-vid.XXXXXX)"
    trap 'mountpoint -q "$MNT" && { fusermount -u "$MNT" 2>/dev/null || fusermount -uz "$MNT" 2>/dev/null; }; rmdir "$MNT" 2>/dev/null || true' EXIT
    mount_dcim "$MNT"
    # Match by basename so the GUI only needs to pass the file name.
    file="$(find "$MNT/DCIM" -type f -name "$name" 2>/dev/null | head -1)"
    [[ -n "$file" && -f "$file" ]] || die "Video not found in camera roll: $name"
    step "Playing $name"
    echo "Close the player window (or press Stop) to finish."
    if command -v gst-play-1.0 >/dev/null 2>&1; then
        gst-play-1.0 --quiet "$file" &
    else
        xdg-open "$file" &
    fi
    PLAYER_PID=$!
    # Forward Stop (SIGTERM) to the player, then the EXIT trap unmounts.
    trap 'kill -TERM $PLAYER_PID 2>/dev/null || true' TERM INT
    wait "$PLAYER_PID" 2>/dev/null || true
    step "Playback finished"
    exit 0
fi

die "Unknown action '$action' (use check|start|list-videos|play)."
