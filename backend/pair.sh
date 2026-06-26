#!/usr/bin/env bash
# pair.sh — manage the trust relationship between this host and the iPhone.
#
# Usage: pair.sh <pair|validate|unpair|list>
#   pair      create a pairing record (user must tap "Trust" on the unlocked phone)
#   validate  check the existing pairing is still valid
#   unpair    remove the pairing record from host and device
#   list      print connected device UDIDs, one per line
#
# Honours $IDEVICE_UDID to target a specific device.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$HERE/_common.sh"

need idevicepair libimobiledevice

action="${1:-validate}"

if [[ "$action" == "list" ]]; then
    step "Scanning for connected devices"
    idevice_id -l
    exit 0
fi

UDID="$(resolve_udid)"

case "$action" in
    pair)
        step "Requesting pairing — tap \"Trust\" on the unlocked iPhone if prompted"
        idevicepair -u "$UDID" pair
        ;;
    validate)
        step "Validating existing pairing"
        idevicepair -u "$UDID" validate
        ;;
    unpair)
        step "Removing pairing record"
        idevicepair -u "$UDID" unpair
        ;;
    *)
        die "Unknown action '$action' (use pair|validate|unpair|list)"
        ;;
esac
