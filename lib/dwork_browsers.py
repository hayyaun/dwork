"""Per-browser consent, HTTP readiness, and dispatch of prepared browser launches."""
import http.client
import subprocess
import time
from urllib.parse import urlsplit

from dwork_common import DworkError, confirm_action
from dwork_launch import BrowserLaunch
from dwork_browser_launch import (browser_command, preflight_browsers, prepare_browser,
                                  validate_browser, validate_url)


def browser_label(task):
    return "default browser" if task.browser == "default" else "browser " + repr(task.browser)


def confirm_browser(task):
    return not task.confirm or confirm_action("Open " + browser_label(task) + " at " + task.url + "?")


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


def open_browser(task, *, launch: BrowserLaunch | None = None):
    launch = launch if launch is not None else prepare_browser(task)
    command = list(launch.arguments)
    if launch.wait_for_dispatch:
        # These helpers exit after dispatch. Wait for their real result, rather
        # than assuming slow PowerShell startup means a successful launch.
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                    text=True, timeout=15)
        except subprocess.TimeoutExpired:
            raise DworkError("Browser dispatch timed out; it may have partially completed. Check the selected browser or Windows interop before retrying.")
        if result.returncode:
            raise DworkError("Browser opener failed: " + (result.stderr.strip() or "exit " + str(result.returncode))
                             + ". Check the selected browser or Windows interop; no alternate browser was opened.")
        return
    # Native Linux browsers and xdg-open can stay alive; detach as with terminals.
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        code = process.wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        return
    if code:
        raise DworkError("Browser opener failed (exit " + str(code) + "). Check the selected browser and graphical session; no alternate browser was opened.")
