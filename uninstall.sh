#!/usr/bin/env bash
#
# uninstall.sh — remove the files install.sh placed on the system.
#
# It does NOT remove the dependency packages (libimobiledevice, ifuse, gtk4,
# uxplay, …) — those may be wanted by other software, so removing them is left to
# you. It also leaves any device backups you created (e.g. idevicebackup2_folder).
#
set -euo pipefail

[[ "$(id -u)" -eq 0 ]] || { echo "Run as root: sudo $0" >&2; exit 1; }

rm -rf /usr/share/iphone-link
rm -f  /usr/bin/iphone-link
rm -f  /usr/share/applications/iphone-link.desktop
rm -f  /usr/share/icons/hicolor/scalable/apps/io.github.rcraig57.iPhoneLink.svg

gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null || true
update-desktop-database -q 2>/dev/null || true

echo "iPhone Link removed. (Dependency packages and your backups were left in place.)"
