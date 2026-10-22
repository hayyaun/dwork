"""Group metadata preserves registry identities without consulting live workloads."""

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import dwork_config
import dwork_docker
import dwork_groups
import dwork_registry
import dwork_registry_store as store
from dwork_common import DworkError


class GroupStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        path = self.root / "state/workspaces.json"
        replacement = patch.object(store, "registry_path", return_value=path)
        replacement.start()
        self.addCleanup(replacement.stop)
        self.target = {"context": "default", "daemon": "engine"}
        self.entries = [self.entry("alpha"), self.entry("beta"), self.entry("host", host=True)]

    def entry(self, name, *, host=False):
        return {
            "name": name,
            "path": str(self.root / name),
            "options": [],
            "environment": {},
            "target": None if host else deepcopy(self.target),
            "members": [
                {
                    "project": name,
                    "directory": str(self.root / name),
                    "enabled": not host,
                    "locked": False,
                    "services": None,
                }
            ],
        }

    def save(self, entries=None, **kwargs):
        with store.registry_lock():
            store.save_registry(self.entries if entries is None else entries, **kwargs)

    def command(self, action, name=None, members=(), preview=False):
        with store.registry_lock(), redirect_stdout(io.StringIO()) as output:
            result = dwork_groups.group_command(
                store.read_registry(), action, name, members, preview
            )
        self.assertEqual(result, 0)
        return output.getvalue()

    def document(self):
        return json.loads(store.registry_path().read_text())

    def test_group_free_reads_do_not_create_or_migrate_state_and_writes_stay_v1(self):
        self.assertEqual(store.read_registry(), [])
        self.assertEqual(store.read_groups(), {})
        self.assertFalse(store.registry_path().parent.exists())
        self.save()
        before = store.registry_path().read_bytes()
        self.assertEqual(store.read_registry(), self.entries)
        self.assertEqual(dwork_registry.read_groups(), {})
        self.assertEqual(store.registry_path().read_bytes(), before)
        self.save()
        self.assertEqual(self.document(), {"version": 1, "workspaces": self.entries})

    def test_first_group_uses_v2_and_old_reader_refuses_before_mutation(self):
        self.save()
        self.command("create", "dev", ["alpha", "host", "alpha"])
        self.assertEqual(self.document()["version"], 2)
        self.assertEqual(store.read_groups(), {"dev": ["alpha", "host"]})
        # Published 0.5.0 rejects any version other than exactly integer 1.
        legacy = self.document()
        with self.assertRaises(ValueError):
            if type(legacy["version"]) is not int or legacy["version"] != 1:
                raise ValueError("unsupported registry")
        before = store.registry_path().read_bytes()
        self.assertEqual(store.read_registry(), self.entries)
        self.assertEqual(store.registry_path().read_bytes(), before)
        self.command("delete", "dev")
        self.assertEqual(self.document(), {"version": 1, "workspaces": self.entries})

    def test_entries_only_updates_preserve_groups_and_existing_fields(self):
        self.save()
        data = self.document()
        data["other_metadata"] = {"preserve": True}
        data["workspaces"][0].update(direct=True, temporary_locked=True, extra="retained")
        store.registry_path().write_text(json.dumps(data))
        entries = store.read_registry()
        self.command("create", "dev", ["alpha", "beta"])
        entries[0]["members"][0]["locked"] = True
        self.save(list(reversed(entries)))
        data = self.document()
        self.assertEqual(data["other_metadata"], {"preserve": True})
        self.assertEqual(data["groups"], {"dev": ["alpha", "beta"]})
        self.assertEqual(data["workspaces"][-1]["extra"], "retained")
        self.assertTrue(data["workspaces"][-1]["temporary_locked"])
        self.assertTrue(data["workspaces"][-1]["direct"])
        self.assertTrue(data["workspaces"][-1]["members"][0]["locked"])

    def test_workspace_rename_and_reregistration_update_overlapping_references_once(self):
        self.save()
        self.command("create", "alpha", ["alpha", "host"])
        self.command("create", "dev", ["beta", "alpha"])
        entries = store.read_registry()
        entries[0]["name"] = "renamed"
        entries[0]["options"] = ["--profile", "development"]
        replacements = []
        original = Path.replace

        def replace(path, destination):
            replacements.append(destination)
            return original(path, destination)

        with patch.object(Path, "replace", autospec=True, side_effect=replace):
            self.save(entries)
        self.assertEqual(replacements, [store.registry_path()])
        self.assertEqual(
            store.read_groups(), {"alpha": ["renamed", "host"], "dev": ["beta", "renamed"]}
        )
        self.assertEqual(store.read_registry()[0], entries[0])

    def test_referenced_forget_and_cross_target_reregistration_are_atomic(self):
        self.save()
        self.command("create", "dev", ["alpha", "beta"])
        before = store.registry_path().read_bytes()
        with self.assertRaisesRegex(DworkError, "group remove dev alpha.*group delete dev"):
            self.save(self.entries[1:])
        self.assertEqual(store.registry_path().read_bytes(), before)
        changed = deepcopy(self.entries)
        changed[0]["target"] = {"context": "other", "daemon": "other"}
        with self.assertRaisesRegex(DworkError, "Invalid workspace registry"):
            self.save(changed)
        self.assertEqual(store.registry_path().read_bytes(), before)
        self.command("remove", "dev", ["alpha"])
        self.save(self.entries[1:])
        self.assertEqual(store.read_groups(), {"dev": ["beta"]})

    def test_failed_atomic_replacement_keeps_registration_and_group_references(self):
        self.save()
        self.command("create", "dev", ["alpha", "beta"])
        before = store.registry_path().read_bytes()
        files = set(store.registry_path().parent.iterdir())
        entries = deepcopy(self.entries)
        entries[0]["name"] = "renamed"
        with patch.object(Path, "replace", side_effect=OSError("interrupted")):
            with self.assertRaisesRegex(OSError, "interrupted"):
                self.save(entries)
        self.assertEqual(store.registry_path().read_bytes(), before)
        self.assertEqual(set(store.registry_path().parent.iterdir()), files)

    def test_malformed_groups_fail_closed_for_reads_and_preserving_saves(self):
        self.save()
        valid = self.document()
        malformed = [
            None,
            [],
            {"bad name": ["alpha"]},
            {"dev": []},
            {"dev": "alpha"},
            {"dev": ["alpha", "alpha"]},
            {"dev": ["unknown"]},
            {"dev": [{"group": "nested"}]},
            {"dev": [True]},
        ]
        for groups in malformed:
            with self.subTest(groups=groups):
                data = {**valid, "version": 2, "groups": groups}
                store.registry_path().write_text(json.dumps(data))
                before = store.registry_path().read_bytes()
                for read in (store.read_registry, store.read_groups):
                    with self.assertRaisesRegex(DworkError, "Invalid workspace registry"):
                        read()
                with self.assertRaisesRegex(DworkError, "Invalid workspace registry"):
                    self.save([])
                self.assertEqual(store.registry_path().read_bytes(), before)
        for version in (1, True, 3):
            data = {**valid, "version": version, "groups": {"dev": ["alpha"]}}
            store.registry_path().write_text(json.dumps(data))
            with self.assertRaisesRegex(DworkError, "Invalid workspace registry"):
                store.read_registry()

    def test_saved_cross_target_groups_are_invalid_even_without_live_docker(self):
        entries = deepcopy(self.entries)
        entries[1]["target"] = {"context": "remote", "daemon": "remote"}
        self.save(entries)
        data = self.document()
        data.update(version=2, groups={"dev": ["alpha", "beta", "host"]})
        store.registry_path().write_text(json.dumps(data))
        with self.assertRaisesRegex(DworkError, "Invalid workspace registry"):
            dwork_groups.select_group(entries, "dev")

    def test_crud_and_selection_are_ordered_offline_and_leave_workloads_untouched(self):
        self.save()
        with (
            patch.object(dwork_docker, "inventory", side_effect=AssertionError("Docker")),
            patch.object(dwork_docker, "docker_target", side_effect=AssertionError("Docker")),
            patch.object(dwork_config, "load_workspace", side_effect=AssertionError("config")),
        ):
            self.command("create", "dev", ["beta", "alpha", "beta"])
            self.command("add", "dev", ["host", "alpha"])
            self.command("create", "alpha", ["alpha", "host"])
            self.assertEqual(
                [e["name"] for e in dwork_groups.select_group(self.entries, "dev")],
                ["beta", "alpha", "host"],
            )
            self.assertEqual(dwork_groups.group_names(), ["alpha", "dev"])
            self.assertIn("NAME", self.command("list"))
            shown = self.command("show", "dev")
            self.assertLess(shown.index("beta ->"), shown.index("alpha ->"))
            self.assertIn("host-only", shown)
            self.assertIn("default / engine", shown)
            self.command("remove", "dev", ["alpha", "alpha"])
            self.assertEqual(store.read_groups()["dev"], ["beta", "host"])
            self.command("delete", "alpha")

    def test_invalid_member_batches_and_nested_group_names_do_not_partially_save(self):
        self.save()
        self.command("create", "dev", ["alpha"])
        before = store.registry_path().read_bytes()
        cases = [
            ("create", "empty", []),
            ("create", "nested", ["dev"]),
            ("create", "dev", ["beta"]),
            ("create", "bad name", ["alpha"]),
            ("add", "dev", ["beta", "unknown"]),
            ("remove", "dev", ["alpha", "unknown"]),
            ("remove", "dev", ["alpha"]),
            ("delete", "missing", []),
            ("add", "dev", []),
            ("remove", "dev", []),
        ]
        for action, name, members in cases:
            with self.subTest(action=action, name=name, members=members):
                with self.assertRaises(DworkError):
                    self.command(action, name, members)
                self.assertEqual(store.registry_path().read_bytes(), before)
        with self.assertRaisesRegex(DworkError, "group delete dev"):
            self.command("remove", "dev", ["alpha"])

    def test_add_rejects_other_saved_targets_and_full_registry_ownership_conflicts(self):
        entries = deepcopy(self.entries)
        entries[1]["target"] = {"context": "other", "daemon": "other"}
        self.save(entries)
        self.command("create", "dev", ["alpha", "host"])
        before = store.registry_path().read_bytes()
        with self.assertRaisesRegex(DworkError, "same saved Docker target"):
            self.command("add", "dev", ["beta"])
        self.assertEqual(store.registry_path().read_bytes(), before)
        entries = deepcopy(self.entries)
        entries[1]["members"][0]["project"] = "alpha"
        self.save(entries, groups={})
        with self.assertRaisesRegex(DworkError, "already registered"):
            self.command("create", "collision", ["alpha"])

    def test_all_management_previews_and_inspection_preserve_bytes(self):
        self.save()
        self.command("create", "dev", ["alpha", "beta"])
        before = store.registry_path().read_bytes()
        for action, name, members in [
            ("create", "other", ["host"]),
            ("add", "dev", ["host"]),
            ("remove", "dev", ["alpha"]),
            ("delete", "dev", []),
        ]:
            self.assertIn("Would", self.command(action, name, members, preview=True))
            self.assertEqual(store.registry_path().read_bytes(), before)
        self.command("list")
        self.command("show", "dev")
        dwork_groups.group_names()
        dwork_groups.select_group(self.entries, "dev")
        self.assertEqual(store.registry_path().read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
