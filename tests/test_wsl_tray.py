"""Windows-to-WSL transport regressions; no real workspace operations or icons."""

import base64
from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "companion/src"))
from dwork_tray import app, client, observer, platforms, startup, wsl, wsl_terminal
from dwork_tray.platforms import CompanionError


def snapshot():
    return {"schema_version": 1, "scope": "registered", "workspaces": []}


def response(output=b"", code=0, errors=b""):
    return subprocess.CompletedProcess([], code, output, errors)


class WslTransportTests(unittest.TestCase):
    def setUp(self):
        tools = patch.object(wsl.shutil, "which", side_effect=lambda name: "C:/tools/" + name)
        tools.start()
        self.addCleanup(tools.stop)
        flags = patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True)
        flags.start()
        self.addCleanup(flags.stop)
        self.transport = wsl.WslTransport("Ubuntu Test", "/home/me/env space/bin/python", "me")

    def test_explicit_target_is_required_and_never_uses_default_distro(self):
        for values in (
            (None, None),
            ("", "/usr/bin/python3"),
            ("Ubuntu", "python3"),
            ("Ubuntu\nOther", "/usr/bin/python3"),
            ("-other", "/usr/bin/python3"),
        ):
            with self.subTest(values=values), self.assertRaises(CompanionError):
                wsl.WslTransport(*values)
        self.assertEqual(
            self.transport.command(),
            [
                "C:/tools/wsl.exe",
                "--distribution",
                "Ubuntu Test",
                "--user",
                "me",
                "--cd",
                "~",
                "--exec",
                "/home/me/env space/bin/python",
            ],
        )
        self.assertFalse(self.transport.supports_startup)
        self.assertIn("Ubuntu Test / me", self.transport.label)

    def test_stopped_or_missing_distro_never_gets_a_command_or_terminal(self):
        for output in (b"", "Debian\r\n".encode("utf-16")):
            for action in (
                lambda: self.transport.read_status(),
                lambda: self.transport.open_operation("switch", "app", "."),
            ):
                with (
                    self.subTest(output=output),
                    patch.object(subprocess, "run", return_value=response(output)) as run,
                ):
                    with self.assertRaisesRegex(CompanionError, "stopped or unavailable"):
                        action()
                    self.assertEqual(run.call_count, 1)
                    self.assertEqual(run.call_args.args[0][1:], ["--list", "--running", "--quiet"])

    def test_utf16_and_utf8_lists_are_names_not_localized_tables(self):
        for output in (
            "Ubuntu Test\r\n".encode("utf-16"),
            "Ubuntu Test\n".encode("utf-16-le"),
            b"Ubuntu Test\n",
        ):
            with (
                self.subTest(output=output),
                patch.object(wsl, "hidden_run", return_value=response(output)),
            ):
                self.transport.require_running()
        with patch.object(
            wsl,
            "hidden_run",
            return_value=response(code=1, errors="WSL unavailable".encode("utf-16")),
        ):
            with self.assertRaisesRegex(CompanionError, "WSL unavailable"):
                self.transport.require_running()

    def test_status_uses_selected_interpreter_bounded_observer_and_json_only(self):
        with patch.object(
            subprocess,
            "run",
            side_effect=[response(b"Ubuntu Test\n"), response(json.dumps(snapshot()).encode())],
        ) as run:
            self.assertEqual(self.transport.read_status(), snapshot())
        command = run.call_args.args[0]
        self.assertEqual(command[:-2], self.transport.command())
        self.assertEqual(command[-2], "-c")
        self.assertIn("start_new_session=True", command[-1])
        self.assertIn("timeout=15", command[-1])
        self.assertNotIn("dwork_tray", command[-1])
        self.assertEqual(run.call_args.kwargs["timeout"], 25)
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)
        self.assertNotIn("shell", run.call_args.kwargs)
        for result in (response(b"NAME STATUS"), response(code=1, errors=b"No module named dwork")):
            with patch.object(wsl, "hidden_run", side_effect=[response(b"Ubuntu Test\n"), result]):
                with self.assertRaisesRegex(CompanionError, "wsl-python"):
                    self.transport.read_status()

    def test_timeouts_only_stop_owned_helpers_and_do_not_terminate_wsl(self):
        with patch.object(
            subprocess, "run", side_effect=subprocess.TimeoutExpired("wsl", 25)
        ) as run:
            with self.assertRaisesRegex(
                CompanionError, "no workspace or distribution was terminated"
            ):
                self.transport.read_status()
        self.assertEqual(run.call_count, 1)
        self.assertNotIn("--terminate", run.call_args.args[0])
        self.assertNotIn("--shutdown", run.call_args.args[0])
        with patch.object(
            observer, "capture_status", side_effect=subprocess.TimeoutExpired("observer", 15)
        ):
            with redirect_stderr(io.StringIO()) as error:
                self.assertEqual(observer.main(), 124)
        self.assertIn("timed out", error.getvalue())

    def test_terminal_handoff_encodes_metacharacters_and_preserves_exact_operation(self):
        name = "space ' quote \" ; $(no-shell) & café 工作"
        with tempfile.TemporaryDirectory() as temporary:
            python = "C:/env ' ; $ & café/python.exe"
            with (
                patch.object(
                    wsl, "hidden_run", side_effect=[response(b"Ubuntu Test\n"), response()]
                ) as run,
                patch.object(wsl, "windows_python", return_value=python),
            ):
                marker = self.transport.open_operation("switch", name, temporary)
            command = run.call_args.args[0]
            self.assertEqual(
                command[:7],
                [
                    "C:/tools/wt.exe",
                    "--window",
                    "new",
                    "new-tab",
                    "--title",
                    "dwork",
                    "C:/tools/powershell.exe",
                ],
            )
            self.assertEqual(command[7:10], ["-NoLogo", "-NoProfile", "-EncodedCommand"])
            self.assertTrue(all(";" not in arg for arg in command))
            script = base64.b64decode(command[-1]).decode("utf-16-le")
            self.assertIn(python.replace("'", "''"), script)
            payload = script.split("'dwork_tray.wsl_terminal' '")[1].split("'")[0]
            spec = json.loads(base64.urlsafe_b64decode(payload))
            self.assertEqual(
                spec,
                {
                    "distribution": "Ubuntu Test",
                    "python": self.transport.python,
                    "user": "me",
                    "action": "switch",
                    "name": name,
                    "marker": str(marker),
                },
            )
            with (
                patch.object(sys, "platform", "win32"),
                patch.object(subprocess, "call", return_value=7) as call,
            ):
                self.assertEqual(wsl_terminal.run_operation(spec), 7)
            self.assertEqual(
                call.call_args.args[0], self.transport.command() + ["-m", "dwork", "switch", name]
            )
            self.assertEqual(call.call_args.kwargs, {})
            self.assertEqual(marker.read_text(), "7")

    def test_down_is_explicit_and_invalid_actions_never_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            spec = {
                "distribution": "Ubuntu",
                "python": "/usr/bin/python3",
                "action": "down",
                "marker": str(Path(temporary) / "done"),
            }
            with (
                patch.object(sys, "platform", "win32"),
                patch.object(subprocess, "call", return_value=0) as call,
            ):
                wsl_terminal.run_operation(spec)
            self.assertEqual(call.call_args.args[0][-3:], ["-m", "dwork", "down"])
            for action in ("stop", "forget", "rm", "quit"):
                with self.subTest(action=action), patch.object(subprocess, "run") as run:
                    with self.assertRaises(CompanionError):
                        self.transport.open_operation(action, None, temporary)
                    run.assert_not_called()
            with (
                patch.object(sys, "platform", "win32"),
                patch.object(subprocess, "call", side_effect=KeyboardInterrupt),
            ):
                self.assertEqual(wsl_terminal.run_operation(spec), 130)
            self.assertEqual(Path(spec["marker"]).read_text(), "130")

    def test_terminal_launcher_error_is_visible_and_does_not_retry(self):
        with patch.object(
            wsl,
            "hidden_run",
            side_effect=[response(b"Ubuntu Test\n"), response(code=1, errors=b"terminal failed")],
        ) as run:
            with self.assertRaisesRegex(CompanionError, "terminal failed"):
                self.transport.open_operation("down", None, ".")
        self.assertEqual(run.call_count, 2)

    def test_missing_host_tools_report_guidance(self):
        for missing in ("wsl.exe", "wt.exe", "powershell.exe"):
            with (
                self.subTest(missing=missing),
                patch.object(
                    wsl.shutil, "which", side_effect=lambda name: None if name == missing else name
                ),
            ):
                with self.assertRaisesRegex(CompanionError, missing):
                    wsl.WslTransport("Ubuntu", "/usr/bin/python3")


class WslUiTests(unittest.TestCase):
    def test_windows_login_cannot_write_and_native_options_are_scoped(self):
        args = SimpleNamespace(
            wsl_distribution="Ubuntu", wsl_python="/usr/bin/python3", wsl_user=None, autostart=None
        )
        with patch.object(app, "native_platform", return_value="linux"):
            with self.assertRaisesRegex(CompanionError, "Windows host"):
                app.select_transport(args)
        with (
            patch.object(app, "native_platform", return_value="win32"),
            patch.object(wsl, "WslTransport") as transport,
        ):
            app.select_transport(args)
            transport.assert_called_once_with("Ubuntu", "/usr/bin/python3", None)
        with (
            patch.object(startup, "native_platform", return_value="win32"),
            patch.object(Path, "mkdir") as mkdir,
        ):
            with self.assertRaisesRegex(CompanionError, "not implemented"):
                startup.set_enabled(True)
            mkdir.assert_not_called()
        with (
            patch.object(app, "native_platform", return_value="win32"),
            redirect_stderr(io.StringIO()) as error,
        ):
            self.assertEqual(app.cli(["--autostart", "enable"]), 1)
        self.assertIn("no settings were changed", error.getvalue())

    def test_windows_menu_has_no_login_action_and_quit_is_local(self):
        transport = Mock(supports_startup=False, label="WSL: Ubuntu")
        transport.read_status.return_value = snapshot()
        ui = SimpleNamespace(
            Icon=Mock(),
            Menu=Mock(SEPARATOR=object()),
            MenuItem=lambda text, action, **kw: SimpleNamespace(text=text, action=action, **kw),
        )
        companion = app.Companion(ui, None, lambda callback: callback(), ".", transport=transport)
        self.assertNotIn(
            "Start at login",
            [entry.text for entry in companion.menu_items() if hasattr(entry, "text")],
        )
        with patch.object(startup, "state") as state:
            companion.quit()
            companion.work()
        state.assert_not_called()
        transport.open_operation.assert_not_called()
        transport.read_status.assert_not_called()
        companion.icon.stop.assert_called_once()

    def test_windows_ui_uses_public_backend_without_gi_or_cocoa(self):
        ui = SimpleNamespace(Icon=SimpleNamespace(HAS_MENU=True))
        modules = {
            "pystray": ui,
            "PIL": SimpleNamespace(Image=Mock(), ImageDraw=Mock()),
            "gi": None,
            "PyObjCTools": None,
        }
        with (
            patch.object(platforms, "native_platform", return_value="win32"),
            patch.dict(os.environ, {"PYSTRAY_BACKEND": "win32"}),
            patch.dict(sys.modules, modules),
        ):
            _, _, schedule = platforms.load_ui()
            callback = Mock()
            schedule(callback)
            callback.assert_called_once()
        with (
            patch.object(platforms, "native_platform", return_value="win32"),
            patch.dict(os.environ, {"PYSTRAY_BACKEND": "gtk"}),
        ):
            with self.assertRaisesRegex(CompanionError, "win32"):
                platforms.load_ui()

    def test_windows_check_reads_status_without_icon_or_operation(self):
        transport = Mock(supports_startup=False)
        transport.read_status.return_value = snapshot()
        with (
            patch.object(app, "select_transport", return_value=transport),
            patch.object(app, "load_ui", return_value=(None, None, None)),
            patch.object(app, "Companion") as companion,
        ):
            self.assertEqual(app.cli(["--check"]), 0)
        transport.read_status.assert_called_once()
        transport.open_operation.assert_not_called()
        companion.assert_not_called()

    def test_observer_source_runs_without_companion_installed_inside_wsl(self):
        with tempfile.TemporaryDirectory() as temporary:
            Path(temporary, "dwork.py").write_text(
                "print(" + repr(json.dumps(snapshot())) + ")", encoding="utf-8"
            )
            source = Path(observer.__file__).read_text(encoding="utf-8")
            env = dict(os.environ, PYTHONPATH=temporary)
            result = subprocess.run(
                [sys.executable, "-c", source], env=env, capture_output=True, text=True
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(client.parse_status(result), snapshot())

    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell quoting integration")
    def test_real_powershell_round_trip_without_wsl_or_terminal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "dwork_tray"
            package.mkdir()
            (package / "__init__.py").write_text("")
            (package / "wsl_terminal.py").write_text(
                "import os, pathlib, sys; pathlib.Path(os.environ['DWORK_TEST_OUTPUT']).write_text(sys.argv[1], encoding='utf-8')"
            )
            spec = {"name": "quotes ' \" ; $() & 工作", "distribution": "Ubuntu"}
            command = wsl.terminal_command("wt.exe", "powershell.exe", spec)
            env = dict(os.environ, PYTHONPATH=temporary, DWORK_TEST_OUTPUT=str(root / "result"))
            result = subprocess.run(command[6:], env=env, cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            actual = json.loads(base64.urlsafe_b64decode((root / "result").read_text()))
            self.assertEqual(actual, spec)


if __name__ == "__main__":
    unittest.main()
