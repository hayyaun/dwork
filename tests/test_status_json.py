"""Machine-readable observations never acquire ownership or mutate state."""

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import os
import subprocess

from jsonschema import Draft7Validator
from pathlib import Path
import sys
from unittest.mock import patch
import unittest

import test_dwork as legacy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import dwork_cli
from dwork_common import DworkError, Workspace
import dwork_config
import dwork_docker
import dwork_registry
import dwork_status
import dwork_tasks


class StatusJsonTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.target = {"context": "default", "daemon": "test"}
        self.workspace = Workspace("app", self.root, {"web": {}}, selected=["web"])
        self.entry = dwork_registry.registration(
            self.root, [], [self.workspace], self.target, "app"
        )

    def test_registered_snapshot_is_private_read_only_and_target_service_scoped(self):
        before = deepcopy(self.entry)
        record = {
            "workspace": str(self.root),
            "directory": str(self.root),
            "project": "app",
            "token": "secret-token",
            "socket": "secret-socket",
            "command": ["secret-argument"],
        }
        items = [
            legacy.container("a", "app", "web", "running"),
            legacy.container("b", "app", "db", "running"),
            legacy.container("c", "other", "web", "running"),
        ]

        def records(state, on_error):
            on_error(record, PermissionError("controller unavailable"))
            return [
                record,
                {**record, "workspace": "/forgotten"},
                {**record, "directory": "/changed"},
            ]

        with (
            patch.object(dwork_registry, "refresh_locks", return_value=False),
            patch.object(dwork_tasks, "running", side_effect=records),
            patch.object(dwork_registry, "save_registry", side_effect=AssertionError("write")),
            patch.object(dwork_registry, "registry_lock", side_effect=AssertionError("lock")),
        ):
            data = dwork_status.snapshot(
                [self.entry],
                scope="registered",
                docker={"target": self.target, "available": True, "error": None},
                containers=items,
            )
        Draft7Validator(
            json.loads(
                (Path(__file__).resolve().parents[1] / "schemas/status.schema.json").read_text()
            )
        ).validate(data)
        row = data["workspaces"][0]
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(row["containers"], {"running": 1, "total": 1})
        self.assertEqual(row["tasks"], {"running": 1, "unresolved": 1})
        self.assertEqual(self.entry, before)
        for secret in (
            "secret-token",
            "secret-socket",
            "secret-argument",
            "environment",
            "options",
        ):
            self.assertNotIn(secret, json.dumps(data))

    def test_host_only_status_avoids_docker_and_does_not_create_state(self):
        entry = dwork_registry.registration(
            self.root, [], [Workspace("host", self.root, {}, enabled=False)], None, "host"
        )
        with (
            patch.object(dwork_docker, "docker_target", side_effect=AssertionError("Docker")),
            patch.object(dwork_tasks, "running", return_value=[]),
        ):
            data = dwork_status.snapshot([entry], scope="registered")
        self.assertEqual(data["workspaces"][0]["status"], "host_only")
        self.assertIsNone(data["docker"]["available"])

    def test_offline_and_other_targets_are_unknown_counts_not_zero(self):
        for docker, state in (
            ({"target": None, "available": False, "error": "offline"}, "docker_unavailable"),
            (
                {
                    "target": {"context": "other", "daemon": "other"},
                    "available": True,
                    "error": None,
                },
                "different_target",
            ),
        ):
            with self.subTest(state=state), patch.object(dwork_tasks, "running", return_value=[]):
                row = dwork_status.snapshot(
                    [self.entry], scope="registered", docker=docker, containers=[]
                )["workspaces"][0]
            self.assertEqual(row["status"], state)
            self.assertIsNone(row["containers"])

    def test_live_locks_are_observed_on_copies_and_kept_policy_is_separate(self):
        (self.root / "dwork.yml").write_text(
            "version: 1\nlocked: true\ncompose: {enabled: false}\n"
        )
        entry = {**self.entry, "temporary_locked": True}
        with (
            patch.dict("os.environ", {"DWORK_KEEP_PROJECTS": "app"}),
            patch.object(dwork_tasks, "running", return_value=[]),
        ):
            row = dwork_status.snapshot(
                [entry],
                scope="registered",
                docker={"target": self.target, "available": True, "error": None},
                containers=[],
            )["workspaces"][0]
        self.assertTrue(row["members"][0]["locked"])
        self.assertTrue(row["members"][0]["protected"])
        self.assertTrue(row["members"][0]["kept"])
        self.assertFalse(self.entry["members"][0]["locked"])

    def test_json_list_is_one_document_and_uses_no_mutation_path(self):
        data = {"schema_version": 1, "scope": "registered", "workspaces": []}
        with (
            patch.object(sys, "argv", ["dwork", "ls", "--json"]),
            patch.object(dwork_status, "registered_snapshot", return_value=data),
            patch.object(dwork_registry, "registry_lock", side_effect=AssertionError("lock")),
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(dwork_cli.cli(), 0)
        self.assertEqual(json.loads(output.getvalue()), data)

    def test_json_status_retains_options_and_no_registry_path(self):
        with (
            patch.object(sys, "argv", ["dwork", "ps", "--json", "--file=custom.yml"]),
            patch.object(
                dwork_status, "current_snapshot", return_value={"schema_version": 1}
            ) as inspect,
            patch.object(dwork_registry, "read_registry", side_effect=AssertionError("registry")),
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(dwork_cli.cli(), 0)
        self.assertEqual(inspect.call_args.args[1], ["--file=custom.yml"])
        self.assertEqual(json.loads(output.getvalue()), {"schema_version": 1})

    def test_current_host_snapshot_never_reads_registry(self):
        workspace = Workspace("host", self.root, {}, enabled=False)
        with (
            patch.object(dwork_config, "discover", return_value=([workspace], False)),
            patch.object(dwork_registry, "read_registry", side_effect=AssertionError("registry")),
            patch.object(dwork_tasks, "running", return_value=[]),
            patch.object(dwork_docker, "docker_target", side_effect=AssertionError("Docker")),
        ):
            data = dwork_status.current_snapshot(self.root, [])
        self.assertEqual(data["scope"], "current")
        self.assertEqual(data["workspaces"][0]["status"], "host_only")

    def test_real_json_list_remains_read_only_while_mutation_lock_is_held(self):
        entry = dwork_registry.registration(
            self.root, [], [Workspace("host", self.root, {}, enabled=False)], None, "host"
        )
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(self.fixture.base / "json-state")}):
            with dwork_registry.registry_lock():
                dwork_registry.save_registry([entry])
                previous = dwork_registry.registry_path().read_bytes()
                result = subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve().parents[1] / "lib/dwork.py"),
                        "list",
                        "--json",
                    ],
                    cwd=self.fixture.base,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["workspaces"][0]["name"], "host")
                self.assertEqual(previous, dwork_registry.registry_path().read_bytes())

    def test_json_flag_combinations_are_rejected(self):
        for args in (
            ["list", "--json", "--names"],
            ["list", "--dry-run", "--json"],
            ["status", "--json", "--json"],
            ["status", "--dry-run", "--json"],
        ):
            with (
                self.subTest(args=args),
                patch.object(sys, "argv", ["dwork", *args]),
                self.assertRaises(DworkError),
            ):
                dwork_cli.main()


if __name__ == "__main__":
    unittest.main()
