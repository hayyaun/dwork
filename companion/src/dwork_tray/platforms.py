"""Small native integrations using public pystray, GLib, and AppHelper APIs."""

import os
import sys
import threading


class CompanionError(Exception):
    pass


def native_platform():
    if sys.platform == "win32":
        return "win32"
    if os.environ.get("WSL_DISTRO_NAME"):
        raise CompanionError(
            "Run the Windows-host companion from PowerShell with --wsl-distribution and --wsl-python. A Linux tray inside WSL is unsupported; the dwork CLI remains usable here."
        )
    if sys.platform == "darwin":
        if sys.version_info < (3, 13):
            raise CompanionError(
                "The macOS companion requires Python 3.13+ for dwork's tracked-command support."
            )
        return "darwin"
    if sys.platform.startswith("linux"):
        return "linux"
    raise CompanionError(
        "The companion currently supports native Linux and macOS; the CLI remains available on its supported platforms."
    )


def load_ui():
    if threading.current_thread() is not threading.main_thread():
        raise CompanionError("The tray event loop must run on the main thread.")
    platform = native_platform()
    if platform == "linux":
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise CompanionError(
                "A graphical Linux desktop is required; use the dwork CLI in headless sessions."
            )
        backend = os.environ.get("PYSTRAY_BACKEND", "appindicator")
        if backend != "appindicator":
            raise CompanionError(
                "The Linux companion requires PYSTRAY_BACKEND=appindicator (AppIndicator or Ayatana); GTK legacy/Xorg fallback cannot guarantee the required menu."
            )
        os.environ.setdefault("PYSTRAY_BACKEND", "appindicator")
    if platform == "win32":
        if os.environ.get("PYSTRAY_BACKEND", "win32") != "win32":
            raise CompanionError("The Windows companion requires PYSTRAY_BACKEND=win32.")
        os.environ.setdefault("PYSTRAY_BACKEND", "win32")
    try:
        import pystray
        from PIL import Image, ImageDraw

        if platform == "darwin":
            from PyObjCTools import AppHelper

            schedule = AppHelper.callAfter
        elif platform == "win32":
            # pystray supports its Windows loop on any thread. Public icon/menu
            # operations can run in the setup/worker thread; no private messages.
            def schedule(callback):
                callback()

        else:
            from gi.repository import Gio, GLib

            try:
                bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
                owned = False
                for watcher in (
                    "org.kde.StatusNotifierWatcher",
                    "org.freedesktop.StatusNotifierWatcher",
                ):
                    present = bus.call_sync(
                        "org.freedesktop.DBus",
                        "/org/freedesktop/DBus",
                        "org.freedesktop.DBus",
                        "NameHasOwner",
                        GLib.Variant("(s)", (watcher,)),
                        GLib.VariantType.new("(b)"),
                        Gio.DBusCallFlags.NONE,
                        1000,
                        None,
                    ).unpack()[0]
                    if present:
                        owned = bool(
                            bus.call_sync(
                                watcher,
                                "/StatusNotifierWatcher",
                                "org.freedesktop.DBus.Properties",
                                "Get",
                                GLib.Variant("(ss)", (watcher, "IsStatusNotifierHostRegistered")),
                                GLib.VariantType.new("(v)"),
                                Gio.DBusCallFlags.NONE,
                                1000,
                                None,
                            ).unpack()[0]
                        )
                        if owned:
                            break
            except GLib.Error as error:
                raise CompanionError(
                    "Cannot inspect the desktop session bus: "
                    + str(error)
                    + "; use the CLI until the tray host is available."
                ) from error
            if not owned:
                raise CompanionError(
                    "No StatusNotifier tray host is running. On GNOME enable compatible AppIndicator/Ayatana indicator support; other desktops need a StatusNotifier host. The CLI is unaffected."
                )

            def schedule(callback):
                def once():
                    callback()
                    return False

                GLib.idle_add(once)

        if not pystray.Icon.HAS_MENU:
            raise CompanionError(
                "This tray backend does not support menus; use AppIndicator/Ayatana on Linux, Cocoa on macOS, or Win32 on Windows."
            )
    except (ImportError, ValueError, RuntimeError) as error:
        raise CompanionError(
            "Tray backend unavailable: "
            + str(error)
            + ". Install the optional dwork-tray package. Linux also needs PyGObject and AppIndicator/Ayatana introspection libraries visible to this Python, plus a compatible desktop indicator host. CLI installs do not need these dependencies."
        ) from error
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((6, 6, 58, 58), radius=12, fill="#253443")
    draw.line((19, 21, 29, 31, 19, 41), fill="white", width=5)
    draw.line((34, 42, 46, 42), fill="#68dfb3", width=4)
    return pystray, image, schedule
