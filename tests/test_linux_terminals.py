"""Native adapter and fake-launcher tests; never opens a GUI or starts a server."""

from pathlib import Path
from unittest.mock import Mock, patch
import json
import os
import shlex
import shutil
import subprocess
import sys
import unittest

import test_dwork as legacy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import dwork_common
import dwork_terminals


class LinuxTerminalTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "WSL_DISTRO_NAME": "", "SHELL": "/bin/bash", "DISPLAY": ":test",
            "WAYLAND_DISPLAY": "", "DWORK_TERMINAL": "auto",
            "XDG_CURRENT_DESKTOP": "",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.platform = patch.object(sys, "platform", "linux")
        self.platform.start()
        self.addCleanup(self.platform.stop)
        self.task = dwork_common.TerminalTask('Backend "title"', ["echo", "hello world"],
                                         Path("/tmp/repo with spaces"))

    def test_platform_default_and_environment_override(self):
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}):
            self.assertEqual(dwork_terminals.choose_launcher(self.task), "windows-terminal")
        with patch.dict(os.environ, {"DWORK_TERMINAL": "konsole"}):
            self.assertEqual(dwork_terminals.choose_launcher(self.task), "konsole")
            self.task.launcher = "gnome-terminal"
            self.assertEqual(dwork_terminals.choose_launcher(self.task), "gnome-terminal")

    def test_desktop_preference_and_installed_fallback(self):
        for desktop, expected in (("KDE", "konsole"), ("GNOME:ubuntu", "gnome-terminal"),
                                  ("XFCE", "xfce4-terminal")):
            with self.subTest(desktop=desktop), patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": desktop}):
                with patch.object(shutil, "which", side_effect=lambda name: "/usr/bin/" + name):
                    self.assertEqual(dwork_terminals.choose_launcher(self.task), expected)
        with patch.object(shutil, "which", side_effect=lambda name: "/usr/bin/xterm" if name == "xterm" else None):
            self.assertEqual(dwork_terminals.choose_launcher(self.task), "xterm")

    def test_auto_does_not_choose_xterm_for_tabs(self):
        self.task.window = "current"
        with patch.object(shutil, "which", side_effect=lambda name: "/usr/bin/xterm" if name == "xterm" else None):
            with self.assertRaises(dwork_common.DworkError):
                dwork_terminals.choose_launcher(self.task)

    def test_each_adapter_uses_argv_and_documented_command_delimiter(self):
        with patch.object(shutil, "which", side_effect=lambda name: "/usr/bin/" + Path(name).name):
            for launcher, delimiter in (("gnome-terminal", "--"), ("konsole", "-e"),
                                        ("xfce4-terminal", "--execute"), ("xterm", "-e")):
                with self.subTest(launcher=launcher):
                    args = dwork_terminals.linux_terminal_arguments(self.task, launcher)
                    self.assertEqual(args[0], launcher)
                    self.assertIn(self.task.title if launcher != "konsole" else "LocalTabTitleFormat=" + self.task.title, args)
                    command = args[args.index(delimiter) + 1:]
                    self.assertEqual(command, ["/usr/bin/bash", "-lic", "exec echo 'hello world'"])

    def test_tabs_are_explicit_for_supported_adapters(self):
        self.task.window = "current"
        with patch.object(shutil, "which", return_value="/bin/bash"):
            for launcher, flag in (("gnome-terminal", "--tab"), ("konsole", "--new-tab"),
                                   ("xfce4-terminal", "--tab")):
                with self.subTest(launcher=launcher):
                    self.assertIn(flag, dwork_terminals.linux_terminal_arguments(self.task, launcher))
            with self.assertRaisesRegex(dwork_common.DworkError, "does not support"):
                dwork_terminals.linux_terminal_arguments(self.task, "xterm")

    def test_headless_and_missing_executable_fail_preflight(self):
        with patch.dict(os.environ, {"DISPLAY": "", "WAYLAND_DISPLAY": ""}):
            with self.assertRaisesRegex(dwork_common.DworkError, "graphical session"):
                dwork_terminals.linux_terminal_arguments(self.task, "gnome-terminal")
        with patch.object(shutil, "which", return_value=None):
            with self.assertRaisesRegex(dwork_common.DworkError, "unavailable"):
                dwork_terminals.linux_terminal_arguments(self.task, "konsole")
        with patch.dict(os.environ, {"DISPLAY": "", "WAYLAND_DISPLAY": "wayland-0"}):
            with patch.object(shutil, "which", return_value="/bin/bash"):
                with self.assertRaisesRegex(dwork_common.DworkError, "X11"):
                    dwork_terminals.linux_terminal_arguments(self.task, "xterm")

    def test_bad_launcher_is_not_treated_as_shell_code(self):
        with patch.dict(os.environ, {"DWORK_TERMINAL": "xterm -e sh"}):
            with self.assertRaises(dwork_common.DworkError):
                dwork_terminals.choose_launcher(self.task)

    def test_native_process_is_detached_without_pipes_and_reports_immediate_failure(self):
        self.task.launcher = "gnome-terminal"
        process = Mock()
        process.wait.side_effect = subprocess.TimeoutExpired("gnome-terminal", .2)
        with patch.object(shutil, "which", return_value="/bin/bash"):
            with patch.object(subprocess, "Popen", return_value=process) as popen:
                dwork_terminals.open_terminal(self.task)
                self.assertEqual(popen.call_args.kwargs["cwd"], self.task.cwd)
                self.assertTrue(popen.call_args.kwargs["start_new_session"])
                self.assertEqual(popen.call_args.kwargs["stdout"], subprocess.DEVNULL)
                self.assertNotIn("shell", popen.call_args.kwargs)
                process.wait.side_effect = None
                process.wait.return_value = 3
                with self.assertRaisesRegex(dwork_common.DworkError, "exit 3"):
                    dwork_terminals.open_terminal(self.task)

    def test_shell_preserves_special_arguments(self):
        values = ["hello world", 'a"$b&c', "$(echo injected)", "`echo injected`"]
        task = dwork_common.TerminalTask("Quoting", ["python3", "-c",
            "print(__import__('json').dumps(__import__('sys').argv[1:]))", *values], Path("/tmp"))
        for shell in ("bash", "zsh"):
            if not shutil.which(shell):
                continue
            with self.subTest(shell=shell), patch.dict(os.environ, {"SHELL": shutil.which(shell)}):
                # Isolate shell parsing from the developers personal login hooks.
                flags = ["--noprofile", "--norc", "-ic"] if shell == "bash" else ["-f", "-ic"]
                command = [dwork_terminals.command_shell(), *flags, "exec " + shlex.join(task.command)]
                result = subprocess.run(command, cwd=task.cwd, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), values)


class LinuxIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.terminal = self.fixture.bin / "gnome-terminal"
        self.terminal.write_text("""#!/usr/bin/env python3
import json, os, sys
with open(os.environ["DWORK_TEST_LOG"], "a") as f:
    f.write(json.dumps(["linux-terminal", *sys.argv[1:]]) + "\\n")
""")
        self.terminal.chmod(0o755)

    def test_health_gate_before_native_launch_in_both_shells(self):
        self.fixture.model(self.root, "main", services={"db": {}})
        (self.root / "dwork.yml").write_text("""version: 1
compose:
  services: [db]
terminals:
  - command: [echo, ready]
    launcher: gnome-terminal
    wait_for: {healthy: [db]}
""")
        db = legacy.container("a", "main", "db")
        db["State"]["Health"] = {"Status": "healthy"}
        for shell in self.fixture.shells:
            result, changes, calls = self.fixture.run_dwork(
                shell, answer="y\n", containers=[db], WSL_DISTRO_NAME="", SHELL="/bin/bash",
                DISPLAY=":test", WAYLAND_DISPLAY="")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(changes, [["start", "a"]])
            launch = next(i for i, c in enumerate(calls) if c[0] == "linux-terminal")
            start = calls.index(["start", "a"])
            self.assertGreater(launch, start)
            self.assertTrue(any(c[0] == "inspect" for c in calls[start+1:launch]))
            self.assertFalse(any("powershell" in c[0] for c in calls))

    def test_headless_aborts_before_other_projects_are_stopped(self):
        self.fixture.model(self.root, "main")
        (self.root / "dwork.yml").write_text("""version: 1
terminals:
  - command: [echo, ready]
    launcher: gnome-terminal
""")
        for shell in self.fixture.shells:
            result, changes, calls = self.fixture.run_dwork(
                shell, containers=[legacy.container("b", "outside", state="running")],
                WSL_DISTRO_NAME="", SHELL="/bin/bash", DISPLAY="", WAYLAND_DISPLAY="")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(changes, [])
            self.assertIn("graphical session", result.stderr)
            self.assertFalse(any(c[0] == "linux-terminal" for c in calls))

    def test_dry_run_never_opens_native_terminal(self):
        (self.root / "dwork.yml").write_text("""version: 1
compose: {enabled: false}
terminals:
  - command: [echo, ready]
    launcher: gnome-terminal
""")
        for shell in self.fixture.shells:
            result, changes, calls = self.fixture.run_dwork(
                shell, "--dry-run", WSL_DISTRO_NAME="", DISPLAY=":test")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls, [])
            self.assertIn("Would open terminal", result.stdout)

if __name__ == "__main__":
    unittest.main()
