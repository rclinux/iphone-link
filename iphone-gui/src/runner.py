"""ScriptRunner — run a backend script and stream its output to the GUI.

The script is spawned as a subprocess; a worker thread reads its merged
stdout/stderr and marshals every update back onto the GTK main loop with
GLib.idle_add (GTK is not thread-safe). We split on BOTH '\\n' and '\\r' so
in-place progress updates (carriage returns) are captured as discrete lines.

Backend convention (see backend/_common.sh):
  * lines beginning "==> " are progress *steps* (shown above the log);
  * "Completed: NN%" or "NN%" anywhere drives the progress bar.
"""

import os
import re
import subprocess
import threading

from gi.repository import GLib

# Accept "Completed: 73.4%" (libimobiledevice backup style) or a bare "73%".
_PCT_RE = re.compile(r"(?:Completed:\s*)?([0-9]+(?:\.[0-9]+)?)%")

# Strip ANSI CSI sequences so cursor moves don't show as stray "[A" in the log.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class ScriptRunner:
    """Run argv, delivering callbacks on the GTK main thread.

    Callbacks (all optional):
      on_line(text)        every output line
      on_progress(pct)     float 0..100 parsed from output
      on_step(text)        a step line (originally prefixed with '==>')
      on_done(rc, error)   rc is the exit code (or -1 on spawn failure);
                           error is a string or None
    """

    def __init__(self, argv, on_line=None, on_progress=None, on_step=None, on_done=None):
        self.argv = [str(a) for a in argv]
        self.on_line = on_line
        self.on_progress = on_progress
        self.on_step = on_step
        self.on_done = on_done
        self.proc = None
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def cancel(self):
        """Terminate the running script (SIGTERM). Best-effort."""
        if self.is_running():
            try:
                self.proc.terminate()
            except OSError:
                pass

    # -- internal ----------------------------------------------------------- #
    def _emit(self, cb, *args):
        if cb is not None:
            GLib.idle_add(cb, *args)

    def _handle_line(self, line: str):
        line = _ANSI_RE.sub("", line)
        if line.startswith("==>"):
            self._emit(self.on_step, line[3:].strip())
            self._emit(self.on_line, line)
            return
        self._emit(self.on_line, line)
        match = _PCT_RE.search(line)
        if match:
            self._emit(self.on_progress, float(match.group(1)))

    def _run(self):
        env = dict(os.environ)
        env["TERM"] = "dumb"  # discourage colour/cursor escapes
        try:
            self.proc = subprocess.Popen(
                self.argv,
                stdin=subprocess.DEVNULL,  # any stray prompt gets EOF, not a hang
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                env=env,
            )
        except OSError as exc:
            self._emit(self.on_done, -1, f"Failed to start: {exc}")
            return

        fd = self.proc.stdout.fileno()
        buf = ""
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk.decode("utf-8", errors="replace")
            parts = re.split(r"[\r\n]", buf)
            buf = parts.pop()  # keep the trailing incomplete fragment
            for line in parts:
                if line:
                    self._handle_line(line)
        if buf:
            self._handle_line(buf)

        self.proc.stdout.close()
        rc = self.proc.wait()
        self._emit(self.on_done, rc, None)
