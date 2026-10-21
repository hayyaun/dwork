"""ANSI presentation never changes commands, plain logs, or confirmation policy."""

from pathlib import Path
from unittest.mock import patch
import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import dwork_common
import dwork_docker
import dwork_terminals


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
            self.assertEqual(dwork_common.color("Started: api", "start"), "\033[32mStarted: api\033[0m")
            self.assertEqual(dwork_common.color("Stopped: api", "stop"), "\033[31mStopped: api\033[0m")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(dwork_common.colored_name("Backend"), "Backend")

    def test_no_color_and_dumb_term_override_tty(self):
        for environment in ({"NO_COLOR": "1"}, {"NO_COLOR": "0"}, {"TERM": "dumb"}):
            with patch.dict(os.environ, environment), contextlib.redirect_stdout(TTY()):
                self.assertEqual(dwork_common.colored_name("Backend"), "Backend")

    def test_names_are_stable_and_display_can_include_quotes(self):
        with contextlib.redirect_stdout(TTY()):
            first = dwork_common.colored_name("Backend")
            self.assertEqual(first, dwork_common.colored_name("Backend"))
            quoted = dwork_common.colored_name("Backend", repr("Backend"))
            self.assertEqual(first.split("m")[0], quoted.split("m")[0])
            self.assertIn("'Backend'", quoted)

    def test_stderr_detection_is_independent(self):
        with contextlib.redirect_stdout(TTY()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(dwork_common.color("warning", "warning", sys.stderr), "warning")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(TTY()):
            self.assertIn("\033[33m", dwork_common.color("warning", "warning", sys.stderr))

    def test_prompt_highlights_title_and_command_without_changing_consent(self):
        task = dwork_common.TerminalTask("Backend", ["make", "run"], Path("/tmp"))
        with contextlib.redirect_stdout(TTY()), patch("builtins.input", return_value="n") as ask:
            self.assertFalse(dwork_terminals.confirm_terminal(task))
            prompt = ask.call_args.args[0]
            self.assertIn(dwork_common.colored_name("Backend", repr("Backend")), prompt)
            self.assertIn("\033[1mmake run\033[0m", prompt)
            self.assertTrue(prompt.endswith("? (y/N) "))

    def test_status_highlights_health_and_state(self):
        workspace = dwork_common.Workspace("api", Path("/tmp"), {"web": {}})
        item = {"Id": "abc", "Config": {"Labels": {"com.docker.compose.project": "api",
                "com.docker.compose.service": "web"}}, "State": {"Status": "running"}}
        for health, code in (("healthy", "32"), ("unhealthy", "31"), ("starting", "33")):
            item["State"]["Health"] = {"Status": health}
            with contextlib.redirect_stdout(TTY()) as output:
                dwork_docker.show_status([workspace], [item])
            self.assertIn("\033[" + code + "mrunning, " + health, output.getvalue())


if __name__ == "__main__":
    unittest.main()
