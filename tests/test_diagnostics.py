"""Read-only diagnostics and partial-failure behavior using fake Docker."""

from pathlib import Path
from unittest.mock import patch
import contextlib
import io
import json
import os
import sys
import time
import unittest

import test_dwork as legacy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import dwork_cli
import dwork_common
import dwork_config
import dwork_docker
import dwork_registry
import dwork_terminals
from dwork_launch import TerminalLaunch


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.fixture.model(self.root, "main")
        environment = patch.dict(os.environ, {"XDG_STATE_HOME": str(self.fixture.base / "state")})
        environment.start()
        self.addCleanup(environment.stop)

    def test_status_is_read_only_and_reports_health_missing_and_unmanaged(self):
        (self.root / "dwork.yml").write_text("version: 1\ncompose:\n  services: [web, db]\n")
        self.fixture.model(self.root, "main", services={"web": {}, "db": {}})
        item = legacy.container("a", "main", state="running")
        item["State"]["Health"] = {"Status": "unhealthy"}
        for shell in self.fixture.shells:
            result, changes, calls = self.fixture.run_dwork(
                shell,
                "status",
                containers=[
                    item,
                    legacy.container("b", "main", "old"),
                    legacy.container("c", "other", state="running"),
                ],
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(changes, [])
            self.assertIn("Docker context: default", result.stdout)
            self.assertIn("running, unhealthy (managed)", result.stdout)
            self.assertIn("db: missing container", result.stdout)
            self.assertIn("(unmanaged)", result.stdout)
            self.assertNotIn("(y/N)", result.stdout)
            self.assertTrue(all(c[0] in ("compose", "context", "ps", "inspect") for c in calls))

    def test_doctor_checks_daemon_and_reports_fix_without_mutation(self):
        for shell in self.fixture.shells:
            result, changes, _ = self.fixture.run_dwork(shell, "doctor", DWORK_TEST_FAIL="ps")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(changes, [])
            self.assertIn("Docker access", result.stderr)
            self.assertIn("docker info", result.stderr)

    def test_doctor_success_and_compose_options(self):
        for shell in self.fixture.shells:
            result, changes, calls = self.fixture.run_dwork(shell, "doctor -f compose.yaml")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(changes, [])
            self.assertIn("all checks passed", result.stdout)
            self.assertIn("-f", calls[0])

    def test_host_only_diagnostics_never_use_docker_or_open_terminals(self):
        (self.root / "dwork.yml").write_text(
            "version: 1\ncompose: {enabled: false}\nterminals:\n"
            "  - command: [echo, hello]\n    launcher: xterm\n"
        )
        for shell in self.fixture.shells:
            result, _, calls = self.fixture.run_dwork(shell, "status")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls, [])
            self.assertIn("preview tracked commands with dwork down --dry-run", result.stdout)
            result, changes, calls = self.fixture.run_dwork(shell, "doctor", SHELL="/no/shell")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(calls, [])
            self.assertEqual(changes, [])
            self.assertIn("Fix:", result.stderr)

    def test_normal_switch_previews_scope_and_respects_protection(self):
        result, changes, _ = self.fixture.run_dwork(
            "bash",
            containers=[
                legacy.container("a", "main"),
                legacy.container("b", "other", state="running"),
                legacy.container("c", "infra", state="running"),
            ],
            DWORK_KEEP_PROJECTS="infra",
            managed_projects=("other", "infra"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "b"], ["start", "a"]])
        self.assertIn("Protected projects (DWORK_KEEP_PROJECTS): infra", result.stdout)
        self.assertLess(result.stdout.index("Would stop:"), result.stdout.index("Executing:"))

    def test_start_failure_reports_completed_pending_and_actual_state(self):
        result, changes, _ = self.fixture.run_dwork(
            "bash",
            containers=[
                legacy.container("a", "main"),
                legacy.container("b", "other", state="running"),
                legacy.container("c", "infra", state="running"),
            ],
            DWORK_KEEP_PROJECTS="infra",
            DWORK_TEST_FAIL="start",
            managed_projects=("other", "infra"),
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(changes, [["stop", "b"], ["start", "a"]])
        self.assertIn("Completed: stop b (other)", result.stderr)
        self.assertIn("Not confirmed complete: start a (main/web)", result.stderr)
        self.assertIn("Still running/restarting: infra/c", result.stderr)
        self.assertIn("docker start b", result.stderr)

    def test_interrupt_preserves_exit_code_and_reports_uncertain_action(self):
        workspace = dwork_common.Workspace("main", self.root, {"web": {}})
        item = legacy.container("a", "main")
        stderr = io.StringIO()
        with (
            patch.object(sys, "argv", ["dwork"]),
            patch.object(dwork_config, "discover", return_value=([workspace], False)),
            patch.object(dwork_docker, "inventory", return_value=[item]),
            patch.object(dwork_docker, "show_target"),
            patch.object(
                dwork_docker,
                "docker_target",
                return_value={"context": "default", "daemon": "test-daemon"},
            ),
            patch.object(dwork_registry, "confirm_registration", return_value=True),
            patch.object(dwork_docker, "docker", side_effect=KeyboardInterrupt),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(dwork_cli.cli(), 130)
        self.assertIn("Switch incomplete at: start a", stderr.getvalue())

    def test_context_override_is_disclosed_without_exposing_endpoint(self):
        result, changes, _ = self.fixture.run_dwork(
            "bash", "status", DOCKER_HOST="tcp://secret-host:2376", DOCKER_CONTEXT=""
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        self.assertIn("DOCKER_HOST is set", result.stdout)
        self.assertNotIn("secret-host", result.stdout)

    def test_doctor_invalid_config_has_fix_and_never_mutates(self):
        (self.root / "dwork.yml").write_text("version: 999\n")
        result, changes, calls = self.fixture.run_dwork("bash", "doctor")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(changes, [])
        self.assertEqual(calls, [])
        self.assertIn("Fix:", result.stderr)

    def test_health_deadline_terminates_a_stalled_fake_docker(self):
        executable = self.fixture.bin / "docker"
        executable.write_text("#!" + sys.executable + "\nimport time; time.sleep(10)\n")
        started = time.monotonic()
        with self.assertRaisesRegex(
            dwork_common.DworkError, "Timed out running command: docker inspect"
        ):
            dwork_docker.wait_healthy(["a"], 0.2)
        self.assertLess(time.monotonic() - started, 3)

    def test_health_inspections_share_one_deadline(self):
        item = legacy.container("a", "main", state="running")
        item["State"]["Health"] = {"Status": "starting"}
        with (
            patch.object(dwork_docker.time, "monotonic", side_effect=[0, 0.1, 0.3, 0.6, 1]),
            patch.object(dwork_docker.time, "sleep"),
            patch.object(dwork_docker, "docker", return_value=json.dumps([item])) as docker,
        ):
            with self.assertRaisesRegex(dwork_common.DworkError, "Timed out waiting for healthy"):
                dwork_docker.wait_healthy(["a"], 1)
        self.assertEqual([call.kwargs["timeout"] for call in docker.call_args_list], [0.9, 0.4])

    def test_health_failure_blocks_terminal_and_reports_service(self):
        item = legacy.container("a", "main", state="running")
        item["State"]["Health"] = {"Status": "unhealthy"}
        with (
            patch.object(sys, "argv", ["dwork"]),
            patch.object(
                dwork_config,
                "discover",
                return_value=(
                    [
                        dwork_common.Workspace(
                            "main",
                            self.root,
                            {"web": {}},
                            terminals=[
                                dwork_common.TerminalTask(
                                    "App", ["echo", "hello"], self.root, ["web"]
                                )
                            ],
                        )
                    ],
                    False,
                ),
            ),
            patch.object(dwork_docker, "inventory", return_value=[item]),
            patch.object(dwork_docker, "show_target"),
            patch.object(
                dwork_docker,
                "docker_target",
                return_value={"context": "default", "daemon": "test-daemon"},
            ),
            patch.object(dwork_registry, "confirm_registration", return_value=True),
            patch.object(
                dwork_terminals,
                "preflight_terminals",
                side_effect=lambda tasks: tuple(
                    TerminalLaunch(("fake-terminal",), task.cwd, "gnome-terminal", task.title)
                    for task in tasks
                ),
            ),
            patch.object(dwork_docker, "docker", return_value=json.dumps([item])),
            patch.object(dwork_terminals, "open_terminal") as launch,
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()) as errors,
        ):
            self.assertEqual(dwork_cli.cli(), 1)
        launch.assert_not_called()
        self.assertIn("wait for healthy a", errors.getvalue())
        self.assertIn("terminal App", errors.getvalue())
        self.assertIn("unhealthy", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
