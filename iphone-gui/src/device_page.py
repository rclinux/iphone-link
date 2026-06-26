"""Device page — identity, pairing/trust status, power and storage.

Reads the connected iPhone's facts from backend/device-info.sh and shows them in
a key/value grid with a connection pill. Pair / Validate / Unpair drive
backend/pair.sh. Everything runs through ScriptRunner so the GUI never blocks and
never reimplements device logic.
"""

import gi

gi.require_version("Gtk", "4.0")

import config  # noqa: E402
from gi.repository import GLib, Gtk  # noqa: E402
from runner import ScriptRunner  # noqa: E402
from widgets import make_intro, make_title, notify  # noqa: E402

INTRO = (
    "Link status for your iPhone. Connect it by USB and unlock it; tap "
    "<b>Trust</b> on the phone the first time. Everything below is read live "
    "from the device through <b>libimobiledevice</b>."
)

# (display label, key emitted by device-info.sh, formatter)
FIELDS = [
    ("Name", "DeviceName", str),
    ("Model", "ProductType", str),
    ("iOS version", "ProductVersion", lambda v: v),
    ("Build", "BuildVersion", str),
    ("UDID", "UDID", str),
    ("Serial", "SerialNumber", str),
    ("Wi-Fi MAC", "WiFiAddress", str),
    ("Battery", "BatteryLevel", lambda v: f"{v}%" if v else ""),
    ("Charging", "Charging", lambda v: {"true": "yes", "false": "no"}.get(v, v)),
    ("Storage", "_storage", str),  # synthesised from total/free below
]


class DevicePage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(18)
        self.set_margin_bottom(18)
        self.set_margin_start(18)
        self.set_margin_end(18)
        self.runner = None

        # Title row with a connection pill on the right.
        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        title_row.append(make_title("Device"))
        spacer = Gtk.Box(hexpand=True)
        title_row.append(spacer)
        self.pill = Gtk.Label(label="Checking…")
        self.pill.set_name("status_pill")
        self.pill.set_valign(Gtk.Align.CENTER)
        title_row.append(self.pill)
        self.append(title_row)

        self.append(make_intro(INTRO))

        # Key/value grid of device facts.
        self.grid = Gtk.Grid()
        self.grid.set_row_spacing(6)
        self.grid.set_column_spacing(12)
        self.grid.set_margin_top(6)
        self._value_labels = {}
        for row, (label_text, key, _fmt) in enumerate(FIELDS):
            k = Gtk.Label(xalign=0, label=f"{label_text}:")
            k.add_css_class("field_key")
            v = Gtk.Label(xalign=0, label="—", selectable=True)
            v.add_css_class("field_value")
            v.set_wrap(True)
            self.grid.attach(k, 0, row, 1, 1)
            self.grid.attach(v, 1, row, 1, 1)
            self._value_labels[key] = v
        self.append(self.grid)

        # Action buttons.
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        buttons.set_halign(Gtk.Align.START)
        buttons.set_margin_top(10)
        self.refresh_btn = Gtk.Button(label="Refresh")
        self.refresh_btn.add_css_class("suggested-action")
        self.refresh_btn.connect("clicked", lambda _b: self.refresh())
        self.pair_btn = Gtk.Button(label="Pair / Trust")
        self.pair_btn.connect("clicked", lambda _b: self._run_pair("pair"))
        self.validate_btn = Gtk.Button(label="Validate")
        self.validate_btn.connect("clicked", lambda _b: self._run_pair("validate"))
        self.unpair_btn = Gtk.Button(label="Unpair")
        self.unpair_btn.add_css_class("destructive-action")
        self.unpair_btn.connect("clicked", lambda _b: self._run_pair("unpair"))
        for b in (self.refresh_btn, self.pair_btn, self.validate_btn, self.unpair_btn):
            buttons.append(b)
        self.append(buttons)

        self.status = Gtk.Label(xalign=0)
        self.status.set_wrap(True)
        self.status.set_margin_top(4)
        self.append(self.status)

        # Initial population shortly after construction (idle so the window maps).
        GLib.idle_add(self.refresh)

    # -- helpers ------------------------------------------------------------ #
    def _set_pill(self, connected: bool, text: str):
        self.pill.set_text(text)
        self.pill.remove_css_class("connected")
        self.pill.remove_css_class("disconnected")
        self.pill.add_css_class("connected" if connected else "disconnected")

    def _clear_values(self):
        for v in self._value_labels.values():
            v.set_text("—")

    def _buttons_sensitive(self, sensitive: bool):
        for b in (self.refresh_btn, self.pair_btn, self.validate_btn, self.unpair_btn):
            b.set_sensitive(sensitive)

    # -- device-info refresh ------------------------------------------------ #
    def refresh(self):
        if self.runner is not None and self.runner.is_running():
            return False
        self._set_pill(False, "Checking…")
        self.status.set_text("")
        self._buttons_sensitive(False)
        self._pending = {}
        self.runner = ScriptRunner(
            [str(config.device_info_script())],
            on_line=self._on_info_line,
            on_done=self._on_info_done,
        )
        self.runner.start()
        return False  # one-shot for GLib.idle_add

    def _on_info_line(self, line: str):
        if ":" not in line:
            return False
        key, _, value = line.partition(":")
        self._pending[key.strip()] = value.strip()
        return False

    def _on_info_done(self, rc, error):
        self._buttons_sensitive(True)
        if error or rc != 0:
            self._clear_values()
            self._set_pill(False, "Disconnected")
            msg = self._pending.get("_err", "")
            self.status.set_text(
                "No iPhone detected, or it is locked. Connect by USB, unlock, "
                "and tap Trust." + (f"  ({msg})" if msg else "")
            )
            return False

        data = self._pending
        # Synthesise the storage line from total/free.
        total = data.get("StorageTotalGiB", "")
        free = data.get("StorageFreeGiB", "")
        if total and free:
            data["_storage"] = f"{free} GiB free of {total} GiB"
        for _label, key, fmt in FIELDS:
            if key in self._value_labels:
                raw = data.get(key, "")
                try:
                    text = fmt(raw) if raw else ""
                except Exception:
                    text = raw
                self._value_labels[key].set_text(text or "—")

        paired = data.get("Paired", "no") == "yes"
        name = data.get("DeviceName", "iPhone")
        if paired:
            self._set_pill(True, f"Connected · {name}")
            self.status.set_text("Paired and trusted.")
        else:
            self._set_pill(True, f"Connected · not trusted")
            self.status.set_text("Connected but not paired — click Pair / Trust.")
        return False

    # -- pairing actions ---------------------------------------------------- #
    def _run_pair(self, action: str):
        if self.runner is not None and self.runner.is_running():
            return
        self._buttons_sensitive(False)
        nice = {"pair": "Pairing", "validate": "Validating", "unpair": "Unpairing"}[action]
        self.status.set_text(f"{nice}…")
        if action == "pair":
            notify(self, "If prompted, unlock the iPhone and tap Trust.", "info")
        self.runner = ScriptRunner(
            [str(config.pair_script()), action],
            on_done=lambda rc, err, a=action: self._on_pair_done(a, rc, err),
        )
        self.runner.start()

    def _on_pair_done(self, action, rc, error):
        if error or rc != 0:
            notify(self, f"{action.capitalize()} failed (see Device status).", "error")
            self.status.set_text(
                f"{action.capitalize()} failed. For Pair, make sure the phone is "
                "unlocked and you tapped Trust."
            )
            self._buttons_sensitive(True)
        else:
            notify(self, f"{action.capitalize()} succeeded.", "success")
            self.refresh()  # re-enables buttons when it finishes
        return False
