"""Shared errors, workspace models, terminal choices, and console helpers."""

from dataclasses import dataclass, field
from pathlib import Path
import os
import sys
import zlib
from typing import TextIO


LINUX_TERMINALS = ("gnome-terminal", "konsole", "xfce4-terminal", "xterm")
LAUNCHERS = ("auto", "windows-terminal", "apple-terminal", *LINUX_TERMINALS)


class DworkError(Exception):
    pass


def color(value: object, style: str, stream: TextIO | None = None) -> str:
    """Keep pipes/logs plain; color is presentation only, never stored in plans."""
    stream = sys.stdout if stream is None else stream
    text = str(value)
    if not stream.isatty() or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return text
    codes = {"start": "32", "stop": "31", "warning": "33", "bold": "1", "dim": "2", "grey": "90"}
    return "\033[" + codes.get(style, style) + "m" + text + "\033[0m"


def colored_name(value: object, display: object | None = None, stream: TextIO | None = None) -> str:
    # Python's hash() is randomized between invocations; CRC32 keeps names stable.
    palette = ("36", "35", "34", "96", "95", "94")
    code = palette[zlib.crc32(str(value).encode("utf-8")) % len(palette)]
    return color(value if display is None else display, code, stream)


def confirm_action(prompt: str) -> bool:
    try:
        return input(prompt + " (y/N) ").strip().lower() == "y"
    except EOFError:
        return False


@dataclass
class TerminalTask:
    title: str
    command: list[str]
    cwd: Path
    healthy: list[str] = field(default_factory=list)
    timeout: float = 180
    window: str = "new"
    launcher: str = "auto"
    confirm: bool = True
    workspace: str | None = None
    directory: str | None = None
    project: str | None = None


@dataclass
class BrowserTask:
    url: str
    wait_url: str | None = None
    timeout: float = 60
    confirm: bool = True
    browser: str = "default"


@dataclass
class Workspace:
    name: str
    directory: Path
    services: dict[str, object]
    enabled: bool = True
    selected: list[str] | None = None
    terminals: list[TerminalTask] = field(default_factory=list)
    configured: bool = False
    locked: bool = False
    browsers: list[BrowserTask] = field(default_factory=list)
    confirm: bool = True

    def manages(self, service: str) -> bool:
        return self.selected is None or service in self.selected
