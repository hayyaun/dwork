"""Per-task consent and dispatch of prepared native terminal/background launches."""

import shlex
import subprocess

from dwork_common import DworkError, color, colored_name
from dwork_launch import TerminalLaunch
from dwork_process import run_command
from dwork_terminal_launch import (
    APPLE_TERMINAL_SCRIPT,
    choose_launcher as choose_launcher,
    command_shell as command_shell,
    linux_terminal_arguments as linux_terminal_arguments,
    macos_terminal_arguments as macos_terminal_arguments,
    powershell_script as powershell_script,
    preflight_terminals as preflight_terminals,
    prepare_terminal,
    task_command as task_command,
    terminal_arguments as terminal_arguments,
)


def confirm_terminal(task):
    if not task.confirm:
        return True
    label = "Run background task " if task.window == "none" else "Open terminal "
    prompt = (
        label
        + colored_name(task.title, repr(task.title))
        + " running "
        + color(shlex.join(task.command), "bold")
        + " in "
        + str(task.cwd)
        + "? (y/N) "
    )
    try:
        answer = input(prompt)
    except EOFError:
        answer = ""
    return answer.strip().lower() == "y"


def open_terminal(task, *, launch: TerminalLaunch | None = None):
    launch = launch if launch is not None else prepare_terminal(task)
    command = list(launch.arguments)
    if launch.launcher == "background":
        process = subprocess.Popen(
            command,
            cwd=launch.cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            code = process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            return process.pid
        if code:
            raise DworkError(
                "Background task "
                + launch.title
                + " exited immediately (exit "
                + str(code)
                + "). Run the command manually to inspect its output."
            )
        return process.pid
    launcher = launch.launcher
    if launcher == "apple-terminal":
        result = subprocess.run(
            command, input=APPLE_TERMINAL_SCRIPT, text=True, capture_output=True
        )
        if result.returncode:
            raise DworkError(
                "Apple Terminal failed to launch: "
                + (result.stderr.strip() or str(result.returncode))
                + ". Check macOS Automation permission for the calling application to control Terminal."
            )
        return
    if launcher == "windows-terminal":
        run_command(command)
        return
    arguments = command
    # GUI emulators can remain alive as long as their command. Detach the
    # launcher without pipes, so dwork returns while the terminal stays open.
    process = subprocess.Popen(
        arguments,
        cwd=launch.cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        code = process.wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        return
    if code:
        raise DworkError(
            launcher + " failed to launch (exit " + str(code) + "). Check your graphical session."
        )
