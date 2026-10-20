"""ANSI presentation never changes commands, plain logs, or confirmation policy."""
import contextlib
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from test_dwork_config import runtime


class TTY(io.StringIO):
    def isatty(self):
        return True


class ColorTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"TERM": "xterm-256color", "NO_COLOR": ""})
        environment.start()
        self.addCleanup(environment.stop)

    def test_color_uses_semantic_styles_only_on_tty(self):
        with contextlib.redirect_stdout(TTY()):
            self.assertEqual(runtime.color("Started: api", "start"), "\033[32mStarted: api\033[0m")
            self.assertEqual(runtime.color("Stopped: api", "stop"), "\033[31mStopped: api\033[0m")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runtime.colored_name("Backend"), "Backend")

    def test_no_color_and_dumb_term_override_tty(self):
        for environment in ({"NO_COLOR": "1"}, {"NO_COLOR": "0"}, {"TERM": "dumb"}):
            with patch.dict(os.environ, environment), contextlib.redirect_stdout(TTY()):
                self.assertEqual(runtime.colored_name("Backend"), "Backend")

    def test_names_are_stable_and_display_can_include_quotes(self):
        with contextlib.redirect_stdout(TTY()):
            first = runtime.colored_name("Backend")
            self.assertEqual(first, runtime.colored_name("Backend"))
            quoted = runtime.colored_name("Backend", repr("Backend"))
            self.assertEqual(first.split("m")[0], quoted.split("m")[0])
            self.assertIn("'Backend'", quoted)

    def test_stderr_detection_is_independent(self):
        with contextlib.redirect_stdout(TTY()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(runtime.color("warning", "warning", runtime.sys.stderr), "warning")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(TTY()):
            self.assertIn("\033[33m", runtime.color("warning", "warning", runtime.sys.stderr))

    def test_prompt_highlights_title_and_command_without_changing_consent(self):
        task = runtime.TerminalTask("Backend", ["make", "run"], Path("/tmp"))
        with contextlib.redirect_stdout(TTY()), patch("builtins.input", return_value="n") as ask:
            self.assertFalse(runtime.confirm_terminal(task))
            prompt = ask.call_args.args[0]
            self.assertIn(runtime.colored_name("Backend", repr("Backend")), prompt)
            self.assertIn("\033[1mmake run\033[0m", prompt)
            self.assertTrue(prompt.endswith("? (y/N) "))

    def test_status_highlights_health_and_state(self):
        workspace = runtime.Workspace("api", Path("/tmp"), {"web": {}})
        item = {"Id": "abc", "Config": {"Labels": {"com.docker.compose.project": "api",
                "com.docker.compose.service": "web"}}, "State": {"Status": "running"}}
        for health, code in (("healthy", "32"), ("unhealthy", "31"), ("starting", "33")):
            item["State"]["Health"] = {"Status": health}
            with contextlib.redirect_stdout(TTY()) as output:
                runtime.show_status([workspace], [item])
            self.assertIn("\033[" + code + "mrunning, " + health, output.getvalue())


if __name__ == "__main__":
    unittest.main()
