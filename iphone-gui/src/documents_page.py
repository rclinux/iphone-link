"""Documents page — move files in and out of an iPhone app's File-Sharing folder.

Thin wrapper over backend/documents.sh: 'list' fills the app dropdown, 'browse'
lists an app's files, 'pull' copies them to a folder here, 'push' sends local
files to the app. Only the selected app's sandbox is mounted (ifuse --documents),
and the script always unmounts.
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
    "Copy files in and out of an app's <b>File Sharing</b> folder — the same list "
    "you see under <i>Finder &gt; iPhone &gt; Files</i>. Pick an app, then pull "
    "its documents to this system or push local files to it. Only that app's "
    "folder is mounted (read-write only while pushing), and it is unmounted "
    "automatically."
)


def _docs_script() -> str:
    return str(config.backend_dir() / "documents.sh")


class DocumentsPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(18)
        self.set_margin_bottom(18)
        self.set_margin_start(18)
        self.set_margin_end(18)
        self.list_runner = None
        self._apps = []  # list of (bundle_id, display_name)

        self.append(make_title("Documents"))
        self.append(make_intro(INTRO))

        # App selector row.
        app_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        app_row.append(Gtk.Label(xalign=0, label="App:"))
        self.app_model = Gtk.StringList()
        self.app_dropdown = Gtk.DropDown(model=self.app_model)
        self.app_dropdown.set_hexpand(True)
        app_row.append(self.app_dropdown)
        self.refresh_btn = Gtk.Button()
        self.refresh_btn.set_icon_name("view-refresh-symbolic")
        self.refresh_btn.set_tooltip_text("Rescan apps with File Sharing")
        self.refresh_btn.connect("clicked", lambda _b: self.load_apps())
        app_row.append(self.refresh_btn)
        self.append(app_row)

        # Destination for pulling.
        self.dest = PathChooser(
            "Save to folder:", mode="folder",
            placeholder="e.g. /home/you/Documents  (an <App>-Documents subfolder is created)",
        )
        self.append(self.dest)

        # Action buttons.
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        buttons.set_halign(Gtk.Align.START)
        self.list_btn = Gtk.Button(label="List files")
        self.list_btn.connect("clicked", lambda _b: self._run_browse())
        self.pull_btn = Gtk.Button(label="Pull documents")
        self.pull_btn.add_css_class("suggested-action")
        self.pull_btn.connect("clicked", lambda _b: self._run_pull())
        self.push_btn = Gtk.Button(label="Push file(s)…")
        self.push_btn.connect("clicked", lambda _b: self._choose_push_files())
        self.cancel_btn = Gtk.Button(label="Cancel")
        self.cancel_btn.set_sensitive(False)
        self.cancel_btn.connect("clicked", lambda _b: self.job.cancel())
        for b in (self.list_btn, self.pull_btn, self.push_btn, self.cancel_btn):
            buttons.append(b)
        self.append(buttons)

        self.error_label = Gtk.Label(xalign=0)
        self.error_label.set_name("error_label")
        self.error_label.set_wrap(True)
        self.append(self.error_label)

        self.job = JobView()
        self.job.set_vexpand(True)
        self.append(self.job)

        GLib.idle_add(self.load_apps)

    # -- helpers ------------------------------------------------------------ #
    def _error(self, text: str):
        self.error_label.set_text(text)

    def _selected_app(self):
        """Return (bundle_id, name) for the chosen app, or None."""
        if not self._apps:
            return None
        idx = self.app_dropdown.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION or idx >= len(self._apps):
            return None
        return self._apps[idx]

    def _set_busy(self, busy: bool):
        for b in (self.list_btn, self.pull_btn, self.push_btn,
                  self.refresh_btn, self.app_dropdown, self.dest):
            b.set_sensitive(not busy)
        self.cancel_btn.set_sensitive(busy)

    # -- load app list ------------------------------------------------------ #
    def load_apps(self):
        if self.list_runner is not None and self.list_runner.is_running():
            return False
        self.refresh_btn.set_sensitive(False)
        self._pending_apps = []
        self.list_runner = ScriptRunner(
            [_docs_script(), "list"],
            on_line=self._on_app_line,
            on_done=self._on_apps_done,
        )
        self.list_runner.start()
        return False

    def _on_app_line(self, line: str):
        if line.startswith("==>") or "\t" not in line:
            return False
        bundle, _, name = line.partition("\t")
        self._pending_apps.append((bundle.strip(), name.strip()))
        return False

    def _on_apps_done(self, rc, error):
        self.refresh_btn.set_sensitive(True)
        while self.app_model.get_n_items() > 0:
            self.app_model.remove(0)
        if error or rc != 0 or not self._pending_apps:
            self._apps = []
            self.app_model.append("(no File-Sharing apps found — connect & unlock)")
            self.app_dropdown.set_sensitive(False)
            return False
        self._apps = sorted(self._pending_apps, key=lambda a: a[1].lower())
        self.app_dropdown.set_sensitive(True)
        for bundle, name in self._apps:
            self.app_model.append(f"{name}  ({bundle})")
        return False

    # -- browse / pull / push ---------------------------------------------- #
    def _run_browse(self):
        app = self._selected_app()
        if app is None:
            self._error("Pick an app first.")
            return
        self._error("")
        self._set_busy(True)
        self.job.run([_docs_script(), "browse", app[0]],
                     on_finished=lambda _rc: self._set_busy(False), noun="Listing")

    def _run_pull(self):
        app = self._selected_app()
        if app is None:
            self._error("Pick an app first.")
            return
        dest = self.dest.get_path()
        if not dest:
            self._error("Choose a destination folder.")
            return
        if not os.path.isdir(dest):
            self._error(f"Destination folder does not exist: {dest}")
            return
        self._error("")
        self._set_busy(True)
        self.job.run([_docs_script(), "pull", app[0], dest],
                     on_finished=lambda _rc: self._set_busy(False), noun="Pull")

    def _choose_push_files(self):
        app = self._selected_app()
        if app is None:
            self._error("Pick an app first.")
            return
        self._error("")
        dialog = Gtk.FileDialog()
        dialog.set_title(f"Choose file(s) to send to {app[1]}")
        dialog.open_multiple(self.get_root(), None, self._on_push_chosen)

    def _on_push_chosen(self, dialog, result):
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            return  # cancelled
        paths = []
        for i in range(files.get_n_items()):
            gfile = files.get_item(i)
            if gfile and gfile.get_path():
                paths.append(gfile.get_path())
        if not paths:
            return
        app = self._selected_app()
        if app is None:
            return
        notify(self, f"Sending {len(paths)} file(s) to {app[1]}…", "info")
        self._set_busy(True)
        self.job.run([_docs_script(), "push", app[0], *paths],
                     on_finished=lambda _rc: self._set_busy(False), noun="Push")
