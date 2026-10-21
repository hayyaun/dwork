"""Terminal launcher selection, argument preparation, and dependency preflight."""

from pathlib import Path
import base64
import os
import shlex
import shutil
import subprocess
import sys

from dwork_common import DworkError, LAUNCHERS, LINUX_TERMINALS
from dwork_launch import TerminalLaunch
from dwork_process import run_command
import dwork_registry_store
import dwork_tasks


APPLE_TERMINAL_SCRIPT = """on run argv
    tell application id "com.apple.Terminal"
        set taskTab to do script (item 1 of argv)
        set custom title of taskTab to item 2 of argv
        activate
    end tell
end run"""


def task_command(task):
    if task.workspace is not None:
        return dwork_tasks.arguments(
            task, dwork_registry_store.registry_path().parent, command_shell()
        )
    return [command_shell(), "-lic", "exec " + shlex.join(task.command)]


def terminal_arguments(task):
    distro = os.environ.get("WSL_DISTRO_NAME")
    shell = shutil.which(os.environ.get("SHELL", "bash"))
    if not distro or not shell:
        raise DworkError(
            "Terminal tasks currently require WSL2 and an available Bash or Zsh shell."
        )
    if Path(shell).name not in ("bash", "zsh"):
        raise DworkError("Terminal tasks require Bash or Zsh as SHELL.")
    if any(c in value for value in (distro, shell) for c in ("\0", "\r", "\n", ";")):
        raise DworkError("WSL distribution and shell cannot contain terminal command separators.")
    # Shell startup loads the normal user PATH; shlex.join preserves command argv.
    return [
        "-w",
        "new" if task.window == "new" else "0",
        "new-tab",
        "--title",
        task.title,
        "wsl.exe",
        "--distribution",
        distro,
        "--cd",
        str(task.cwd),
        "--exec",
        *task_command(task),
    ]


def powershell_script(task):
    arguments = subprocess.list2cmdline(terminal_arguments(task)).replace("'", "''")
    # Start-Process receives one explicitly quoted ArgumentList, per Microsoft docs.
    return (
        "$ErrorActionPreference = 'Stop'; "
        "$process = Start-Process -FilePath wt.exe -ArgumentList '"
        + arguments
        + "' -PassThru; $process.WaitForExit(); exit $process.ExitCode"
    )


def command_shell():
    shell = shutil.which(os.environ.get("SHELL", "bash"))
    if not shell or Path(shell).name not in ("bash", "zsh"):
        raise DworkError("Terminal tasks require an available Bash or Zsh as SHELL.")
    return shell


def choose_launcher(task):
    selected = task.launcher
    if selected == "auto":
        selected = os.environ.get("DWORK_TERMINAL", "auto") or "auto"
    if selected not in LAUNCHERS:
        raise DworkError("DWORK_TERMINAL must be one of: " + ", ".join(LAUNCHERS))
    if selected != "auto":
        return selected
    if os.environ.get("WSL_DISTRO_NAME"):
        return "windows-terminal"
    if sys.platform == "darwin":
        return "apple-terminal"
    if not sys.platform.startswith("linux"):
        raise DworkError(
            "Terminal launching supports Linux, macOS, and WSL; Compose-only mode is still available."
        )
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    preferred = (
        "konsole"
        if "kde" in desktop
        else "xfce4-terminal"
        if "xfce" in desktop
        else "gnome-terminal"
        if "gnome" in desktop
        else None
    )
    order = ([preferred] if preferred else []) + [p for p in LINUX_TERMINALS if p != preferred]
    for launcher in order:
        if launcher == "xterm" and task.window == "current":
            continue
        if shutil.which(launcher):
            return launcher
    raise DworkError(
        "No supported Linux terminal is installed for this window mode. Install GNOME Terminal, Konsole, Xfce Terminal, or xterm (new windows only), or set DWORK_TERMINAL."
    )


def linux_terminal_arguments(task, launcher):
    if not sys.platform.startswith("linux"):
        raise DworkError("Native terminal launchers require Linux.")
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        raise DworkError(
            "Native Linux terminal tasks require a graphical session (DISPLAY or WAYLAND_DISPLAY)."
        )
    if launcher not in LINUX_TERMINALS or not shutil.which(launcher):
        raise DworkError("Linux terminal is unavailable: " + launcher)
    if launcher == "xterm":
        if task.window == "current":
            raise DworkError(
                "xterm does not support window: current; use window: new or a tab-capable launcher."
            )
        if not os.environ.get("DISPLAY"):
            raise DworkError("xterm requires an X11 DISPLAY (including XWayland).")
    command = task_command(task)
    if launcher == "gnome-terminal":
        return [
            launcher,
            "--window" if task.window == "new" else "--tab",
            "--title",
            task.title,
            "--working-directory",
            str(task.cwd),
            "--",
            *command,
        ]
    if launcher == "konsole":
        return [
            launcher,
            "--separate" if task.window == "new" else "--new-tab",
            "--workdir",
            str(task.cwd),
            "-p",
            "LocalTabTitleFormat=" + task.title,
            "-e",
            *command,
        ]
    if launcher == "xfce4-terminal":
        return [
            launcher,
            "--window" if task.window == "new" else "--tab",
            "--title",
            task.title,
            "--working-directory",
            str(task.cwd),
            "--execute",
            *command,
        ]
    return [launcher, "-title", task.title, "-e", *command]


def macos_terminal_arguments(task):
    if sys.platform != "darwin":
        raise DworkError("Apple Terminal requires macOS.")
    if task.window != "new":
        raise DworkError(
            "Apple Terminal supports window: new only; its scripting interface cannot create tabs. Use window: new or none."
        )
    if not shutil.which("osascript"):
        raise DworkError("Apple Terminal requires macOS osascript.")
    # Terminal's documented `do script` creates a new window without a target.
    # User values travel as argv, never as AppleScript source. Shell quoting
    # preserves cwd and the task's existing supervisor or command arguments.
    command = "cd -- " + shlex.quote(str(task.cwd)) + " && " + shlex.join(task_command(task))
    return ["osascript", "-", command, task.title]


def prepare_terminal(task) -> TerminalLaunch:
    """Resolve launcher, shell, supervisor identity, and transport without dispatch."""
    if task.window == "none":
        arguments = (
            task_command(task)
            if task.workspace is not None
            else [command_shell(), "-lc", "exec " + shlex.join(task.command)]
        )
        launcher = "background"
    else:
        launcher = choose_launcher(task)
        if launcher == "windows-terminal":
            script = powershell_script(task)
            if not shutil.which("powershell.exe"):
                raise DworkError(
                    "Windows terminal tasks require Windows PowerShell and Windows Terminal."
                )
            encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
            arguments = [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                encoded,
            ]
        elif launcher == "apple-terminal":
            arguments = macos_terminal_arguments(task)
        else:
            arguments = linux_terminal_arguments(task, launcher)
    return TerminalLaunch(tuple(arguments), task.cwd, launcher, task.title)


def preflight_terminals(tasks):
    if tasks:
        dwork_tasks.require_support()
    windows = False
    prepared = []
    for task in tasks:
        launch = prepare_terminal(task)
        windows = windows or launch.launcher == "windows-terminal"
        program = task.command[0]
        local = (task.cwd / program).resolve()
        available = (
            (local.is_file() and os.access(local, os.X_OK))
            if "/" in program
            else bool(shutil.which(program))
        )
        if not available:
            raise DworkError("Terminal command is unavailable: " + program)
        prepared.append(launch)
    if windows:
        run_command(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "(Get-Command wt.exe -ErrorAction Stop).Source",
            ]
        )
    return tuple(prepared)
