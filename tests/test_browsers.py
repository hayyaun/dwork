"""Browser config, readiness, and host-opener tests; no real servers or GUIs."""

from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch
import base64
import http.client
import io
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import dwork_browsers
import dwork_cli
import dwork_common
import dwork_config
import dwork_registry
import dwork_terminals
from dwork_launch import BrowserLaunch, TerminalLaunch
import dwork_workspaces


def browser(
    url="http://localhost:3000/",
    wait_url="http://localhost:3000/",
    timeout=60,
    confirm=True,
    browser="default",
):
    return SimpleNamespace(
        url=url, wait_url=wait_url, timeout=timeout, confirm=confirm, browser=browser
    )


class BrowserConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def load(self, item):
        import yaml

        config = {"version": 1, "compose": {"enabled": False}, "browsers": [item]}
        (self.root / "dwork.yml").write_text(yaml.safe_dump(config))
        return dwork_config.load_workspace(self.root)

    def test_defaults_wait_for_target_and_require_confirmation(self):
        workspace = self.load({"url": "http://localhost:3000/"})
        self.assertEqual(len(workspace.browsers), 1)
        task = workspace.browsers[0]
        self.assertEqual(task.url, "http://localhost:3000/")
        self.assertEqual(task.wait_url, task.url)
        self.assertEqual(task.timeout, 60)
        self.assertTrue(task.confirm)
        self.assertEqual(task.browser, "default")

    def test_workspace_and_task_confirmation_settings_are_independent(self):
        import yaml

        for root_confirm in (None, True, False):
            expected = True if root_confirm is None else root_confirm
            with self.subTest(root_confirm=root_confirm):
                config = {
                    "version": 1,
                    "compose": {"enabled": False},
                    "terminals": [{"command": ["echo", "ready"], "confirm": not expected}],
                    "browsers": [{"url": "http://localhost:3000/", "confirm": not expected}],
                }
                if root_confirm is not None:
                    config["confirm"] = root_confirm
                (self.root / "dwork.yml").write_text(yaml.safe_dump(config))
                workspace = dwork_config.load_workspace(self.root)
                self.assertEqual(workspace.confirm, expected)
                self.assertEqual(workspace.terminals[0].confirm, not expected)
                self.assertEqual(workspace.browsers[0].confirm, not expected)

    def test_custom_browser_combines_with_no_wait_and_no_confirmation(self):
        task = self.load(
            {
                "url": "http://localhost:3000",
                "browser": "Firefox",
                "wait_for": False,
                "confirm": False,
            }
        ).browsers[0]
        self.assertEqual(task.browser, "Firefox")
        with (
            patch("builtins.input", side_effect=AssertionError("must not prompt")),
            patch.object(
                dwork_browsers, "http_status", side_effect=AssertionError("must not probe")
            ),
        ):
            self.assertTrue(dwork_browsers.confirm_browser(task))
            dwork_browsers.wait_ready(task)

    def test_invalid_browser_names_fail_schema_validation(self):
        for value in (
            None,
            False,
            10,
            [],
            {},
            "",
            " ",
            " firefox",
            "firefox ",
            "-a",
            "firefox\n",
            "firefox\x00",
            "firefox\x7f",
        ):
            with (
                self.subTest(browser=value),
                self.assertRaisesRegex(dwork_common.DworkError, "browser.browser"),
            ):
                self.load({"url": "http://localhost:3000", "browser": value})

    def test_separate_health_endpoint_and_explicit_no_wait(self):
        task = self.load(
            {
                "url": "http://localhost:3000/app?mode=dev#home",
                "confirm": False,
                "wait_for": {"url": "http://localhost:3000/health", "timeout": 12},
            }
        ).browsers[0]
        self.assertEqual(task.url, "http://localhost:3000/app?mode=dev#home")
        self.assertEqual(task.wait_url, "http://localhost:3000/health")
        self.assertEqual(task.timeout, 12)
        self.assertFalse(task.confirm)
        self.assertIsNone(
            self.load({"url": "https://example.com", "wait_for": False}).browsers[0].wait_url
        )

    def test_invalid_url_schemes_credentials_and_controls_are_rejected(self):
        values = [
            None,
            "",
            "localhost:3000",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "http://",
            "http://user:pass@localhost:3000",
            "http://localhost:99999/",
            "http://localhost:3000/a b",
            "http://localhost:3000/a\n",
            "http://localhost:3000/\x00",
            "http://localhost:3000/é",
        ]
        for value in values:
            with self.subTest(url=value), self.assertRaises(dwork_common.DworkError):
                self.load({"url": value})

    def test_invalid_options_do_not_silently_coerce_values(self):
        values = [
            {"url": "http://localhost:3000", "unknown": True},
            {"url": "http://localhost:3000", "confirm": "false"},
            {"url": "http://localhost:3000", "confirm": 0},
            {"url": "http://localhost:3000", "wait_for": True},
            {"url": "http://localhost:3000", "wait_for": {"port": 3000}},
            {"url": "http://localhost:3000", "wait_for": {"url": "file:///tmp/ready"}},
        ]
        values += [
            {"url": "http://localhost:3000", "wait_for": {"timeout": timeout}}
            for timeout in (0, -1, 3601, True, "60", float("inf"), float("nan"))
        ]
        for value in values:
            with self.subTest(value=value), self.assertRaises(dwork_common.DworkError):
                self.load(value)

    def test_absent_browsers_preserves_existing_workspace(self):
        (self.root / "dwork.yml").write_text("version: 1\ncompose: {enabled: false}\n")
        self.assertEqual(dwork_config.load_workspace(self.root).browsers, [])


class BrowserConfirmationTests(unittest.TestCase):
    def test_default_confirmation_accepts_only_yes(self):
        for answer in ("", "n", "no", "yes"):
            with self.subTest(answer=answer), patch("builtins.input", return_value=answer):
                self.assertFalse(dwork_browsers.confirm_browser(browser()))
        for answer in ("y", "Y", " y "):
            with self.subTest(answer=answer), patch("builtins.input", return_value=answer):
                self.assertTrue(dwork_browsers.confirm_browser(browser()))
        with patch("builtins.input", side_effect=EOFError):
            self.assertFalse(dwork_browsers.confirm_browser(browser()))

    def test_explicit_false_skips_prompt(self):
        with patch("builtins.input", side_effect=AssertionError("must not prompt")):
            self.assertTrue(dwork_browsers.confirm_browser(browser(confirm=False)))


class BrowserReadinessTests(unittest.TestCase):
    def test_get_preserves_query_omits_fragment_and_closes_connection(self):
        connection = Mock()
        connection.getresponse.return_value.status = 200
        with patch.object(http.client, "HTTPConnection", return_value=connection) as factory:
            dwork_browsers.wait_ready(
                browser(wait_url="http://localhost:3000/health?ready=1#ignored")
            )
        self.assertEqual(factory.call_args.args[:2], ("localhost", 3000))
        self.assertEqual(connection.request.call_args.args[:2], ("GET", "/health?ready=1"))
        connection.close.assert_called()
        connection.getresponse.return_value.close.assert_called_once()

    def test_https_uses_verified_stdlib_connection(self):
        connection = Mock()
        connection.getresponse.return_value.status = 204
        with patch.object(http.client, "HTTPSConnection", return_value=connection) as https:
            dwork_browsers.wait_ready(browser(wait_url="https://localhost:3443/ready"))
        self.assertEqual(https.call_args.args[:2], ("localhost", 3443))
        self.assertNotIn("context", https.call_args.kwargs)
        connection.close.assert_called()

    def test_redirect_response_is_ready_without_following_it(self):
        connection = Mock()
        connection.getresponse.return_value.status = 302
        with patch.object(http.client, "HTTPConnection", return_value=connection) as factory:
            dwork_browsers.wait_ready(browser())
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(connection.request.call_count, 1)

    def test_unready_responses_retry_then_succeed(self):
        connection = Mock()
        connection.getresponse.side_effect = [Mock(status=503), Mock(status=200)]
        with patch.object(http.client, "HTTPConnection", return_value=connection):
            with patch("time.sleep"):
                dwork_browsers.wait_ready(browser())
        self.assertEqual(connection.request.call_count, 2)
        self.assertEqual(connection.close.call_count, 2)

    def test_connection_errors_timeout_without_opening_browser(self):
        connection = Mock()
        connection.request.side_effect = ConnectionRefusedError("not listening")
        with patch.object(http.client, "HTTPConnection", return_value=connection):
            with patch("time.monotonic", side_effect=[0, 0, 61, 61, 61]):
                with patch("time.sleep"), self.assertRaises(dwork_common.DworkError):
                    dwork_browsers.wait_ready(browser())
        connection.close.assert_called()

    def test_wait_disabled_does_not_contact_network(self):
        with patch.object(
            http.client, "HTTPConnection", side_effect=AssertionError("must not probe")
        ):
            with patch.object(
                http.client, "HTTPSConnection", side_effect=AssertionError("must not probe")
            ):
                dwork_browsers.wait_ready(browser(wait_url=None))


class BrowserOpenerTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(
            os.environ, {"WSL_DISTRO_NAME": "", "DISPLAY": ":test", "WAYLAND_DISPLAY": ""}
        )
        environment.start()
        self.addCleanup(environment.stop)

    def test_wsl_uses_windows_default_even_when_linux_desktop_exists(self):
        url = "http://localhost:3000/?q=';$(Get-Process)&other=ok"
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}):
            with patch("shutil.which", return_value="/mnt/c/Windows/powershell.exe"):
                command = dwork_browsers.browser_command(url)
        self.assertEqual(command[0], "powershell.exe")
        script = base64.b64decode(command[command.index("-EncodedCommand") + 1]).decode("utf-16le")
        self.assertIn("Start-Process -FilePath '" + url.replace("'", "''") + "'", script)
        self.assertIn("$ErrorActionPreference = 'Stop'", script)
        self.assertEqual(command[command.index("-WindowStyle") + 1], "Hidden")
        self.assertNotIn("xdg-open", command)

    def test_wsl_interop_failure_never_falls_back_to_linux_browser(self):
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}):
            with patch(
                "shutil.which",
                side_effect=lambda name: "/usr/bin/xdg-open" if name == "xdg-open" else None,
            ):
                with self.assertRaises(dwork_common.DworkError):
                    dwork_browsers.preflight_browsers([browser()])

    def test_native_defaults_use_os_openers_and_keep_url_as_one_argument(self):
        url = "https://example.com/?a=one&b='two'"
        with patch.object(sys, "platform", "darwin"):
            self.assertEqual(dwork_browsers.browser_command(url), ["/usr/bin/open", url])
        with (
            patch.object(sys, "platform", "linux"),
            patch("shutil.which", return_value="/usr/bin/xdg-open"),
        ):
            self.assertEqual(dwork_browsers.browser_command(url), ["xdg-open", url])

    def test_custom_macos_application_is_one_argument(self):
        url = "https://example.com/?q=one&other='two'"
        with patch.object(sys, "platform", "darwin"):
            for application in ("Firefox", "Google Chrome", "/Applications/Firefox.app"):
                self.assertEqual(
                    dwork_browsers.browser_command(url, application),
                    ["/usr/bin/open", "-a", application, url],
                )

    def test_custom_linux_browser_resolves_executable_and_detaches(self):
        url = "http://localhost:3000/?q=$(touch%20injected)&other='two'"
        process = Mock()
        process.wait.side_effect = subprocess.TimeoutExpired("firefox", 0.2)
        with (
            patch.object(sys, "platform", "linux"),
            patch("shutil.which", return_value="/opt/Browser With Spaces/firefox") as which,
            patch.object(subprocess, "Popen", return_value=process) as popen,
            patch.object(subprocess, "run") as run,
        ):
            dwork_browsers.open_browser(browser(url=url, browser="firefox"))
        which.assert_called_once_with("firefox")
        self.assertEqual(popen.call_args.args[0], ["/opt/Browser With Spaces/firefox", url])
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertNotIn("shell", popen.call_args.kwargs)
        run.assert_not_called()

    def test_missing_custom_linux_browser_does_not_fall_back(self):
        with (
            patch.object(sys, "platform", "linux"),
            patch("shutil.which", return_value=None) as which,
        ):
            with self.assertRaisesRegex(dwork_common.DworkError, "Custom browser executable"):
                dwork_browsers.preflight_browsers([browser(browser="missing-browser")])
        which.assert_called_once_with("missing-browser")

    def test_wsl_custom_browser_and_url_are_literal_windows_arguments(self):
        executable = r"C:\Program Files\Browser's Folder\firefox.exe"
        url = 'http://localhost:3000/?q="hello"&other=\'$(Get-Process);ok'
        with (
            patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}),
            patch("shutil.which", return_value="/Windows/powershell.exe") as which,
        ):
            command = dwork_browsers.browser_command(url, executable)
        script = base64.b64decode(command[-1]).decode("utf-16le")
        self.assertIn(
            "Start-Process -FilePath 'C:\\Program Files\\Browser''s Folder\\firefox.exe'", script
        )
        self.assertIn("http://localhost:3000/?q=\\\"hello\\\"&other=''$(Get-Process);ok", script)
        self.assertIn("-ArgumentList '", script)
        which.assert_called_once_with("powershell.exe")
        self.assertNotIn("xdg-open", command)

    def test_wsl_rejects_linux_and_relative_paths_before_launch(self):
        for executable in (
            "firefox",
            "/usr/bin/firefox",
            "/mnt/c/Firefox/firefox.exe",
            r"relative\firefox.exe",
            r"C:firefox.exe",
            "firefox.exe --private",
        ):
            with (
                self.subTest(executable=executable),
                patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}),
                patch("shutil.which", return_value="/Windows/powershell.exe"),
                patch.object(subprocess, "run") as run,
            ):
                with self.assertRaisesRegex(dwork_common.DworkError, "Windows .exe"):
                    dwork_browsers.preflight_browsers([browser(browser=executable)])
                run.assert_not_called()

    def test_confirmation_names_selected_browser(self):
        with patch("builtins.input", return_value="y") as prompt:
            self.assertTrue(dwork_browsers.confirm_browser(browser(browser="Firefox")))
        self.assertIn("browser 'Firefox'", prompt.call_args.args[0])

    def test_headless_linux_and_missing_opener_fail_preflight(self):
        with patch.object(sys, "platform", "linux"):
            with patch.dict(os.environ, {"DISPLAY": "", "WAYLAND_DISPLAY": ""}):
                with self.assertRaises(dwork_common.DworkError):
                    dwork_browsers.preflight_browsers([browser()])
            with (
                patch("shutil.which", return_value=None),
                self.assertRaises(dwork_common.DworkError),
            ):
                dwork_browsers.preflight_browsers([browser()])

    def test_linux_opener_detaches_without_shell_and_reports_failure(self):
        process = Mock()
        process.wait.side_effect = subprocess.TimeoutExpired("xdg-open", 0.2)
        with (
            patch.object(sys, "platform", "linux"),
            patch("shutil.which", return_value="/usr/bin/xdg-open"),
        ):
            with patch.object(subprocess, "Popen", return_value=process) as popen:
                dwork_browsers.open_browser(browser())
                self.assertEqual(popen.call_args.args[0], ["xdg-open", "http://localhost:3000/"])
                self.assertTrue(popen.call_args.kwargs["start_new_session"])
                self.assertEqual(popen.call_args.kwargs["stdin"], subprocess.DEVNULL)
                self.assertNotIn("shell", popen.call_args.kwargs)
                process.wait.side_effect = None
                process.wait.return_value = 4
                with self.assertRaises(dwork_common.DworkError):
                    dwork_browsers.open_browser(browser())

    def test_macos_and_wsl_wait_for_dispatch_result_without_shell(self):
        for platform, distro, executable in (
            ("darwin", "", "/usr/bin/open"),
            ("linux", "Ubuntu", "powershell.exe"),
        ):
            with (
                self.subTest(platform=platform, distro=distro),
                patch.object(sys, "platform", platform),
            ):
                with (
                    patch.dict(os.environ, {"WSL_DISTRO_NAME": distro}),
                    patch("shutil.which", return_value="/Windows/powershell.exe"),
                ):
                    with patch.object(
                        subprocess, "run", return_value=Mock(returncode=0, stderr="")
                    ) as run:
                        with patch.object(subprocess, "Popen") as popen:
                            dwork_browsers.open_browser(browser())
                    self.assertEqual(run.call_args.args[0][0], executable)
                    self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
                    self.assertTrue(run.call_args.kwargs["capture_output"])
                    self.assertGreater(run.call_args.kwargs["timeout"], 0)
                    self.assertNotIn("shell", run.call_args.kwargs)
                    popen.assert_not_called()

    def test_macos_and_wsl_dispatch_error_or_timeout_never_falls_back(self):
        for platform, distro in (("darwin", ""), ("linux", "Ubuntu")):
            with (
                self.subTest(platform=platform, distro=distro),
                patch.object(sys, "platform", platform),
            ):
                with (
                    patch.dict(os.environ, {"WSL_DISTRO_NAME": distro}),
                    patch("shutil.which", return_value="/Windows/powershell.exe"),
                ):
                    with patch.object(
                        subprocess,
                        "run",
                        return_value=Mock(returncode=1, stderr="association unavailable"),
                    ) as run:
                        with patch.object(subprocess, "Popen") as popen:
                            with self.assertRaisesRegex(
                                dwork_common.DworkError, "association unavailable"
                            ):
                                dwork_browsers.open_browser(browser())
                            run.side_effect = subprocess.TimeoutExpired("opener", 15)
                            with self.assertRaisesRegex(dwork_common.DworkError, "timed out"):
                                dwork_browsers.open_browser(browser())
                    self.assertEqual(run.call_count, 2)
                    popen.assert_not_called()


class BrowserLifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.task = dwork_common.TerminalTask("Frontend", ["npm", "run", "dev"], self.root)
        self.browser = browser()
        self.workspace = dwork_common.Workspace(
            "app", self.root, {}, enabled=False, terminals=[self.task], browsers=[self.browser]
        )
        self.entry = dwork_registry.registration(self.root, [], [self.workspace], None, "app")
        self.terminal_launch = TerminalLaunch(
            ("fake-terminal",), self.root, "gnome-terminal", "Frontend"
        )
        self.browser_launch = BrowserLaunch(("fake-browser",), False)
        patches = [
            patch.object(dwork_config, "discover", return_value=([self.workspace], False)),
            patch.object(dwork_config, "registration_directory", return_value=self.root),
            patch.object(dwork_registry, "refresh_locks", return_value=False),
            patch.object(
                dwork_registry, "save_registry", side_effect=AssertionError("must not write")
            ),
            patch.object(
                dwork_terminals,
                "preflight_terminals",
                side_effect=lambda tasks: tuple(self.terminal_launch for task in tasks),
            ),
            patch.object(
                dwork_browsers,
                "preflight_browsers",
                side_effect=lambda tasks: tuple(self.browser_launch for task in tasks),
            ),
            patch.object(dwork_terminals, "confirm_terminal", return_value=True),
            patch.object(dwork_terminals, "open_terminal"),
            patch.object(dwork_browsers, "confirm_browser", return_value=True),
            patch.object(dwork_browsers, "wait_ready"),
            patch.object(dwork_browsers, "open_browser"),
            patch("sys.stdout", new_callable=io.StringIO),
        ]
        self.mocks = [item.start() for item in patches]
        for item in patches:
            self.addCleanup(item.stop)

    def switch(self, preview=False):
        return dwork_workspaces.switch_workspace(self.root, [], "switch", preview, [self.entry])

    def planned_task(self):
        return replace(self.task, workspace=str(self.root), directory=str(self.root), project="app")

    def test_servers_launch_before_browser_readiness_and_open(self):
        calls = []
        self.mocks[7].side_effect = lambda task, **kwargs: calls.append("terminal")
        self.mocks[9].side_effect = lambda task: calls.append("ready")
        self.mocks[10].side_effect = lambda task, **kwargs: calls.append("browser")
        self.assertEqual(self.switch(), 0)
        self.assertEqual(calls, ["terminal", "ready", "browser"])
        self.assertEqual(self.switch(), 0)
        self.assertEqual(calls, ["terminal", "ready", "browser"] * 2)

    def test_declined_activation_never_launches_tasks_or_probes_browsers(self):
        with patch("builtins.input", return_value="n"):
            self.assertEqual(
                dwork_workspaces.switch_workspace(self.root, [], "activate", False, [self.entry]), 0
            )
        for operation in self.mocks[6:11]:
            operation.assert_not_called()

    def test_root_confirm_false_keeps_terminal_and_browser_consent_separate(self):
        self.workspace.confirm = False
        with patch("builtins.input", side_effect=AssertionError("activation must not prompt")):
            self.assertEqual(
                dwork_workspaces.switch_workspace(self.root, [], "activate", False, [self.entry]), 0
            )
        self.mocks[6].assert_called_once_with(self.planned_task())
        self.assertIsNone(self.task.workspace)
        self.mocks[8].assert_called_once_with(self.browser)

    def test_dry_run_has_no_preflight_prompt_probe_or_launch(self):
        self.assertEqual(self.switch(preview=True), 0)
        for operation in self.mocks[4:11]:
            operation.assert_not_called()
        self.assertIn("Would open default browser", self.mocks[11].getvalue())
        self.assertIn("Would wait for HTTP readiness", self.mocks[11].getvalue())

    def test_declining_browser_skips_readiness_and_open(self):
        self.mocks[8].return_value = False
        self.assertEqual(self.switch(), 0)
        self.mocks[9].assert_not_called()
        self.mocks[10].assert_not_called()

    def test_readiness_failure_leaves_dispatched_terminal_and_stops_remaining_browsers(self):
        later = browser(url="http://localhost:3001/", wait_url="http://localhost:3001/")
        self.workspace.browsers.append(later)
        self.mocks[9].side_effect = dwork_common.DworkError("not ready")
        with patch("sys.stderr", new_callable=io.StringIO) as errors:
            with self.assertRaises(dwork_common.DworkError):
                self.switch()
        self.mocks[7].assert_called_once_with(self.planned_task(), launch=self.terminal_launch)
        self.assertIsNone(self.task.workspace)
        self.mocks[8].assert_called_once_with(self.browser)
        self.mocks[9].assert_called_once_with(self.browser)
        self.mocks[10].assert_not_called()
        self.assertIn("Switch incomplete at: browser http://localhost:3000/", errors.getvalue())
        self.assertIn("Completed: launched terminal Frontend", errors.getvalue())
        self.assertIn("browser http://localhost:3001/", errors.getvalue())
        self.assertIn("No automatic rollback", errors.getvalue())

    def test_missing_browser_prerequisite_blocks_terminal_launch(self):
        self.mocks[5].side_effect = dwork_common.DworkError("no Windows interop")
        with self.assertRaises(dwork_common.DworkError):
            self.switch()
        self.mocks[7].assert_not_called()

    def test_doctor_checks_opener_only_without_requesting_or_opening_url(self):
        self.assertEqual(dwork_cli.doctor(self.root, []), 0)
        self.mocks[5].assert_called_once_with([self.browser])
        for operation in self.mocks[7:11]:
            operation.assert_not_called()
        self.assertIn("Browser opener", self.mocks[11].getvalue())

    def test_doctor_reports_actionable_opener_failure_without_requesting_url(self):
        self.mocks[5].side_effect = dwork_common.DworkError("no Windows interop")
        with patch("sys.stderr", new_callable=io.StringIO) as errors:
            self.assertEqual(dwork_cli.doctor(self.root, []), 1)
        self.assertIn("no Windows interop", errors.getvalue())
        self.assertIn("Fix:", errors.getvalue())
        self.assertIn("Windows PowerShell", errors.getvalue())
        for operation in self.mocks[7:11]:
            operation.assert_not_called()

    def test_status_and_registration_do_not_preflight_probe_or_open_browser(self):
        self.assertEqual(
            dwork_workspaces.switch_workspace(self.root, [], "status", False, [self.entry]), 0
        )
        self.mocks[3].side_effect = None
        self.assertEqual(
            dwork_workspaces.switch_workspace(self.root, [], "register", False, [self.entry]), 0
        )
        self.mocks[3].assert_called_once()
        for operation in self.mocks[4:11]:
            operation.assert_not_called()


if __name__ == "__main__":
    unittest.main()
