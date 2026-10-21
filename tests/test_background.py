"""Detached task launch: no GUI dependency, explicit consent, and preserved health gates."""

from pathlib import Path
from unittest.mock import Mock, patch
import json
import os
import subprocess
import sys
import unittest

import test_dwork as legacy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import dwork_common
import dwork_terminals
import dwork_terminal_launch


class BackgroundTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.task = dwork_common.TerminalTask(
            "Worker", ["echo", "hello world", "$(not-a-command)"], self.root, window="none"
        )

    def test_preflight_ignores_graphical_and_launcher_dependencies(self):
        with (
            patch.dict(
                os.environ,
                {
                    "SHELL": "/bin/bash",
                    "DWORK_TERMINAL": "invalid",
                    "DISPLAY": "",
                    "WAYLAND_DISPLAY": "",
                },
            ),
            patch.object(
                dwork_terminals,
                "choose_launcher",
                side_effect=AssertionError("must not choose GUI"),
            ),
        ):
            dwork_terminals.preflight_terminals([self.task])

    def test_detached_flags_quoting_and_immediate_failure(self):
        process = Mock(pid=4321)
        process.wait.side_effect = subprocess.TimeoutExpired("worker", 0.2)
        with (
            patch.object(dwork_terminal_launch, "command_shell", return_value="/bin/bash"),
            patch.object(subprocess, "Popen", return_value=process) as launch,
        ):
            self.assertEqual(dwork_terminals.open_terminal(self.task), 4321)
            self.assertEqual(
                launch.call_args.args[0],
                ["/bin/bash", "-lc", "exec echo 'hello world' '$(not-a-command)'"],
            )
            self.assertTrue(launch.call_args.kwargs["start_new_session"])
            self.assertEqual(launch.call_args.kwargs["cwd"], self.root)
            for stream in ("stdin", "stdout", "stderr"):
                self.assertEqual(launch.call_args.kwargs[stream], subprocess.DEVNULL)
            process.wait.side_effect = None
            process.wait.return_value = 7
            with self.assertRaisesRegex(dwork_common.DworkError, "exited immediately"):
                dwork_terminals.open_terminal(self.task)

    def test_real_harmless_child_runs_in_its_own_session_and_survives_dispatch(self):
        # Avoid personal login hooks while testing the process/session behavior.
        shell = self.fixture.bin / "bash"
        shell.write_text(
            "#!"
            + sys.executable
            + "\nimport os,sys\nos.execv('/bin/bash', ['bash', '--noprofile', '--norc', '-c', sys.argv[2]])\n"
        )
        shell.chmod(0o755)
        output = self.root / "child.json"
        code = (
            "import json,os,time; from pathlib import Path; Path("
            + repr(str(output))
            + ").write_text("
            "json.dumps({'pid':os.getpid(),'sid':os.getsid(0),'stdin':os.isatty(0)})); time.sleep(0.8)"
        )
        task = dwork_common.TerminalTask(
            "Harmless test", [sys.executable, "-c", code], self.root, window="none"
        )
        processes = []
        real_launch = subprocess.Popen

        def launch(*args, **kwargs):
            process = real_launch(*args, **kwargs)
            processes.append(process)
            return process

        try:
            with (
                patch.object(dwork_terminal_launch, "command_shell", return_value=str(shell)),
                patch.object(subprocess, "Popen", side_effect=launch),
            ):
                pid = dwork_terminals.open_terminal(task)
            self.assertIsNone(processes[0].poll())
            self.assertEqual(processes[0].wait(timeout=5), 0)
            state = json.loads(output.read_text())
            self.assertEqual(state["pid"], pid)
            self.assertEqual(state["sid"], pid)
            self.assertFalse(state["stdin"])
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=5)

    def test_confirmation_is_not_bypassed(self):
        with patch("builtins.input", return_value="") as ask:
            self.assertFalse(dwork_terminals.confirm_terminal(self.task))
            self.assertIn("Run background task 'Worker'", ask.call_args.args[0])
        self.task.confirm = False
        with patch("builtins.input", side_effect=AssertionError("no prompt expected")):
            self.assertTrue(dwork_terminals.confirm_terminal(self.task))

    def test_preview_and_decline_do_not_launch_background_commands(self):
        marker = self.root / "should-not-exist"
        (self.root / "dwork.yml").write_text(
            json.dumps(
                {
                    "version": 1,
                    "compose": {"enabled": False},
                    "terminals": [
                        {"title": "Worker", "command": ["touch", str(marker)], "window": "none"}
                    ],
                }
            )
        )
        for args in ("--dry-run", ""):
            result, changes, calls = self.fixture.run_dwork("bash", args, SHELL="/bin/bash")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(changes, [])
            self.assertEqual(calls, [])
            self.assertFalse(marker.exists())
            self.assertIn(
                "Would run detached:" if args else "Skipped background task:", result.stdout
            )

    def test_health_failure_blocks_background_task(self):
        self.fixture.model(self.root, "main", services={"db": {}})
        marker = self.root / "should-not-exist"
        (self.root / "dwork.yml").write_text(
            json.dumps(
                {
                    "version": 1,
                    "terminals": [
                        {
                            "command": ["touch", str(marker)],
                            "window": "none",
                            "confirm": False,
                            "wait_for": {"healthy": ["db"]},
                        }
                    ],
                }
            )
        )
        item = legacy.container("a", "main", "db", "running")
        item["State"]["Health"] = {"Status": "unhealthy"}
        result, changes, _ = self.fixture.run_dwork("bash", containers=[item], SHELL="/bin/bash")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(changes, [])
        self.assertIn("unhealthy", result.stderr)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
