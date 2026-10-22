"""Named lifecycle batches preserve consent, registration identity, and ownership."""

import contextlib
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_dwork as legacy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import dwork_browsers
import dwork_common
import dwork_docker
import dwork_registry
import dwork_tasks
import dwork_terminals
import dwork_workspaces
from dwork_launch import BrowserLaunch


class NamedWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.state = self.fixture.base / "state/dwork/workspaces.json"

    def cli(self, args, **kwargs):
        kwargs.setdefault("answer", "y\ny\n")
        return self.fixture.run_dwork("bash", args, register_current=False, **kwargs)

    def register(self, name, *, enabled=True, config=None, **environment):
        directory = self.root / name
        self.fixture.model(directory, name, services={"web": {}, "db": {}})
        settings = {"version": 1, "compose": {"enabled": enabled}}
        settings.update(config or {})
        (directory / "dwork.yml").write_text(json.dumps(settings))
        result, changes, _ = self.cli("register " + name, cwd=directory, **environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        return directory

    def entries(self):
        return json.loads(self.state.read_text())["workspaces"]

    def test_up_starts_selected_set_once_without_stopping_other_workspaces(self):
        self.register("alpha")
        self.register("beta")
        self.register("other")
        before = self.state.read_bytes()
        result, changes, _ = self.cli(
            "up alpha beta alpha",
            cwd=self.fixture.base,
            containers=[
                legacy.container("a", "alpha"),
                legacy.container("b", "beta"),
                legacy.container("c", "other", state="running"),
            ],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["start", "a"], ["start", "b"]])
        self.assertEqual(result.stdout.count("Start plan:"), 2)
        self.assertEqual(self.state.read_bytes(), before)

    def test_no_argument_up_still_switches_away_from_outgoing_workspaces(self):
        alpha = self.register("alpha")
        self.register("beta")
        result, changes, _ = self.cli(
            "up",
            cwd=alpha,
            containers=[
                legacy.container("a", "alpha"),
                legacy.container("b", "beta", state="running"),
            ],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "b"], ["start", "a"]])

    def test_up_declining_a_later_activation_cancels_the_whole_batch(self):
        self.register("alpha")
        self.register("beta")
        result, changes, _ = self.cli(
            "up alpha beta",
            answer="y\nn\n",
            containers=[legacy.container("a", "alpha"), legacy.container("b", "beta")],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        self.assertIn("plan for alpha?", result.stdout)
        self.assertIn("plan for beta?", result.stdout)
        self.assertIn("Cancelled", result.stdout)

    def test_unknown_later_name_blocks_up_and_down_before_docker_or_writes(self):
        self.register("alpha")
        before = self.state.read_bytes()
        for command in ("up alpha missing", "down alpha missing", "up alpha missing --dry-run"):
            with self.subTest(command=command):
                result, changes, calls = self.cli(command)
                self.assertEqual(result.returncode, 1)
                self.assertIn("Unknown workspace(s): missing", result.stderr)
                self.assertEqual((changes, calls), ([], []))
                self.assertEqual(self.state.read_bytes(), before)

    def test_later_missing_directory_or_identity_drift_blocks_all_starts(self):
        self.register("alpha")
        beta = self.register("beta")
        containers = [legacy.container("a", "alpha"), legacy.container("b", "beta")]
        self.fixture.model(beta, "changed-project")
        result, changes, _ = self.cli("up alpha beta", containers=containers)
        self.assertEqual(result.returncode, 1)
        self.assertIn("changed since registration", result.stderr)
        self.assertEqual(changes, [])
        beta.rename(self.root / "moved")
        result, changes, calls = self.cli("up alpha beta", containers=containers)
        self.assertEqual(result.returncode, 1)
        self.assertIn("directory unavailable", result.stderr)
        self.assertEqual((changes, calls), ([], []))

    def test_later_terminal_preflight_failure_blocks_all_starts(self):
        self.register("alpha")
        self.register(
            "beta",
            config={
                "terminals": [
                    {"command": ["dwork-unavailable-regression-command"], "window": "none"}
                ]
            },
        )
        result, changes, _ = self.cli(
            "up alpha beta",
            containers=[legacy.container("a", "alpha"), legacy.container("b", "beta")],
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Terminal command is unavailable", result.stderr)
        self.assertEqual(changes, [])
        self.assertNotIn("Apply the listed", result.stdout)

    def test_up_and_down_dry_run_placements_never_prompt_or_mutate(self):
        self.register("alpha")
        self.register("beta")
        before = self.state.read_bytes()
        for command in (
            "up --dry-run alpha beta",
            "up alpha --dry-run beta",
            "up alpha beta --dry-run",
            "down --dry-run alpha beta",
            "down alpha --dry-run beta",
            "down alpha beta --dry-run",
        ):
            with self.subTest(command=command):
                result, changes, _ = self.cli(
                    command,
                    answer="",
                    containers=[
                        legacy.container("a", "alpha"),
                        legacy.container("b", "beta", state="running"),
                    ],
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(changes, [])
                self.assertNotIn("(y/N)", result.stdout)
                self.assertEqual(self.state.read_bytes(), before)

    def test_up_keeps_saved_environments_and_independent_task_owners(self):
        task = {"command": ["echo", "test"], "window": "none"}
        alpha = self.register(
            "alpha", enabled=False, config={"terminals": [task]}, COMPOSE_PROFILES="first"
        )
        beta = self.register(
            "beta", enabled=False, config={"terminals": [task]}, COMPOSE_PROFILES="second"
        )
        observed = []

        def execute(plan, entries):
            observed.append(
                (
                    os.environ.get("COMPOSE_PROFILES"),
                    Path.cwd(),
                    plan.terminals[0].task.workspace,
                    plan.terminals[0].task.directory,
                )
            )

        with (
            patch("builtins.input", return_value="y"),
            patch.object(dwork_workspaces, "execute_activation", side_effect=execute),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            dwork_workspaces.up_registered_workspaces(self.entries(), ["alpha", "beta"], False)
        self.assertEqual(
            observed,
            [("first", alpha, str(alpha), str(alpha)), ("second", beta, str(beta), str(beta))],
        )

    def test_up_preserves_task_browser_and_configured_activation_consent(self):
        config = {
            "confirm": False,
            "terminals": [{"command": ["echo", "test"], "window": "none"}],
            "browsers": [{"url": "http://localhost:3000", "wait_for": False}],
        }
        self.register("alpha", enabled=False, config=config)
        self.register("beta", enabled=False, config=config)
        with (
            patch("builtins.input", return_value="n") as consent,
            patch.object(dwork_terminals, "open_terminal") as terminal,
            patch.object(dwork_browsers, "open_browser") as browser,
            patch.object(
                dwork_browsers,
                "preflight_browsers",
                return_value=[BrowserLaunch(("fake-browser",), False)],
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            dwork_workspaces.up_registered_workspaces(self.entries(), ["alpha", "beta"], False)
        terminal.assert_not_called()
        browser.assert_not_called()
        self.assertEqual(consent.call_count, 4)
        self.assertTrue(
            all("Apply the listed" not in call.args[0] for call in consent.call_args_list)
        )

    def test_down_selects_only_requested_services_and_respects_keep_and_locks(self):
        self.register("alpha", config={"compose": {"services": ["db"]}})
        self.register("beta")
        self.register("locked", config={"locked": True})
        self.register("other")
        result, changes, _ = self.cli(
            "down alpha beta locked alpha",
            DWORK_KEEP_PROJECTS="beta",
            containers=[
                legacy.container("a", "alpha", "db", "paused"),
                legacy.container("b", "alpha", "web", "running"),
                legacy.container("c", "beta", state="running"),
                legacy.container("d", "locked", state="running"),
                legacy.container("e", "other", state="running"),
            ],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "a"]])
        self.assertEqual(
            {entry["name"] for entry in self.entries()}, {"alpha", "beta", "locked", "other"}
        )

    def test_down_keeps_missing_directory_shutdown_and_host_only_scope(self):
        alpha = self.register("alpha")
        self.register("host", enabled=False)
        result, changes, calls = self.cli("down host")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((changes, calls), ([], []))
        alpha.rename(self.root / "moved")
        result, changes, _ = self.cli(
            "down alpha", containers=[legacy.container("a", "alpha", state="running")]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "a"]])

    def test_down_scopes_tracked_tasks_and_unrelated_controller_errors(self):
        alpha = self.register("alpha", enabled=False)
        beta = self.register("beta", enabled=False)

        def record(directory, project):
            return {
                "workspace": str(directory),
                "directory": str(directory),
                "project": project,
                "title": project,
                "pid": 1,
                "command": ["echo", project],
            }

        records = [record(alpha, "alpha"), record(beta, "beta")]

        def running(state, *, on_error):
            on_error(records[1], OSError("unrelated controller"))
            return records

        with patch.object(dwork_tasks, "running", side_effect=running):
            plan = dwork_workspaces.plan_shutdown(
                self.entries(), None, [], set(), include_workspaces={str(alpha)}
            )
        self.assertEqual(plan.tasks, [records[0]])
        self.assertEqual(plan.protected_tasks, [])

        def inaccessible(state, *, on_error):
            on_error(records[0], OSError("selected controller"))
            return records

        with (
            patch.object(dwork_tasks, "running", side_effect=inaccessible),
            self.assertRaisesRegex(dwork_common.DworkError, "Shutdown blocked"),
        ):
            dwork_workspaces.plan_shutdown(
                self.entries(), None, [], set(), include_workspaces={str(alpha)}
            )

    def test_down_rechecks_live_lock_after_consent_without_losing_other_entries(self):
        alpha = self.register("alpha")
        self.register("beta")
        entries = self.entries()

        def consent(prompt):
            (alpha / "dwork.yml").write_text(json.dumps({"version": 1, "locked": True}))
            return True

        with (
            patch.object(dwork_common, "confirm_action", side_effect=consent),
            patch.object(dwork_docker, "docker_target", return_value=entries[0]["target"]),
            patch.object(dwork_docker, "show_target"),
            patch.object(
                dwork_docker,
                "inventory",
                return_value=[legacy.container("a", "alpha", state="running")],
            ),
            patch.object(dwork_docker, "docker") as docker,
            patch.object(dwork_registry, "save_registry") as save,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            dwork_workspaces.down_workspaces(entries, False, ["alpha"])
        docker.assert_not_called()
        self.assertEqual({entry["name"] for entry in save.call_args.args[0]}, {"alpha", "beta"})

    def test_down_does_not_hide_full_registry_ownership_collisions(self):
        self.register("alpha")
        data = json.loads(self.state.read_text())
        alias = deepcopy(data["workspaces"][0])
        alias.update(name="alias", path=str(self.root / "alias"))
        data["workspaces"].append(alias)
        self.state.write_text(json.dumps(data))
        result, changes, calls = self.cli("down alpha")
        self.assertEqual(result.returncode, 1)
        self.assertIn("already registered", result.stderr)
        self.assertEqual((changes, calls), ([], []))

    def test_no_argument_up_compose_flags_and_invalid_named_flags(self):
        self.fixture.model(self.root, "current")
        result, changes, calls = self.cli("up --dry-run -p custom")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Current Compose project: current", result.stdout)
        self.assertTrue(any("-p" in call and "custom" in call for call in calls), calls)
        self.assertEqual(changes, [])
        self.register("alpha")
        for command in (
            "up alpha -f compose.yml",
            "down alpha --all",
            "up alpha --dry-run --dry-run",
        ):
            result, changes, calls = self.cli(command)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Usage: dwork", result.stderr)
            self.assertEqual((changes, calls), ([], []))


if __name__ == "__main__":
    unittest.main()
