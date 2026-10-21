"""Local task supervision using POSIX process groups and private Unix sockets.

Each supervisor owns an unreaped child until its group has been stopped. Clients
never signal a saved PID: a live supervisor authenticates every control request.
"""
import base64
import json
import os
from pathlib import Path
import secrets
import select
import signal
import socket
import sys
import tempfile
import termios
import time

from dwork_common import DworkError


def require_support():
    """Keep the unreaped-child identity guarantee on supported Python builds."""
    if sys.platform == "darwin" and (sys.version_info < (3, 13)
            or not hasattr(os, "waitid") or not hasattr(os, "WNOWAIT")):
        raise DworkError("Tracked terminal and background tasks on macOS require Python 3.13 or newer"
                         + " with os.waitid support. Install a current Python (for example, brew install python@3.14)"
                         + " and reinstall dwork using that interpreter.")


def request(record, action):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(7 if action == "stop" else .5)
        client.connect(record["socket"])
        client.sendall(json.dumps({"token": record["token"], "action": action}).encode() + b"\n")
        with client.makefile("rb") as stream:
            response = json.loads(stream.readline(4096))
        if not isinstance(response, dict) or response.get("token") != record["token"]:
            raise ValueError("Task controller identity changed")
        return response


def stop(record, state):
    """Stop an approved task, or recognize its supervisor's completed cleanup.

    Supervisors unlink their token record only after stopping the owned process
    group. A vanished connection alone cannot prove completion: a crashed or
    inaccessible controller with a remaining record must still fail shutdown.
    """
    token = record["token"]
    if (not isinstance(token, str) or len(token) != 48
            or any(c not in "0123456789abcdef" for c in token)):
        raise ValueError("Invalid task controller token")
    try:
        response = request(record, "stop")
    except (FileNotFoundError, ConnectionError, json.JSONDecodeError) as error:
        # Empty input is a closed socket; a nonempty malformed response is a
        # protocol failure, even if its record subsequently disappears.
        if isinstance(error, json.JSONDecodeError) and error.doc:
            raise
        try:
            (Path(state) / "tasks" / (token + ".json")).lstat()
        except FileNotFoundError:
            return False
        raise
    if response.get("state") != "stopped":
        raise DworkError("Task controller did not confirm shutdown.")
    return True


def running(state):
    """Read-only discovery; stale files never authorize signalling a process."""
    records = []
    for path in sorted((Path(state) / "tasks").glob("*.json")):
        try:
            record = json.loads(path.read_text())
            if (not isinstance(record, dict) or any(not isinstance(record.get(key), str) for key in
                    ("socket", "token", "workspace", "directory", "project", "title"))
                    or type(record.get("pid")) is not int or not isinstance(record.get("command"), list)
                    or any(not isinstance(arg, str) for arg in record["command"])):
                continue
            response = request(record, "status")
            if response.get("state") == "running":
                records.append(record)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return records


def arguments(task, state, shell):
    require_support()
    payload = {"state": str(state), "workspace": task.workspace,
               "directory": task.directory, "project": task.project,
               "title": task.title, "command": task.command, "cwd": str(task.cwd),
               "visible": task.window != "none", "shell": shell}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return [sys.executable, str(Path(__file__).resolve()), encoded]


def group_keeper():
    """Keep an owned process alive until group cleanup, or kill the group on EOF."""
    try:
        for signum in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT, signal.SIGQUIT,
                       signal.SIGTTIN, signal.SIGTTOU, signal.SIGTSTP):
            signal.signal(signum, signal.SIG_IGN)
        signal.pthread_sigmask(signal.SIG_SETMASK, ())
        os.write(1, b"1")
        os.close(1)
        # Only the supervisor owns the writing end. Its exit must not orphan tasks.
        while os.read(0, 1):
            pass
    finally:
        # Also covers a supervisor exiting before it receives the readiness ACK.
        os.killpg(os.getpgrp(), signal.SIGKILL)


def start_group_keeper(group):
    """Join the owned child's existing group with a member kept alive for cleanup."""
    ready_read, ready_write = os.pipe()
    control_read, control_write = os.pipe()
    keeper = None
    ready = False
    try:
        actions = [(os.POSIX_SPAWN_DUP2, control_read, 0),
                   (os.POSIX_SPAWN_DUP2, ready_write, 1)]
        actions.extend((os.POSIX_SPAWN_CLOSE, fd) for fd in
                       (ready_read, ready_write, control_read, control_write))
        keeper = os.posix_spawn(sys.executable,
            [sys.executable, str(Path(__file__).resolve()), "--group-keeper"],
            os.environ, setpgroup=group, file_actions=actions,
            # An interactive shell can stop its background group before the
            # keeper finishes starting. Block those signals until it ignores them.
            setsigmask=(signal.SIGHUP, signal.SIGTERM, signal.SIGINT, signal.SIGQUIT,
                        signal.SIGTTIN, signal.SIGTTOU, signal.SIGTSTP))
        os.close(control_read)
        control_read = None
        os.close(ready_write)
        ready_write = None
        if not select.select([ready_read], [], [], 5)[0] or os.read(ready_read, 1) != b"1":
            raise DworkError("Task process-group keeper did not become ready")
        ready = True
        return keeper, control_write
    finally:
        for fd in (ready_read, ready_write, control_read):
            if fd is not None:
                os.close(fd)
        if not ready:
            os.close(control_write)
            if keeper is not None:
                try:
                    os.kill(keeper, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                finally:
                    os.waitpid(keeper, 0)


def supervise(spec):
    import shlex
    require_support()
    os.chdir(spec["cwd"])
    visible = spec["visible"]
    foreground = os.tcgetpgrp(0) if visible else None
    terminal_settings = termios.tcgetattr(0) if visible else None
    # The supervisor hands the terminal to its command, then takes it back before
    # starting an ordinary shell. It must be able to restore foreground ownership.
    signal.signal(signal.SIGTTOU, signal.SIG_IGN)
    stopping = False

    def interrupted(signum, frame):
        nonlocal stopping
        stopping = True

    for signum in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupted)

    pid = None
    keeper = None
    keeper_control = None
    record_path = None
    exit_code = 0

    def exited():
        # WNOWAIT keeps the child (and its group ID) reserved until group cleanup.
        return os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None

    def stop_group():
        nonlocal pid, keeper, keeper_control
        if pid is None:
            if keeper is not None:
                try:
                    os.kill(keeper, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.waitpid(keeper, 0)
                keeper = None
                os.close(keeper_control)
                keeper_control = None
            return
        for signum in (signal.SIGTERM, signal.SIGCONT):
            try:
                os.killpg(pid, signum)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 5
        while not exited() and time.monotonic() < deadline:
            time.sleep(.05)
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.waitpid(pid, 0)
        pid = None
        if keeper is not None:
            os.waitpid(keeper, 0)
            keeper = None
            os.close(keeper_control)
            keeper_control = None

    try:
        state = Path(spec["state"]) / "tasks"
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        token = secrets.token_hex(24)
        # A short private directory avoids AF_UNIX's pathname length limit even
        # when XDG_STATE_HOME is deeply nested. No TCP port or daemon is needed.
        with tempfile.TemporaryDirectory(prefix="dwork-task-") as temporary:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                endpoint = str(Path(temporary) / "control")
                server.bind(endpoint)
                server.listen(4)
                server.settimeout(.1)
                command = [spec["shell"], "-lic" if visible else "-lc",
                           "exec " + shlex.join(spec["command"])]
                pid = os.posix_spawn(command[0], command, os.environ, setpgroup=0,
                                     setsigdef=(signal.SIGINT, signal.SIGQUIT, signal.SIGTERM,
                                                signal.SIGHUP, signal.SIGTTOU, signal.SIGTTIN,
                                                signal.SIGTSTP, signal.SIGPIPE))
                # Darwin cannot signal a zombie-only group. A live owned member
                # stays through the final signal, without hiding genuine EPERM.
                # The unreaped command reserves the group even if it exits before
                # the keeper joins. Keep PID=PGID for interactive shell job control.
                if sys.platform == "darwin":
                    keeper, keeper_control = start_group_keeper(pid)
                if visible:
                    os.tcsetpgrp(0, pid)
                    os.killpg(pid, signal.SIGCONT)
                record = {key: spec[key] for key in
                          ("workspace", "directory", "project", "title", "command")}
                record.update(socket=endpoint, token=token, pid=pid)
                record_path = state / (token + ".json")
                with tempfile.NamedTemporaryFile(mode="w", dir=state, delete=False) as stream:
                    temporary_record = Path(stream.name)
                    json.dump(record, stream)
                temporary_record.replace(record_path)
                while not stopping and not exited():
                    try:
                        client, _ = server.accept()
                    except socket.timeout:
                        continue
                    with client:
                        client.settimeout(.5)
                        try:
                            with client.makefile("rb") as stream:
                                message = json.loads(stream.readline(4096))
                            if not isinstance(message, dict) or message.get("token") != token:
                                continue
                            action = message.get("action")
                            if action == "stop":
                                stop_group()
                                stopping = True
                            response = {"token": token, "state": "stopped" if stopping else "running"}
                            client.sendall(json.dumps(response).encode() + b"\n")
                        except (OSError, ValueError, TypeError):
                            continue
                if pid is not None and not stopping:
                    status = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                    if status is not None:
                        exit_code = status.si_status if status.si_code == os.CLD_EXITED else 128 + status.si_status
                stop_group()
                # Publish completed cleanup before closing the controller socket,
                # so a concurrent stop cannot see a stale live-task record.
                record_path.unlink(missing_ok=True)
                record_path = None
    finally:
        stop_group()
        if record_path is not None:
            record_path.unlink(missing_ok=True)
        if visible:
            os.tcsetpgrp(0, foreground)
            termios.tcsetattr(0, termios.TCSADRAIN, terminal_settings)
    if visible:
        print("\ndwork task finished. This terminal is now an ordinary shell.", flush=True)
        # No controller remains in this shell. Later user work cannot be stopped
        # by dwork down, even if the same terminal tab is reused.
        os.execv(spec["shell"], [spec["shell"], "-il"])
    return exit_code


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--group-keeper"]:
            group_keeper()
            sys.exit(0)
        sys.exit(supervise(json.loads(base64.urlsafe_b64decode(sys.argv[1]))))
    except (DworkError, OSError, ValueError, KeyError, TypeError) as error:
        print("dwork task: " + str(error), file=sys.stderr)
        sys.exit(1)
