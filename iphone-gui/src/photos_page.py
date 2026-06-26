"""Photos page — copy the iPhone camera roll (DCIM) to a folder on this system.

Thin wrapper over backend/photos.sh: 'list' summarises the camera roll, 'copy'
pulls every photo/video into <dest>/iPhone-Photos with a live progress bar. The
device is mounted read-only and always unmounted by the script; originals are
never touched.
"""

import gi

gi.require_version("Gtk", "4.0")

import os  # noqa: E402

import config  # noqa: E402
from gi.repository import GLib, Gtk  # noqa: E402
from jobview import JobView  # noqa: E402
from runner import ScriptRunner  # noqa: E402
from widgets import PathChooser, make_intro, make_title, notify  # noqa: E402

INTRO = (
    "Copy the photos and videos in your camera roll (<tt>DCIM</tt>) to a folder "
    "on this system. The phone is mounted <b>read-only</b> with <b>ifuse</b> and "
    "unmounted automatically — originals are never changed. Files land in an "
    "<tt>iPhone-Photos</tt> subfolder of the destination you pick."
)


def _photos_script() -> str:
    return str(config.backend_dir() / "photos.sh")


class PhotosPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(18)
        self.set_margin_bottom(18)
        self.set_margin_start(18)
        self.set_margin_end(18)
        self.scan_runner = None

        self.append(make_title("Photos"))
        self.append(make_intro(INTRO))

        # Summary row: a "Scan device" button + a label that fills with counts.
        summary = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.scan_btn = Gtk.Button(label="Scan device")
        self.scan_btn.connect("clicked", lambda _b: self.scan())
        summary.append(self.scan_btn)
        self.summary_label = Gtk.Label(xalign=0, label="Not scanned yet.")
        self.summary_label.set_wrap(True)
        summary.append(self.summary_label)
        self.append(summary)

        self.dest = PathChooser(
            "Save to folder:", mode="folder",
            placeholder="e.g. /home/you/Pictures  (an iPhone-Photos subfolder is created)",
        )
        self.append(self.dest)

        opts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.new_only = Gtk.CheckButton(label="Skip files already copied (incremental)")
        self.new_only.set_active(True)
        opts.append(self.new_only)
        self.append(opts)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        buttons.set_halign(Gtk.Align.START)
        self.start_btn = Gtk.Button(label="Copy photos")
        self.start_btn.add_css_class("suggested-action")
        self.start_btn.connect("clicked", self._on_start)
        self.cancel_btn = Gtk.Button(label="Cancel")
        self.cancel_btn.set_sensitive(False)
        self.cancel_btn.connect("clicked", self._on_cancel)
        buttons.append(self.start_btn)
        buttons.append(self.cancel_btn)
        self.append(buttons)

        self.error_label = Gtk.Label(xalign=0)
        self.error_label.set_name("error_label")
        self.error_label.set_wrap(True)
        self.append(self.error_label)

        self.job = JobView()
        self.job.set_vexpand(True)
        self.append(self.job)

    # -- helpers ------------------------------------------------------------ #
    def _error(self, text: str):
        self.error_label.set_text(text)

    def _set_inputs_sensitive(self, sensitive: bool):
        for w in (self.dest, self.new_only, self.start_btn, self.scan_btn):
            w.set_sensitive(sensitive)
        self.cancel_btn.set_sensitive(not sensitive)

    # -- scan (list) -------------------------------------------------------- #
    def scan(self):
        if self.scan_runner is not None and self.scan_runner.is_running():
            return
        self.scan_btn.set_sensitive(False)
        self.summary_label.set_text("Scanning…")
        self._scan_data = {}
        self.scan_runner = ScriptRunner(
            [_photos_script(), "list"],
            on_line=self._on_scan_line,
            on_done=self._on_scan_done,
        )
        self.scan_runner.start()

    def _on_scan_line(self, line: str):
        if ":" in line and not line.startswith("==>"):
            key, _, value = line.partition(":")
            self._scan_data[key.strip()] = value.strip()
        return False

    def _on_scan_done(self, rc, error):
        self.scan_btn.set_sensitive(True)
        if error or rc != 0:
            self.summary_label.set_text(
                "Couldn't read the camera roll. Connect, unlock, and trust the phone.")
            return False
        d = self._scan_data
        self.summary_label.set_text(
            f"{d.get('TotalFiles', '?')} items "
            f"({d.get('Photos', '?')} photos, {d.get('Videos', '?')} videos), "
            f"{d.get('TotalSize', '?')} total.")
        return False

    # -- copy --------------------------------------------------------------- #
    def _on_start(self, _button):
        self._error("")
        dest = self.dest.get_path()
        if not dest:
            self._error("Choose a destination folder.")
            return
        if not os.path.isdir(dest):
            self._error(f"Destination folder does not exist: {dest}")
            return
        argv = [_photos_script(), "copy", dest]
        if self.new_only.get_active():
            argv.append("--new")
        self._set_inputs_sensitive(False)
        self.job.run(argv, on_finished=lambda _rc: self._set_inputs_sensitive(True),
                     noun="Photo copy")

    def _on_cancel(self, _button):
        self.job.cancel()
