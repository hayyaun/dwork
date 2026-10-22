"""Native Linux/macOS CLI execution and existing terminal handoff."""

import base64
import json
from pathlib import Path
import subprocess
import sys
import uuid

from dwork_tray import observer
from dwork_tray.client import parse_status, validate_operation
from dwork_tray.platforms import CompanionError


def capture_status():
    try:
        return observer.capture_status()
    except subprocess.TimeoutExpired as error:
        raise CompanionError(
            "dwork status timed out; inspect Docker/controller access with the CLI."
        ) from error


def read_status():
    return parse_status(capture_status())


def open_operation(action, name, completion_directory):
    validate_operation(action, name)
    # Reuse supported native adapters without registering/tracking the operation
    # terminal as an application task. The CLI inside it owns all consent/locking.
    from dwork_common import TerminalTask
    from dwork_terminals import open_terminal

    marker = Path(completion_directory) / (uuid.uuid4().hex + ".done")
    payload = base64.urlsafe_b64encode(
        json.dumps({"action": action, "name": name, "marker": str(marker)}).encode()
    ).decode()
    task = TerminalTask(
        "dwork: " + (name if name is not None else "stop workspaces"),
        [sys.executable, "-m", "dwork_tray.command", payload],
        Path.home(),
        confirm=False,
    )
    open_terminal(task)
    return marker


class NativeTransport:
    supports_startup = True
    label = ""

    def read_status(self):
        return read_status()

    def open_operation(self, action, name, completion_directory):
        return open_operation(action, name, completion_directory)
