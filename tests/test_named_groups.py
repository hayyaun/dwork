"""Reusable selections keep ownership, batch consent, and combined switch boundaries."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_dwork as legacy
import test_named_workspaces as named

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import dwork_browsers
import dwork_common
import dwork_docker
import dwork_tasks
import dwork_terminals
import dwork_workspaces
from dwork_launch import BrowserLaunch


class NamedGroupTests(unittest.TestCase):
    def setUp(self):
        self.fixture = named.NamedWorkspaceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.state = self.fixture.state

    def cli(self, command, **kwargs):
        kwargs.setdefault("answer", "y\n" * 10)
        return self.fixture.cli(command, **kwargs)

    def register(self, name, **kwargs):
        return self.fixture.register(name, **kwargs)

    def group(self, name, *members):
        result, changes, calls = self.cli("group create " + " ".join((name, *members)))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((changes, calls), ([], []))

    def test_empty_listing_is_read_only_and_management_rejects_bad_syntax(self):
        for command in ("group list", "group list --names"):
            result, changes, calls = self.cli(command)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((changes, calls), ([], []))
            self.assertFalse(self.state.parent.exists())
        for command in (
            "group",
            "group missing",
            "group create dev",
            "group add dev",
            "group show",
            "group list extra",
            "group delete dev extra",
            "group list --dry-run",
            "group show dev --dry-run",
            "group list --json",
        ):
            with self.subTest(command=command):
                result, changes, calls = self.cli(command)
                self.assertEqual(result.returncode, 1)
                self.assertIn("Usage:", result.stderr)
                self.assertEqual((changes, calls), ([], []))
                self.assertFalse(self.state.parent.exists())

    def test_management_and_namespace_are_explicit_without_workload_changes(self):
        self.register("dev", enabled=False)
        self.register("api", enabled=False)
        self.register("web", enabled=False)
        self.group("dev", "api")
        for command in (
            "group --dry-run add dev web",
            "group add --dry-run dev web",
            "group add dev web --dry-run",
        ):
            before = self.state.read_bytes()
            result, changes, calls = self.cli(command)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.state.read_bytes(), before)
            self.assertEqual((changes, calls), ([], []))
        result, _, _ = self.cli("group add dev web")
        self.assertEqual(result.returncode, 0, result.stderr)
        result, _, calls = self.cli("group list --names")
        self.assertEqual(result.stdout, "dev\n")
        self.assertEqual(calls, [])
        result, _, calls = self.cli("group show dev")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("api", result.stdout)
        self.assertIn("web", result.stdout)
        self.assertEqual(calls, [])
        result, _, _ = self.cli("group remove dev api")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.state.read_text())["groups"], {"dev": ["web"]})
        result, _, _ = self.cli("group delete dev")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({entry["name"] for entry in self.fixture.entries()}, {"dev", "api", "web"})

    def test_up_group_is_additive_and_direct_member_selection_stays_individual(self):
        for name in ("alpha", "beta", "other"):
            self.register(name)
        self.group("dev", "alpha", "beta")
        containers = [
            legacy.container("a", "alpha"),
            legacy.container("b", "beta"),
            legacy.container("c", "other", state="running"),
        ]
        before = self.state.read_bytes()
        result, changes, _ = self.cli("up --group dev", containers=containers)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["start", "a"], ["start", "b"]])
        result, changes, _ = self.cli("up alpha", containers=containers)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["start", "a"]])
        self.assertEqual(self.state.read_bytes(), before)

    def test_switch_keeps_all_members_and_stops_only_eligible_outgoing_owners_once(self):
        for name in ("alpha", "beta", "out1", "out2", "keep"):
            self.register(name)
        self.register("locked", config={"locked": True})
        self.group("dev", "alpha", "beta")
        result, changes, _ = self.cli(
            "switch --group dev",
            DWORK_KEEP_PROJECTS="keep",
            containers=[
                legacy.container("a", "alpha", state="running"),
                legacy.container("b", "beta"),
                legacy.container("c", "out1", state="running"),
                legacy.container("d", "out2", state="paused"),
                legacy.container("e", "locked", state="running"),
                legacy.container("f", "keep", state="running"),
                legacy.container("g", "unregistered", state="running"),
            ],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "c", "d"], ["start", "b"]])
        self.assertIn("Combined group switch plan: dev", result.stdout)
        self.assertNotIn("Other registered workspaces are left running.", result.stdout)

    def test_down_group_respects_services_locks_keep_and_shared_membership(self):
        self.register("alpha", config={"compose": {"services": ["db"]}})
        for name in ("beta", "temporary", "other"):
            self.register(name)
        self.register("locked", config={"locked": True})
        self.group("dev", "alpha", "beta", "temporary", "locked")
        self.group("another", "alpha", "other")
        result, _, _ = self.cli("lock temporary")
        self.assertEqual(result.returncode, 0, result.stderr)
        before = self.state.read_bytes()
        result, changes, _ = self.cli(
            "down --group dev",
            DWORK_KEEP_PROJECTS="beta",
            containers=[
                legacy.container("a", "alpha", "db", "paused"),
                legacy.container("b", "alpha", "web", "running"),
                legacy.container("c", "beta", state="running"),
                legacy.container("d", "temporary", state="running"),
                legacy.container("e", "locked", state="running"),
                legacy.container("f", "other", state="running"),
            ],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "a"]])
        self.assertEqual(self.state.read_bytes(), before)

    def test_group_selectors_reject_unknown_mixed_and_duplicate_options_before_docker(self):
        self.register("alpha")
        self.group("dev", "alpha")
        before = self.state.read_bytes()
        for command in (
            "up --group missing",
            "down --group missing",
            "switch --group missing",
            "up alpha --group dev",
            "down --group dev alpha",
            "switch alpha --group dev",
            "up --group",
            "up --group --dry-run",
            "down --group dev --group dev",
            "switch --group dev --dry-run --dry-run",
            "up -f compose.yaml --group dev",
        ):
            with self.subTest(command=command):
                result, changes, calls = self.cli(command)
                self.assertEqual(result.returncode, 1)
                self.assertEqual((changes, calls), ([], []))
                self.assertEqual(self.state.read_bytes(), before)

    def test_all_preview_positions_leave_registry_unchanged_and_never_prompt(self):
        self.register("alpha")
        self.register("other")
        self.group("dev", "alpha")
        before = self.state.read_bytes()
        for mode in ("up", "switch", "down"):
            for suffix in ("--dry-run --group dev", "--group dev --dry-run"):
                result, changes, _ = self.cli(
                    mode + " " + suffix,
                    answer="",
                    containers=[
                        legacy.container("a", "alpha"),
                        legacy.container("b", "other", state="running"),
                    ],
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(changes, [])
                self.assertNotIn("(y/N)", result.stdout)
                self.assertEqual(self.state.read_bytes(), before)

    def test_group_or_later_member_decline_cancels_before_any_changes(self):
        self.register("alpha")
        self.register("beta")
        self.register("other")
        self.group("dev", "alpha", "beta")
        before = self.state.read_bytes()
        for command, answers in (
            ("switch --group dev", ("", "n\n", "y\ny\nn\n")),
            ("up --group dev", ("", "y\nn\n")),
            ("down --group dev", ("", "n\n")),
        ):
            for answer in answers:
                result, changes, _ = self.cli(
                    command,
                    answer=answer,
                    containers=[
                        legacy.container("a", "alpha", state="running"),
                        legacy.container("b", "beta"),
                        legacy.container("c", "other", state="running"),
                    ],
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(changes, [])
                self.assertIn("Cancelled", result.stdout)
                self.assertEqual(self.state.read_bytes(), before)

    def test_later_missing_directory_drift_or_preflight_failure_blocks_group_switch(self):
        self.register("alpha")
        beta = self.register("beta")
        self.register("other")
        self.group("dev", "alpha", "beta")
        containers = [
            legacy.container("a", "alpha"),
            legacy.container("b", "beta"),
            legacy.container("c", "other", state="running"),
        ]
        before = self.state.read_bytes()
        (beta / "dwork.yml").write_text(
            json.dumps(
                {
                    "version": 1,
                    "terminals": [{"command": ["unavailable-dwork-group-test"], "window": "none"}],
                }
            )
        )
        result, changes, _ = self.cli("switch --group dev", containers=containers)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(changes, [])
        self.assertIn("Terminal command is unavailable", result.stderr)
        self.fixture.fixture.model(beta, "changed")
        result, changes, _ = self.cli("switch --group dev", containers=containers)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(changes, [])
        self.assertIn("changed since registration", result.stderr)
        beta.rename(beta.with_name("moved"))
        result, changes, calls = self.cli("switch --group dev", containers=containers)
        self.assertEqual(result.returncode, 1)
        self.assertEqual((changes, calls), ([], []))
        self.assertEqual(self.state.read_bytes(), before)

    def test_host_only_group_needs_no_docker_and_keeps_task_browser_consent(self):
        config = {
            "confirm": False,
            "terminals": [{"command": ["echo", "test"], "window": "none"}],
            "browsers": [{"url": "http://localhost:3000", "wait_for": False}],
        }
        self.register("alpha", enabled=False, config=config)
        self.register("beta", enabled=False, config=config)
        self.group("dev", "alpha", "beta")
        with (
            patch("builtins.input", side_effect=["y", "n", "n", "n", "n"]) as consent,
            patch.object(dwork_terminals, "open_terminal") as terminal,
            patch.object(dwork_browsers, "open_browser") as browser,
            patch.object(
                dwork_browsers,
                "preflight_browsers",
                return_value=[BrowserLaunch(("fake-browser",), False)],
            ),
            patch.object(dwork_docker, "docker_target") as target,
            patch.object(dwork_docker, "inventory") as inventory,
            patch.dict(os.environ, {"XDG_STATE_HOME": str(self.fixture.fixture.base / "state")}),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            dwork_workspaces.switch_registered_group(
                self.fixture.entries(), ["alpha", "beta"], "dev", False
            )
        self.assertEqual(consent.call_count, 5)
        self.assertIn("group dev", consent.call_args_list[0].args[0])
        self.assertTrue(
            all("Apply the listed" not in call.args[0] for call in consent.call_args_list)
        )
        terminal.assert_not_called()
        browser.assert_not_called()
        target.assert_not_called()
        inventory.assert_not_called()

    def test_switch_retains_member_context_ownership_order_and_restores_after_failure(self):
        config = {
            "confirm": False,
            "terminals": [{"command": ["echo", "test"], "window": "none", "confirm": False}],
            "browsers": [{"url": "http://localhost:3000", "wait_for": False, "confirm": False}],
        }
        alpha = self.register("alpha", enabled=False, config=config, COMPOSE_PROFILES="first")
        beta = self.register("beta", enabled=False, config=config, COMPOSE_PROFILES="second")
        self.group("dev", "alpha", "beta")
        observed = []

        def terminal(task, *, launch):
            observed.append(
                ("terminal", Path.cwd(), os.environ.get("COMPOSE_PROFILES"), task.workspace)
            )
            return 123

        def browser(task, *, launch):
            observed.append(("browser", Path.cwd(), os.environ.get("COMPOSE_PROFILES")))
            if Path.cwd() == beta:
                raise dwork_common.DworkError("group browser failure")

        original = Path.cwd()
        original_profile = os.environ.get("COMPOSE_PROFILES")
        with (
            patch("builtins.input", return_value="y"),
            patch.object(dwork_terminals, "open_terminal", side_effect=terminal),
            patch.object(dwork_browsers, "open_browser", side_effect=browser),
            patch.object(
                dwork_browsers,
                "preflight_browsers",
                return_value=[BrowserLaunch(("fake-browser",), False)],
            ),
            patch.dict(os.environ, {"XDG_STATE_HOME": str(self.fixture.fixture.base / "state")}),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()) as errors,
        ):
            with self.assertRaisesRegex(dwork_common.DworkError, "group browser failure"):
                dwork_workspaces.switch_registered_group(
                    self.fixture.entries(), ["alpha", "beta"], "dev", False
                )
        self.assertEqual(
            observed,
            [
                ("terminal", alpha, "first", str(alpha)),
                ("terminal", beta, "second", str(beta)),
                ("browser", alpha, "first"),
                ("browser", beta, "second"),
            ],
        )
        self.assertEqual(Path.cwd(), original)
        self.assertEqual(os.environ.get("COMPOSE_PROFILES"), original_profile)
        self.assertIn("No automatic rollback", errors.getvalue())
        self.assertIn("switch --group dev --dry-run", errors.getvalue())

    def test_shutdown_lock_policy_is_rechecked_after_group_confirmation(self):
        self.register("alpha", config={"confirm": False})
        other = self.register("other")
        self.group("dev", "alpha")
        containers = [
            legacy.container("a", "alpha"),
            legacy.container("b", "other", state="running"),
        ]

        def consent(prompt):
            (other / "dwork.yml").write_text(json.dumps({"version": 1, "locked": True}))
            return "y"

        def docker(*args):
            self.assertEqual(args, ("start", "a"))
            return ""

        with (
            patch("builtins.input", side_effect=consent),
            patch.object(
                dwork_docker, "docker_target", return_value=self.fixture.entries()[0]["target"]
            ),
            patch.object(dwork_docker, "read_model", return_value=("alpha", {"web": {}, "db": {}})),
            patch.object(dwork_docker, "show_target"),
            patch.object(dwork_docker, "inventory", return_value=containers),
            patch.object(dwork_docker, "docker", side_effect=docker) as mutate,
            patch.dict(os.environ, {"XDG_STATE_HOME": str(self.fixture.fixture.base / "state")}),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            entries = self.fixture.entries()
            dwork_workspaces.switch_registered_group(entries, ["alpha"], "dev", False)
        self.assertEqual(mutate.call_count, 1)
        self.assertIn("now locked", output.getvalue())
        self.assertEqual(json.loads(self.state.read_text())["groups"], {"dev": ["alpha"]})

    def test_down_missing_member_directory_uses_saved_ownership(self):
        alpha = self.register("alpha")
        self.group("dev", "alpha")
        alpha.rename(alpha.with_name("moved"))
        result, changes, _ = self.cli(
            "down --group dev", containers=[legacy.container("a", "alpha", state="running")]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "a"]])

    def test_switch_keeps_selected_tracked_commands_and_stops_only_outgoing_owners(self):
        alpha = self.register("alpha", enabled=False, config={"confirm": False})
        beta = self.register("beta", enabled=False, config={"confirm": False})
        outgoing = self.register("outgoing", enabled=False)
        self.group("dev", "alpha", "beta")
        records = [
            {
                "workspace": str(directory),
                "directory": str(directory),
                "project": directory.name,
                "title": directory.name,
                "pid": index,
                "command": ["echo", directory.name],
            }
            for index, directory in enumerate((alpha, beta, outgoing), 1)
        ]
        with (
            patch("builtins.input", return_value="y"),
            patch.object(dwork_tasks, "running", return_value=records),
            patch.object(dwork_tasks, "stop", return_value=True) as stop,
            patch.dict(os.environ, {"XDG_STATE_HOME": str(self.fixture.fixture.base / "state")}),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            dwork_workspaces.switch_registered_group(
                self.fixture.entries(), ["alpha", "beta"], "dev", False
            )
        stop.assert_called_once_with(records[2], self.state.parent)

    def test_shutdown_failure_blocks_every_destination_and_reports_combined_recovery(self):
        for name in ("alpha", "beta", "outgoing"):
            self.register(name, config={"confirm": False})
        self.group("dev", "alpha", "beta")
        containers = [
            legacy.container("a", "alpha"),
            legacy.container("b", "beta"),
            legacy.container("c", "outgoing", state="running"),
        ]

        def mutate(*args):
            if args[0] == "stop":
                raise dwork_common.DworkError("simulated stop failure")
            self.fail("No destination may start after failed outgoing shutdown")

        with (
            patch("builtins.input", return_value="y"),
            patch.object(
                dwork_docker,
                "read_model",
                side_effect=lambda directory, options: (
                    Path(directory).name,
                    {"web": {}, "db": {}},
                ),
            ),
            patch.object(
                dwork_docker, "docker_target", return_value=self.fixture.entries()[0]["target"]
            ),
            patch.object(dwork_docker, "inventory", return_value=containers),
            patch.object(dwork_docker, "show_target"),
            patch.object(dwork_docker, "docker", side_effect=mutate) as docker,
            patch.dict(os.environ, {"XDG_STATE_HOME": str(self.fixture.fixture.base / "state")}),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()) as errors,
        ):
            with self.assertRaisesRegex(dwork_common.DworkError, "simulated stop failure"):
                dwork_workspaces.switch_registered_group(
                    self.fixture.entries(), ["alpha", "beta"], "dev", False
                )
        docker.assert_called_once_with("stop", "c")
        self.assertIn("start a", errors.getvalue())
        self.assertIn("start b", errors.getvalue())
        self.assertIn("switch --group dev --dry-run", errors.getvalue())

    def test_existing_discovered_bundle_remains_one_member_with_its_own_confirmation(self):
        parent = self.fixture.root / "bundle"
        self.fixture.fixture.model(parent / "api", "api")
        self.fixture.fixture.model(parent / "web", "web")
        result, _, _ = self.cli("register bundle", cwd=parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.register("peer", enabled=False, config={"confirm": False})
        self.group("dev", "bundle", "peer")
        containers = [legacy.container("a", "api"), legacy.container("b", "web")]
        result, changes, _ = self.cli(
            "switch --group dev", answer="y\ny\nn\n", containers=containers
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        self.assertIn("Start all listed projects in bundle together?", result.stdout)
        self.assertIn("Cancelled", result.stdout)
        result, changes, _ = self.cli("switch --group dev", containers=containers)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["start", "a"], ["start", "b"]])

    def test_health_failure_or_interrupt_follows_all_member_starts_and_blocks_launches(self):
        self.register(
            "alpha",
            config={
                "confirm": False,
                "terminals": [
                    {"command": ["echo", "test"], "window": "none", "wait_for": {"healthy": ["db"]}}
                ],
            },
        )
        self.register("beta", config={"confirm": False})
        self.register("outgoing")
        self.group("dev", "alpha", "beta")
        containers = [
            legacy.container("a", "alpha", "db"),
            legacy.container("b", "beta"),
            legacy.container("c", "outgoing", state="running"),
        ]
        for failure in (dwork_common.DworkError("health timeout"), KeyboardInterrupt()):
            with (
                self.subTest(failure=type(failure).__name__),
                patch("builtins.input", return_value="y"),
                patch.object(
                    dwork_docker,
                    "read_model",
                    side_effect=lambda directory, options: (
                        Path(directory).name,
                        {"web": {}, "db": {}},
                    ),
                ),
                patch.object(
                    dwork_docker, "docker_target", return_value=self.fixture.entries()[0]["target"]
                ),
                patch.object(dwork_docker, "inventory", return_value=containers),
                patch.object(dwork_docker, "show_target"),
                patch.object(dwork_docker, "docker", return_value="") as docker,
                patch.object(dwork_docker, "wait_healthy", side_effect=failure),
                patch.object(dwork_terminals, "open_terminal") as terminal,
                patch.dict(
                    os.environ, {"XDG_STATE_HOME": str(self.fixture.fixture.base / "state")}
                ),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()) as errors,
            ):
                with self.assertRaises(type(failure)):
                    dwork_workspaces.switch_registered_group(
                        self.fixture.entries(), ["alpha", "beta"], "dev", False
                    )
            self.assertEqual(
                [call.args for call in docker.call_args_list],
                [("stop", "c"), ("start", "a"), ("start", "b")],
            )
            terminal.assert_not_called()
            self.assertIn("Completed: stop c", errors.getvalue())
            self.assertIn("start b", errors.getvalue())
            self.assertIn("Not confirmed complete: wait for healthy a", errors.getvalue())
            self.assertIn("switch --group dev --dry-run", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
