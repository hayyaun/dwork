"""Workspace ownership and CLI integration; fake Docker and isolated user state."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import test_dwork as legacy
from test_dwork_config import runtime


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.state = self.fixture.base / "state/dwork/workspaces.json"
        self.fixture.model(self.root, "main")

    def run_cli(self, args="", **kwargs):
        return self.fixture.run_dwork("bash", args, register_current=False, **kwargs)

    def entries(self):
        return json.loads(self.state.read_text())["workspaces"]

    def register(self, directory=None, name="", **kwargs):
        result, changes, _ = self.run_cli("register " + name, cwd=directory, **kwargs)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])

    def test_first_run_consent_and_rerun(self):
        for shell in self.fixture.shells:
            with self.subTest(shell=shell):
                self.state.unlink(missing_ok=True)
                result, changes, _ = self.fixture.run_dwork(
                    shell, answer="y\n", register_current=False,
                    containers=[legacy.container("a", "main"),
                                legacy.container("b", "unregistered", state="running")])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Register and switch?", result.stdout)
                self.assertEqual(changes, [["start", "a"]])
                self.assertEqual(self.entries()[0]["path"], str(self.root))
                result, _, _ = self.fixture.run_dwork(shell, register_current=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("Register and switch?", result.stdout)

    def test_decline_eof_and_dry_run_do_not_register_or_mutate(self):
        for args, answer in (("", ""), ("", "n\n"), ("--dry-run", "y\n")):
            result, changes, _ = self.run_cli(args, answer=answer,
                                             containers=[legacy.container("a", "main")])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(changes, [])
            self.assertFalse(self.state.exists())
        # A preview must not even create the state directory or lock file.
        preview_state = self.fixture.base / "preview-state"
        self.run_cli("--dry-run", XDG_STATE_HOME=str(preview_state))
        self.assertFalse(preview_state.exists())

    def test_register_list_switch_and_forget_from_elsewhere(self):
        self.register(name="my-app")
        result, _, _ = self.run_cli("list", cwd=self.fixture.base)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("my-app  " + str(self.root), result.stdout)
        result, changes, _ = self.run_cli("switch my-app", cwd=self.fixture.base,
                                         containers=[legacy.container("a", "main")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["start", "a"]])
        before = self.state.read_bytes()
        result, changes, _ = self.run_cli("switch my-app --dry-run", cwd=self.fixture.base,
                                         containers=[legacy.container("a", "main")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        self.assertEqual(self.state.read_bytes(), before)
        result, changes, calls = self.run_cli("forget my-app", cwd=self.fixture.base)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        self.assertEqual(calls, [])
        self.assertEqual(self.entries(), [])
        self.assertTrue((self.root / "compose.yaml").exists())

    def test_only_registered_services_stop_and_keep_projects_still_wins(self):
        other = self.fixture.base / "other"
        self.fixture.model(other, "other", services={"db": {}, "app": {}})
        (other / "dwork.yml").write_text("version: 1\ncompose: {services: [db]}\n")
        self.register(other)
        self.register()
        items = [legacy.container("a", "main"),
                 legacy.container("b", "other", "db", "running"),
                 legacy.container("c", "other", "app", "running"),
                 legacy.container("d", "unknown", state="running")]
        result, changes, _ = self.run_cli(containers=items)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "b"], ["start", "a"]])
        result, changes, _ = self.run_cli(containers=items, DWORK_KEEP_PROJECTS="other")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["start", "a"]])
        self.run_cli("forget other")
        result, changes, _ = self.run_cli(containers=items)
        self.assertEqual(changes, [["start", "a"]])

    def test_context_and_daemon_scope_and_target_changes(self):
        other = self.fixture.base / "other"
        self.fixture.model(other, "other")
        self.register(other, DWORK_TEST_CONTEXT="remote")
        self.register()
        result, changes, _ = self.run_cli(containers=[legacy.container("b", "other", state="running")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        for override in ({"DWORK_TEST_CONTEXT": "remote"}, {"DWORK_TEST_DAEMON": "new-daemon"}):
            result, changes, _ = self.run_cli("switch main", **override)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Docker target changed", result.stderr)
            self.assertEqual(changes, [])

    def test_colliding_project_and_name_are_rejected_before_mutation(self):
        self.register()
        other = self.fixture.base / "other"
        self.fixture.model(other, "main")
        result, changes, _ = self.run_cli("register another", cwd=other)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Compose project already registered", result.stderr)
        self.assertEqual(changes, [])
        self.fixture.model(other, "other")
        result, changes, _ = self.run_cli("register main", cwd=other)
        self.assertEqual(result.returncode, 1)
        self.assertIn("name already registered", result.stderr)

    def test_changed_identity_requires_explicit_reregistration(self):
        self.register()
        self.fixture.model(self.root, "renamed")
        result, changes, _ = self.run_cli(containers=[legacy.container("a", "renamed")])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(changes, [])
        self.register(name="main")
        result, changes, _ = self.run_cli("switch main", containers=[legacy.container("a", "renamed")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["start", "a"]])

    def test_saved_relative_files_and_compose_environment(self):
        custom = self.root / "custom.json"
        custom.write_text(json.dumps({"name": "custom", "services": {"web": {}}}))
        self.register(name="app -f custom.json", COMPOSE_PROFILES="dev")
        result, changes, calls = self.run_cli("switch app", cwd=self.fixture.base,
                                             containers=[legacy.container("a", "custom")],
                                             COMPOSE_FILE="missing.yaml", COMPOSE_PROFILES="wrong")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["start", "a"]])
        self.assertIn("custom.json", calls[0])
        self.assertEqual(self.entries()[0]["environment"]["COMPOSE_PROFILES"], "dev")

    def test_parent_and_symlink_paths_share_registration(self):
        child = self.root / "nested"
        child.mkdir()
        self.register(child)
        self.assertEqual(self.entries()[0]["path"], str(self.root))
        alias = self.fixture.base / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.register(alias)
        self.assertEqual(len(self.entries()), 1)
        result, _, _ = self.run_cli(cwd=child)
        self.assertNotIn("Register and switch?", result.stdout)

    def test_discovered_children_are_one_switchable_workspace(self):
        (self.root / "compose.yaml").unlink()
        self.fixture.model(self.root / "backend", "api")
        self.fixture.model(self.root / "frontend", "ui")
        self.register(name="stack")
        result, changes, _ = self.run_cli("switch stack", cwd=self.fixture.base, answer="y\n",
                                         containers=[legacy.container("a", "api"), legacy.container("b", "ui")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["start", "a"], ["start", "b"]])
        self.assertEqual(len(self.entries()[0]["members"]), 2)

    def test_missing_directories_are_unavailable_and_not_stopped(self):
        self.register()
        moved = self.fixture.base / "moved"
        self.root.rename(moved)
        result, _, _ = self.run_cli("list", cwd=self.fixture.base)
        self.assertIn("unavailable directory", result.stdout)
        result, changes, _ = self.run_cli("switch main", cwd=self.fixture.base)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(changes, [])
        other = self.fixture.base / "other"
        self.fixture.model(other, "other")
        self.register(other)
        result, changes, _ = self.run_cli(cwd=other, containers=[legacy.container("a", "main", state="running")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])

    def test_host_only_registry_and_offline_list_need_no_docker(self):
        (self.root / "dwork.yml").write_text("version: 1\ncompose: {enabled: false}\n")
        self.register(name="host")
        result, changes, calls = self.run_cli("switch host", cwd=self.fixture.base)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])
        result, _, calls = self.run_cli("list", cwd=self.fixture.base)
        self.assertEqual(calls, [])
        self.assertIn("host-only", result.stdout)

    def test_list_preserves_entries_when_docker_is_offline(self):
        self.register()
        before = self.state.read_bytes()
        result, changes, _ = self.run_cli("list", DWORK_TEST_DAEMON="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Docker status unavailable", result.stdout)
        self.assertIn(str(self.root), result.stdout)
        self.assertEqual(changes, [])
        self.assertEqual(self.state.read_bytes(), before)

    def test_group_decline_does_not_register(self):
        (self.root / "compose.yaml").unlink()
        self.fixture.model(self.root / "backend", "api")
        result, changes, _ = self.run_cli(answer="y\nn\n",
                                         containers=[legacy.container("a", "api")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        self.assertFalse(self.state.exists())

    def test_switch_uses_destination_terminal_and_keeps_session_confirmation(self):
        (self.root / "dwork.yml").write_text(
            "version: 1\ncompose: {enabled: false}\nterminals:\n"
            "  - title: Destination\n    command: [echo, ready]\n")
        launcher = self.fixture.bin / "powershell.exe"
        launcher.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["DWORK_TEST_LOG"], "a") as stream:
    stream.write(json.dumps(["terminal", *sys.argv[1:]]) + "\\n")
''')
        launcher.chmod(0o755)
        self.register(name="host")
        for answer, count in (("n\n", 0), ("y\n", 1)):
            result, changes, calls = self.run_cli(
                "switch host", cwd=self.fixture.base, answer=answer,
                WSL_DISTRO_NAME="Ubuntu", SHELL="/bin/bash")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(changes, [])
            self.assertIn("Open terminal 'Destination'", result.stdout)
            self.assertIn(str(self.root), result.stdout)
            self.assertEqual(sum("-EncodedCommand" in call for call in calls), count)

    def test_read_only_diagnostics_do_not_create_registry(self):
        for args in ("status", "doctor", "list"):
            result, changes, _ = self.run_cli(args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(changes, [])
            self.assertFalse(self.state.parent.exists())

    def test_ancestor_dwork_takes_precedence_over_nearer_compose_for_registration(self):
        (self.root / "dwork.yml").write_text("version: 1\ncompose: {enabled: false}\n")
        child = self.root / "child"
        self.fixture.model(child, "child")
        self.register(child, "host")
        self.assertEqual(self.entries()[0]["path"], str(self.root))
        self.assertIsNone(self.entries()[0]["target"])

    def test_corrupt_registry_fails_closed(self):
        self.state.parent.mkdir(parents=True)
        self.state.write_text("{broken")
        for args in ("", "--dry-run", "register", "list", "forget main", "switch main"):
            result, changes, calls = self.run_cli(args, answer="y\n")
            self.assertEqual(result.returncode, 1, args)
            self.assertIn("Invalid workspace registry", result.stderr)
            self.assertEqual(changes, [])
            self.assertEqual(calls, [])
        self.assertEqual(self.state.read_text(), "{broken")

    def test_malformed_target_is_reported_without_traceback(self):
        self.register()
        data = json.loads(self.state.read_text())
        data["workspaces"][0]["target"] = ["context", "daemon"]
        self.state.write_text(json.dumps(data))
        result, changes, calls = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Invalid workspace registry", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(changes, [])
        self.assertEqual(calls, [])

    def test_usage_errors_do_not_mutate(self):
        for args in ("switch", "forget", "switch nope", "list extra", "recognize", "register --dry-run"):
            result, changes, _ = self.run_cli(args)
            self.assertEqual(result.returncode, 1, args)
            self.assertEqual(changes, [])
        self.assertFalse(self.state.exists())

    def test_registry_lock_prevents_concurrent_mutation(self):
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(self.fixture.base / "state")}):
            with runtime.registry_lock():
                result, changes, calls = self.run_cli("register")
                self.assertEqual(result.returncode, 1)
                self.assertIn("in progress", result.stderr)
                self.assertEqual(changes, [])
                self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
