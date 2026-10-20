"""Recursive registration and the real checkbox picker; isolated state/fake Docker."""
import contextlib
import io
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import test_dwork as legacy
from test_dwork_config import runtime


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.state = self.fixture.base / "state/dwork/workspaces.json"

    def run_cli(self, args="scan", **kwargs):
        return self.fixture.run_dwork("bash", args, register_current=False, **kwargs)

    def configured(self, directory, enabled=False, name=None):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "dwork.yml").write_text(json.dumps({"version": 1, "compose": {"enabled": enabled}}))
        if enabled:
            self.fixture.model(directory, name or directory.name)

    def entries(self):
        return json.loads(self.state.read_text())["workspaces"]

    def test_recurses_including_root_and_skips_git_and_symlinks(self):
        self.configured(self.root)
        self.configured(self.root / "deep/a/b")
        self.configured(self.root / ".git/hidden")
        self.configured(self.fixture.base / "outside")
        (self.root / "link").symlink_to(self.fixture.base / "outside", target_is_directory=True)
        result, changes, calls = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        self.assertEqual(calls, [])
        self.assertEqual({e["path"] for e in self.entries()}, {str(self.root), str(self.root / "deep/a/b")})

    def test_optional_compose_prompt_defaults_to_no(self):
        self.configured(self.root / "configured")
        self.fixture.model(self.root / "compose-only", "other")
        for answer in ("", "n\n", "\n"):
            self.state.unlink(missing_ok=True)
            result, changes, _ = self.run_cli(answer=answer)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Also review 1 Compose-only", result.stdout)
            self.assertEqual(len(self.entries()), 1)
            self.assertEqual(changes, [])

    def test_preview_never_registers_or_prompts(self):
        self.configured(self.root / "configured")
        self.fixture.model(self.root / "compose-only", "other")
        result, changes, _ = self.run_cli("scan --dry-run", answer="y\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Would register:", result.stdout)
        self.assertIn("Compose candidate (not selected):", result.stdout)
        self.assertNotIn("(y/N)", result.stdout)
        self.assertEqual(changes, [])
        self.assertFalse(self.state.parent.exists())

    def test_existing_custom_registration_is_preserved(self):
        self.configured(self.root / "app")
        result, _, _ = self.run_cli("register custom", cwd=self.root / "app")
        self.assertEqual(result.returncode, 0, result.stderr)
        before = self.state.read_bytes()
        result, changes, _ = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Already registered: custom", result.stdout)
        self.assertEqual(self.state.read_bytes(), before)
        self.assertEqual(changes, [])

    def test_bad_config_and_project_collision_are_reported_without_losing_valid_entries(self):
        self.configured(self.root / "a", True, "shared")
        self.configured(self.root / "b", True, "shared")
        self.configured(self.root / "c")
        (self.root / "c/dwork.yml").write_text("version: 99\n")
        result, changes, _ = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Compose project already registered", result.stderr)
        self.assertIn("version must be 1", result.stderr)
        self.assertEqual(len(self.entries()), 1)
        self.assertEqual(changes, [])

    def test_duplicate_host_names_get_stable_suffixes(self):
        self.configured(self.root / "one/app")
        self.configured(self.root / "two/app")
        result, _, _ = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([e["name"] for e in self.entries()], ["app", "app-2"])

    def test_scan_does_not_apply_callers_compose_environment_to_each_project(self):
        self.configured(self.root / "app", True)
        result, changes, _ = self.run_cli(COMPOSE_FILE="missing.yaml", COMPOSE_PROJECT_NAME="wrong")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.entries()[0]["environment"], {})
        self.assertEqual(self.entries()[0]["members"][0]["project"], "app")
        self.assertEqual(changes, [])

    def test_only_selected_compose_directory_is_registered_and_switches_below_parent_config(self):
        self.configured(self.root)
        child, skipped = self.root / "child", self.root / "skip"
        self.fixture.model(child, "child")
        self.fixture.model(skipped, "skip")
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(self.fixture.base / "state")}), \
                patch.object(runtime, "docker_target", return_value={"context": "default", "daemon": "test-daemon"}), \
                patch.object(runtime, "read_model", return_value=("child", {"web": {}})), \
                patch.object(runtime, "choose_compose_directories", return_value=[child]) as picker, \
                patch("builtins.input", return_value="y"), contextlib.redirect_stdout(io.StringIO()):
            with runtime.registry_lock():
                self.assertEqual(runtime.scan_workspaces(self.root, [], False), 0)
        self.assertEqual(picker.call_args.args[0], [child, skipped])
        self.assertEqual({e["path"] for e in self.entries()}, {str(self.root), str(child)})
        for args in ("switch child", ""):
            result, changes, _ = self.run_cli(args, cwd=child, containers=[legacy.container("a", "child")])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(changes, [["start", "a"]])

    def test_piped_yes_does_not_bypass_checkbox_and_keeps_first_phase(self):
        self.configured(self.root / "configured")
        self.fixture.model(self.root / "compose-only", "other")
        result, changes, _ = self.run_cli(answer="y\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires an interactive terminal", result.stderr)
        self.assertEqual(len(self.entries()), 1)
        self.assertEqual(changes, [])

    def test_checkbox_real_pty_arrows_space_enter_and_cancel_restore_terminal(self):
        import fcntl
        import pty
        import struct
        import termios
        lib = legacy.SOURCE.parent / "lib"
        script = ("import sys,json; from pathlib import Path; sys.path.insert(0," + repr(str(lib)) + "); "
                  "import dwork; result=dwork.choose_compose_directories([Path('first'),Path('second')],Path('.')); "
                  "print('PICKER_RESULT:'+json.dumps([str(p) for p in result]))")
        for keys, expected in ((b" \x1bOB \x1bOA \n", '["second"]'), (b"q", "[]")):
            master, slave = pty.openpty()
            try:
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 90, 0, 0))
                original = termios.tcgetattr(slave)
                env = dict(os.environ, TERM="xterm")
                process = subprocess.Popen([sys.executable, "-B", "-c", script], cwd=self.root,
                                           stdin=slave, stdout=slave, stderr=slave, env=env)
                try:
                    output, sent = b"", False
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        if select.select([master], [], [], 0.1)[0]:
                            output += os.read(master, 65536)
                        if not sent and b"Select Compose workspaces" in output:
                            os.write(master, keys)
                            sent = True
                        if process.poll() is not None:
                            while select.select([master], [], [], 0)[0]:
                                output += os.read(master, 65536)
                            break
                    self.assertEqual(process.poll(), 0, output.decode(errors="replace"))
                    self.assertIn("PICKER_RESULT:" + expected, output.decode(errors="replace"))
                    self.assertEqual(termios.tcgetattr(slave), original)
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait()
            finally:
                os.close(master)
                os.close(slave)


if __name__ == "__main__":
    unittest.main()
