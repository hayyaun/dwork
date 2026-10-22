"""Companion policy/transport tests use fake native UI; never opens applications."""

from contextlib import ExitStack, redirect_stderr
import base64
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "companion/src"))
from dwork_tray import app, command, observer, platforms, startup
from dwork_tray import native as client
from dwork_tray.model import workspace_items
from dwork_tray.platforms import CompanionError
import dwork_terminals


def snapshot():
    return {
        "schema_version": 1,
        "scope": "registered",
        "workspaces": [
            {
                "name": "app",
                "status": "host_only",
                "directory_available": True,
                "members": [{"protected": True}],
                "containers": {"running": 0, "total": 0},
                "tasks": {"running": 2, "unresolved": 1},
            }
        ],
    }


class FakeMenu:
    SEPARATOR = object()

    def __init__(self, items):
        self.items = items


class TrayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dwork-tray-tests-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.scheduled = []
        self.icon = Mock()
        self.ui = SimpleNamespace(
            Icon=Mock(return_value=self.icon),
            Menu=FakeMenu,
            MenuItem=lambda text, action, **kwargs: SimpleNamespace(
                text=text, action=action, **kwargs
            ),
        )
        self.companion = app.Companion(
            self.ui, object(), self.scheduled.append, self.root, interval=5
        )

    def test_protocol_client_never_scrapes_text_or_answers_prompts(self):
        response = Mock(returncode=0, stdout=json.dumps(snapshot()), stderr="")
        with patch.object(client, "capture_status", return_value=response):
            self.assertEqual(client.read_status(), snapshot())
        for output in ("NAME STATUS PATH", json.dumps({"schema_version": True}), "[]"):
            with (
                self.subTest(output=output),
                patch.object(
                    client, "capture_status", return_value=Mock(returncode=0, stdout=output)
                ),
                self.assertRaises(CompanionError),
            ):
                client.read_status()
        process = Mock(pid=42, returncode=0)
        process.communicate.return_value = (json.dumps(snapshot()), "")
        context = MagicMock()
        context.__enter__.return_value = process
        with patch.object(subprocess, "Popen", return_value=context) as start:
            result = client.capture_status()
        self.assertEqual(start.call_args.args[0], [sys.executable, "-m", "dwork", "list", "--json"])
        self.assertEqual(start.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertTrue(start.call_args.kwargs["start_new_session"])
        process.communicate.assert_called_once_with(timeout=15)
        self.assertEqual(json.loads(result.stdout), snapshot())
        process.communicate.side_effect = [subprocess.TimeoutExpired("observer", 15), ("", "")]
        with (
            patch.object(subprocess, "Popen", return_value=context),
            patch.object(os, "killpg", create=True) as stop,
            self.assertRaisesRegex(CompanionError, "timed out"),
        ):
            client.capture_status()
        stop.assert_called_once_with(42, observer.signal.SIGKILL)

    def test_menu_data_shows_protection_and_unresolved_tasks_without_mutation(self):
        data = snapshot()
        rows = workspace_items(data)
        self.assertEqual(rows[0].name, "app")
        self.assertIn("protected", rows[0].label)
        self.assertIn("unresolved", rows[0].label)
        self.assertEqual(data, snapshot())
        data["workspaces"][0]["members"].append({"protected": False})
        self.assertIn("[partly protected]", workspace_items(data)[0].label)
        data["workspaces"][0]["name"] = "line\ncontrol\x1bname"
        self.assertNotIn("\n", workspace_items(data)[0].label)
        self.assertNotIn("\x1b", workspace_items(data)[0].label)
        for field, value in (
            ("members", ["invalid"]),
            ("tasks", "invalid"),
            ("containers", {"running": True, "total": 1}),
        ):
            invalid = snapshot()
            invalid["workspaces"][0][field] = value
            with self.subTest(field=field), self.assertRaises(CompanionError):
                workspace_items(invalid)

    def test_refresh_publishes_on_scheduled_ui_thread_only(self):
        with patch.object(client, "read_status", return_value=snapshot()):
            worker = threading.Thread(target=self.companion.refresh)
            worker.start()
            worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.companion.rows, ())
        self.icon.update_menu.assert_not_called()
        self.scheduled.pop()()
        self.assertEqual(self.companion.rows[0].name, "app")
        self.icon.update_menu.assert_called_once()

    def test_click_queues_existing_core_action_without_executing_on_ui_thread(self):
        self.companion.rows = workspace_items(snapshot())
        rows = list(self.companion.menu_items())
        with patch.object(client, "open_operation") as operation:
            rows[1].action(self.icon, rows[1])
            operation.assert_not_called()
        self.assertEqual(self.companion.jobs.get_nowait(), ("switch", "app"))
        self.assertEqual(rows[-1].text, "Quit tray")
        self.assertIsNone(self.companion.startup_enabled)

    def test_periodic_refresh_and_completion_refresh_are_read_only(self):
        calls = []

        def status():
            calls.append("status")
            if len(calls) == 2:
                self.companion.closed.set()
            return snapshot()

        with (
            patch.object(startup, "state", return_value=False),
            patch.object(client, "read_status", side_effect=status),
            patch.object(self.companion.jobs, "get", return_value=("idle", None)),
            patch.object(app.time, "monotonic", side_effect=[10, 10, 15, 15]),
        ):
            self.companion.work()
        self.assertEqual(calls, ["status", "status"])
        self.companion.closed.clear()
        marker = self.root / "operation.done"
        marker.write_text("1")
        self.companion.pending = [marker]
        with (
            patch.object(startup, "state", return_value=False),
            patch.object(
                client,
                "read_status",
                side_effect=lambda: (self.companion.closed.set(), snapshot())[1],
            ) as read,
            patch.object(self.companion.jobs, "get", return_value=("idle", None)),
        ):
            self.companion.work()
        read.assert_called_once()
        self.assertFalse(marker.exists())

    def test_quit_only_closes_the_companion_and_ignores_queued_updates(self):
        self.companion.publish(rows=workspace_items(snapshot()))
        with (
            patch.object(client, "open_operation") as operation,
            patch.object(startup, "set_enabled") as login,
        ):
            self.companion.quit()
            self.companion.enqueue("down")
            self.scheduled.pop()()
            self.companion.work()
        operation.assert_not_called()
        login.assert_not_called()
        self.icon.stop.assert_called_once()
        self.assertEqual(self.companion.rows, ())

    def test_terminal_handoff_has_no_application_task_ownership(self):
        name = "literal 'space' $(not-shell)"
        with patch.object(dwork_terminals, "open_terminal") as open_terminal:
            marker = client.open_operation("switch", name, self.root)
        task = open_terminal.call_args.args[0]
        self.assertIsNone(task.workspace)
        self.assertEqual(task.command[:3], [sys.executable, "-m", "dwork_tray.command"])
        payload = json.loads(base64.urlsafe_b64decode(task.command[3]))
        self.assertEqual(payload, {"action": "switch", "name": name, "marker": str(marker)})
        with patch.object(subprocess, "call", return_value=1) as core:
            self.assertEqual(command.run_operation(payload), 1)
        self.assertEqual(core.call_args.args[0], [sys.executable, "-m", "dwork", "switch", name])
        self.assertEqual(core.call_args.kwargs, {})
        self.assertEqual(marker.read_text(), "1")

    def test_down_is_explicit_and_invalid_actions_never_reach_core(self):
        spec = {"action": "down", "name": None, "marker": str(self.root / "done")}
        with patch.object(subprocess, "call", return_value=0) as core:
            self.assertEqual(command.run_operation(spec), 0)
        self.assertEqual(core.call_args.args[0], [sys.executable, "-m", "dwork", "down"])
        for action in ("forget", "rm", "stop", "quit"):
            with (
                self.subTest(action=action),
                patch.object(subprocess, "call") as core,
                self.assertRaises(ValueError),
            ):
                command.run_operation({**spec, "action": action})
            core.assert_not_called()

    def test_platform_limits_and_main_thread_requirement_are_explicit(self):
        with (
            patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}),
            self.assertRaisesRegex(CompanionError, "Windows-host"),
        ):
            platforms.native_platform()
        with (
            patch.dict(os.environ, {"WSL_DISTRO_NAME": ""}),
            patch.object(sys, "platform", "win32"),
        ):
            self.assertEqual(platforms.native_platform(), "win32")
        with (
            patch.object(threading, "current_thread", return_value=object()),
            self.assertRaisesRegex(CompanionError, "main thread"),
        ):
            platforms.load_ui()
        with (
            patch.object(platforms, "native_platform", return_value="linux"),
            patch.dict(os.environ, {"DISPLAY": "", "WAYLAND_DISPLAY": ""}),
            self.assertRaisesRegex(CompanionError, "graphical"),
        ):
            platforms.load_ui()
        with (
            patch.object(platforms, "native_platform", return_value="linux"),
            patch.dict(os.environ, {"DISPLAY": ":test", "PYSTRAY_BACKEND": "xorg"}),
            self.assertRaisesRegex(CompanionError, "requires PYSTRAY_BACKEND"),
        ):
            platforms.load_ui()

    def test_missing_gui_dependency_fails_without_any_cli_actions(self):
        with (
            patch.object(platforms, "native_platform", return_value="darwin"),
            patch.dict(sys.modules, {"pystray": None}),
            self.assertRaisesRegex(CompanionError, "optional dwork-tray"),
        ):
            platforms.load_ui()
        with (
            patch.object(app, "select_transport", return_value=client.NativeTransport()),
            patch.object(app, "load_ui", side_effect=CompanionError("missing indicator host")),
            patch.object(client, "open_operation") as operation,
            redirect_stderr(io.StringIO()) as errors,
        ):
            self.assertEqual(app.cli(["--check"]), 1)
        operation.assert_not_called()
        self.assertIn("missing indicator host", errors.getvalue())

    def test_native_ui_schedulers_use_public_main_loop_apis(self):
        callbacks = []
        image = SimpleNamespace(new=Mock(return_value=object()))
        draw = SimpleNamespace(Draw=Mock())
        pystray = SimpleNamespace(Icon=SimpleNamespace(HAS_MENU=True))
        glib = SimpleNamespace(
            Variant=lambda *args: object(),
            VariantType=SimpleNamespace(new=lambda kind: kind),
            idle_add=callbacks.append,
            Error=RuntimeError,
        )
        bus = SimpleNamespace(call_sync=Mock(return_value=SimpleNamespace(unpack=lambda: (True,))))
        gio = SimpleNamespace(
            bus_get_sync=lambda *args: bus,
            BusType=SimpleNamespace(SESSION=0),
            DBusCallFlags=SimpleNamespace(NONE=0),
        )
        modules = {
            "pystray": pystray,
            "PIL": SimpleNamespace(Image=image, ImageDraw=draw),
            "gi": SimpleNamespace(),
            "gi.repository": SimpleNamespace(GLib=glib, Gio=gio),
            "PyObjCTools": SimpleNamespace(AppHelper=SimpleNamespace(callAfter=callbacks.append)),
        }
        for platform in ("linux", "darwin"):
            with (
                self.subTest(platform=platform),
                patch.dict(sys.modules, modules),
                patch.object(platforms, "native_platform", return_value=platform),
                patch.dict(os.environ, {"DISPLAY": ":test", "PYSTRAY_BACKEND": "appindicator"}),
            ):
                _, _, schedule = platforms.load_ui()
                callback = Mock()
                schedule(callback)
                callback.assert_not_called()
                queued = callbacks.pop()
                queued()
                callback.assert_called_once()
        with (
            patch.dict(sys.modules, modules),
            patch.object(platforms, "native_platform", return_value="linux"),
            patch.dict(os.environ, {"DISPLAY": ":test", "PYSTRAY_BACKEND": "appindicator"}),
        ):
            bus.call_sync.return_value = SimpleNamespace(unpack=lambda: (False,))
            with self.assertRaisesRegex(CompanionError, "No StatusNotifier"):
                platforms.load_ui()

    def test_status_failure_clears_stale_action_rows(self):
        self.companion.rows = workspace_items(snapshot())
        with patch.object(client, "read_status", side_effect=CompanionError("offline")):
            self.companion.refresh()
        self.scheduled.pop()()
        self.assertEqual(self.companion.rows, ())
        self.assertIn("offline", self.companion.message)


class StartupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dwork-login-tests-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def environment(self, stack, platform):
        stack.enter_context(patch.object(platforms, "native_platform", return_value=platform))
        stack.enter_context(patch.object(startup, "native_platform", return_value=platform))
        stack.enter_context(patch.object(Path, "home", return_value=self.root))
        stack.enter_context(patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config")}))

    def test_login_is_opt_in_and_exact_owned_entries_are_idempotent(self):
        for platform in ("linux", "darwin"):
            with self.subTest(platform=platform), ExitStack() as stack:
                self.environment(stack, platform)
                path, content = startup.entry()
                self.assertFalse(startup.state())
                self.assertFalse(path.exists())
                startup.set_enabled(True)
                self.assertTrue(startup.state())
                self.assertEqual(path.read_bytes(), content)
                startup.set_enabled(True)
                if platform == "darwin":
                    entry = plistlib.loads(content)
                    self.assertTrue(entry["RunAtLoad"])
                    self.assertFalse(entry["KeepAlive"])
                    self.assertEqual(entry["ProgramArguments"][1:], ["-m", "dwork_tray"])
                startup.set_enabled(False)
                self.assertFalse(path.exists())

    def test_edited_or_linked_login_entries_are_preserved(self):
        for platform in ("linux", "darwin"):
            with self.subTest(platform=platform), ExitStack() as stack:
                self.environment(stack, platform)
                path, _ = startup.entry()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"user-owned")
                for enabled in (True, False):
                    with self.assertRaisesRegex(CompanionError, "edited or belongs"):
                        startup.set_enabled(enabled)
                    self.assertEqual(path.read_bytes(), b"user-owned")
                path.unlink()
                outside = self.root / "outside"
                outside.write_bytes(b"outside")
                path.symlink_to(outside)
                for enabled in (True, False):
                    with self.assertRaisesRegex(CompanionError, "symlink"):
                        startup.set_enabled(enabled)
                    self.assertEqual(outside.read_bytes(), b"outside")

    def test_unsupported_desktop_executable_path_never_writes_login_entry(self):
        with ExitStack() as stack:
            self.environment(stack, "linux")
            stack.enter_context(
                patch.object(sys, "executable", str(self.root / "venv%name/bin/python"))
            )
            with self.assertRaisesRegex(CompanionError, "unsupported by the desktop launcher"):
                startup.set_enabled(True)
        self.assertFalse((self.root / "config").exists())

    def test_venv_python_path_is_not_resolved_away(self):
        with ExitStack() as stack:
            self.environment(stack, "darwin")
            stack.enter_context(patch.object(sys, "executable", str(self.root / "venv/bin/python")))
            _, content = startup.entry()
        self.assertEqual(
            plistlib.loads(content)["ProgramArguments"][0], str(self.root / "venv/bin/python")
        )


if __name__ == "__main__":
    unittest.main()
