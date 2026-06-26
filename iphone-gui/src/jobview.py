"""JobView — the run area shared by the Backup and Restore pages.

Shows the current step, a progress bar driven by partclone's percentage, and a
collapsible dark log with the full script output. Owns a ScriptRunner and
re-enables the page's controls when the job finishes.
"""

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk  # noqa: E402

from runner import ScriptRunner  # noqa: E402
from widgets import notify  # noqa: E402


class JobView(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.runner = None
        self._on_finished = None
        self._noun = "Operation"

        self.step_label = Gtk.Label(xalign=0)
        self.step_label.set_name("step_label")
        self.step_label.set_wrap(True)
        self.append(self.step_label)

        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(True)
        self.progress.set_text("Idle")
        self.append(self.progress)

        self.expander = Gtk.Expander(label="Output log")
        self.expander.set_expanded(True)  # fills the page; still collapsible
        self.expander.set_vexpand(True)
        self.append(self.expander)

        self.textview = Gtk.TextView()
        self.textview.set_name("textview_log")
        self.textview.set_editable(False)
        self.textview.set_cursor_visible(False)
        self.textview.set_monospace(True)
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(260)
        scrolled.set_vexpand(True)
        scrolled.set_child(self.textview)
        self.expander.set_child(scrolled)

    # -- log helpers -------------------------------------------------------- #
    def _append(self, text: str):
        buf = self.textview.get_buffer()
        buf.insert(buf.get_end_iter(), text + "\n")
        # Autoscroll to the bottom.
        mark = buf.create_mark(None, buf.get_end_iter(), False)
        self.textview.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)
        buf.delete_mark(mark)

    def clear_log(self):
        self.textview.get_buffer().set_text("")

    # -- run lifecycle ------------------------------------------------------ #
    def run(self, argv, on_finished=None, noun="Operation"):
        """Start argv. on_finished(rc) is called (on the main thread) at exit.

        ``noun`` names the task (e.g. "Backup") for the completion toast.
        """
        self._on_finished = on_finished
        self._noun = noun
        self.clear_log()
        self.progress.set_fraction(0.0)
        self.progress.set_text("Starting…")
        self.step_label.set_text("Starting…")
        self.expander.set_expanded(True)

        self.runner = ScriptRunner(
            argv,
            on_line=self._on_line,
            on_progress=self._on_progress,
            on_step=self._on_step,
            on_done=self._on_done,
        )
        self.runner.start()

    def cancel(self):
        if self.runner:
            self.runner.cancel()

    def is_running(self) -> bool:
        return self.runner is not None and self.runner.is_running()

    # -- runner callbacks (main thread via GLib.idle_add) ------------------- #
    def _on_line(self, line):
        self._append(line)
        return False

    def _on_progress(self, pct):
        self.progress.set_fraction(max(0.0, min(1.0, pct / 100.0)))
        self.progress.set_text(f"{pct:.0f}%")
        return False

    def _on_step(self, step):
        self.step_label.set_text(step)
        # A new imaging/restoring step: reset the bar for the new partition.
        self.progress.set_fraction(0.0)
        self.progress.set_text(step)
        return False

    def _on_done(self, rc, error):
        if error:
            self.step_label.set_text(f"Failed to start: {error}")
            self.progress.set_text("Error")
            notify(self, f"{self._noun} failed to start", "error")
        elif rc == 0:
            self.step_label.set_text("Done.")
            self.progress.set_fraction(1.0)
            self.progress.set_text("Complete")
            notify(self, f"{self._noun} complete", "success")
        else:
            self.step_label.set_text(f"Stopped (exit code {rc}). See the log.")
            self.progress.set_text(f"Failed (exit {rc})")
            notify(self, f"{self._noun} stopped (exit {rc})", "error")
        if self._on_finished:
            self._on_finished(rc if not error else -1)
        return False
