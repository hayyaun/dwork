"""Apple Terminal adapter tests; never execute AppleScript or open a GUI."""
from pathlib import Path
from unittest.mock import Mock, patch
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import dwork_common
import dwork_terminals
import dwork_tasks
import test_dwork as legacy


class MacOSTerminalTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"WSL_DISTRO_NAME": "", "SHELL": "/bin/zsh",
                                           "DWORK_TERMINAL": "auto"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.platform = patch.object(sys, "platform", "darwin")
        self.platform.start()
        self.addCleanup(self.platform.stop)
        self.task = dwork_common.TerminalTask('Title " & \\ test',
            ["echo", "hello world", "$(touch injected)", "a'b"], Path("/tmp/repo 'with spaces"))
        self.which = patch.object(shutil, "which", side_effect=lambda name: "/usr/bin/" + Path(name).name)
        self.which.start()
        self.addCleanup(self.which.stop)

    def test_auto_selects_apple_terminal_and_explicit_settings_keep_precedence(self):
        self.assertEqual(dwork_terminals.choose_launcher(self.task), "apple-terminal")
        with patch.dict(os.environ, {"DWORK_TERMINAL": "apple-terminal"}):
            self.assertEqual(dwork_terminals.choose_launcher(self.task), "apple-terminal")
            self.task.launcher = "gnome-terminal"
            self.assertEqual(dwork_terminals.choose_launcher(self.task), "gnome-terminal")
        self.task.launcher = "auto"
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}):
            self.assertEqual(dwork_terminals.choose_launcher(self.task), "windows-terminal")

    def test_command_and_title_are_data_and_shell_arguments_round_trip(self):
        args = dwork_terminals.macos_terminal_arguments(self.task)
        self.assertEqual(args[:2], ["osascript", "-"])
        self.assertEqual(args[3], self.task.title)
        self.assertEqual(shlex.split(args[2]),
                         ["cd", "--", str(self.task.cwd), "&&", *dwork_terminals.task_command(self.task)])
        self.assertNotIn(self.task.title, dwork_terminals.APPLE_TERMINAL_SCRIPT)
        self.assertIn('do script (item 1 of argv)', dwork_terminals.APPLE_TERMINAL_SCRIPT)
        self.assertNotIn("System Events", dwork_terminals.APPLE_TERMINAL_SCRIPT)

    def test_registered_task_keeps_supervisor_and_identity(self):
        self.task.workspace = "/tmp/workspace"
        self.task.directory = str(self.task.cwd)
        self.task.project = "frontend"
        # This test verifies argv transport while running under Linux's Python;
        # the runtime capability check is independently covered by task tests.
        with patch.object(dwork_tasks, "require_support"):
            args = dwork_terminals.macos_terminal_arguments(self.task)
            self.assertEqual(shlex.split(args[2])[4:], dwork_terminals.task_command(self.task))

    def test_tabs_missing_interpreter_and_wrong_platform_fail_before_launch(self):
        self.task.window = "current"
        with self.assertRaisesRegex(dwork_common.DworkError, "new only"):
            dwork_terminals.macos_terminal_arguments(self.task)
        self.task.window = "new"
        with patch.object(shutil, "which", return_value=None):
            with self.assertRaisesRegex(dwork_common.DworkError, "osascript"):
                dwork_terminals.macos_terminal_arguments(self.task)
        with patch.object(sys, "platform", "linux"):
            with self.assertRaisesRegex(dwork_common.DworkError, "requires macOS"):
                dwork_terminals.macos_terminal_arguments(self.task)

    def test_launcher_uses_stdin_and_reports_automation_errors(self):
        with patch.object(subprocess, "run", return_value=Mock(returncode=0)) as run:
            dwork_terminals.open_terminal(self.task)
            self.assertEqual(run.call_args.args[0], dwork_terminals.macos_terminal_arguments(self.task))
            self.assertEqual(run.call_args.kwargs["input"], dwork_terminals.APPLE_TERMINAL_SCRIPT)
            self.assertTrue(run.call_args.kwargs["capture_output"])
            self.assertNotIn("shell", run.call_args.kwargs)
            run.return_value = Mock(returncode=1, stderr="Not authorized to send Apple events (-1743)")
            with self.assertRaisesRegex(dwork_common.DworkError, "Automation permission"):
                dwork_terminals.open_terminal(self.task)

    def test_preflight_rejects_tab_before_any_command_launch(self):
        self.task.window = "current"
        with patch.object(dwork_tasks, "require_support"), patch.object(subprocess, "run") as run:
            with self.assertRaisesRegex(dwork_common.DworkError, "new only"):
                dwork_terminals.preflight_terminals([self.task])
            run.assert_not_called()


@unittest.skipUnless(sys.platform == "darwin", "Requires the installed macOS Terminal dictionary")
class MacOSDictionaryTests(unittest.TestCase):
    def test_script_compiles_against_the_installed_terminal_dictionary(self):
        # Compiling checks the supported application dictionary without executing
        # the script, opening terminals, or asking for Automation permission.
        with tempfile.TemporaryDirectory(prefix="dwork-applescript-") as temporary:
            script = Path(temporary) / "terminal.applescript"
            script.write_text(dwork_terminals.APPLE_TERMINAL_SCRIPT)
            result = subprocess.run(["osacompile", "-o", str(Path(temporary) / "terminal.scpt"), str(script)],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless(sys.platform == "darwin", "Requires the actual macOS launch path")
class MacOSIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        interpreter = self.fixture.bin / "osascript"
        interpreter.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["DWORK_TEST_LOG"], "a") as stream:
    stream.write(json.dumps(["apple-terminal", *sys.argv[1:], sys.stdin.read()]) + "\\n")
''')
        interpreter.chmod(0o755)
        (self.root / "dwork.yml").write_text('''version: 1
compose: {enabled: false}
terminals:
  - title: Frontend
    command: [echo, ready]
    window: new
''')

    def test_cli_confirmation_dry_run_and_script_transport_without_a_gui(self):
        for shell in self.fixture.shells:
            for args, answer, opens in (("--dry-run", "", False), ("", "n\n", False),
                                         ("", "y\n", True)):
                with self.subTest(shell=shell, args=args, answer=answer):
                    result, changes, calls = self.fixture.run_dwork(
                        shell, args, answer=answer, WSL_DISTRO_NAME="", SHELL="/bin/zsh")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(changes, [])
                    self.assertEqual(bool(calls), opens)
                    if opens:
                        self.assertEqual(calls[0][:2], ["apple-terminal", "-"])
                        self.assertEqual(calls[0][-1], dwork_terminals.APPLE_TERMINAL_SCRIPT)
                        self.assertEqual(calls[0][-2], "Frontend")


if __name__ == "__main__":
    unittest.main()
