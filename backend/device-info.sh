#!/usr/bin/env bash
# device-info.sh — report the connected iPhone's identity, pairing, power and
# storage as "Key: Value" lines the Device page parses and displays.
#
# Usage: device-info.sh
# Honours $IDEVICE_UDID to target a specific device.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$HERE/_common.sh"

need ideviceinfo libimobiledevice
need idevicepair libimobiledevice

UDID="$(resolve_udid)"

# A single key from a domain (or the default domain). Empty string on failure so
# one missing value never aborts the whole report.
info() { ideviceinfo -u "$UDID" "$@" 2>/dev/null || true; }

echo "UDID: $UDID"
echo "DeviceName: $(info -k DeviceName)"
echo "ProductType: $(info -k ProductType)"
echo "ProductVersion: $(info -k ProductVersion)"
echo "BuildVersion: $(info -k BuildVersion)"
echo "DeviceClass: $(info -k DeviceClass)"
echo "CPUArchitecture: $(info -k CPUArchitecture)"
echo "SerialNumber: $(info -k SerialNumber)"
echo "WiFiAddress: $(info -k WiFiAddress)"

# Pairing / trust status.
if idevicepair -u "$UDID" validate >/dev/null 2>&1; then
    echo "Paired: yes"
else
    echo "Paired: no"
fi

# Battery (domain com.apple.mobile.battery).
echo "BatteryLevel: $(info -q com.apple.mobile.battery -k BatteryCurrentCapacity)"
charging="$(info -q com.apple.mobile.battery -k BatteryIsCharging)"
echo "Charging: ${charging:-unknown}"

# Storage (domain com.apple.disk_usage), reported in bytes -> GiB with one decimal.
total="$(info -q com.apple.disk_usage -k TotalDataCapacity)"
avail="$(info -q com.apple.disk_usage -k TotalDataAvailable)"
to_gib() { [[ -n "$1" && "$1" =~ ^[0-9]+$ ]] && awk -v b="$1" 'BEGIN{printf "%.1f", b/1073741824}' || echo ""; }
echo "StorageTotalGiB: $(to_gib "$total")"
echo "StorageFreeGiB: $(to_gib "$avail")"
