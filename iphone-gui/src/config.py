"""Shared paths and constants for the iPhone Link GUI.

The GUI is a thin front end over the libimobiledevice wrapper scripts in
backend/. It does NOT reimplement any device logic — it builds the right command
line and shows the output. Keeping the scripts authoritative means the CLI and
GUI can never drift.
"""

import os
from pathlib import Path

APP_ID = "io.github.rcraig57.iPhoneLink"
APP_NAME = "iPhone Link"
APP_VERSION = "0.1.0"
ICON_NAME = "io.github.rcraig57.iPhoneLink"

_HERE = Path(__file__).resolve().parent  # .../iphone-gui/src


def icons_dir() -> Path:
    """Base dir holding hicolor/scalable/apps/<icon>.svg (for the icon theme)."""
    return _HERE.parents[0] / "data" / "icons"


def icon_file() -> Path:
    return icons_dir() / "hicolor" / "scalable" / "apps" / f"{ICON_NAME}.svg"


def backend_dir() -> Path:
    """Locate the directory holding the libimobiledevice wrapper scripts.

    Order: $IPHONE_BACKEND_DIR, the dev layout (sibling of iphone-gui), then a
    couple of install locations. Falls back to the first candidate so error
    messages name a sensible path.
    """
    candidates = []
    env = os.environ.get("IPHONE_BACKEND_DIR")
    if env:
        candidates.append(Path(env))
    candidates.append(_HERE.parents[1] / "backend")  # iPhone_utility/backend
    candidates.append(Path("/usr/share/iphone-link/backend"))
    candidates.append(Path("/usr/lib/iphone-link"))
    for c in candidates:
        if (c / "device-info.sh").is_file():
            return c
    return candidates[0]


def device_info_script() -> Path:
    return backend_dir() / "device-info.sh"


def pair_script() -> Path:
    return backend_dir() / "pair.sh"


def style_path() -> Path:
    return _HERE / "style.css"
