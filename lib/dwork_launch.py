"""Immutable prepared launch data; preparing a launch never grants consent."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TerminalLaunch:
    arguments: tuple[str, ...]
    cwd: Path
    launcher: str
    title: str


@dataclass(frozen=True)
class BrowserLaunch:
    arguments: tuple[str, ...]
    wait_for_dispatch: bool
