"""Optional shared tray loop; only the existing CLI mutates workspace state."""

import argparse
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time

from dwork_tray import client, startup
from dwork_tray.model import plain, workspace_items
from dwork_tray.platforms import CompanionError, load_ui


class Companion:
    def __init__(self, ui, image, schedule, completion_directory, interval=15):
        self.ui, self.schedule = ui, schedule
        self.directory, self.interval = Path(completion_directory), interval
        self.rows = ()
        self.message = "Loading workspace status…"
        self.startup_enabled = None
        self.startup_error = ""
        self.closed = threading.Event()
        self.jobs = queue.Queue()
        self.pending = []
        self.icon = ui.Icon("dwork", image, "dwork workspaces", menu=ui.Menu(self.menu_items))

    def enqueue(self, action, name=None):
        if not self.closed.is_set():
            self.jobs.put((action, name))

    def menu_items(self):
        item = self.ui.MenuItem
        yield item(plain(self.message), None, enabled=False)
        for row in self.rows:
            # Values remain argv data. A later rename is validated again by core.
            yield item(row.label, self.activation(row.name), enabled=row.available)
        yield self.ui.Menu.SEPARATOR
        yield item("Refresh", lambda icon, entry: self.enqueue("refresh"))
        yield item("Stop eligible workspaces…", lambda icon, entry: self.enqueue("down"))
        yield item(
            "Start at login",
            lambda icon, entry: self.enqueue("startup"),
            checked=lambda entry: bool(self.startup_enabled),
            enabled=self.startup_enabled is not None,
        )
        yield item("Quit tray", lambda icon, entry: self.quit())

    def activation(self, name):
        def activate(icon, entry):
            self.enqueue("switch", name)

        return activate

    def publish(self, rows=None, message=None, enabled=None):
        def update():
            if self.closed.is_set():
                return
            if rows is not None:
                self.rows = rows
            if message is not None:
                self.message = message
            if enabled is not None:
                self.startup_enabled = enabled
            self.icon.update_menu()

        self.schedule(update)

    def refresh(self):
        try:
            rows = workspace_items(client.read_status())
            self.publish(
                rows=rows, message="Registered workspaces — select to activate" + self.startup_error
            )
        except (CompanionError, OSError, ValueError, KeyError, TypeError) as error:
            self.publish(rows=(), message="Status unavailable: " + str(error))

    def work(self):
        try:
            self.publish(enabled=startup.state())
        except (CompanionError, OSError) as error:
            self.startup_error = "; login entry: " + str(error)
            self.publish(message=str(error))
        next_refresh = 0
        while not self.closed.is_set():
            try:
                action, name = self.jobs.get(timeout=0.5)
            except queue.Empty:
                action, name = "idle", None
            if self.closed.is_set():
                break
            try:
                if action in ("switch", "down"):
                    self.pending.append(client.open_operation(action, name, self.directory))
                    next_refresh = 0
                elif action == "startup":
                    enabled = not startup.state()
                    startup.set_enabled(enabled)
                    self.publish(
                        enabled=enabled,
                        message="Login startup "
                        + ("enabled for next login" if enabled else "disabled"),
                    )
                elif action == "refresh":
                    next_refresh = 0
                for marker in self.pending[:]:
                    if marker.exists():
                        marker.unlink()
                        self.pending.remove(marker)
                        next_refresh = 0
                if time.monotonic() >= next_refresh:
                    self.refresh()
                    next_refresh = time.monotonic() + self.interval
            except (CompanionError, OSError, ValueError, KeyError, TypeError) as error:
                self.publish(message="Operation unavailable: " + str(error))

    def setup(self, icon):
        self.schedule(lambda: setattr(icon, "visible", True))
        threading.Thread(target=self.work, name="dwork-tray-worker", daemon=False).start()

    def quit(self):
        # Never stop commands, signal tracked processes, or change login settings.
        self.closed.set()
        self.jobs.put(("quit", None))
        self.icon.stop()

    def run(self):
        try:
            self.icon.run(setup=self.setup)
        finally:
            self.closed.set()
            self.jobs.put(("quit", None))


def cli(argv=None):
    parser = argparse.ArgumentParser(
        description="Optional dwork tray companion for native Linux and macOS"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check tray dependencies/host without starting the icon or CLI operations",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Read-only refresh interval in seconds (5–3600; default 15)",
    )
    parser.add_argument(
        "--autostart",
        choices=("enable", "disable", "status"),
        help="Explicitly manage this installation's user login entry (never starts it now)",
    )
    args = parser.parse_args(argv)
    if not 5 <= args.interval <= 3600:
        parser.error("--interval must be between 5 and 3600 seconds")
    if args.check and args.autostart:
        parser.error("--check and --autostart are separate operations")
    try:
        if args.autostart:
            if args.autostart == "status":
                print("enabled" if startup.state() else "disabled")
            else:
                path = startup.set_enabled(args.autostart == "enable")
                print(
                    "Login startup "
                    + ("enabled" if args.autostart == "enable" else "disabled")
                    + ": "
                    + str(path)
                    + "; current workspaces and tray processes were left alone."
                )
            return 0
        ui, image, schedule = load_ui()
        if args.check:
            print(
                "Supported tray backend and host available; no applications or workspaces launched."
            )
            return 0
        with tempfile.TemporaryDirectory(prefix="dwork-tray-") as temporary:
            Companion(ui, image, schedule, temporary, args.interval).run()
        return 0
    except (CompanionError, OSError, ValueError, RuntimeError) as error:
        print("dwork-tray: " + str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
