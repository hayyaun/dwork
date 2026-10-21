"""Lifecycle planning is data-only; execution preserves order and reports typed outcomes."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

import test_dwork as legacy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from dwork_common import BrowserTask, DworkError, TerminalTask, Workspace
from dwork_plans import (
    ActionStatus,
    ExecutionResult,
    LaunchTerminal,
    OpenBrowser,
    ShutdownPlan,
    StartContainer,
    StopContainers,
    StopTask,
    WaitHealthy,
    build_activation_plan,
)
import dwork_browsers
import dwork_docker
import dwork_registry
import dwork_tasks
import dwork_terminals
import dwork_workspaces


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("/workspace/selected")
        self.outgoing = Path("/workspace/outgoing")
        self.task = TerminalTask(
            "Worker", ["echo", "ready"], self.root, healthy=["db"], timeout=17, window="none"
        )
        self.browser = BrowserTask("http://localhost:3000", "http://localhost:3000/health")
        self.workspace = Workspace(
            "selected", self.root, {"db": {}}, terminals=[self.task], browsers=[self.browser]
        )
        self.record = {
            "socket": "/private/controller.sock",
            "token": "a" * 48,
            "workspace": str(self.outgoing),
            "directory": str(self.outgoing),
            "project": "outgoing",
            "title": "stop fake-container",
            "pid": 42,
            "command": ["echo", "outgoing"],
        }
        self.inventory = [
            legacy.container("db-id", "selected", "db"),
            legacy.container("old-id", "outgoing", state="running"),
        ]
        self.shutdown = ShutdownPlan([self.inventory[1]], [self.record], [])
        self.entries = [{"name": "outgoing", "path": str(self.outgoing)}]

    def plan(self, preview=False):
        return build_activation_plan(
            self.root, [self.workspace], self.inventory, self.shutdown, preview=preview
        )

    def execution_mocks(self, stack):
        operations = {
            "stop_task": (dwork_tasks, "stop", True),
            "docker": (dwork_docker, "docker", ""),
            "inventory": (dwork_docker, "inventory", self.inventory),
            "healthy": (dwork_docker, "wait_healthy", None),
            "confirm_terminal": (dwork_terminals, "confirm_terminal", True),
            "terminal": (dwork_terminals, "open_terminal", 123),
            "confirm_browser": (dwork_browsers, "confirm_browser", True),
            "ready": (dwork_browsers, "wait_ready", None),
            "browser": (dwork_browsers, "open_browser", None),
        }
        mocks = {
            name: stack.enter_context(patch.object(module, function, return_value=value))
            for name, (module, function, value) in operations.items()
        }
        stack.enter_context(redirect_stdout(StringIO()))
        mocks["stderr"] = stack.enter_context(redirect_stderr(StringIO()))
        return mocks

    def test_plan_is_a_snapshot_of_ordered_typed_actions_without_io(self):
        with (
            patch("builtins.input") as prompt,
            patch("subprocess.run") as run,
            patch("subprocess.Popen") as popen,
            patch.object(Path, "resolve", side_effect=AssertionError("unresolved paths")),
        ):
            plan = self.plan()
        prompt.assert_not_called()
        run.assert_not_called()
        popen.assert_not_called()
        self.assertEqual(
            [type(action) for action in plan.actions],
            [StopTask, StopContainers, StartContainer, WaitHealthy, LaunchTerminal, OpenBrowser],
        )
        self.assertEqual(plan.starts[0].container.identifier, "db-id")
        self.assertEqual(plan.gates[0].container_ids, ("db-id",))
        self.assertEqual(plan.gates[0].timeout, 17)
        task = plan.terminals[0].task
        self.assertEqual(
            (task.workspace, task.directory, task.project),
            (str(self.root), str(self.root), "selected"),
        )
        self.assertIsNone(self.task.workspace)
        self.task.command.append("changed")
        self.inventory[0]["Id"] = "changed"
        self.record["command"].append("changed")
        self.assertEqual(task.command, ["echo", "ready"])
        self.assertEqual(plan.inventory[0]["Id"], "db-id")
        self.assertEqual(plan.actions[0].record["command"], ["echo", "outgoing"])

    def test_missing_health_dependency_warns_in_preview_and_blocks_live_planning(self):
        self.inventory = []
        preview = self.plan(preview=True)
        self.assertTrue(
            any("Terminal launch would be blocked" in warning for warning in preview.warnings)
        )
        self.assertEqual(preview.gates, ())
        with self.assertRaisesRegex(DworkError, "Required healthy service selected/db"):
            self.plan()

    def test_start_selection_keeps_existing_service_and_exited_job_policy(self):
        self.workspace.terminals = []
        self.inventory = [
            legacy.container("db", "selected", "db"),
            legacy.container("old-job", "selected", "removed-service"),
            legacy.container("paused", "selected", "db", "paused"),
            legacy.container("unknown", "unregistered"),
        ]
        self.assertEqual(
            [action.container.identifier for action in self.plan().starts], ["db", "old-job"]
        )
        self.workspace.selected = ["db"]
        plan = self.plan()
        self.assertEqual([action.container.identifier for action in plan.starts], ["db"])
        self.assertTrue(any("paused" in warning for warning in plan.warnings))

    def test_post_confirmation_lock_recheck_replaces_only_shutdown_actions(self):
        target = {"context": "default", "daemon": "daemon"}
        entries = [
            {
                "name": "outgoing",
                "path": str(self.outgoing),
                "target": target,
                "members": [
                    {
                        "project": "outgoing",
                        "directory": str(self.outgoing),
                        "enabled": True,
                        "services": None,
                        "locked": False,
                    }
                ],
            }
        ]
        plan = self.plan()

        def lock(values):
            values[0]["members"][0]["locked"] = True
            return True

        with (
            patch.object(dwork_registry, "refresh_locks", side_effect=lock),
            redirect_stdout(StringIO()),
        ):
            allowed, changed = dwork_workspaces.recheck_shutdown(
                plan.shutdown, entries, target, set()
            )
        approved = replace(plan, shutdown=allowed)
        self.assertTrue(changed)
        self.assertTrue(any(isinstance(action, StopTask) for action in plan.actions))
        self.assertFalse(
            any(isinstance(action, (StopTask, StopContainers)) for action in approved.actions)
        )
        self.assertEqual(
            approved.actions, (*plan.starts, *plan.gates, *plan.terminals, *plan.browsers)
        )

    def test_executor_keeps_shutdown_start_health_task_and_browser_order(self):
        events = []
        with ExitStack() as stack:
            mocks = self.execution_mocks(stack)
            for name in ("stop_task", "healthy", "terminal", "ready", "browser"):
                value = mocks[name].return_value
                mocks[name].side_effect = lambda *args, name=name, value=value, **kwargs: (
                    events.append(name),
                    value,
                )[1]
            mocks["docker"].side_effect = lambda verb, *ids: events.append((verb, ids))
            mocks["confirm_terminal"].side_effect = lambda task: (
                events.append("confirm_terminal"),
                True,
            )[1]
            mocks["confirm_browser"].side_effect = lambda browser: (
                events.append("confirm_browser"),
                True,
            )[1]
            result = dwork_workspaces.execute_activation(self.plan(), self.entries)
        self.assertEqual(
            events,
            [
                "stop_task",
                ("stop", ("old-id",)),
                ("start", ("db-id",)),
                "healthy",
                "confirm_terminal",
                "terminal",
                "confirm_browser",
                "ready",
                "browser",
            ],
        )
        self.assertTrue(all(item.status is ActionStatus.COMPLETED for item in result.results))
        self.assertEqual(result.results[4].supervisor_pid, 123)
        self.assertEqual(result.pending, ())
        self.assertIsNone(result.current)

    def test_declined_actions_are_skipped_without_launching_or_probing(self):
        with ExitStack() as stack:
            mocks = self.execution_mocks(stack)
            mocks["confirm_terminal"].return_value = False
            mocks["confirm_browser"].return_value = False
            result = dwork_workspaces.execute_activation(self.plan(), self.entries)
            for name in ("terminal", "ready", "browser"):
                mocks[name].assert_not_called()
        self.assertEqual([item.status for item in result.results[-2:]], [ActionStatus.SKIPPED] * 2)
        self.assertEqual(len(result.completed), 4)
        self.assertEqual(result.pending, ())

    def test_failures_and_interruptions_record_current_action_and_leave_later_work_pending(self):
        for index, operation in enumerate(
            ("stop_task", "stop", "start", "healthy", "terminal", "ready")
        ):
            for exception in (DworkError("injected failure"), KeyboardInterrupt()):
                with (
                    self.subTest(operation=operation, exception=type(exception).__name__),
                    ExitStack() as stack,
                ):
                    mocks = self.execution_mocks(stack)
                    if operation in ("stop", "start"):

                        def docker(verb, *ids):
                            if verb == operation:
                                raise exception
                            return ""

                        mocks["docker"].side_effect = docker
                    else:
                        mocks[operation].side_effect = exception
                    plan = self.plan()
                    result = ExecutionResult(plan.actions)
                    with self.assertRaises(type(exception)):
                        dwork_workspaces.execute_activation(plan, self.entries, result=result)
                    expected = (
                        ActionStatus.INTERRUPTED
                        if isinstance(exception, KeyboardInterrupt)
                        else ActionStatus.FAILED
                    )
                    self.assertEqual(
                        [item.status for item in result.results],
                        [ActionStatus.COMPLETED] * index
                        + [expected]
                        + [ActionStatus.PENDING] * (5 - index),
                    )
                    self.assertIs(result.current, result.results[index])
                    if isinstance(exception, DworkError):
                        self.assertIn("injected failure", result.current.error)
                    if index < 4:
                        mocks["terminal"].assert_not_called()
                    if index < 5:
                        mocks["ready"].assert_not_called()
                    mocks["browser"].assert_not_called()

    def test_finished_tasks_and_opaque_labels_cannot_generate_container_recovery_commands(self):
        with ExitStack() as stack:
            mocks = self.execution_mocks(stack)
            mocks["stop_task"].return_value = False
            mocks["ready"].side_effect = DworkError("not ready")
            stack.enter_context(
                patch.object(dwork_workspaces, "action_label", return_value="opaque display text")
            )
            plan = self.plan()
            result = ExecutionResult(plan.actions)
            with self.assertRaisesRegex(DworkError, "not ready"):
                dwork_workspaces.execute_activation(plan, self.entries, result=result)
            self.assertEqual(result.results[0].status, ActionStatus.ALREADY_FINISHED)
            self.assertIn("Completed: finished task", mocks["stderr"].getvalue())
            self.assertIn("docker start old-id", mocks["stderr"].getvalue())
            self.assertNotIn("docker start fake-container", mocks["stderr"].getvalue())
            self.assertNotIn("docker start task", mocks["stderr"].getvalue())
            self.assertEqual(mocks["docker"].call_args_list[1].args, ("start", "db-id"))

    def test_used_results_cannot_replay_commands(self):
        with ExitStack() as stack:
            mocks = self.execution_mocks(stack)
            result = dwork_workspaces.execute_activation(self.plan(), self.entries)
            calls = mocks["docker"].call_count
            with self.assertRaisesRegex(ValueError, "already been used"):
                dwork_workspaces.execute_actions(result, self.entries, "Switch")
            self.assertEqual(mocks["docker"].call_count, calls)

    def test_all_health_gates_precede_every_terminal_confirmation(self):
        self.workspace.terminals.append(replace(self.task, title="Second", timeout=23))
        plan = self.plan()
        self.assertEqual(
            [type(action) for action in plan.actions],
            [
                StopTask,
                StopContainers,
                StartContainer,
                WaitHealthy,
                WaitHealthy,
                LaunchTerminal,
                LaunchTerminal,
                OpenBrowser,
            ],
        )
        events = []
        with ExitStack() as stack:
            mocks = self.execution_mocks(stack)
            mocks["healthy"].side_effect = lambda ids, timeout: events.append(("healthy", timeout))
            mocks["confirm_terminal"].side_effect = lambda task: (
                events.append(("confirm", task.title)),
                False,
            )[1]
            result = dwork_workspaces.execute_activation(plan, self.entries)
        self.assertEqual(
            events, [("healthy", 17), ("healthy", 23), ("confirm", "Worker"), ("confirm", "Second")]
        )
        self.assertEqual([item.status for item in result.results[5:7]], [ActionStatus.SKIPPED] * 2)


if __name__ == "__main__":
    unittest.main()
