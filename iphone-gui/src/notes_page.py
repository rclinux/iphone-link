"""Notes page — browse and read your Apple Notes in-app, and optionally export.

Notes live in the same device backup as Messages. "Load notes" reads the backup's
NoteStore.sqlite via backend/notes.sh (JSON to stdout — nothing written to disk),
lists the titles on the left, and shows the selected note's text on the right.
"Export" still writes per-note files. Read-only on the device throughout.
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
    "Browse and read your <b>Notes</b>. They live in a device backup (the same "
    "one the Messages page uses), so back up once, then <b>Load notes</b> to list "
    "them and click a title to read it. <b>Export</b> writes them to files. "
    "Read-only — nothing on the device is changed."
)


def _notes_script() -> str:
    return str(config.backend_dir() / "notes.sh")


class NotesPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_top(18)
        self.set_margin_bottom(18)
        self.set_margin_start(18)
        self.set_margin_end(18)
        self.runner = None
        self._notes = []

        self.append(make_title("Notes"))
        self.append(make_intro(INTRO))

        self.backup_dir = PathChooser(
            "Backup folder:", mode="folder",
            placeholder="where the device backup is stored (same as the Messages page)")
        self.append(self.backup_dir)

        # Action buttons.
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.load_btn = Gtk.Button(label="Load notes")
        self.load_btn.add_css_class("suggested-action")
        self.load_btn.connect("clicked", lambda _b: self._load())
        self.backup_btn = Gtk.Button(label="Back up device")
        self.backup_btn.connect("clicked", lambda _b: self._backup())
        self.export_btn = Gtk.Button(label="Export to folder…")
        self.export_btn.connect("clicked", lambda _b: self._choose_export())
        for b in (self.load_btn, self.backup_btn, self.export_btn):
            buttons.append(b)
        self.append(buttons)

        self.status = Gtk.Label(xalign=0, label="Choose the backup folder, then Load notes.")
        self.status.set_wrap(True)
        self.append(self.status)

        # Two-pane viewer: title list | note content.
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
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_left_margin(10)
        self.view.set_right_margin(10)
        self.view.set_top_margin(8)
        buf = self.view.get_buffer()
        self._tag_title = buf.create_tag("title", weight=Pango.Weight.BOLD,
                                         scale=1.3)
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
        self.status.set_text("Loading notes…")
        self._buf_lines = []
        self.runner = ScriptRunner(
            [_notes_script(), "view", bdir],
            on_line=lambda ln: (self._buf_lines.append(ln), False)[1],
            on_done=self._on_loaded,
        )
        self.runner.start()

    def _on_loaded(self, rc, error):
        self._set_busy(False)
        if error or rc != 0:
            self.status.set_text("Couldn't load notes. Connect/unlock the phone and "
                                 "make sure a backup exists in that folder.")
            return False
        text = "".join(self._buf_lines).strip()
        try:
            self._notes = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            self.status.set_text("Couldn't parse notes data.")
            return False
        self._clear_list()
        for idx, note in enumerate(self._notes):
            self.listbox.append(self._make_row(note))
        n = len(self._notes)
        self.status.set_text(f"{n} note{'s' if n != 1 else ''}. Click a title to read it.")
        first = self.listbox.get_row_at_index(0)
        if first is not None:
            self.listbox.select_row(first)
        return False

    def _make_row(self, note):
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(8)
        box.set_margin_end(8)
        title = Gtk.Label(xalign=0, label=note.get("title") or "Untitled")
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.add_css_class("field_key")
        meta = Gtk.Label(xalign=0)
        meta.set_markup(f"<small>{GLib.markup_escape_text(note.get('folder',''))}"
                        f"  ·  {GLib.markup_escape_text((note.get('modified') or '')[:10])}</small>")
        meta.add_css_class("dim-label")
        box.append(title)
        box.append(meta)
        row.set_child(box)
        row._note = note
        return row

    def _on_row_selected(self, _listbox, row):
        if row is None:
            return
        note = getattr(row, "_note", None)
        if note is None:
            return
        buf = self.view.get_buffer()
        buf.set_text("")
        end = buf.get_end_iter()
        buf.insert_with_tags(end, (note.get("title") or "Untitled") + "\n", self._tag_title)
        meta = (f"{note.get('folder','')}   ·   created {note.get('created','')}"
                f"   ·   modified {note.get('modified','')}\n")
        buf.insert_with_tags(buf.get_end_iter(), meta, self._tag_meta)
        buf.insert(buf.get_end_iter(), "\n" + (note.get("body") or "") + "\n")

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
            [_notes_script(), "backup", bdir],
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
            self.status.set_text("Backup complete. Click Load notes.")
            notify(self, "Backup complete", "success")
        return False

    def _choose_export(self):
        bdir = self.backup_dir.get_path()
        if not bdir or not os.path.isdir(bdir):
            self.status.set_text("Choose the backup folder first.")
            return
        dialog = Gtk.FileDialog()
        dialog.set_title("Choose a folder to export notes into")
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
        self.status.set_text(f"Exporting notes to {out}…")
        self.runner = ScriptRunner(
            [_notes_script(), "export", bdir, out],
            on_done=lambda rc, err, o=out: self._on_export_done(rc, err, o),
        )
        self.runner.start()

    def _on_export_done(self, rc, error, out):
        self._set_busy(False)
        if error or rc != 0:
            self.status.set_text("Export failed.")
            notify(self, "Notes export failed", "error")
        else:
            self.status.set_text(f"Exported notes to {out}.")
            notify(self, "Notes exported", "success")
        return False
