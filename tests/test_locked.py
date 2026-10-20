"""Lock policy is live, persistent when unavailable, and cannot be stopped by dwork."""
import json
import contextlib
import io
import os
import unittest
from unittest.mock import patch

import test_dwork as legacy
from test_dwork_config import runtime


class LockedTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.state = self.fixture.base / "state/dwork/workspaces.json"

    def run_cli(self, args, **kwargs):
        kwargs.setdefault("answer", "y\n")
        return self.fixture.run_dwork("bash", args, register_current=False, **kwargs)

    def configure(self, directory, name, locked):
        self.fixture.model(directory, name)
        (directory / "dwork.yml").write_text(json.dumps({"version": 1, "locked": locked}))

    def register(self, name, locked=False):
        directory = self.root / name
        self.configure(directory, name, locked)
        result, _, _ = self.run_cli("register", cwd=directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        return directory

    def entries(self):
        return json.loads(self.state.read_text())["workspaces"]

    def test_locked_workspace_stays_listed_and_is_protected_on_switch_and_down(self):
        self.register("infra", True)
        self.register("other")
        app = self.register("app")
        items = [legacy.container("a", "infra", state="running"),
                 legacy.container("b", "other", state="running"), legacy.container("c", "app")]
        result, changes, _ = self.run_cli("", cwd=app, containers=items)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "b"], ["start", "c"]])
        self.assertIn("Locked projects: infra", result.stdout)
        result, changes, _ = self.run_cli("down", containers=items)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "b"]])
        result, _, _ = self.run_cli("list", containers=items)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[locked]", result.stdout)
        self.assertEqual(len(self.entries()), 3)

    def test_locked_workspace_can_still_be_activated(self):
        self.register("infra", True)
        result, changes, _ = self.run_cli("switch infra", containers=[legacy.container("a", "infra")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["start", "a"]])

    def test_new_lock_applies_without_reregistration_and_snapshot_survives_missing_directory(self):
        directory = self.register("infra")
        self.configure(directory, "infra", True)
        before = self.state.read_bytes()
        items = [legacy.container("a", "infra", state="paused")]
        result, changes, _ = self.run_cli("down --dry-run", containers=items)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        self.assertEqual(self.state.read_bytes(), before)
        result, changes, _ = self.run_cli("down", containers=items)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        self.assertTrue(self.entries()[0]["members"][0]["locked"])
        directory.rename(self.root / "moved")
        result, changes, _ = self.run_cli("down", containers=items)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])

    def test_explicit_false_unlocks_without_reregistration(self):
        directory = self.register("infra", True)
        self.configure(directory, "infra", False)
        result, changes, _ = self.run_cli("down", containers=[legacy.container("a", "infra", state="running")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "a"]])
        self.assertFalse(self.entries()[0]["members"][0]["locked"])

    def test_missing_config_keeps_last_known_lock(self):
        directory = self.register("infra", True)
        (directory / "dwork.yml").unlink()
        result, changes, _ = self.run_cli("down", containers=[legacy.container("a", "infra", state="running")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])

    def test_invalid_live_policy_is_protected_instead_of_silently_unlocked(self):
        directory = self.register("infra")
        for config in ('version: 1\nlocked: "false"\n', "version: 1\nlocked: false\nlocked: true\n", "version: 99\n"):
            (directory / "dwork.yml").write_text(config)
            result, changes, _ = self.run_cli("down", containers=[legacy.container("a", "infra", state="running")])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(changes, [])
            self.assertIn("protecting infra", result.stderr)

    def test_list_is_read_only_when_live_lock_changes(self):
        directory = self.register("infra")
        self.configure(directory, "infra", True)
        before = self.state.read_bytes()
        result, changes, _ = self.run_cli("list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[locked]", result.stdout)
        self.assertEqual(changes, [])
        self.assertEqual(self.state.read_bytes(), before)

    def test_mixed_child_group_protects_only_locked_child(self):
        self.configure(self.root / "group/db", "db", True)
        self.configure(self.root / "group/api", "api", False)
        result, _, _ = self.run_cli("register stack", cwd=self.root / "group")
        self.assertEqual(result.returncode, 0, result.stderr)
        items = [legacy.container("a", "db", state="running"), legacy.container("b", "api", state="running")]
        result, changes, _ = self.run_cli("down", containers=items)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "b"]])
        result, _, _ = self.run_cli("list")
        self.assertIn("[locked: db]", result.stdout)

    def test_legacy_registry_members_default_to_unlocked(self):
        self.register("infra")
        data = json.loads(self.state.read_text())
        del data["workspaces"][0]["members"][0]["locked"]
        self.state.write_text(json.dumps(data))
        result, changes, _ = self.run_cli("down", containers=[legacy.container("a", "infra", state="running")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "a"]])

    def test_locked_requires_boolean_before_docker_is_called(self):
        for value in ("true", "false", 0, 1, None):
            self.configure(self.root, "infra", value)
            with patch.object(runtime, "read_model") as model:
                with self.assertRaisesRegex(runtime.DworkError, "locked must be true or false"):
                    runtime.load_workspace(self.root)
            model.assert_not_called()

    def test_lock_enabled_while_registration_prompt_is_open_is_rechecked_before_stopping(self):
        infra = self.register("infra")
        app = self.root / "app"
        self.configure(app, "app", False)
        def accept_and_lock(entry):
            self.configure(infra, "infra", True)
            return True
        items = [legacy.container("a", "infra", state="running"), legacy.container("b", "app")]
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(self.fixture.base / "state")}), \
                patch.object(runtime, "discover", return_value=([runtime.Workspace("app", app, {"web": {}})], False)), \
                patch.object(runtime, "docker_target", return_value={"context": "default", "daemon": "test-daemon"}), \
                patch.object(runtime, "show_target"), patch.object(runtime, "inventory", return_value=items), \
                patch.object(runtime, "confirm_registration", side_effect=accept_and_lock), \
                patch.object(runtime, "docker") as docker, contextlib.redirect_stdout(io.StringIO()) as output:
            with runtime.registry_lock():
                self.assertEqual(runtime.switch_workspace(app, [], "activate", False, runtime.read_registry()), 0)
        self.assertIn("Skipped stop: infra is now locked", output.getvalue())
        self.assertEqual([call.args for call in docker.call_args_list], [("start", "b")])
        self.assertEqual(len(self.entries()), 2)


if __name__ == "__main__":
    unittest.main()
