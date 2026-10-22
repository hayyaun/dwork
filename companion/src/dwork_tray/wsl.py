"""Windows host transport for one explicitly selected WSL distribution."""

import base64
from importlib import resources
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import uuid

from dwork_tray.client import parse_status, validate_operation
from dwork_tray.platforms import CompanionError


def selected_value(value, label):
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or value.startswith("-")
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise CompanionError(
            label + " must be an explicit nonempty value without control characters."
        )
    return value


def target(distribution, python, user=None):
    distribution = selected_value(distribution, "--wsl-distribution")
    python = selected_value(python, "--wsl-python")
    if not PurePosixPath(python).is_absolute():
        raise CompanionError(
            "--wsl-python must be an absolute Linux interpreter path with dwork installed."
        )
    if user is not None:
        user = selected_value(user, "--wsl-user")
    return distribution, python, user


def executable(name):
    path = shutil.which(name)
    if not path:
        raise CompanionError(
            name + " is required on the Windows host; install/enable it before starting the tray."
        )
    return path


def decode_output(output):
    # WSL's quiet list is UTF-16 on current Windows; command output is UTF-8.
    # Support BOM-marked output and UTF-8 implementations without locale parsing.
    if output.startswith((b"\xff\xfe", b"\xfe\xff")):
        return output.decode("utf-16")
    return output.decode("utf-16-le" if b"\0" in output else "utf-8-sig")


def hidden_run(command, timeout):
    try:
        return subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as error:
        raise CompanionError(
            "Windows/WSL transport timed out. Only its local helper was stopped; no workspace or distribution was terminated."
        ) from error


def wsl_command(wsl, distribution, python, user=None):
    distribution, python, user = target(distribution, python, user)
    command = [wsl, "--distribution", distribution]
    if user is not None:
        command += ["--user", user]
    return command + ["--cd", "~", "--exec", python]


def windows_python():
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe":
        python = python.with_name("python.exe")
        if not python.is_file():
            raise CompanionError("Interactive operations require python.exe beside pythonw.exe.")
    return str(python)


def terminal_command(wt, powershell, spec):
    payload = base64.urlsafe_b64encode(json.dumps(spec).encode("utf-8")).decode("ascii")
    # Windows Terminal treats semicolons as command separators. Its argv contains
    # only fixed tokens and an encoded PowerShell command; all variable data is
    # inside literal arguments. No execution-policy changes or profile loading.
    python = windows_python().replace("'", "''")
    script = "& '" + python + "' -m dwork_tray.wsl_terminal '" + payload + "'; exit $LASTEXITCODE"
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return [
        wt,
        "--window",
        "new",
        "new-tab",
        "--title",
        "dwork",
        powershell,
        "-NoLogo",
        "-NoProfile",
        "-EncodedCommand",
        encoded,
    ]


class WslTransport:
    supports_startup = False

    def __init__(self, distribution, python, user=None):
        self.distribution, self.python, self.user = target(distribution, python, user)
        self.wsl = executable("wsl.exe")
        self.wt = executable("wt.exe")
        self.powershell = executable("powershell.exe")
        self.label = (
            "WSL: " + self.distribution + (" / " + self.user if self.user else " / default user")
        )

    def require_running(self):
        result = hidden_run([self.wsl, "--list", "--running", "--quiet"], 5)
        if result.returncode:
            raise CompanionError(
                "Cannot list running WSL distributions: "
                + decode_output(result.stderr or result.stdout).strip()
            )
        running = {
            line.strip() for line in decode_output(result.stdout).splitlines() if line.strip()
        }
        if self.distribution not in running:
            raise CompanionError(
                "WSL distribution "
                + self.distribution
                + " is stopped or unavailable. Start it deliberately in Windows Terminal, then Refresh; the tray does not start stopped distributions."
            )

    def command(self):
        return wsl_command(self.wsl, self.distribution, self.python, self.user)

    def read_status(self):
        self.require_running()
        source = resources.files("dwork_tray").joinpath("observer.py").read_text(encoding="utf-8")
        result = hidden_run(self.command() + ["-c", source], 25)
        try:
            return parse_status(
                subprocess.CompletedProcess(
                    result.args,
                    result.returncode,
                    decode_output(result.stdout),
                    decode_output(result.stderr),
                )
            )
        except CompanionError as error:
            raise CompanionError(
                str(error)
                + "; check --wsl-python and install a CLI with version-1 JSON support in the selected distribution/user."
            ) from error

    def open_operation(self, action, name, completion_directory):
        validate_operation(action, name)
        self.require_running()
        marker = Path(completion_directory) / (uuid.uuid4().hex + ".done")
        spec = {
            "distribution": self.distribution,
            "python": self.python,
            "user": self.user,
            "action": action,
            "name": name,
            "marker": str(marker),
        }
        result = hidden_run(terminal_command(self.wt, self.powershell, spec), 10)
        if result.returncode:
            raise CompanionError(
                "Windows Terminal handoff failed: "
                + decode_output(result.stderr or result.stdout).strip()
            )
        return marker
