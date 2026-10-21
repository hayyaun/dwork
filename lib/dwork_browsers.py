"""HTTP readiness and OS-default browser launching, including the Windows host on WSL."""
import base64
import http.client
import os
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit

from dwork_common import DworkError, confirm_action


def validate_url(value, where="browser.url"):
    if (not isinstance(value, str) or not value or not value.isascii()
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)):
        raise DworkError(where + " must be an HTTP/HTTPS URL without whitespace or control characters; percent-encode non-ASCII characters.")
    try:
        parts = urlsplit(value)
        port = parts.port
        valid = (parts.scheme in ("http", "https") and parts.hostname
                 and parts.username is None and parts.password is None
                 and "\\" not in value and (port is None or port > 0))
    except ValueError:
        valid = False
    if not valid:
        raise DworkError(where + " must be an absolute HTTP/HTTPS URL without credentials and with a valid port.")
    return value


def browser_command(url):
    # WSL must never fall through to xdg-open, even when Windows interop fails.
    if os.environ.get("WSL_DISTRO_NAME"):
        if not shutil.which("powershell.exe"):
            raise DworkError("Browser launching on WSL requires Windows PowerShell (powershell.exe) and Windows interop; no Linux browser will be opened.")
        script = "$ErrorActionPreference = 'Stop'; Start-Process -FilePath '" + url.replace("'", "''") + "'"
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                "-EncodedCommand", encoded]
    if sys.platform == "darwin":
        return ["/usr/bin/open", url]
    if sys.platform.startswith("linux"):
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            raise DworkError("Browser launching on Linux requires a graphical desktop session.")
        if not shutil.which("xdg-open"):
            raise DworkError("Browser launching on Linux requires xdg-open (xdg-utils).")
        return ["xdg-open", url]
    raise DworkError("Browser launching supports macOS, native Linux desktops, and WSL.")


def preflight_browsers(tasks):
    for task in tasks:
        browser_command(task.url)


def confirm_browser(task):
    return not task.confirm or confirm_action("Open default browser at " + task.url + "?")


def http_status(url, timeout):
    """Fetch headers directly, without proxies, redirects, or downloading a body."""
    parts = urlsplit(url)
    connection_type = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(parts.hostname, parts.port, timeout=timeout)
    try:
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        connection.request("GET", path, headers={"Connection": "close"})
        response = connection.getresponse()
        try:
            return response.status
        finally:
            response.close()
    finally:
        connection.close()


def wait_ready(task):
    if task.wait_url is None:
        return
    deadline = time.monotonic() + task.timeout
    last = "no response"
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DworkError("Browser readiness timed out for " + task.wait_url + " (" + last + "); browser was not opened. Started tasks and containers remain running.")
        try:
            status = http_status(task.wait_url, min(2, remaining))
            if 200 <= status < 400:
                return
            last = "HTTP " + str(status)
        except (OSError, http.client.HTTPException) as error:
            last = str(error)
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(0.25, remaining))


def open_browser(task):
    command = browser_command(task.url)
    if command[0] != "xdg-open":
        # These helpers exit after dispatch. Wait for their real result, rather
        # than assuming slow PowerShell startup means a successful launch.
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                    text=True, timeout=15)
        except subprocess.TimeoutExpired:
            raise DworkError("Default browser dispatch timed out; it may have partially completed. Check the default browser or Windows interop before retrying.")
        if result.returncode:
            raise DworkError("Default browser opener failed: " + (result.stderr.strip() or "exit " + str(result.returncode))
                             + ". Check the default browser association or Windows interop; no alternate browser was opened.")
        return
    # xdg-open may keep running while the browser lives, so detach as with terminals.
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        code = process.wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        return
    if code:
        raise DworkError("Default browser opener failed (exit " + str(code) + "). Check the desktop/browser association or Windows interop; no alternate browser was opened.")
