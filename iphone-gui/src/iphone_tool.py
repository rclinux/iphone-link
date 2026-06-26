#!/usr/bin/env python3
"""iPhone Link — GTK4 front end for the libimobiledevice wrapper scripts.

Securely links a connected iPhone to this Linux system. Run via the
`iphone-link` launcher (or directly with python3 for previewing). The GUI is a
thin wrapper: every operation runs an audited shell script in backend/, so the
GUI and CLI never drift apart.
"""

import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

import config  # noqa: E402
from about_page import AboutPage  # noqa: E402
from device_page import DevicePage  # noqa: E402
from documents_page import DocumentsPage  # noqa: E402
from media_page import MediaPage  # noqa: E402
from messages_page import MessagesPage  # noqa: E402
from notes_page import NotesPage  # noqa: E402
from photos_page import PhotosPage  # noqa: E402
from widgets import Toast  # noqa: E402


class IPhoneLinkWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title(config.APP_NAME)
        self.set_default_size(1100, 820)
        self.set_icon_name(config.ICON_NAME)

        header = Gtk.HeaderBar()
        self.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        body.set_vexpand(True)

        # Float transient toasts over the page area, bottom-centre.
        overlay = Gtk.Overlay()
        overlay.set_vexpand(True)
        overlay.set_child(body)
        self.toast = Toast()
        overlay.add_overlay(self.toast)
        root.append(overlay)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)

        sidebar = Gtk.StackSidebar()
        sidebar.set_stack(self.stack)
        sidebar.set_name("sidebar")
        sidebar.set_size_request(180, -1)
        body.append(sidebar)
        body.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        body.append(self.stack)

        self.stack.add_titled(DevicePage(), "device", "Device")
        self.stack.add_titled(PhotosPage(), "photos", "Photos")
        self.stack.add_titled(DocumentsPage(), "documents", "Documents")
        self.stack.add_titled(MessagesPage(), "messages", "Messages")
        self.stack.add_titled(NotesPage(), "notes", "Notes")
        self.stack.add_titled(MediaPage(), "media", "Media")
        self.stack.add_titled(AboutPage(), "about", "About")

        # Optional: open on a specific page (handy for launchers / testing).
        initial = os.environ.get("IPHONE_INITIAL_PAGE")
        if initial:
            self.stack.set_visible_child_name(initial)

    def show_toast(self, message: str, kind: str = "info"):
        """Reveal a transient notification; reached from pages via widgets.notify."""
        self.toast.show(message, kind)


class IPhoneLinkApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=config.APP_ID)

    def do_activate(self):
        self._register_icons()
        self._load_css()
        win = self.get_active_window() or IPhoneLinkWindow(self)
        win.present()

    def _register_icons(self):
        display = Gdk.Display.get_default()
        if display is None:
            return
        theme = Gtk.IconTheme.get_for_display(display)
        theme.add_search_path(str(config.icons_dir()))

    def _load_css(self):
        display = Gdk.Display.get_default()
        if display is None:
            return
        provider = Gtk.CssProvider()
        try:
            provider.load_from_string(config.style_path().read_text())
        except (OSError, AttributeError):
            provider.load_from_path(str(config.style_path()))
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


def main():
    app = IPhoneLinkApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
