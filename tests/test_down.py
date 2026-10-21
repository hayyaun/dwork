"""Batch shutdown stays inside registered ownership; never contacts real Docker."""

from pathlib import Path
from unittest.mock import patch
import contextlib
import io
import sys
import unittest

import test_dwork as legacy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import dwork_cli
import dwork_docker
import dwork_registry


class DownTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.state = self.fixture.base / "state/dwork/workspaces.json"

    def run_cli(self, args, **kwargs):
        kwargs.setdefault("answer", "y\n")
        return self.fixture.run_dwork("bash", args, register_current=False, **kwargs)

    def test_confirmation_decline_eof_and_preview_preserve_registry(self):
        self.register("api")
        before = self.state.read_bytes()
        for args, answer in (("down", "n\n"), ("down", "\n"), ("down", ""), ("down --dry-run", "")):
            with self.subTest(args=args, answer=answer):
                result, changes, _ = self.run_cli(
                    args, answer=answer, containers=[legacy.container("a", "api", state="running")]
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(changes, [])
                self.assertEqual(self.state.read_bytes(), before)
                if args == "down":
                    self.assertLess(
                        result.stdout.index("Would stop:"), result.stdout.index("Stop all listed")
                    )
                    self.assertIn("Cancelled", result.stdout)
                else:
                    self.assertNotIn("(y/N)", result.stdout)

    def register(self, name, services=None, **kwargs):
        directory = self.root / name
        self.fixture.model(directory, name, services={"web": {}, "db": {}})
        if services is not None:
            (directory / "dwork.yml").write_text(
                "version: 1\ncompose: {services: " + str(services) + "}\n"
            )
        result, changes, _ = self.run_cli("register", cwd=directory, **kwargs)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        return directory

    def test_stops_all_registered_workspaces_in_one_batch_from_anywhere(self):
        self.register("api")
        self.register("ui")
        self.register("infra")
        before = self.state.read_bytes()
        unlabelled = legacy.container("unlabelled", "")
        unlabelled["Config"]["Labels"] = {}
        result, changes, calls = self.run_cli(
            "down",
            cwd=self.fixture.base,
            containers=[
                legacy.container("a", "api", state="running"),
                legacy.container("b", "ui", state="restarting"),
                legacy.container("c", "infra", state="running"),
                legacy.container("d", "unknown", state="running"),
                unlabelled,
                legacy.container("e", "api", state="exited"),
            ],
            DWORK_KEEP_PROJECTS="infra",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "a", "b"]])
        self.assertIn("Stopped: api/web / a", result.stdout)
        self.assertIn("Stopped: ui/web / b", result.stdout)
        self.assertEqual(self.state.read_bytes(), before)
        self.assertFalse(any(c[0] == "compose" for c in calls))

    def test_respects_service_selection_and_stops_paused_workloads(self):
        self.register("api", services=["db"])
        result, changes, _ = self.run_cli(
            "down",
            containers=[
                legacy.container("a", "api", "db", "paused"),
                legacy.container("b", "api", "web", "running"),
            ],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "a"]])

    def test_preview_is_read_only_and_preserves_registry(self):
        self.register("api")
        before = self.state.read_bytes()
        result, changes, _ = self.run_cli(
            "down --dry-run", containers=[legacy.container("a", "api", state="running")]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Would stop: a", result.stdout)
        self.assertNotIn("Stopped:", result.stdout)
        self.assertEqual(changes, [])
        self.assertEqual(self.state.read_bytes(), before)

    def test_empty_registry_needs_no_docker_or_preview_state(self):
        result, changes, calls = self.run_cli("down --dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])
        self.assertEqual(changes, [])
        self.assertFalse(self.state.parent.exists())

    def test_host_only_registry_needs_no_docker(self):
        (self.root / "dwork.yml").write_text("version: 1\ncompose: {enabled: false}\n")
        result, _, _ = self.run_cli("register host")
        self.assertEqual(result.returncode, 0, result.stderr)
        result, changes, calls = self.run_cli("down")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])
        self.assertEqual(changes, [])

    def test_other_targets_are_left_alone(self):
        self.register("remote", DWORK_TEST_CONTEXT="remote")
        self.register("daemon", DWORK_TEST_DAEMON="other-daemon")
        result, changes, _ = self.run_cli(
            "down",
            containers=[
                legacy.container("a", "remote", state="running"),
                legacy.container("b", "daemon", state="running"),
            ],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])

    def test_missing_directory_does_not_prevent_explicit_shutdown(self):
        directory = self.register("api")
        directory.rename(self.root / "moved")
        result, changes, _ = self.run_cli(
            "down", containers=[legacy.container("a", "api", state="running")]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "a"]])

    def test_batch_failure_reports_actual_partial_state(self):
        self.register("api")
        result, changes, _ = self.run_cli(
            "down",
            containers=[
                legacy.container("a", "api", state="running"),
                legacy.container("b", "api", "db", "running"),
            ],
            DWORK_TEST_FAIL="stop",
            DWORK_TEST_STOPPED='["a"]',
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(changes, [["stop", "a", "b"]])
        self.assertIn("Down incomplete", result.stderr)
        self.assertIn("api/web / a: exited", result.stderr)
        self.assertIn("api/db / b: running", result.stderr)

    def test_noop_and_invalid_options(self):
        self.register("api")
        result, changes, _ = self.run_cli("down", containers=[legacy.container("a", "api")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        for args in ("down all", "down --all", "down -f compose.yaml"):
            result, changes, calls = self.run_cli(args)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Usage: dwork down", result.stderr)
            self.assertEqual(changes, [])
            self.assertEqual(calls, [])

    def test_interrupt_keeps_exit_code_and_reports_incomplete_batch(self):
        target = {"context": "default", "daemon": "test"}
        entries = [
            {
                "target": target,
                "path": str(self.root),
                "members": [
                    {
                        "enabled": True,
                        "project": "api",
                        "directory": str(self.root),
                        "services": None,
                    }
                ],
            }
        ]
        with (
            patch.object(dwork_registry, "read_registry", return_value=entries),
            patch.object(dwork_registry, "registry_lock", return_value=contextlib.nullcontext()),
            patch.object(dwork_docker, "docker_target", return_value=target),
            patch.object(dwork_docker, "show_target"),
            patch.object(
                dwork_docker,
                "inventory",
                return_value=[legacy.container("a", "api", state="running")],
            ),
            patch.object(dwork_docker, "docker", side_effect=KeyboardInterrupt),
            patch("builtins.input", return_value="y"),
            patch.object(sys, "argv", ["dwork", "down"]),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()) as errors,
        ):
            self.assertEqual(dwork_cli.cli(), 130)
        self.assertIn("Down incomplete", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
