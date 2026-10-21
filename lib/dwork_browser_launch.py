"""Browser value validation, platform selection, and opener preparation."""

from pathlib import PureWindowsPath
import base64
import os
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

from dwork_common import DworkError
from dwork_launch import BrowserLaunch


def validate_url(value, where="browser.url"):
    if (
        not isinstance(value, str)
        or not value
        or not value.isascii()
        or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise DworkError(
            where
            + " must be an HTTP/HTTPS URL without whitespace or control characters; percent-encode non-ASCII characters."
        )
    try:
        parts = urlsplit(value)
        port = parts.port
        valid = (
            parts.scheme in ("http", "https")
            and parts.hostname
            and parts.username is None
            and parts.password is None
            and "\\" not in value
            and (port is None or port > 0)
        )
    except ValueError:
        valid = False
    if not valid:
        raise DworkError(
            where + " must be an absolute HTTP/HTTPS URL without credentials and with a valid port."
        )
    return value


def validate_browser(value):
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or value.startswith("-")
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise DworkError(
            "browser.browser must be default or a nonempty browser executable/application name or path without control characters or surrounding whitespace."
        )
    return value


def browser_command(url, browser="default"):
    browser = validate_browser(browser)
    custom = browser != "default"
    # WSL must never fall through to xdg-open, even when Windows interop fails.
    if os.environ.get("WSL_DISTRO_NAME"):
        if not shutil.which("powershell.exe"):
            raise DworkError(
                "Browser launching on WSL requires Windows PowerShell (powershell.exe) and Windows interop; no Linux browser will be opened."
            )
        if custom:
            path = PureWindowsPath(browser)
            if (
                not browser.lower().endswith(".exe")
                or '"' in browser
                or (not path.is_absolute() and any(c in browser for c in ("/", "\\", ":")))
            ):
                raise DworkError(
                    "Custom browsers on WSL must be Windows .exe names or absolute Windows .exe paths (for example, C:\\Program Files\\Mozilla Firefox\\firefox.exe); Linux browser paths are not supported."
                )
        executable = browser if custom else url
        script = (
            "$ErrorActionPreference = 'Stop'; Start-Process -FilePath '"
            + executable.replace("'", "''")
            + "'"
        )
        if custom:
            # Start-Process joins ArgumentList into a Windows command line.
            # list2cmdline preserves the entire URL as one native argument.
            arguments = subprocess.list2cmdline([url])
            script += " -ArgumentList '" + arguments.replace("'", "''") + "'"
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        return [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-EncodedCommand",
            encoded,
        ]
    if sys.platform == "darwin":
        return ["/usr/bin/open", "-a", browser, url] if custom else ["/usr/bin/open", url]
    if sys.platform.startswith("linux"):
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            raise DworkError("Browser launching on Linux requires a graphical desktop session.")
        if custom:
            executable = shutil.which(browser)
            if not executable:
                raise DworkError(
                    "Custom browser executable is unavailable: "
                    + browser
                    + ". Specify one executable name or absolute path, without command-line flags."
                )
            return [executable, url]
        if not shutil.which("xdg-open"):
            raise DworkError("Browser launching on Linux requires xdg-open (xdg-utils).")
        return ["xdg-open", url]
    raise DworkError("Browser launching supports macOS, native Linux desktops, and WSL.")


def prepare_browser(task) -> BrowserLaunch:
    """Resolve a browser opener without HTTP requests or launching applications."""
    command = browser_command(task.url, task.browser)
    wait = sys.platform == "darwin" or bool(os.environ.get("WSL_DISTRO_NAME"))
    return BrowserLaunch(tuple(command), wait)


def preflight_browsers(tasks):
    return tuple(prepare_browser(task) for task in tasks)
