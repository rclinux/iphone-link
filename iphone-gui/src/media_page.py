"""Media page — two functions in tabs:

  * Videos — browse the camera-roll videos and play one locally (read-only over
    ifuse; nothing on the device is changed). Playback uses gst-play-1.0.
  * AirPlay receiver — run UxPlay so the iPhone can mirror its screen/audio TO
    this PC (the phone connects to this host).

Both are thin wrappers over backend/media.sh.
"""

import gi

gi.require_version("Gtk", "4.0")

import socket  # noqa: E402

import config  # noqa: E402
from gi.repository import GLib, Gtk, Pango  # noqa: E402
from jobview import JobView  # noqa: E402
from runner import ScriptRunner  # noqa: E402
from widgets import make_intro, make_title, notify  # noqa: E402

RECV_INTRO = (
    "Play your iPhone's screen and audio on this PC with <b>AirPlay</b>. Start the "
    "receiver, then on the iPhone open <b>Control Center → Screen Mirroring</b> "
    "and choose this PC. A video window opens when mirroring begins."
)
VIDEO_INTRO = (
    "Browse the videos in your camera roll and play one here. The phone is mounted "
    "<b>read-only</b> and unmounted automatically — originals are never changed."
)


def _media_script() -> str:
    return str(config.backend_dir() / "media.sh")


def _human(nbytes: int) -> str:
    f = float(nbytes)
    for unit in ("B", "KB", "MB", "GB"):
        if f < 1024 or unit == "GB":
            return f"{f:.0f} {unit}" if unit == "B" else f"{f:.1f} {unit}"
        f /= 1024
    return f"{f:.1f} GB"


class MediaPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_top(18)
        self.set_margin_bottom(18)
        self.set_margin_start(18)
        self.set_margin_end(18)
        self.vid_runner = None
        self.play_runner = None
        self.recv_runner = None
        self._stopping = False

        self.append(make_title("Media"))

        notebook = Gtk.Notebook()
        notebook.set_vexpand(True)
        notebook.append_page(self._build_videos_tab(), Gtk.Label(label="Videos"))
        notebook.append_page(self._build_receiver_tab(),
                             Gtk.Label(label="AirPlay receiver"))
        self.append(notebook)

    # ===================== Videos tab ==================================== #
    def _build_videos_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(12)
        box.set_margin_start(4)
        box.set_margin_end(4)
        box.append(make_intro(VIDEO_INTRO))

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.load_vids_btn = Gtk.Button(label="Load videos")
        self.load_vids_btn.add_css_class("suggested-action")
        self.load_vids_btn.connect("clicked", lambda _b: self._load_videos())
        self.play_btn = Gtk.Button(label="Play")
        self.play_btn.connect("clicked", lambda _b: self._play_selected())
        self.stop_play_btn = Gtk.Button(label="Stop playback")
        self.stop_play_btn.set_sensitive(False)
        self.stop_play_btn.connect("clicked", lambda _b: self._stop_play())
        for b in (self.load_vids_btn, self.play_btn, self.stop_play_btn):
            row.append(b)
        box.append(row)

        self.vid_status = Gtk.Label(xalign=0, label="Click Load videos to list the camera roll.")
        self.vid_status.set_wrap(True)
        box.append(self.vid_status)

        self.vid_list = Gtk.ListBox()
        self.vid_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.vid_list.connect("row-activated", lambda _lb, _r: self._play_selected())
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_child(self.vid_list)
        scrolled.set_vexpand(True)
        box.append(scrolled)
        return box

    def _clear_videos(self):
        child = self.vid_list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.vid_list.remove(child)
            child = nxt

    def _load_videos(self):
        if self.vid_runner is not None and self.vid_runner.is_running():
            return
        self.load_vids_btn.set_sensitive(False)
        self.vid_status.set_text("Reading camera roll…")
        self._vid_lines = []
        self.vid_runner = ScriptRunner(
            [_media_script(), "list-videos"],
            on_line=lambda ln: (self._vid_lines.append(ln), False)[1],
            on_done=self._on_videos_loaded,
        )
        self.vid_runner.start()

    def _on_videos_loaded(self, rc, error):
        self.load_vids_btn.set_sensitive(True)
        self._clear_videos()
        if error or rc != 0:
            self.vid_status.set_text("Couldn't read the camera roll. Connect, unlock, "
                                     "and trust the phone.")
            return False
        videos = []
        for ln in self._vid_lines:
            if "\t" in ln and not ln.startswith("==>"):
                size, _, name = ln.partition("\t")
                if size.strip().isdigit():
                    videos.append((name.strip(), int(size.strip())))
        if not videos:
            self.vid_status.set_text("No videos in the camera roll.")
            return False
        for name, size in videos:
            self.vid_list.append(self._make_video_row(name, size))
        self.vid_status.set_text(f"{len(videos)} video(s). Select one and click Play "
                                 "(or double-click).")
        first = self.vid_list.get_row_at_index(0)
        if first is not None:
            self.vid_list.select_row(first)
        return False

    def _make_video_row(self, name, size):
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_top(5)
        box.set_margin_bottom(5)
        box.set_margin_start(8)
        box.set_margin_end(8)
        label = Gtk.Label(xalign=0, label=name, hexpand=True)
        label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        size_label = Gtk.Label(xalign=1, label=_human(size))
        size_label.add_css_class("dim-label")
        box.append(label)
        box.append(size_label)
        row.set_child(box)
        row._video = name
        return row

    def _play_selected(self):
        if self.play_runner is not None and self.play_runner.is_running():
            notify(self, "Already playing — stop it first.", "info")
            return
        row = self.vid_list.get_selected_row()
        if row is None:
            self.vid_status.set_text("Select a video first.")
            return
        name = getattr(row, "_video", None)
        if not name:
            return
        self.play_btn.set_sensitive(False)
        self.stop_play_btn.set_sensitive(True)
        self.vid_status.set_text(f"Playing {name} — close the player window or press "
                                 "Stop playback to finish.")
        self.play_runner = ScriptRunner(
            [_media_script(), "play", name],
            on_done=self._on_play_done,
        )
        self.play_runner.start()

    def _stop_play(self):
        if self.play_runner is not None:
            self.play_runner.cancel()

    def _on_play_done(self, rc, error):
        self.play_btn.set_sensitive(True)
        self.stop_play_btn.set_sensitive(False)
        self.vid_status.set_text("Playback finished.")
        return False

    # ===================== AirPlay receiver tab ========================== #
    def _build_receiver_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(12)
        box.set_margin_start(4)
        box.set_margin_end(4)
        box.append(make_intro(RECV_INTRO))

        self.recv_status = Gtk.Label(xalign=0, label="Checking AirPlay receiver…")
        self.recv_status.set_wrap(True)
        box.append(self.recv_status)

        name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        name_row.append(Gtk.Label(xalign=0, label="Receiver name:"))
        self.name_entry = Gtk.Entry()
        self.name_entry.set_hexpand(True)
        self.name_entry.set_text(f"iPhone Link @ {socket.gethostname()}")
        name_row.append(self.name_entry)
        box.append(name_row)

        opts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.fullscreen = Gtk.CheckButton(label="Full-screen mirror window")
        self.pin = Gtk.CheckButton(label="Require a PIN to connect")
        opts.append(self.fullscreen)
        opts.append(self.pin)
        box.append(opts)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.start_btn = Gtk.Button(label="Start receiver")
        self.start_btn.add_css_class("suggested-action")
        self.start_btn.connect("clicked", lambda _b: self._start_receiver())
        self.stop_btn = Gtk.Button(label="Stop receiver")
        self.stop_btn.add_css_class("destructive-action")
        self.stop_btn.set_sensitive(False)
        self.stop_btn.connect("clicked", lambda _b: self._stop_receiver())
        buttons.append(self.start_btn)
        buttons.append(self.stop_btn)
        box.append(buttons)

        self.job = JobView()
        self.job.set_vexpand(True)
        box.append(self.job)

        GLib.idle_add(self._check_receiver)
        return box

    def _check_receiver(self):
        self._check_lines = []
        self.recv_runner = ScriptRunner(
            [_media_script(), "check"],
            on_line=lambda ln: (self._check_lines.append(ln), False)[1],
            on_done=self._on_check_done,
        )
        self.recv_runner.start()
        return False

    def _on_check_done(self, rc, error):
        data = {}
        for ln in self._check_lines:
            if ":" in ln and not ln.startswith("==>"):
                k, _, v = ln.partition(":")
                data[k.strip()] = v.strip()
        if data.get("Ready") == "yes":
            self.recv_status.set_markup("<b>Ready.</b> Start the receiver, then pick it "
                                        "from Screen Mirroring on the iPhone.")
        else:
            missing = [k for k in ("UxPlay", "GStreamer", "mDNS (avahi)")
                       if "MISSING" in data.get(k, "") or "NOT" in data.get(k, "")]
            self.recv_status.set_markup(
                "<b>Not ready.</b> Problem with: " + (", ".join(missing) or "setup") + ".")
            self.start_btn.set_sensitive(False)
        return False

    def _start_receiver(self):
        name = self.name_entry.get_text().strip() or f"iPhone Link @ {socket.gethostname()}"
        argv = [_media_script(), "start", "--name", name]
        if self.fullscreen.get_active():
            argv.append("--fullscreen")
        if self.pin.get_active():
            argv.append("--pin")
        self._stopping = False
        self.start_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(True)
        for w in (self.name_entry, self.fullscreen, self.pin):
            w.set_sensitive(False)
        self.recv_status.set_markup(
            f"<b>Receiver running.</b> On the iPhone pick "
            f"“{GLib.markup_escape_text(name)}” from Screen Mirroring.")
        notify(self, "AirPlay receiver started.", "success")
        self.job.run(argv, on_finished=self._on_receiver_finished, noun="AirPlay receiver")

    def _stop_receiver(self):
        self._stopping = True
        self.job.cancel()

    def _on_receiver_finished(self, _rc):
        self.start_btn.set_sensitive(True)
        self.stop_btn.set_sensitive(False)
        for w in (self.name_entry, self.fullscreen, self.pin):
            w.set_sensitive(True)
        if self._stopping:
            self.recv_status.set_markup("<b>Receiver stopped.</b> Start it again when "
                                        "you want to mirror.")
        else:
            self.recv_status.set_markup("<b>Receiver exited.</b> See the log for details.")
        return False
