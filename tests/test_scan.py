"""Recursive registration and the real checkbox picker; isolated state/fake Docker."""

from pathlib import Path
from unittest.mock import patch
import contextlib
import io
import json
import os
import select
import shutil
import subprocess
import sys
import time
import unittest

from test_colors import TTY
import test_dwork as legacy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import dwork_docker
import dwork_registry
import dwork_scan


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

    def test_recurses_through_container_directories_and_skips_symlinks(self):
        self.configured(self.root / "first")
        self.configured(self.root / "deep/a/b")
        self.configured(self.fixture.base / "outside")
        (self.root / "link").symlink_to(self.fixture.base / "outside", target_is_directory=True)
        result, changes, calls = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        self.assertEqual(calls, [])
        self.assertEqual({e["path"] for e in self.entries()}, {str(self.root / "first"), str(self.root / "deep/a/b")})

    def test_repo_markers_prune_descendants_but_continue_siblings(self):
        markers = ("package.json", "pyproject.toml", "Cargo.toml", "go.mod", "composer.json",
                   "Gemfile", "pom.xml", "build.gradle", "mix.exs", "pubspec.yaml", ".git")
        for index, marker in enumerate(markers):
            repo = self.root / str(index)
            self.configured(repo / "nested")
            (repo / marker).write_text("")
        self.configured(self.root / "sibling")
        real_scandir = os.scandir
        with patch.object(os, "scandir", side_effect=real_scandir) as scanned:
            configured, _, errors = dwork_scan.scan_directories(self.root)
        self.assertEqual(configured, [self.root / "sibling"])
        self.assertEqual(errors, [])
        self.assertFalse(any(Path(call.args[0]).name == "nested" for call in scanned.call_args_list))

    def test_root_boundary_is_checked_before_pruning(self):
        self.configured(self.root)
        self.configured(self.root / "nested")
        configured, _, errors = dwork_scan.scan_directories(self.root)
        self.assertEqual(configured, [self.root])
        self.assertEqual(errors, [])

    def test_git_directory_and_compose_boundaries_are_detected(self):
        self.configured(self.root / "git-repo/nested")
        (self.root / "git-repo/.git").mkdir()
        self.fixture.model(self.root / "compose-repo", "compose-repo")
        self.configured(self.root / "compose-repo/nested")
        configured, compose, errors = dwork_scan.scan_directories(self.root)
        self.assertEqual(configured, [])
        self.assertEqual(compose, [self.root / "compose-repo"])
        self.assertEqual(errors, [])

    def test_dependency_cache_and_build_directories_are_not_traversed(self):
        ignored = ("node_modules", "vendor", ".venv", "venv", "__pycache__",
                   ".next", "dist", "build", "target", ".cache")
        for name in ignored:
            self.configured(self.root / "project" / name / "hidden")
        expected = [self.root / "project" / name for name in ("src", "packages", "apps", "infra")]
        for directory in expected:
            self.configured(directory)
        real_scandir = os.scandir
        with patch.object(os, "scandir", side_effect=real_scandir) as scanned:
            configured, compose, errors = dwork_scan.scan_directories(self.root)
        self.assertEqual(set(configured), set(expected))
        self.assertEqual(compose, [])
        self.assertEqual(errors, [])
        visited = {Path(call.args[0]) for call in scanned.call_args_list}
        self.assertTrue(all(self.root / "project" / name not in visited for name in ignored))

    def test_explicit_scan_root_is_searched_even_if_its_name_is_ignored(self):
        root = self.root / "vendor"
        self.configured(root / "my-project")
        configured, _, errors = dwork_scan.scan_directories(root)
        self.assertEqual(configured, [root / "my-project"])
        self.assertEqual(errors, [])

    def test_progress_shows_last_directory_in_grey_and_leaves_a_clean_line(self):
        deepest = self.root / "one/two"
        deepest.mkdir(parents=True)
        with patch.dict(os.environ, {"TERM": "xterm", "NO_COLOR": ""}), \
                patch.object(shutil, "get_terminal_size", return_value=os.terminal_size((200, 24))), \
                contextlib.redirect_stdout(TTY()) as output:
            dwork_scan.scan_directories(self.root)
        text = output.getvalue()
        self.assertIn("\033[90mSearching: " + str(self.root), text)
        self.assertTrue(text.endswith("\033[90mone\033[0m\n\033[90m  two\033[0m\n"))

    def test_progress_clears_parent_rows_when_moving_to_a_sibling_branch(self):
        directories = [self.root, self.root / "bbb", self.root / "bbb/b2", self.root / "ccc"]
        walk = [(str(path), [], []) for path in directories]
        with patch.dict(os.environ, {"TERM": "xterm", "NO_COLOR": ""}), \
                patch.object(os, "walk", return_value=iter(walk)), \
                patch.object(time, "monotonic", side_effect=range(10)), \
                contextlib.redirect_stdout(TTY()) as output:
            dwork_scan.scan_directories(self.root)
        text = output.getvalue()
        self.assertIn("\033[90mbbb\033[0m\n\033[90m  b2\033[0m", text)
        self.assertEqual(text.rsplit("\033[J", 1)[1], "\033[90mccc\033[0m\n")

    def test_progress_is_omitted_for_redirected_output(self):
        (self.root / "child").mkdir()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            dwork_scan.scan_directories(self.root)
        self.assertEqual(output.getvalue(), "")

    def test_interrupted_scan_finishes_its_progress_line(self):
        def interrupted(*args, **kwargs):
            yield str(self.root), [], []
            raise KeyboardInterrupt
        with patch.dict(os.environ, {"TERM": "xterm"}), \
                patch.object(os, "walk", side_effect=interrupted), \
                contextlib.redirect_stdout(TTY()) as output:
            with self.assertRaises(KeyboardInterrupt):
                dwork_scan.scan_directories(self.root)
        self.assertTrue(output.getvalue().endswith("\n"))

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

    def test_only_selected_compose_directory_is_registered_and_switches(self):
        self.configured(self.root / "configured")
        child, skipped = self.root / "child", self.root / "skip"
        self.fixture.model(child, "child")
        self.fixture.model(skipped, "skip")
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(self.fixture.base / "state")}), \
                patch.object(dwork_docker, "docker_target", return_value={"context": "default", "daemon": "test-daemon"}), \
                patch.object(dwork_docker, "read_model", return_value=("child", {"web": {}})), \
                patch.object(dwork_scan, "choose_compose_directories", return_value=[child]) as picker, \
                patch("builtins.input", return_value="y"), contextlib.redirect_stdout(io.StringIO()):
            with dwork_registry.registry_lock():
                self.assertEqual(dwork_scan.scan_workspaces(self.root, [], False), 0)
        self.assertEqual(picker.call_args.args[0], [child, skipped])
        self.assertEqual({e["path"] for e in self.entries()}, {str(self.root / "configured"), str(child)})
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
                  "import dwork_scan; result=dwork_scan.choose_compose_directories([Path('first'),Path('second')],Path('.')); "
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
