"""CLI protocol client and terminal handoff; no independent lifecycle policy."""

import base64
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import uuid

from dwork_tray.platforms import CompanionError


def capture_status():
    command = [sys.executable, "-m", "dwork", "list", "--json"]
    # This session contains only our read-only observer and its helper commands.
    # Keep its parent unreaped until cleanup; never signal a saved workload PID.
    with subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as process:
        try:
            output, errors = process.communicate(timeout=15)
        except subprocess.TimeoutExpired as error:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise CompanionError(
                "dwork status timed out; inspect Docker/controller access with the CLI."
            ) from error
        return subprocess.CompletedProcess(command, process.returncode, output, errors)


def read_status():
    result = capture_status()
    if result.returncode:
        raise CompanionError(result.stderr.strip() or "dwork list --json failed")
    try:
        data = json.loads(result.stdout)
        if (
            type(data.get("schema_version")) is not int
            or data["schema_version"] != 1
            or data.get("scope") != "registered"
            or not isinstance(data.get("workspaces"), list)
        ):
            raise ValueError("unsupported status schema")
        for row in data["workspaces"]:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("name"), str)
                or not isinstance(row.get("status"), str)
            ):
                raise ValueError("invalid workspace row")
        return data
    except (ValueError, TypeError, AttributeError) as error:
        raise CompanionError(
            "Expected dwork's version-1 JSON status interface. Install a dwork build containing the companion interface; older 0.3.0 releases do not include it."
        ) from error


def open_operation(action, name, completion_directory):
    if (
        action not in ("switch", "down")
        or (action == "switch" and not isinstance(name, str))
        or (action == "down" and name is not None)
    ):
        raise CompanionError("Unsupported companion action")
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
