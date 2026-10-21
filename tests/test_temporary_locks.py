"""Local workspace locks preserve YAML policy and protect shutdown boundaries."""

import fcntl
import json
import unittest

import test_dwork as legacy


class TemporaryLockTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.state = self.fixture.base / "state/dwork/workspaces.json"

    def cli(self, args, **kwargs):
        kwargs.setdefault("answer", "y\n")
        return self.fixture.run_dwork("bash", args, register_current=False, **kwargs)

    def configure(self, directory, name, locked=False):
        self.fixture.model(directory, name)
        (directory / "dwork.yml").write_text(json.dumps({"version": 1, "locked": locked}))

    def register(self, name, locked=False):
        directory = self.root / name
        self.configure(directory, name, locked)
        result, _, _ = self.cli("register " + name, cwd=directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        return directory

    def entries(self):
        return json.loads(self.state.read_text())["workspaces"]

    def test_multiple_locks_are_local_idempotent_and_need_no_docker(self):
        directories = [self.register("infra"), self.register("app")]
        configs = [(directory / "dwork.yml").read_bytes() for directory in directories]
        for command in ("lock infra app infra", "lock infra app"):
            result, changes, calls = self.cli(command)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((changes, calls), ([], []))
            self.assertTrue(all(entry["temporary_locked"] for entry in self.entries()))
            self.assertTrue(all(not entry["members"][0]["locked"] for entry in self.entries()))
        for command in ("unlock infra app", "unlock infra app"):
            result, changes, calls = self.cli(command)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((changes, calls), ([], []))
            self.assertTrue(
                all(not entry.get("temporary_locked", False) for entry in self.entries())
            )
        self.assertEqual(
            configs, [(directory / "dwork.yml").read_bytes() for directory in directories]
        )

    def test_unknown_batch_name_changes_nothing(self):
        self.register("infra")
        for command in (
            "lock infra missing",
            "unlock infra missing",
            "lock infra missing --dry-run",
        ):
            before = self.state.read_bytes()
            result, changes, calls = self.cli(command)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unknown workspace(s): missing", result.stderr)
            self.assertEqual(self.state.read_bytes(), before)
            self.assertEqual((changes, calls), ([], []))

    def test_preview_never_creates_or_changes_state(self):
        result, changes, calls = self.cli("lock missing --dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.state.parent.exists())
        self.assertEqual((changes, calls), ([], []))
        self.register("infra")
        for command in ("lock --dry-run infra", "lock infra --dry-run", "unlock infra --dry-run"):
            before = self.state.read_bytes()
            result, changes, calls = self.cli(command)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Would", result.stdout)
            self.assertEqual(self.state.read_bytes(), before)
            self.assertEqual((changes, calls), ([], []))

    def test_lock_protects_switch_and_down_but_allows_activation(self):
        self.register("infra")
        self.register("other")
        self.register("app")
        result, _, _ = self.cli("lock infra")
        self.assertEqual(result.returncode, 0, result.stderr)
        items = [
            legacy.container("a", "infra", state="running"),
            legacy.container("b", "other", state="running"),
            legacy.container("c", "app"),
        ]
        result, changes, _ = self.cli("switch app", containers=items)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "b"], ["start", "c"]])
        self.assertIn("Locked projects: infra", result.stdout)
        result, changes, _ = self.cli("down", containers=items)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "b"]])
        result, changes, _ = self.cli("switch infra", containers=[legacy.container("a", "infra")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["start", "a"]])

    def test_unlock_keeps_configured_locks_and_existing_exclusions(self):
        self.register("infra", locked=True)
        self.register("app")
        self.register("kept")
        for command in ("lock infra app kept", "unlock infra app kept"):
            result, _, _ = self.cli(command)
            self.assertEqual(result.returncode, 0, result.stderr)
        items = [
            legacy.container("a", "infra", state="running"),
            legacy.container("b", "app", state="running"),
            legacy.container("c", "kept", state="running"),
        ]
        result, changes, _ = self.cli("down", containers=items, DWORK_KEEP_PROJECTS="kept")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "b"]])
        self.assertTrue(
            next(e for e in self.entries() if e["name"] == "infra")["members"][0]["locked"]
        )

    def test_group_lock_protects_all_members_and_unlock_restores_child_policy(self):
        group = self.root / "group"
        self.configure(group / "db", "db", locked=True)
        self.configure(group / "api", "api")
        result, _, _ = self.cli("register stack", cwd=group)
        self.assertEqual(result.returncode, 0, result.stderr)
        result, _, _ = self.cli("lock stack")
        self.assertEqual(result.returncode, 0, result.stderr)
        items = [
            legacy.container("a", "db", state="running"),
            legacy.container("b", "api", state="running"),
        ]
        result, changes, _ = self.cli("down", containers=items)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        before = self.state.read_bytes()
        result, _, _ = self.cli("ls", containers=items)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"(?m)^stack\s+.*\s+temporary \+ db\s+")
        self.assertEqual(self.state.read_bytes(), before)
        result, _, _ = self.cli("unlock stack")
        self.assertEqual(result.returncode, 0, result.stderr)
        result, changes, _ = self.cli("down", containers=items)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "b"]])

    def test_lock_survives_rename_reregistration_and_missing_directory(self):
        directory = self.register("infra")
        for command in ("lock infra", "rename infra shared", "register shared"):
            result, _, _ = self.cli(command, cwd=directory)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.entries()[0]["temporary_locked"])
        directory.rename(self.root / "moved")
        result, changes, _ = self.cli(
            "down", containers=[legacy.container("a", "infra", state="running")]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        result, changes, calls = self.cli("unlock shared")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((changes, calls), ([], []))
        result, changes, _ = self.cli(
            "down", containers=[legacy.container("a", "infra", state="running")]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "a"]])

    def test_mutation_respects_operation_lock_while_preview_remains_read_only(self):
        self.register("infra")
        before = self.state.read_bytes()
        with (self.state.parent / "workspaces.lock").open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for command in ("lock infra", "unlock infra"):
                result, changes, calls = self.cli(command)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("in progress", result.stderr)
                self.assertEqual((changes, calls), ([], []))
                self.assertEqual(self.state.read_bytes(), before)
            result, changes, calls = self.cli("lock infra --dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((changes, calls), ([], []))
            self.assertEqual(self.state.read_bytes(), before)

    def test_forget_discards_temporary_lock(self):
        directory = self.register("infra")
        for command in ("lock infra", "forget infra", "register infra"):
            result, _, _ = self.cli(command, cwd=directory)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.entries()[0].get("temporary_locked", False))

    def test_invalid_registry_lock_fails_closed_before_docker(self):
        self.register("infra")
        data = json.loads(self.state.read_text())
        for value in ("false", "true", 0, 1, None):
            data["workspaces"][0]["temporary_locked"] = value
            self.state.write_text(json.dumps(data))
            result, changes, calls = self.cli("down")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Invalid workspace registry", result.stderr)
            self.assertEqual((changes, calls), ([], []))

    def test_missing_names_and_unknown_options_do_not_mutate(self):
        for command in ("lock", "unlock", "lock --all", "unlock --dry-run", "lock infra --force"):
            result, changes, calls = self.cli(command)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Usage: dwork", result.stderr)
            self.assertFalse(self.state.parent.exists())
            self.assertEqual((changes, calls), ([], []))


if __name__ == "__main__":
    unittest.main()
