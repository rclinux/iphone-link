#!/usr/bin/env bash
# Shared helpers for the iPhone Link backend scripts.
#
# The GUI is a thin wrapper: it only builds a command line and streams the
# output of these scripts. Keeping all device logic here means the CLI and GUI
# can never drift. Every script sources this file.

set -euo pipefail

# Emit a "step" line the GUI recognises (runner.py strips the "==>" prefix and
# shows it above the progress area). Use for human-facing progress milestones.
step() { printf '==> %s\n' "$*"; }

# Fatal error: print to stderr and exit non-zero so the GUI marks the job failed.
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# Verify a required command exists, with a helpful message naming the package.
need() {
    command -v "$1" >/dev/null 2>&1 || die "Required tool '$1' not found. Install '${2:-$1}'."
}

# Resolve the target device UDID. Honours $IDEVICE_UDID if set; otherwise picks
# the single connected device, or fails clearly if zero / more than one.
resolve_udid() {
    need idevice_id libimobiledevice
    if [[ -n "${IDEVICE_UDID:-}" ]]; then
        printf '%s\n' "$IDEVICE_UDID"
        return 0
    fi
    local ids
    mapfile -t ids < <(idevice_id -l 2>/dev/null || true)
    case "${#ids[@]}" in
        0) die "No iPhone detected. Connect and unlock the device, then tap Trust." ;;
        1) printf '%s\n' "${ids[0]}" ;;
        *) die "Multiple devices connected; set IDEVICE_UDID to choose one: ${ids[*]}" ;;
    esac
}
