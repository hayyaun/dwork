"""Tests use a fake Git executable and never stage, commit, or push real files."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / ".shell_functions"
FAKE_GIT = r"""#!/usr/bin/env python3
import json, os, sys
with open(os.environ["GOT_TEST_LOG"], "a") as stream:
    stream.write(json.dumps(sys.argv[1:]) + "\n")
if sys.argv[1] == os.environ.get("GOT_TEST_FAIL"):
    sys.exit(7)
"""

class GotTests(unittest.TestCase):
    def run_got(self, shell, args, fail=""):
        with tempfile.TemporaryDirectory(prefix="shellfunx-got-") as temp:
            root = Path(temp)
            executable = root / "git"
            executable.write_text(FAKE_GIT)
            executable.chmod(0o755)
            log = root / "git.jsonl"
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                       GOT_TEST_LOG=str(log), GOT_TEST_FAIL=fail)
            script = ". " + shlex.quote(str(SOURCE)) + "\ngot"
            if args:
                script += " " + " ".join(shlex.quote(arg) for arg in args)
            result = subprocess.run([shell, "-c", script], env=env, cwd=temp,
                                    capture_output=True, text=True)
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            return result, calls

    def shells(self):
        found = [shell for shell in ("bash", "zsh") if shutil.which(shell)]
        self.assertTrue(found)
        return found

    def test_subject_only(self):
        for shell in self.shells():
            with self.subTest(shell=shell):
                result, calls = self.run_got(shell, ["Fix checkout"])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [["add", "."], ["commit", "-m", "Fix checkout"], ["push"]])

    def test_optional_body_preserves_message(self):
        subject = 'Fix "checkout" and $billing'
        body = "Keep spaces and apostrophes: user's order.\nSecond line."
        for shell in self.shells():
            with self.subTest(shell=shell):
                result, calls = self.run_got(shell, [subject, body])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [["add", "."], ["commit", "-m", subject, "-m", body], ["push"]])

    def test_invalid_arguments_run_no_git(self):
        for shell in self.shells():
            for args in ([], [""], ["", "body"], ["one", "two", "three"]):
                with self.subTest(shell=shell, args=args):
                    result, calls = self.run_got(shell, args)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(calls, [])
                    self.assertIn("Usage: got", result.stderr)

    def test_failure_stops_chain_and_preserves_status(self):
        expected = {"add": [["add", "."]],
                    "commit": [["add", "."], ["commit", "-m", "subject"]],
                    "push": [["add", "."], ["commit", "-m", "subject"], ["push"]]}
        for shell in self.shells():
            for fail, calls_expected in expected.items():
                with self.subTest(shell=shell, fail=fail):
                    result, calls = self.run_got(shell, ["subject"], fail)
                    self.assertEqual(result.returncode, 7)
                    self.assertEqual(calls, calls_expected)

if __name__ == "__main__":
    unittest.main()
