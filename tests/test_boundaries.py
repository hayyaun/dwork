"""Regression checks for parsing, persistence/policy, and prepared launch boundaries."""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from dwork_common import BrowserTask, DworkError, TerminalTask, Workspace
from dwork_config_parse import decode_config, parse_config
from dwork_launch import BrowserLaunch, TerminalLaunch
from dwork_plans import ShutdownPlan, build_activation_plan
import dwork_browsers
import dwork_browser_launch
import dwork_config
import dwork_docker
import dwork_registry
import dwork_registry_policy as policy
import dwork_registry_store as store
import dwork_tasks
import dwork_terminals
import dwork_terminal_launch
import dwork_workspaces


class ConfigurationBoundaryTests(unittest.TestCase):
    def test_parsing_is_data_only_and_does_not_share_mutable_input(self):
        raw = {"version": 1, "compose": {"files": ["compose.dev.yml"], "services": ["db"]},
               "terminals": [{"command": ["echo", "hello world"], "cwd": "unresolved",
                              "wait_for": {"healthy": ["db"]}}],
               "browsers": [{"url": "http://localhost:3000"}]}
        with patch.object(Path, "resolve", side_effect=AssertionError("filesystem")), \
                patch.object(Path, "is_dir", side_effect=AssertionError("filesystem")), \
                patch.object(dwork_docker, "read_model", side_effect=AssertionError("Compose")), \
                patch.object(subprocess, "run", side_effect=AssertionError("process")), \
                patch.object(dwork_browsers, "http_status", side_effect=AssertionError("HTTP")):
            parsed = parse_config(raw)
        raw["terminals"][0]["command"].append("changed")
        self.assertEqual(parsed.terminals[0].command, ("echo", "hello world"))
        self.assertEqual(parsed.terminals[0].cwd, "unresolved")
        self.assertIsNone(parsed.terminals[0].title)
        self.assertTrue(parsed.confirm)
        self.assertTrue(parsed.terminals[0].confirm)
        self.assertEqual(parsed.terminals[0].timeout, 180)
        self.assertEqual(parsed.browsers[0].wait_url, "http://localhost:3000")
        self.assertEqual(parsed.browsers[0].timeout, 60)
        with self.assertRaises(FrozenInstanceError):
            parsed.confirm = False

    def test_decoder_and_parser_keep_strict_rules_without_docker(self):
        invalid = ["version: 1\nversion: 1", "version: true", "version: 1\nconfirm: 'false'",
                   "version: 1\nunknown: true", "version: 1\ncompose: {enabled: false, files: [x]}",
                   "version: 1\nterminals: [{command: [echo], title: null}]",
                   "version: 1\nterminals: [{command: [echo], wait_for: {timeout: .inf}}]",
                   "version: 1\nbrowsers: [{url: 'file:///tmp/page'}]"]
        with patch.object(dwork_docker, "read_model", side_effect=AssertionError("Compose")):
            for text in invalid:
                with self.subTest(text=text), self.assertRaises(DworkError):
                    parse_config(decode_config(text))

    def test_resolution_preserves_compose_precedence_paths_and_late_defaults(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            caller = root / "caller"
            caller.mkdir()
            (root / "task").mkdir()
            config = parse_config({"version": 1, "compose": {"files": ["compose.yml"], "services": ["db"]},
                "terminals": [{"command": ["echo", "ready"], "cwd": "task", "wait_for": {"healthy": ["db"]}}]})
            cases = [((), "", ["-f", str(root / "compose.yml")]),
                     (("--file=explicit.yml",), "", ["--file=explicit.yml"]),
                     ((), "from-env.yml", [])]
            for options, environment, expected in cases:
                with self.subTest(options=options, environment=environment), \
                        patch.dict(os.environ, {"COMPOSE_FILE": environment}), \
                        patch.object(dwork_docker, "read_model", return_value=("resolved-project", {"db": {}})) as model:
                    workspace = dwork_config.resolve_workspace(config, root, options, compose_directory=caller)
                model.assert_called_once_with(caller, expected)
                self.assertEqual(workspace.terminals[0].title, "dwork: resolved-project")
                self.assertEqual(workspace.terminals[0].cwd, root / "task")
                workspace.selected.append("changed")
                workspace.terminals[0].command.append("changed")
            self.assertEqual(config.selected, ("db",))
            self.assertEqual(config.terminals[0].command, ("echo", "ready"))

    def test_resolution_keeps_service_directory_and_separator_restrictions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = [({"compose": {"services": ["missing"]}}, "unknown service"),
                     ({"terminals": [{"command": ["echo"], "cwd": "missing"}]}, "directory does not exist"),
                     ({"terminals": [{"command": ["echo"], "wait_for": {"healthy": ["missing"]}}]}, "Health prerequisites"),
                     ({"compose": {"services": ["db"]}, "terminals": [{"command": ["echo"], "wait_for": {"healthy": ["web"]}}]}, "included in compose.services"),
                     ({"terminals": [{"command": ["echo", "a;b"]}]}, "semicolon separators")]
            for extra, message in cases:
                with self.subTest(extra=extra), \
                        patch.object(dwork_docker, "read_model", return_value=("app", {"db": {}, "web": {}})), \
                        self.assertRaisesRegex(DworkError, message):
                    dwork_config.resolve_workspace(parse_config({"version": 1, **extra}), root)
            host = parse_config({"version": 1, "compose": {"enabled": False}})
            with self.assertRaisesRegex(DworkError, "CLI options are not allowed"):
                dwork_config.resolve_workspace(host, root, ["-f", "compose.yml"])


class RegistryBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        environment = patch.dict(os.environ, {"XDG_STATE_HOME": str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)
        self.target = {"context": "default", "daemon": "daemon"}
        self.entry = {"name": "owner", "path": str(self.root / "workspace"), "options": [],
            "environment": {}, "target": self.target, "members": [{"project": "app",
                "directory": str(self.root / "workspace"), "enabled": True, "locked": False,
                "services": ["db"]}]}

    def test_storage_round_trip_is_independent_of_live_policy_and_ownership(self):
        with patch.object(policy, "check_ownership", side_effect=AssertionError("policy")), \
                patch.object(dwork_registry, "refresh_locks", side_effect=AssertionError("live config")):
            self.assertEqual(store.read_registry(), [])
            self.assertFalse(store.registry_path().parent.exists())
            with store.registry_lock():
                store.save_registry([self.entry])
            self.assertEqual(store.read_registry(), [self.entry])
            self.assertEqual(json.loads(store.registry_path().read_text())["version"], 1)
        self.assertEqual(dwork_registry.read_registry(), [self.entry])

    def test_failed_atomic_replace_keeps_previous_file_and_cleans_temporary(self):
        with store.registry_lock():
            store.save_registry([self.entry])
            previous = store.registry_path().read_bytes()
            before = set(store.registry_path().parent.iterdir())
            with patch.object(Path, "replace", side_effect=OSError("replacement failed")), \
                    self.assertRaisesRegex(OSError, "replacement failed"):
                store.save_registry([])
            self.assertEqual(store.registry_path().read_bytes(), previous)
            self.assertEqual(set(store.registry_path().parent.iterdir()), before)

    def test_pure_policy_retains_target_service_locks_and_identity_rules(self):
        entries = [self.entry]
        record = {"workspace": self.entry["path"], "directory": self.entry["members"][0]["directory"],
                  "project": "app"}
        original = deepcopy(entries)
        with patch.object(Path, "is_dir", side_effect=AssertionError("filesystem")), \
                patch.object(store, "read_registry", side_effect=AssertionError("storage")), \
                patch.object(dwork_docker, "inventory", side_effect=AssertionError("Docker")):
            self.assertEqual(policy.registered_services(entries, self.target), {"app": ["db"]})
            self.assertEqual(policy.registered_services(entries, {"context": "other", "daemon": "other"}), {})
            self.assertIsNone(policy.task_protection(record, entries, set()))
            self.assertEqual(policy.task_protection(record, entries, {"app"}), "DWORK_KEEP_PROJECTS")
            self.assertEqual(policy.task_protection({**record, "workspace": "/forgotten"}, entries, set()), "workspace no longer registered")
            self.assertEqual(policy.task_protection({**record, "directory": "/changed"}, entries, set()), "workspace ownership changed")
            for field, expected in (("locked", "locked"), ("temporary_locked", "temporarily locked")):
                protected = deepcopy(entries)
                location = protected[0]["members"][0] if field == "locked" else protected[0]
                location[field] = True
                self.assertEqual(policy.registered_services(protected, self.target), {})
                self.assertEqual(policy.locked_projects(protected, self.target), ["app"])
                self.assertEqual(policy.task_protection(record, protected, set()), expected)
        self.assertEqual(entries, original)

    def test_conflicts_are_target_scoped_and_host_tasks_keep_ownership(self):
        candidate = deepcopy(self.entry)
        candidate["path"] = str(self.root / "other")
        with self.assertRaisesRegex(DworkError, "already registered"):
            policy.check_ownership([self.entry], candidate)
        candidate["target"] = {"context": "other", "daemon": "other"}
        policy.check_ownership([self.entry], candidate)
        policy.check_ownership([self.entry], self.entry)
        host = deepcopy(self.entry)
        host["target"] = None
        host["members"][0]["enabled"] = False
        self.assertEqual(policy.registered_services([host], None), {})
        record = {"workspace": host["path"], "directory": host["members"][0]["directory"], "project": "app"}
        self.assertIsNone(policy.task_protection(record, [host], set()))
        with self.assertRaisesRegex(DworkError, "Ambiguous"):
            policy.registered_services([self.entry, deepcopy(self.entry)], self.target)


class LaunchBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("/workspace with spaces")
        self.task = TerminalTask("Worker 'title'", ["echo", "hello world", "$(literal)"], self.root,
            workspace=str(self.root), directory=str(self.root), project="app")
        self.browser = BrowserTask("http://localhost:3000/?query=a&b=c", None)

    def preparation_environment(self, stack, platform, wsl=""):
        stack.enter_context(patch.object(sys, "platform", platform))
        stack.enter_context(patch.dict(os.environ, {"SHELL": "/bin/bash", "WSL_DISTRO_NAME": wsl,
            "DISPLAY": ":test", "WAYLAND_DISPLAY": "", "DWORK_TERMINAL": "auto", "XDG_CURRENT_DESKTOP": ""}))
        stack.enter_context(patch.object(shutil, "which", side_effect=lambda name: "/bin/" + Path(name).name))
        stack.enter_context(patch.object(dwork_tasks, "require_support"))

    def test_terminal_preflight_carries_exact_owned_command_to_dispatch(self):
        cases = [("linux", "", "new", "gnome-terminal"), ("linux", "", "none", "background"),
                 ("darwin", "", "new", "apple-terminal"), ("linux", "Ubuntu", "new", "windows-terminal")]
        for platform, wsl, window, expected in cases:
            task = replace(self.task, window=window)
            with self.subTest(launcher=expected), ExitStack() as stack:
                self.preparation_environment(stack, platform, wsl)
                probe = stack.enter_context(patch.object(dwork_terminal_launch, "run_command"))
                run = stack.enter_context(patch.object(subprocess, "run", return_value=Mock(returncode=0)))
                popen = stack.enter_context(patch.object(subprocess, "Popen", return_value=Mock(pid=42)))
                popen.return_value.wait.side_effect = subprocess.TimeoutExpired("launcher", .2)
                prepared, = dwork_terminals.preflight_terminals([task])
                run.assert_not_called()
                popen.assert_not_called()
                self.assertEqual(probe.call_count, int(expected == "windows-terminal"))
                self.assertEqual(prepared.launcher, expected)
                with patch.object(dwork_terminals, "prepare_terminal", side_effect=AssertionError("reprepare")), \
                        patch.object(shutil, "which", side_effect=AssertionError("reresolve")), \
                        patch.dict(os.environ, {"WSL_DISTRO_NAME": "changed", "SHELL": "invalid", "DWORK_TERMINAL": "invalid"}), \
                        patch.object(sys, "platform", "unsupported"), \
                        patch.object(dwork_terminals, "run_command") as dispatch:
                    dwork_terminals.open_terminal(task, launch=prepared)
                actual = dispatch if expected == "windows-terminal" else run if expected == "apple-terminal" else popen
                self.assertEqual(actual.call_args.args[0], list(prepared.arguments))
                if expected in ("background", "gnome-terminal"):
                    self.assertEqual(popen.call_args.kwargs["cwd"], self.root)
                if expected == "background":
                    payload = json.loads(base64.urlsafe_b64decode(prepared.arguments[-1]))
                    self.assertEqual((payload["workspace"], payload["directory"], payload["project"]),
                                     (str(self.root), str(self.root), "app"))
                    self.assertEqual(payload["command"], self.task.command)

    def test_browser_preflight_carries_opener_and_transport_without_http(self):
        cases = [("linux", "", "default", False), ("linux", "", "firefox", False),
                 ("darwin", "", "Firefox", True), ("linux", "Ubuntu", "default", True),
                 ("linux", "Ubuntu", "firefox.exe", True)]
        for platform, wsl, browser, waited in cases:
            task = replace(self.browser, browser=browser)
            with self.subTest(platform=platform, wsl=wsl, browser=browser), ExitStack() as stack:
                self.preparation_environment(stack, platform, wsl)
                run = stack.enter_context(patch.object(subprocess, "run", return_value=Mock(returncode=0)))
                popen = stack.enter_context(patch.object(subprocess, "Popen"))
                popen.return_value.wait.side_effect = subprocess.TimeoutExpired("browser", .2)
                request = stack.enter_context(patch.object(dwork_browsers, "http_status"))
                prepared, = dwork_browsers.preflight_browsers([task])
                run.assert_not_called()
                popen.assert_not_called()
                request.assert_not_called()
                self.assertEqual(prepared.wait_for_dispatch, waited)
                with patch.object(dwork_browsers, "prepare_browser", side_effect=AssertionError("reprepare")), \
                        patch.object(shutil, "which", side_effect=AssertionError("reresolve")), \
                        patch.dict(os.environ, {"WSL_DISTRO_NAME": "changed"}), \
                        patch.object(sys, "platform", "unsupported"):
                    dwork_browsers.open_browser(task, launch=prepared)
                actual, unused = (run, popen) if waited else (popen, run)
                self.assertEqual(actual.call_args.args[0], list(prepared.arguments))
                unused.assert_not_called()
                request.assert_not_called()

    def test_preparation_keeps_parent_path_policy_and_single_windows_probe(self):
        with ExitStack() as stack:
            self.preparation_environment(stack, "linux", "Ubuntu")
            probe = stack.enter_context(patch.object(dwork_terminal_launch, "run_command"))
            self.assertEqual(len(dwork_terminals.preflight_terminals([self.task, replace(self.task, title="Second")])), 2)
            probe.assert_called_once()
            with patch.object(shutil, "which", side_effect=lambda name: None if name == "unavailable" else "/bin/" + Path(name).name):
                with self.assertRaisesRegex(DworkError, "Terminal command is unavailable"):
                    dwork_terminals.preflight_terminals([replace(self.task, command=["unavailable"])])
            probe.assert_called_once()

    def test_prepared_actions_still_require_separate_consent(self):
        workspace = Workspace("app", self.root, {}, enabled=False, terminals=[self.task], browsers=[self.browser])
        plan = build_activation_plan(self.root, [workspace], [], ShutdownPlan([], [], []), preview=False)
        terminal = TerminalLaunch(("fake-terminal",), self.root, "gnome-terminal", self.task.title)
        browser = BrowserLaunch(("fake-browser",), False)
        with patch.object(dwork_terminals, "preflight_terminals", return_value=(terminal,)), \
                patch.object(dwork_browsers, "preflight_browsers", return_value=(browser,)):
            prepared = dwork_workspaces.prepare_launches(plan)
        self.assertIsNone(plan.terminals[0].launch)
        self.assertEqual(prepared.terminals[0].launch, terminal)
        with patch("builtins.input", side_effect=["n", "n"]) as consent, \
                patch.object(dwork_terminals, "open_terminal") as task_open, \
                patch.object(dwork_browsers, "open_browser") as browser_open, \
                patch.object(dwork_browsers, "wait_ready") as ready, redirect_stdout(StringIO()):
            result = dwork_workspaces.execute_activation(prepared, [])
        self.assertEqual(consent.call_count, 2)
        self.assertEqual([item.status.value for item in result.results], ["skipped", "skipped"])
        task_open.assert_not_called()
        browser_open.assert_not_called()
        ready.assert_not_called()


if __name__ == "__main__":
    unittest.main()
