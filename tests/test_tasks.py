"""Real harmless tasks, private controllers, and terminal foreground handoff."""

from pathlib import Path
from unittest.mock import patch
import contextlib
import faulthandler
import io
import json
import os
import select
import shutil
import signal
import subprocess
import sys
import time
import unittest

import test_dwork as legacy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import dwork_common
import dwork_docker
import dwork_registry
import dwork_tasks
import dwork_terminals
import dwork_workspaces


class TaskRuntimeTests(unittest.TestCase):
    def test_old_macos_python_fails_before_supervisor_changes_directory_or_spawns(self):
        with patch.object(sys, "platform", "darwin"), \
                patch.object(sys, "version_info", (3, 12)), \
                patch.object(os, "chdir") as chdir, patch.object(os, "posix_spawn") as spawn:
            with self.assertRaisesRegex(dwork_common.DworkError, "macOS require Python 3.13"):
                dwork_tasks.supervise({})
        chdir.assert_not_called()
        spawn.assert_not_called()

    def test_linux_minimum_and_supported_macos_python_are_accepted(self):
        for platform, version in (("linux", (3, 10)), ("darwin", (3, 13)), ("darwin", (3, 14))):
            with self.subTest(platform=platform, version=version), \
                    patch.object(sys, "platform", platform), patch.object(sys, "version_info", version):
                dwork_tasks.require_support()

    def test_old_macos_python_fails_before_building_task_arguments(self):
        with patch.object(sys, "platform", "darwin"), patch.object(sys, "version_info", (3, 12)):
            with self.assertRaisesRegex(dwork_common.DworkError, "reinstall dwork"):
                dwork_tasks.arguments(None, None, None)


class TaskTests(unittest.TestCase):
    def setUp(self):
        # A POSIX alarm reports blocked frames and terminates a hung test without
        # starting a watchdog thread before the real PTY tests call forkpty().
        previous_alarm = signal.signal(signal.SIGALRM, signal.SIG_DFL)
        faulthandler.register(signal.SIGALRM, chain=True)
        signal.alarm(30)
        def cancel_alarm():
            signal.alarm(0)
            faulthandler.unregister(signal.SIGALRM)
            signal.signal(signal.SIGALRM, previous_alarm)
        # Add first so it stays armed through process and PTY cleanup.
        self.addCleanup(cancel_alarm)
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.state = self.fixture.base / "state/dwork"
        self.shell = self.fixture.bin / "bash"
        self.shell.write_text("#!" + sys.executable + "\nimport os,sys\n"
            "if sys.argv[1] == '-il': os.execv('/bin/bash', ['bash','--noprofile','--norc','-i'])\n"
            "os.execv('/bin/bash', ['bash','--noprofile','--norc', '-ic' if sys.argv[1] == '-lic' else '-c',sys.argv[2]])\n")
        self.shell.chmod(0o755)
        self.env = dict(os.environ, XDG_STATE_HOME=str(self.fixture.base / "state"), SHELL=str(self.shell))
        self.patch_env = patch.dict(os.environ, self.env)
        self.patch_env.start()
        self.addCleanup(self.patch_env.stop)
        self.configure(False)
        result, _, _ = self.cli("register host")
        self.assertEqual(result.returncode, 0, result.stderr)

    def configure(self, locked):
        (self.root / "dwork.yml").write_text(json.dumps({"version": 1, "locked": locked,
                                                       "compose": {"enabled": False}}))

    def cli(self, args, **kwargs):
        return self.fixture.run_dwork("bash", args, register_current=False, SHELL=str(self.shell), **kwargs)

    def wait_for(self, predicate):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(.03)
        self.fail("Task did not reach expected state")

    def task(self, command=None, visible=False):
        return dwork_common.TerminalTask("Worker", command or [sys.executable, "-c", "import time; time.sleep(60)"],
            self.root, window="new" if visible else "none", workspace=str(self.root),
            directory=str(self.root), project=self.root.name)

    def launch(self, task=None):
        task = task or self.task()
        previous = {r["token"] for r in dwork_tasks.running(self.state)}
        process = subprocess.Popen(dwork_terminals.task_command(task), env=self.env, cwd=self.root,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        def cleanup():
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=8)
        self.addCleanup(cleanup)
        record = self.wait_for(lambda: [r for r in dwork_tasks.running(self.state)
                                       if r["token"] not in previous])[0]
        return process, record

    def test_group_keeper_joins_exited_command_and_survives_until_final_group_kill(self):
        child = os.posix_spawn(sys.executable,
            [sys.executable, "-c", "raise SystemExit(7)"], os.environ, setpgroup=0)
        owned = {child}
        control = None
        try:
            self.wait_for(lambda: os.waitid(os.P_PID, child,
                          os.WEXITED | os.WNOHANG | os.WNOWAIT))
            keeper, control = dwork_tasks.start_group_keeper(child)
            owned.add(keeper)
            # Reaping the real command must not release the owned group identity.
            _, status = os.waitpid(child, 0)
            owned.remove(child)
            self.assertEqual(os.waitstatus_to_exitcode(status), 7)
            self.assertEqual(os.getpgid(keeper), child)
            os.killpg(child, signal.SIGTERM)
            os.killpg(child, signal.SIGCONT)
            self.assertIsNone(os.waitid(os.P_PID, keeper,
                              os.WEXITED | os.WNOHANG | os.WNOWAIT))
            os.killpg(child, signal.SIGKILL)
            self.wait_for(lambda: os.waitid(os.P_PID, keeper,
                          os.WEXITED | os.WNOHANG | os.WNOWAIT))
            _, status = os.waitpid(keeper, 0)
            owned.remove(keeper)
            self.assertEqual(os.waitstatus_to_exitcode(status), -signal.SIGKILL)
        finally:
            if control is not None:
                os.close(control)
            for pid in owned:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.waitpid(pid, 0)

    def test_group_keeper_kills_task_when_supervisor_ownership_pipe_closes(self):
        marker = self.root / "group-child-ready"
        code = "import pathlib,time; pathlib.Path(" + repr(str(marker)) + ").touch(); time.sleep(60)"
        child = os.posix_spawn(sys.executable, [sys.executable, "-c", code],
                               os.environ, setpgroup=0)
        owned = {child}
        control = None
        try:
            keeper, control = dwork_tasks.start_group_keeper(child)
            owned.add(keeper)
            self.wait_for(marker.exists)
            os.close(control)
            control = None
            # The command cannot keep the supervisor's ownership writer open.
            for pid in (child, keeper):
                self.wait_for(lambda: os.waitid(os.P_PID, pid,
                              os.WEXITED | os.WNOHANG | os.WNOWAIT))
                _, status = os.waitpid(pid, 0)
                owned.remove(pid)
                self.assertEqual(os.waitstatus_to_exitcode(status), -signal.SIGKILL)
        finally:
            if control is not None:
                os.close(control)
            for pid in owned:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.waitpid(pid, 0)

    def test_group_keeper_kills_task_if_supervisor_exits_before_readiness_ack(self):
        child = os.posix_spawn(sys.executable,
            [sys.executable, "-c", "import time; time.sleep(60)"], os.environ, setpgroup=0)
        owned = {child}
        read_ack, write_ack = os.pipe()
        os.close(read_ack)
        try:
            # No ACK reader remains: the keeper must clean up even if its first
            # write fails before it can observe EOF on the ownership pipe.
            keeper = os.posix_spawn(sys.executable,
                [sys.executable, str(Path(dwork_tasks.__file__).resolve()), "--group-keeper"],
                os.environ, setpgroup=child, file_actions=[
                    (os.POSIX_SPAWN_OPEN, 0, os.devnull, os.O_RDONLY, 0),
                    (os.POSIX_SPAWN_DUP2, write_ack, 1),
                    (os.POSIX_SPAWN_CLOSE, write_ack)])
            owned.add(keeper)
            for pid in (child, keeper):
                self.wait_for(lambda: os.waitid(os.P_PID, pid,
                              os.WEXITED | os.WNOHANG | os.WNOWAIT))
                _, status = os.waitpid(pid, 0)
                owned.remove(pid)
                self.assertEqual(os.waitstatus_to_exitcode(status), -signal.SIGKILL)
        finally:
            os.close(write_ack)
            for pid in owned:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.waitpid(pid, 0)

    def test_cli_tracks_background_and_down_preview_decline_lock_rename_and_stop(self):
        # Exercise the actual launch path, including owner information assigned by dwork.
        config = {"version": 1, "compose": {"enabled": False}, "terminals": [{
            "title": "Worker", "command": [sys.executable, "-c", "__import__('time').sleep(60)"],
            "window": "none", "confirm": False}]}
        (self.root / "dwork.yml").write_text(json.dumps(config))
        result, _, _ = self.cli("", answer="y\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        record = self.wait_for(lambda: dwork_tasks.running(self.state))[0]
        def cleanup():
            try:
                dwork_tasks.request(record, "stop")
            except (OSError, ValueError):
                pass
        self.addCleanup(cleanup)
        before = {p: p.read_bytes() for p in self.state.rglob("*.json")}
        for args, answer in (("down --dry-run", ""), ("down", "n\n"), ("down", "")):
            result, changes, calls = self.cli(args, answer=answer)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Would stop task: host/Worker", result.stdout)
            self.assertEqual(changes, [])
            self.assertEqual(calls, [])
            self.assertEqual({p: p.read_bytes() for p in self.state.rglob("*.json")}, before)
            self.assertEqual(dwork_tasks.request(record, "status")["state"], "running")
        self.configure(True)
        result, _, _ = self.cli("down", answer="y\n")
        self.assertIn("Keep task (locked): host/Worker", result.stdout)
        self.assertNotIn("(y/N)", result.stdout)
        self.assertEqual(dwork_tasks.request(record, "status")["state"], "running")
        self.configure(False)
        self.cli("rename host renamed")
        result, _, calls = self.cli("down", answer="y\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Stopped task: renamed/Worker", result.stdout)
        self.assertEqual(calls, [])
        self.wait_for(lambda: not list((self.state / "tasks").glob("*.json")))

    def test_process_group_stops_descendants_and_preserves_unrelated_process(self):
        marker = self.root / "child-stopped"
        child = ("import signal,time,pathlib; "
                 "signal.signal(signal.SIGTERM, lambda *_: (pathlib.Path(" + repr(str(marker))
                 + ").write_text('stopped'), exit(0))); print('ready',flush=True); time.sleep(60)")
        parent = ("import subprocess,signal,time,sys; "
                  "p=subprocess.Popen([sys.executable,'-c'," + repr(child) + "],stdout=subprocess.PIPE); "
                  "p.stdout.readline(); signal.signal(signal.SIGTERM,lambda *_: (p.wait(),exit(0))); time.sleep(60)")
        process, record = self.launch(self.task([sys.executable, "-c", parent]))
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(lambda: (unrelated.terminate(), unrelated.wait(timeout=5)))
        # Parent installs its handler after its child is ready.
        time.sleep(.2)
        result, _, _ = self.cli("down", answer="y\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(process.wait(timeout=6), 0)
        self.assertEqual(marker.read_text(), "stopped")
        self.assertIsNone(unrelated.poll())

    def test_keep_projects_and_forgotten_workspaces_leave_tasks_running(self):
        process, record = self.launch()
        result, _, _ = self.cli("down", answer="y\n", DWORK_KEEP_PROJECTS=self.root.name)
        self.assertIn("Keep task (DWORK_KEEP_PROJECTS)", result.stdout)
        self.cli("forget host")
        result, _, _ = self.cli("down", answer="y\n")
        self.assertIn("workspace no longer registered", result.stdout)
        self.assertIsNone(process.poll())
        self.assertEqual(dwork_tasks.request(record, "status")["state"], "running")

    def test_combined_plan_stops_tasks_before_registered_containers(self):
        (self.root / "dwork.yml").write_text("version: 1\n")
        self.fixture.model(self.root, self.root.name)
        result, _, _ = self.cli("register host")
        self.assertEqual(result.returncode, 0, result.stderr)
        process, record = self.launch()
        result, changes, _ = self.cli("down", answer="y\n", containers=[
            legacy.container("a", self.root.name, state="running")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "a"]])
        self.assertLess(result.stdout.index("Stopped task:"), result.stdout.index("Stopped: repo/web"))
        self.assertEqual(process.wait(timeout=2), 0)

    def test_mixed_group_preserves_locked_child_task(self):
        group = self.fixture.base / "group"
        for name, locked in (("infra", True), ("app", False)):
            child = group / name
            child.mkdir(parents=True)
            (child / "dwork.yml").write_text(json.dumps({"version": 1, "locked": locked,
                                                        "compose": {"enabled": False}}))
        result, _, _ = self.cli("register stack", cwd=group)
        self.assertEqual(result.returncode, 0, result.stderr)
        processes = []
        for name in ("infra", "app"):
            task = self.task()
            task.workspace, task.directory, task.project = str(group), str(group / name), name
            processes.append(self.launch(task))
        result, _, _ = self.cli("down", answer="y\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Keep task (locked): stack/Worker", result.stdout)
        self.assertIn("Stopped task: stack/Worker", result.stdout)
        self.assertIsNone(processes[0][0].poll())
        self.assertEqual(processes[1][0].wait(timeout=2), 0)

    def test_lock_changed_during_confirmation_is_rechecked(self):
        process, record = self.launch()
        def lock_and_accept(prompt):
            self.configure(True)
            return True
        with dwork_registry.registry_lock(), patch.object(dwork_common, "confirm_action", side_effect=lock_and_accept), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(dwork_workspaces.down_workspaces(dwork_registry.read_registry(), False), 0)
        self.assertIn("Skipped task (locked)", output.getvalue())
        self.assertIsNone(process.poll())

    def test_stale_or_wrong_token_records_never_signal_saved_pid(self):
        process, record = self.launch()
        path = next((self.state / "tasks").glob("*.json"))
        before = path.read_bytes()
        path.write_text(json.dumps(dict(record, token="wrong")))
        result, _, _ = self.cli("down", answer="y\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(process.poll())
        path.write_bytes(before)
        dwork_tasks.request(record, "stop")
        process.wait(timeout=6)
        path.write_text(json.dumps(record))  # Simulate state left after a crash/reboot.
        result, _, _ = self.cli("down", answer="y\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Would stop task:", result.stdout)

    def test_background_failure_keeps_nonzero_exit_and_cleans_record(self):
        task = self.task([sys.executable, "-c", "raise SystemExit(7)"])
        process = subprocess.run(dwork_terminals.task_command(task), env=self.env,
                                 stdin=subprocess.DEVNULL, capture_output=True, timeout=5)
        self.assertEqual(process.returncode, 7, process.stderr)
        self.assertEqual(list((self.state / "tasks").glob("*.json")), [])

    def test_visible_adapters_forward_supervisor_and_workspace_identity(self):
        task = self.task(visible=True)
        command = dwork_terminals.task_command(task)
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}):
            args = dwork_terminals.terminal_arguments(task)
            self.assertEqual(args[args.index("--exec") + 1:], command)
        with patch.dict(os.environ, {"DISPLAY": ":test"}), \
                patch.object(sys, "platform", "linux"), \
                patch.object(shutil, "which", side_effect=lambda program: str(self.shell)):
            for launcher, delimiter in (("gnome-terminal", "--"), ("konsole", "-e"),
                                        ("xfce4-terminal", "--execute"), ("xterm", "-e")):
                args = dwork_terminals.linux_terminal_arguments(task, launcher)
                self.assertEqual(args[args.index(delimiter) + 1:], command)

    def test_termination_timeout_kills_uncooperative_command(self):
        marker = self.root / "ready"
        code = ("import signal,time,pathlib; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                "pathlib.Path(" + repr(str(marker)) + ").write_text('ready'); time.sleep(60)")
        process, record = self.launch(self.task([sys.executable, "-c", code]))
        self.wait_for(marker.exists)
        started = time.monotonic()
        response = dwork_tasks.request(record, "stop")
        self.assertEqual(response["state"], "stopped")
        self.assertGreaterEqual(time.monotonic() - started, 4.9)
        self.assertEqual(process.wait(timeout=2), 0)

    def test_visible_task_keeps_terminal_and_later_shell_work_outside_tracking(self):
        self.check_visible_terminal()

    def test_visible_zsh_task_returns_to_an_ordinary_shell(self):
        self.check_visible_zsh()

    def test_macos_keeper_preserves_bash_foreground_input_stop_and_shell_handoff(self):
        self.check_visible_terminal(force_macos=True)

    def test_macos_keeper_preserves_zsh_foreground_input_stop_and_shell_handoff(self):
        self.check_visible_zsh(force_macos=True)

    def check_visible_zsh(self, force_macos=False):
        shell = shutil.which("zsh")
        if not shell:
            self.skipTest("Zsh unavailable")
        self.shell = self.fixture.bin / "zsh"
        self.shell.write_text("#!" + sys.executable + "\nimport os,sys\n"
            + "shell=" + repr(shell) + "\n"
            + "if sys.argv[1] == '-il': os.execv(shell, ['zsh','-f','-i'])\n"
            + "os.execv(shell, ['zsh','-f','-ic' if sys.argv[1] == '-lic' else '-c',sys.argv[2]])\n")
        self.shell.chmod(0o755)
        self.env.update(SHELL=str(self.shell), ZDOTDIR=str(self.fixture.base))
        with patch.dict(os.environ, self.env):
            self.check_visible_terminal(force_macos=force_macos)

    def test_controller_failure_reports_incomplete_and_leaves_containers_alone(self):
        (self.root / "dwork.yml").write_text("version: 1\n")
        self.fixture.model(self.root, self.root.name)
        result, _, _ = self.cli("register host")
        self.assertEqual(result.returncode, 0, result.stderr)
        process, record = self.launch()
        with dwork_registry.registry_lock(), \
                patch.object(dwork_common, "confirm_action", return_value=True), \
                patch.object(dwork_docker, "docker_target", return_value={"context": "default", "daemon": "test-daemon"}), \
                patch.object(dwork_docker, "show_target"), \
                patch.object(dwork_docker, "inventory", return_value=[legacy.container("a", self.root.name, state="running")]), \
                patch.object(dwork_tasks, "running", return_value=[record]), \
                patch.object(dwork_tasks, "request", side_effect=TimeoutError("controller timed out")), \
                patch.object(dwork_docker, "docker") as docker, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(dwork_common.DworkError, "Down incomplete"):
                dwork_workspaces.down_workspaces(dwork_registry.read_registry(), False)
            docker.assert_not_called()
        self.assertIsNone(process.poll())

    def check_visible_terminal(self, force_macos=False):
        import pty
        task = self.task([sys.executable, "-c", "import time; print(input('TASK_INPUT>'),flush=True); time.sleep(60)"], True)
        args = dwork_terminals.task_command(task)
        if force_macos:
            # Exercise the complete keeper branch on Linux as well as Darwin.
            # The public POSIX APIs used by that branch are available on both.
            code = ("import base64,json,sys; sys.path.insert(0," + repr(str(
                    Path(dwork_tasks.__file__).parent)) + "); import dwork_tasks; "
                    "dwork_tasks.sys.platform='darwin'; dwork_tasks.require_support=lambda:None; "
                    "sys.exit(dwork_tasks.supervise(json.loads(base64.urlsafe_b64decode(sys.argv[1]))))")
            args = [args[0], "-c", code, args[2]]
        pid, master = pty.fork()
        if pid == 0:
            os.execve(args[0], args, self.env)
        def cleanup():
            # Like pty.spawn(), close the master before waiting: a Darwin slave
            # can otherwise wait for terminal output to drain while exiting.
            os.close(master)
            for signum in (signal.SIGHUP, signal.SIGKILL):
                try:
                    os.kill(pid, signum)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    if os.waitpid(pid, os.WNOHANG)[0]:
                        return
                    time.sleep(.05)
            self.fail("PTY child did not exit after its master was closed and SIGKILL was sent")
        self.addCleanup(cleanup)
        def until(marker):
            output = b""
            deadline = time.monotonic() + 7
            while marker not in output and time.monotonic() < deadline:
                if select.select([master], [], [], .1)[0]:
                    output += os.read(master, 65536)
            self.assertIn(marker, output)
        record = self.wait_for(lambda: dwork_tasks.running(self.state))[0]
        until(b"TASK_INPUT>")
        os.write(master, b"input-works\n")
        until(b"input-works")
        result, _, _ = self.cli("down", answer="y\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        until(b"ordinary shell")
        os.write(master, b"printf 'SHELL_%s\\n' alive\n")
        until(b"SHELL_alive")
        self.assertEqual(dwork_tasks.running(self.state), [])
        self.cli("down", answer="y\n")
        os.write(master, b"printf 'STILL_%s\\n' alive\n")
        until(b"STILL_alive")


if __name__ == "__main__":
    unittest.main()
