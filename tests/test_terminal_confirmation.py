"""Session consent behavior for native and Windows adapters; fake launchers only."""

import base64
import json
import sys
import unittest
import test_dwork as legacy


class TerminalConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.native_launcher = "apple-terminal" if sys.platform == "darwin" else "gnome-terminal"
        for name, label in (
            ("gnome-terminal", "linux-terminal"),
            ("osascript", "apple-terminal"),
            ("powershell.exe", "powershell"),
        ):
            path = self.fixture.bin / name
            path.write_text(
                """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["DWORK_TEST_LOG"], "a") as f:
    f.write(json.dumps(["""
                + repr(label)
                + """, *sys.argv[1:]]) + "\\n")
"""
            )
            path.chmod(0o755)

    def write_config(self, launcher, confirms, directory=None):
        tasks = []
        for index, confirm in enumerate(confirms):
            task = {
                "title": "Session" + str(index + 1),
                "command": ["echo", "ready"],
                "launcher": launcher,
            }
            if confirm != "default":
                task["confirm"] = confirm
            tasks.append(task)
        folder = directory or self.root
        folder.mkdir(parents=True, exist_ok=True)
        # Isolate per-session consent from the separate activation prompt.
        (folder / "dwork.yml").write_text(
            json.dumps(
                {"version": 1, "confirm": False, "compose": {"enabled": False}, "terminals": tasks}
            )
        )

    def run_case(self, shell, launcher, answer="", args=""):
        result, changes, calls = self.fixture.run_dwork(
            shell,
            args=args,
            answer=answer,
            SHELL="/bin/bash",
            WSL_DISTRO_NAME="Ubuntu" if launcher == "windows-terminal" else "",
            DISPLAY=":test",
            WAYLAND_DISPLAY="",
        )
        launches = [
            call
            for call in calls
            if call[0] in ("linux-terminal", "apple-terminal")
            or (call[0] == "powershell" and "-EncodedCommand" in call)
        ]
        return result, launches, calls

    def cases(self):
        return [
            (shell, launcher)
            for shell in self.fixture.shells
            for launcher in ("windows-terminal", self.native_launcher)
        ]

    def test_default_decline_empty_and_eof_skip(self):
        for shell, launcher in self.cases():
            self.write_config(launcher, ["default"])
            for answer in ("", "\n", "n\n", "yes\n"):
                with self.subTest(shell=shell, launcher=launcher, answer=answer):
                    result, launches, _ = self.run_case(shell, launcher, answer)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(launches, [])
                    self.assertIn("Skipped terminal: Session1", result.stdout)
                    self.assertIn("? (y/N)", result.stdout)

    def test_each_session_gets_its_own_prompt(self):
        for shell, launcher in self.cases():
            with self.subTest(shell=shell, launcher=launcher):
                self.write_config(launcher, ["default", "default"])
                result, launches, _ = self.run_case(shell, launcher, "n\nY\n")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.count("? (y/N)"), 2)
                self.assertEqual(len(launches), 1)
                launch = launches[0]
                if launcher == "windows-terminal":
                    text = base64.b64decode(launch[-1]).decode("utf-16le")
                else:
                    text = " ".join(launch)
                self.assertIn("Session2", text)
                self.assertNotIn("Session1", text)

    def test_false_only_skips_confirmation_for_that_session(self):
        for shell, launcher in self.cases():
            with self.subTest(shell=shell, launcher=launcher):
                self.write_config(launcher, [False, True])
                result, launches, _ = self.run_case(shell, launcher)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(launches), 1)
                self.assertEqual(result.stdout.count("? (y/N)"), 1)
                self.assertIn("Opening terminal: Session1", result.stdout)
                self.assertIn("Skipped terminal: Session2", result.stdout)

    def test_explicit_false_allows_no_input_for_both_sessions(self):
        for shell, launcher in self.cases():
            with self.subTest(shell=shell, launcher=launcher):
                self.write_config(launcher, [False, False])
                result, launches, _ = self.run_case(shell, launcher)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(launches), 2)
                self.assertNotIn("? (y/N)", result.stdout)

    def test_dry_run_shows_policy_without_asking_or_launching(self):
        for shell, launcher in self.cases():
            with self.subTest(shell=shell, launcher=launcher):
                self.write_config(launcher, ["default", False])
                result, launches, calls = self.run_case(shell, launcher, args="--dry-run")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("[confirmation required]", result.stdout)
                self.assertIn("[confirm: false]", result.stdout)
                self.assertNotIn("? (y/N)", result.stdout)
                self.assertEqual(calls, [])

    def test_yaml_option_requires_boolean(self):
        for value in ("false", 0, None):
            self.write_config(self.native_launcher, [value])
            for shell in self.fixture.shells:
                with self.subTest(shell=shell, value=value):
                    result, launches, calls = self.run_case(shell, self.native_launcher)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("terminal.confirm must be true or false", result.stderr)
                    self.assertEqual(calls, [])

    def test_child_discovery_consent_does_not_approve_session(self):
        for shell in self.fixture.shells:
            child = self.root / "backend"
            self.write_config(self.native_launcher, ["default"], child)
            result, launches, _ = self.run_case(shell, self.native_launcher, "y\nn\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Switch all listed projects together? (y/N)", result.stdout)
            self.assertIn("Skipped terminal: Session1", result.stdout)
            self.assertEqual(launches, [])


if __name__ == "__main__":
    unittest.main()
