"""Config and health-gated terminal tests; no real Docker or terminals."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import test_dwork as legacy

SPEC = importlib.util.spec_from_file_location("dwork_runtime", legacy.SOURCE.parent / "lib/dwork.py")
runtime = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime
SPEC.loader.exec_module(runtime)

class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.shells = self.fixture.shells

    def config(self, text, directory=None):
        directory = directory or self.root
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "dwork.yml").write_text(text)

    def test_disabled_compose_never_reads_docker(self):
        self.fixture.model(self.root, "invalid", fail=True)
        self.config("version: 1\ncompose:\n  enabled: false\n")
        for shell in self.shells:
            result, changes, calls = self.fixture.run_dwork(shell)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls, [])

    def test_explicit_service_selection(self):
        self.fixture.model(self.root, "main", services={"db": {}, "app": {}})
        self.config("version: 1\ncompose:\n  services: [db]\n")
        items = [legacy.container("a", "main", "db"),
                 legacy.container("b", "main", "app")]
        for shell in self.shells:
            result, changes, _ = self.fixture.run_dwork(shell, containers=items)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(changes, [["start", "a"]])
            self.assertNotIn("main/app", result.stderr)

    def test_config_owns_compose_file_choice(self):
        file = self.root / "custom.yaml"
        file.write_text(json.dumps({"name": "custom", "services": {}}))
        self.config("version: 1\ncompose:\n  files: [custom.yaml]\n")
        for shell in self.shells:
            result, _, _ = self.fixture.run_dwork(shell, "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Current Compose project: custom", result.stdout)

    def test_dry_run_shows_terminal_without_launching(self):
        self.config("""version: 1
compose:
  enabled: false
terminals:
  - title: Example
    command: [echo, "hello world"]
""")
        for shell in self.shells:
            result, changes, calls = self.fixture.run_dwork(shell, "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Would open terminal: Example", result.stdout)
            self.assertEqual(calls, [])

    def test_invalid_configs_fail_before_any_docker_call(self):
        variants = [
            "version: 2\n",
            "version: 1\nversion: 1\n",
            "version: 1\nunknown: true\n",
            "version: 1\ncompose: {enabled: maybe}\n",
            "version: 1\ncompose: {enabled: false}\nterminals: [{command: echo hi}]\n",
            "version: 1\ncompose: {enabled: false}\nterminals: [{command: [echo], launcher: invalid}]\n",
            "version: 1\ncompose: {enabled: false}\nterminals: [{command: [echo], unknown: 1}]\n",
            "version: 1\ncompose: {enabled: false}\nterminals: [{command: [echo], wait_for: {healthy: [db]}}]\n",
        ]
        for config in variants:
            self.config(config)
            for shell in self.shells:
                with self.subTest(config=config, shell=shell):
                    result, changes, calls = self.fixture.run_dwork(shell)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(changes, [])
                    self.assertEqual(calls, [])

    def health_config(self):
        self.fixture.model(self.root, "main", services={"db": {"healthcheck": {"test": ["CMD", "true"]}}})
        self.config("""version: 1
compose:
  services: [db]
terminals:
  - title: Backend
    command: [echo, run]
    wait_for:
      healthy: [db]
      timeout: 0.02
""")
        executable = self.fixture.bin / "powershell.exe"
        executable.write_text("""#!/usr/bin/env python3
import json, os, sys
with open(os.environ["DWORK_TEST_LOG"], "a") as f:
    f.write(json.dumps(["powershell", *sys.argv[1:]]) + "\\n")
""")
        executable.chmod(0o755)

    def test_healthy_container_starts_before_terminal_launch(self):
        self.health_config()
        item = legacy.container("a", "main", "db")
        item["State"]["Health"] = {"Status": "healthy"}
        for shell in self.shells:
            result, changes, calls = self.fixture.run_dwork(
                shell, answer="y\n", containers=[item], WSL_DISTRO_NAME="Ubuntu", SHELL="/bin/bash")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(changes, [["start", "a"]])
            launch = next(i for i, call in enumerate(calls) if "-EncodedCommand" in call)
            start = calls.index(["start", "a"])
            self.assertGreater(launch, start)
            self.assertTrue(any(call[0] == "inspect" for call in calls[start+1:launch]))

    def test_failed_health_never_opens_terminal(self):
        self.health_config()
        for status in ("unhealthy", "starting", None):
            item = legacy.container("a", "main", "db", state="running")
            if status:
                item["State"]["Health"] = {"Status": status}
            for shell in self.shells:
                with self.subTest(status=status, shell=shell):
                    result, _, calls = self.fixture.run_dwork(
                        shell, answer="y\n", containers=[item], WSL_DISTRO_NAME="Ubuntu", SHELL="/bin/bash")
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertFalse(any("-EncodedCommand" in call for call in calls))

    def test_missing_required_container_aborts_before_stopping_others(self):
        self.health_config()
        for shell in self.shells:
            result, changes, calls = self.fixture.run_dwork(
                shell, containers=[legacy.container("b", "other", state="running")])
            self.assertEqual(result.returncode, 1)
            self.assertIn("Create it manually", result.stderr)
            self.assertEqual(changes, [])
            self.assertFalse(any(call[0] == "powershell" for call in calls))

    def test_child_config_discovery_requires_confirmation(self):
        self.config("version: 1\ncompose: {enabled: false}\n", self.root / "child")
        for shell in self.shells:
            result, changes, calls = self.fixture.run_dwork(shell, answer="\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("child -> child", result.stdout)
            self.assertIn("Cancelled", result.stdout)
            self.assertEqual(changes, [])

    def test_parent_config_found_from_subdirectory(self):
        self.config("version: 1\ncompose: {enabled: false}\n")
        child = self.root / "nested"
        child.mkdir()
        for shell in self.shells:
            result, _, calls = self.fixture.run_dwork(shell, cwd=child)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls, [])

    def test_later_failed_health_gate_blocks_all_terminals(self):
        self.health_config()
        self.fixture.model(self.root, "main", services={"db": {}, "cache": {}})
        self.config("""version: 1
compose:
  services: [db, cache]
terminals:
  - command: [echo, first]
    wait_for: {healthy: [db]}
  - command: [echo, second]
    wait_for: {healthy: [cache]}
""")
        db = legacy.container("a", "main", "db", state="running")
        db["State"]["Health"] = {"Status": "healthy"}
        cache = legacy.container("b", "main", "cache", state="running")
        cache["State"]["Health"] = {"Status": "unhealthy"}
        for shell in self.shells:
            result, changes, calls = self.fixture.run_dwork(
                shell, containers=[db, cache], WSL_DISTRO_NAME="Ubuntu", SHELL="/bin/bash")
            self.assertEqual(result.returncode, 1)
            self.assertFalse(any("-EncodedCommand" in call for call in calls))

    def test_unavailable_terminal_platform_aborts_before_switch(self):
        self.health_config()
        db = legacy.container("a", "main", "db", state="running")
        db["State"]["Health"] = {"Status": "healthy"}
        for shell in self.shells:
            result, changes, calls = self.fixture.run_dwork(
                shell, containers=[db, legacy.container("b", "other", state="running")],
                WSL_DISTRO_NAME="", SHELL="/bin/bash", DWORK_TERMINAL="gnome-terminal",
                DISPLAY="", WAYLAND_DISPLAY="")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(changes, [])
            self.assertFalse(any("-EncodedCommand" in call for call in calls))

    def test_terminal_argument_quoting_and_encoded_transport(self):
        task = runtime.TerminalTask("Title ' & space", ["echo", "hello world", 'a"$b&c'],
                                    Path("/home/user/repo with spaces"))
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu", "SHELL": "/bin/bash"}):
            args = runtime.terminal_arguments(task)
            self.assertEqual(args[-1], "exec echo 'hello world' 'a\"$b&c'")
            self.assertIn(str(task.cwd), args)
            with patch.object(runtime, "run_command") as command:
                runtime.open_terminal(task)
                call = command.call_args.args[0]
                self.assertIn("-EncodedCommand", call)
                decoded = base64.b64decode(call[-1]).decode("utf-16le")
                self.assertEqual(decoded, runtime.powershell_script(task))
                self.assertIn("Title '' & space", decoded)

    def test_all_health_gates_pass_before_any_launch(self):
        self.health_config()
        # Direct health tests use official inspect JSON fields and a bounded clock.
        with patch.object(runtime, "docker", return_value=json.dumps([
            {"Id": "a", "State": {"Status": "running", "Health": {"Status": "healthy"}}}
        ])):
            runtime.wait_healthy(["a"], 1)
        with patch.object(runtime, "docker", return_value="[]"):
            with self.assertRaises(runtime.DworkError):
                runtime.wait_healthy(["a"], 1)

if __name__ == "__main__":
    unittest.main()
