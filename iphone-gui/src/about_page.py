"""About / Help page."""

import gi

gi.require_version("Gtk", "4.0")

import config  # noqa: E402
from gi.repository import Gtk  # noqa: E402
from widgets import make_intro, make_title  # noqa: E402

ABOUT = (
    f"<b>{config.APP_NAME}</b>  v{config.APP_VERSION}\n\n"
    "Securely link your iPhone to this Linux system to share documents and photos, "
    "read and export messages and notes, and play the iPhone's media on the PC. "
    "It is a thin wrapper: every operation runs the same audited "
    "shell scripts in <tt>backend/</tt> that you can run from a terminal, built on "
    "<b>libimobiledevice</b>, so the GUI and CLI can never drift apart.\n\n"
    "<b>What it does</b>\n"
    "• <b>Device</b> — shows identity, pairing/trust, battery and storage read "
    "live from the phone, and manages pairing (Pair / Validate / Unpair).\n"
    "• <b>Photos</b> — copies the camera roll (DCIM) to a folder you choose, with "
    "an incremental (skip-already-copied) mode. Read-only ifuse mount.\n"
    "• <b>Documents</b> — lists apps that enable File Sharing and copies files "
    "in and out of their document folders (the only feature that writes to the phone).\n"
    "• <b>Messages</b> — browse and read your conversations in-app, and export them "
    "to text or CSV from a device backup (reads <tt>sms.db</tt>, decoding modern "
    "attributed-body text).\n"
    "• <b>Notes</b> — browse and read your notes in-app, and export them to one text "
    "file per note (grouped by folder) or CSV, from the same backup (decodes the "
    "compressed note bodies).\n"
    "• <b>Media</b> — plays camera-roll videos locally, and runs an <b>AirPlay</b> "
    "receiver (UxPlay) so the iPhone can mirror its screen and audio to this PC; pick "
    "this PC from Screen Mirroring on the iPhone.\n\n"
    "<i>Notifications and clipboard sync are out of scope: iOS exposes no public "
    "API to mirror them over USB without a companion app.</i>\n\n"
    "<b>Safety</b>\n"
    "• Nothing is read from the phone until it is connected, unlocked, and you "
    "tap <b>Trust</b>.\n"
    "• The GUI never reimplements device logic; it only builds a command line and "
    "streams the script's output, so what it does is auditable.\n"
    "• File copies are explicit and go only to folders you pick.\n\n"
    "Look and feel inspired by Erik Dubois' Arch Linux Tweak Tool, matching the "
    "sibling Disk Recovery Tool."
)


class AboutPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(18)
        self.set_margin_bottom(18)
        self.set_margin_start(18)
        self.set_margin_end(18)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        icon_path = config.icon_file()
        if icon_path.is_file():
            icon = Gtk.Image.new_from_file(str(icon_path))
            icon.set_pixel_size(48)
            header.append(icon)
        header.append(make_title("About"))
        header.set_valign(Gtk.Align.CENTER)
        self.append(header)

        intro = make_intro(ABOUT)
        intro.set_vexpand(True)
        intro.set_valign(Gtk.Align.START)
        self.append(intro)

        info = Gtk.Label(xalign=0)
        info.set_wrap(True)
        info.set_markup(f"<small>Backend scripts: <tt>{config.backend_dir()}</tt></small>")
        self.append(info)
