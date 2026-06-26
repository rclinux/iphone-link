#!/usr/bin/env bash
#
# install.sh — universal installer for iPhone Link.
#
# Detects the distribution family from /etc/os-release, installs the runtime
# dependencies with the matching package manager, and copies the application into
# a standard system layout (/usr/share/iphone-link, /usr/bin/iphone-link, the
# desktop entry and icon).
#
# Unlike the sibling Disk Recovery Tool, iPhone Link does NOT need polkit/root at
# runtime — it talks to the phone through your user's usbmuxd. Root is only needed
# for THIS installer (it writes under /usr and installs packages).
#
# Supported families:  arch (pacman) · debian (apt) · fedora (dnf)
#
# Usage:   sudo ./install.sh
#
set -euo pipefail

# --------------------------------------------------------------------------- #
# Output helpers.
# --------------------------------------------------------------------------- #
if [[ -t 1 ]]; then
  C_RESET=$'\e[0m'; C_BOLD=$'\e[1m'; C_BLUE=$'\e[34m'; C_RED=$'\e[31m'; C_GREEN=$'\e[32m'; C_YEL=$'\e[33m'
else
  C_RESET=""; C_BOLD=""; C_BLUE=""; C_RED=""; C_GREEN=""; C_YEL=""
fi
msg()  { printf '%s==>%s %s\n' "$C_BLUE$C_BOLD"  "$C_RESET" "$*"; }
ok()   { printf '%s==>%s %s\n' "$C_GREEN$C_BOLD" "$C_RESET" "$*"; }
warn() { printf '%s[!]%s %s\n' "$C_YEL$C_BOLD"   "$C_RESET" "$*"; }
die()  { printf '%s[x]%s %s\n' "$C_RED$C_BOLD"   "$C_RESET" "$*" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# 0. Must be root (writes under /usr and installs packages).
# --------------------------------------------------------------------------- #
[[ "$(id -u)" -eq 0 ]] || die "Run as root: sudo $0"

SRC="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[[ -d "$SRC/iphone-gui" && -d "$SRC/backend" ]] \
  || die "Run this from the project root (iphone-gui/ and backend/ not found)."

# --------------------------------------------------------------------------- #
# 1. Detect the distribution family. Check ID first, then ID_LIKE, so derivatives
#    (Mint→debian, CachyOS→arch, …) map cleanly.
# --------------------------------------------------------------------------- #
[[ -r /etc/os-release ]] || die "/etc/os-release not found — cannot detect distro."
# shellcheck source=/dev/null
. /etc/os-release
haystack=" ${ID:-} ${ID_LIKE:-} "
FAMILY=""
case "$haystack" in
  *" arch "*|*" archlinux "*|*" cachyos "*) FAMILY=arch ;;
  *" debian "*|*" ubuntu "*)                FAMILY=debian ;;
  *" fedora "*|*" rhel "*|*" centos "*)     FAMILY=fedora ;;
esac
[[ -n "$FAMILY" ]] || die "Unsupported distro (ID='${ID:-?}' ID_LIKE='${ID_LIKE:-?}'). Supported: arch, debian, fedora."
msg "Detected distro family: $FAMILY  (${PRETTY_NAME:-$ID})"

# --------------------------------------------------------------------------- #
# 2. Per-family package manager + dependency names. The set of needs is the same
#    across distros; only the names differ. UxPlay (AirPlay receiver) is OPTIONAL
#    and handled separately because it isn't in every default repo.
# --------------------------------------------------------------------------- #
case "$FAMILY" in
  arch)
    PM_INSTALL=(pacman -S --needed --noconfirm)
    PKGS=(libimobiledevice usbmuxd ifuse fuse3 avahi coreutils
          gst-plugins-base gst-plugins-good gst-plugins-bad
          python python-gobject gtk4)
    UXPLAY_PKG=uxplay
    ;;
  debian)
    export DEBIAN_FRONTEND=noninteractive
    PM_INSTALL=(apt-get install -y)
    apt-get update -qq || true
    PKGS=(libimobiledevice-utils usbmuxd ifuse fuse3 avahi-daemon coreutils
          gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good
          gstreamer1.0-plugins-bad gstreamer1.0-libav
          python3 python3-gi gir1.2-gtk-4.0 libgtk-4-1)
    UXPLAY_PKG=uxplay
    ;;
  fedora)
    PM_INSTALL=(dnf install -y)
    PKGS=(libimobiledevice usbmuxd ifuse fuse avahi coreutils
          gstreamer1-plugins-base gstreamer1-plugins-good
          gstreamer1-plugins-bad-free
          python3 python3-gobject gtk4)
    UXPLAY_PKG=uxplay
    ;;
esac

msg "Installing core dependencies (${#PKGS[@]} packages)..."
"${PM_INSTALL[@]}" "${PKGS[@]}"

# UxPlay is only needed for the Media → AirPlay receiver. Don't fail the whole
# install if the distro's repos don't carry it.
msg "Installing UxPlay (optional — AirPlay receiver)..."
if "${PM_INSTALL[@]}" "$UXPLAY_PKG" 2>/dev/null; then
  ok "UxPlay installed."
else
  warn "Could not install '$UXPLAY_PKG' from the default repos."
  warn "iPhone Link works without it; only the Media → AirPlay receiver is disabled."
  warn "On Arch it's in the AUR; on Fedora try a COPR; or build from https://github.com/FDH2/UxPlay."
fi

# Make sure the per-user services the app relies on are enabled.
systemctl enable --now usbmuxd 2>/dev/null || true
systemctl enable --now avahi-daemon 2>/dev/null || true

# --------------------------------------------------------------------------- #
# 3. Install the application files into the layout the launcher + config.py
#    already look for (/usr/share/iphone-link).
# --------------------------------------------------------------------------- #
SHARE=/usr/share/iphone-link
ICON_REL=icons/hicolor/scalable/apps/io.github.rcraig57.iPhoneLink.svg

msg "Installing application files..."
install -dm755 "$SHARE/src"
install -m644  "$SRC"/iphone-gui/src/*.py "$SRC"/iphone-gui/src/style.css "$SHARE/src/"

install -dm755 "$SHARE/backend"
install -m755  "$SRC"/backend/*.sh "$SHARE/backend/"
install -m755  "$SRC"/backend/*.py "$SHARE/backend/"

install -Dm644 "$SRC/iphone-gui/data/$ICON_REL" "$SHARE/data/$ICON_REL"

install -Dm755 "$SRC/iphone-gui/bin/iphone-link" /usr/bin/iphone-link
install -Dm644 "$SRC/iphone-gui/data/iphone-link.desktop" /usr/share/applications/iphone-link.desktop
install -Dm644 "$SRC/iphone-gui/data/$ICON_REL" "/usr/share/$ICON_REL"

# --------------------------------------------------------------------------- #
# 4. Refresh icon + desktop caches (best-effort).
# --------------------------------------------------------------------------- #
gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null || true
update-desktop-database -q 2>/dev/null || true

ok "iPhone Link installed."
echo
echo "  Launch:  iphone-link   (or from your application menu)"
echo "  Do NOT run it with sudo — it uses your user's usbmuxd."
echo "  Connect the iPhone by USB, unlock it, and tap Trust the first time."
echo "  Uninstall:  sudo $SRC/uninstall.sh"
