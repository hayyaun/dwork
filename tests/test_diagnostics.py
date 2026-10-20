"""Read-only diagnostics and partial-failure behavior using fake Docker."""
import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

import test_dwork as legacy
from test_dwork_config import runtime


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
            result, changes, calls = self.fixture.run_dwork(shell, "status", containers=[
                item, legacy.container("b", "main", "old"),
                legacy.container("c", "other", state="running")])
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
            "  - command: [echo, hello]\n    launcher: xterm\n")
        for shell in self.fixture.shells:
            result, _, calls = self.fixture.run_dwork(shell, "status")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls, [])
            self.assertIn("not tracked", result.stdout)
            result, changes, calls = self.fixture.run_dwork(shell, "doctor", SHELL="/no/shell")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(calls, [])
            self.assertEqual(changes, [])
            self.assertIn("Fix:", result.stderr)

    def test_normal_switch_previews_scope_and_respects_protection(self):
        result, changes, _ = self.fixture.run_dwork("bash", containers=[
            legacy.container("a", "main"), legacy.container("b", "other", state="running"),
            legacy.container("c", "infra", state="running")], DWORK_KEEP_PROJECTS="infra",
            managed_projects=("other", "infra"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "b"], ["start", "a"]])
        self.assertIn("Protected projects (DWORK_KEEP_PROJECTS): infra", result.stdout)
        self.assertLess(result.stdout.index("Would stop:"), result.stdout.index("Executing:"))

    def test_start_failure_reports_completed_pending_and_actual_state(self):
        result, changes, _ = self.fixture.run_dwork("bash", containers=[
            legacy.container("a", "main"), legacy.container("b", "other", state="running"),
            legacy.container("c", "infra", state="running")],
            DWORK_KEEP_PROJECTS="infra", DWORK_TEST_FAIL="start", managed_projects=("other", "infra"))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(changes, [["stop", "b"], ["start", "a"]])
        self.assertIn("Completed: stop b (other)", result.stderr)
        self.assertIn("Not confirmed complete: start a (main/web)", result.stderr)
        self.assertIn("Still running/restarting: infra/c", result.stderr)
        self.assertIn("docker start b", result.stderr)

    def test_interrupt_preserves_exit_code_and_reports_uncertain_action(self):
        workspace = runtime.Workspace("main", self.root, {"web": {}})
        item = legacy.container("a", "main")
        stderr = io.StringIO()
        with patch.object(runtime.sys, "argv", ["dwork"]), \
                patch.object(runtime, "discover", return_value=([workspace], False)), \
                patch.object(runtime, "inventory", return_value=[item]), \
                patch.object(runtime, "show_target"), \
                patch.object(runtime, "docker_target", return_value={"context": "default", "daemon": "test-daemon"}), \
                patch.object(runtime, "confirm_registration", return_value=True), \
                patch.object(runtime, "docker", side_effect=KeyboardInterrupt), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            self.assertEqual(runtime.cli(), 130)
        self.assertIn("Switch incomplete at: start a", stderr.getvalue())

    def test_context_override_is_disclosed_without_exposing_endpoint(self):
        result, changes, _ = self.fixture.run_dwork(
            "bash", "status", DOCKER_HOST="tcp://secret-host:2376", DOCKER_CONTEXT="")
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

    def test_health_failure_blocks_terminal_and_reports_service(self):
        item = legacy.container("a", "main", state="running")
        item["State"]["Health"] = {"Status": "unhealthy"}
        with patch.object(runtime.sys, "argv", ["dwork"]), \
                patch.object(runtime, "discover", return_value=([
                    runtime.Workspace("main", self.root, {"web": {}}, terminals=[
                        runtime.TerminalTask("App", ["echo", "hello"], self.root, ["web"])])], False)), \
                patch.object(runtime, "inventory", return_value=[item]), \
                patch.object(runtime, "show_target"), \
                patch.object(runtime, "docker_target", return_value={"context": "default", "daemon": "test-daemon"}), \
                patch.object(runtime, "confirm_registration", return_value=True), \
                patch.object(runtime, "preflight_terminals"), \
                patch.object(runtime, "docker", return_value=json.dumps([item])), \
                patch.object(runtime, "open_terminal") as launch, \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(runtime.cli(), 1)
        launch.assert_not_called()
        self.assertIn("wait for healthy a", errors.getvalue())
        self.assertIn("terminal App", errors.getvalue())
        self.assertIn("unhealthy", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
