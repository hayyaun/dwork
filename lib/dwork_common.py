"""Shared errors, workspace models, terminal choices, and console helpers."""
from dataclasses import dataclass, field
from pathlib import Path
import os
import sys
import zlib


LINUX_TERMINALS = ("gnome-terminal", "konsole", "xfce4-terminal", "xterm")
LAUNCHERS = ("auto", "windows-terminal", "apple-terminal", *LINUX_TERMINALS)


class DworkError(Exception):
    pass


def color(value, style, stream=None):
    """Keep pipes/logs plain; color is presentation only, never stored in plans."""
    stream = sys.stdout if stream is None else stream
    text = str(value)
    if not stream.isatty() or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return text
    codes = {"start": "32", "stop": "31", "warning": "33", "bold": "1", "dim": "2", "grey": "90"}
    return "\033[" + codes.get(style, style) + "m" + text + "\033[0m"


def colored_name(value, display=None, stream=None):
    # Python's hash() is randomized between invocations; CRC32 keeps names stable.
    palette = ("36", "35", "34", "96", "95", "94")
    code = palette[zlib.crc32(str(value).encode("utf-8")) % len(palette)]
    return color(value if display is None else display, code, stream)


def confirm_action(prompt):
    try:
        return input(prompt + " (y/N) ").strip().lower() == "y"
    except EOFError:
        return False


@dataclass
class TerminalTask:
    title: str
    command: list
    cwd: Path
    healthy: list = field(default_factory=list)
    timeout: float = 180
    window: str = "new"
    launcher: str = "auto"
    confirm: bool = True
    workspace: str = None
    directory: str = None
    project: str = None


@dataclass
class BrowserTask:
    url: str
    wait_url: str = None
    timeout: float = 60
    confirm: bool = True
    browser: str = "default"


@dataclass
class Workspace:
    name: str
    directory: Path
    services: dict
    enabled: bool = True
    selected: object = None
    terminals: list = field(default_factory=list)
    configured: bool = False
    locked: bool = False
    browsers: list = field(default_factory=list)
    confirm: bool = True

    def manages(self, service):
        return self.selected is None or service in self.selected
