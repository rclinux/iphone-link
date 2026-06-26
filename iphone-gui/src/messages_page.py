"""Messages page — browse and read your conversations in-app, and optionally
export.

Messages live in a device backup (the same one Notes uses). "Load messages"
reads sms.db via backend/messages.sh (JSON to stdout — nothing written to disk),
lists conversations on the left, and shows the selected transcript on the right.
"Export" still writes text/CSV files. Read-only on the device throughout.

Very large conversations are capped when displayed (the newest messages) to keep
the view responsive; Export always writes the full history.
"""

import gi

gi.require_version("Gtk", "4.0")

import json  # noqa: E402
import os  # noqa: E402

import config  # noqa: E402
from gi.repository import GLib, Gtk, Pango  # noqa: E402
from runner import ScriptRunner  # noqa: E402
from widgets import PathChooser, make_intro, make_title, notify  # noqa: E402

INTRO = (
    "Browse and read your <b>text messages</b>. They live in a device backup "
    "(the same one the Notes page uses), so back up once, then <b>Load "
    "messages</b> to list conversations and click one to read it. <b>Export</b> "
    "writes text or CSV files. Read-only — nothing on the device is changed."
)

# Cap how many of the newest messages we render for one conversation (some chats
# have tens of thousands). Export always writes everything.
VIEW_CAP = 2000


def _msg_script() -> str:
    return str(config.backend_dir() / "messages.sh")


class MessagesPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_top(18)
        self.set_margin_bottom(18)
        self.set_margin_start(18)
        self.set_margin_end(18)
        self.runner = None
        self._convos = []

        self.append(make_title("Messages"))
        self.append(make_intro(INTRO))

        self.backup_dir = PathChooser(
            "Backup folder:", mode="folder",
            placeholder="where the device backup is stored (same as the Notes page)")
        self.append(self.backup_dir)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.load_btn = Gtk.Button(label="Load messages")
        self.load_btn.add_css_class("suggested-action")
        self.load_btn.connect("clicked", lambda _b: self._load())
        self.backup_btn = Gtk.Button(label="Back up device")
        self.backup_btn.connect("clicked", lambda _b: self._backup())
        self.export_btn = Gtk.Button(label="Export to folder…")
        self.export_btn.connect("clicked", lambda _b: self._choose_export())
        for b in (self.load_btn, self.backup_btn, self.export_btn):
            buttons.append(b)
        self.append(buttons)

        self.status = Gtk.Label(xalign=0,
                                label="Choose the backup folder, then Load messages.")
        self.status.set_wrap(True)
        self.append(self.status)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_vexpand(True)
        paned.set_position(300)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-selected", self._on_row_selected)
        left = Gtk.ScrolledWindow()
        left.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        left.set_child(self.listbox)
        left.set_size_request(280, -1)
        paned.set_start_child(left)

        self.view = Gtk.TextView()
        self.view.set_editable(False)
        self.view.set_cursor_visible(False)
        self.view.set_monospace(True)
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_left_margin(10)
        self.view.set_right_margin(10)
        self.view.set_top_margin(8)
        buf = self.view.get_buffer()
        self._tag_head = buf.create_tag("head", weight=Pango.Weight.BOLD, scale=1.2)
        self._tag_me = buf.create_tag("me", foreground="#1a5fb4")
        self._tag_meta = buf.create_tag("meta", foreground="#888888")
        right = Gtk.ScrolledWindow()
        right.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        right.set_child(self.view)
        paned.set_end_child(right)

        self.append(paned)

    # -- helpers ------------------------------------------------------------ #
    def _set_busy(self, busy: bool):
        for b in (self.load_btn, self.backup_btn, self.export_btn, self.backup_dir):
            b.set_sensitive(not busy)

    def _clear_list(self):
        child = self.listbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt

    # -- load (view JSON) --------------------------------------------------- #
    def _load(self):
        bdir = self.backup_dir.get_path()
        if not bdir or not os.path.isdir(bdir):
            self.status.set_text("Choose the backup folder first (run a backup if you haven't).")
            return
        if self.runner is not None and self.runner.is_running():
            return
        self._set_busy(True)
        self.status.set_text("Loading messages…")
        self._buf_lines = []
        self.runner = ScriptRunner(
            [_msg_script(), "view", bdir],
            on_line=lambda ln: (self._buf_lines.append(ln), False)[1],
            on_done=self._on_loaded,
        )
        self.runner.start()

    def _on_loaded(self, rc, error):
        self._set_busy(False)
        if error or rc != 0:
            self.status.set_text("Couldn't load messages. Connect/unlock the phone and "
                                 "make sure a backup exists in that folder.")
            return False
        try:
            self._convos = json.loads("".join(self._buf_lines).strip())
        except (json.JSONDecodeError, ValueError):
            self.status.set_text("Couldn't parse messages data.")
            return False
        self._clear_list()
        for convo in self._convos:
            self.listbox.append(self._make_row(convo))
        total = sum(c["count"] for c in self._convos)
        self.status.set_text(
            f"{len(self._convos)} conversations, {total} messages. Click one to read it.")
        first = self.listbox.get_row_at_index(0)
        if first is not None:
            self.listbox.select_row(first)
        return False

    def _make_row(self, convo):
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(8)
        box.set_margin_end(8)
        title = Gtk.Label(xalign=0, label=convo.get("title") or "Unknown")
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.add_css_class("field_key")
        meta = Gtk.Label(xalign=0)
        meta.set_markup(f"<small>{convo.get('count', 0)} messages"
                        f"  ·  {GLib.markup_escape_text((convo.get('last') or '')[:10])}</small>")
        box.append(title)
        box.append(meta)
        row.set_child(box)
        row._convo = convo
        return row

    def _on_row_selected(self, _listbox, row):
        if row is None:
            return
        convo = getattr(row, "_convo", None)
        if convo is None:
            return
        buf = self.view.get_buffer()
        buf.set_text("")
        title = convo.get("title") or "Unknown"
        buf.insert_with_tags(buf.get_end_iter(), title + "\n", self._tag_head)

        msgs = convo.get("messages", [])
        shown = msgs
        if len(msgs) > VIEW_CAP:
            shown = msgs[-VIEW_CAP:]
            buf.insert_with_tags(
                buf.get_end_iter(),
                f"(showing the most recent {VIEW_CAP} of {len(msgs)} messages — "
                f"Export saves them all)\n", self._tag_meta)
        buf.insert(buf.get_end_iter(), "\n")
        for m in shown:
            tag = self._tag_me if m.get("sender") == "Me" else self._tag_meta
            buf.insert_with_tags(buf.get_end_iter(),
                                 f"[{m.get('ts','')}] {m.get('sender','')}: ", tag)
            buf.insert(buf.get_end_iter(), (m.get("body") or "") + "\n")

    # -- backup / export ---------------------------------------------------- #
    def _backup(self):
        bdir = self.backup_dir.get_path()
        if not bdir:
            self.status.set_text("Choose a backup folder.")
            return
        notify(self, "Starting backup — the first one is full and can take a while.", "info")
        self._set_busy(True)
        self.status.set_text("Backing up device… (this can take a while)")
        self.runner = ScriptRunner(
            [_msg_script(), "backup", bdir],
            on_step=lambda s: (self.status.set_text(s), False)[1],
            on_done=self._on_backup_done,
        )
        self.runner.start()

    def _on_backup_done(self, rc, error):
        self._set_busy(False)
        if error or rc != 0:
            self.status.set_text("Backup failed — connect and unlock the iPhone.")
            notify(self, "Backup failed", "error")
        else:
            self.status.set_text("Backup complete. Click Load messages.")
            notify(self, "Backup complete", "success")
        return False

    def _choose_export(self):
        bdir = self.backup_dir.get_path()
        if not bdir or not os.path.isdir(bdir):
            self.status.set_text("Choose the backup folder first.")
            return
        dialog = Gtk.FileDialog()
        dialog.set_title("Choose a folder to export messages into")
        dialog.select_folder(self.get_root(), None, self._on_export_folder)

    def _on_export_folder(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        if not folder:
            return
        bdir = self.backup_dir.get_path()
        out = folder.get_path()
        self._set_busy(True)
        self.status.set_text(f"Exporting messages to {out}…")
        self.runner = ScriptRunner(
            [_msg_script(), "export", bdir, out],
            on_done=lambda rc, err, o=out: self._on_export_done(rc, err, o),
        )
        self.runner.start()

    def _on_export_done(self, rc, error, out):
        self._set_busy(False)
        if error or rc != 0:
            self.status.set_text("Export failed.")
            notify(self, "Messages export failed", "error")
        else:
            self.status.set_text(f"Exported messages to {out}.")
            notify(self, "Messages exported", "success")
        return False
