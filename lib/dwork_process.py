"""Shared checked subprocess execution for Docker and native dispatch helpers."""

from pathlib import Path
from typing import Sequence
import shlex
import subprocess

from dwork_common import DworkError


def run_command(
    args: Sequence[str], cwd: str | Path | None = None, *, timeout: float | None = None
) -> str:
    try:
        result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise DworkError(
            "Timed out running command: "
            + shlex.join(args)
            + ". Inspect workload state before retrying."
        ) from error
    if result.returncode:
        raise DworkError(result.stderr.strip() or "Command failed: " + shlex.join(args))
    return result.stdout
