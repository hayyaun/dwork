"""Exercise CI completion discovery with safe and unsafe function paths."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix" and shutil.which("zsh"), "Zsh is not installed")
class PackagingSmokeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dwork-compinit-smoke-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.secure = self.root / "secure"
        self.insecure = self.root / "insecure"
        self.secure.mkdir(mode=0o700)
        self.insecure.mkdir(mode=0o700)
        self.insecure.chmod(0o777)
        (self.secure / "_dwork").write_text("#compdef dwork\n")
        # The same function name must not shadow the trusted completion.
        (self.insecure / "_dwork").write_text("#compdef dwork-untrusted\n")
        default = subprocess.run(
            ["zsh", "-fc", "print -rl -- $fpath"],
            text=True,
            capture_output=True,
            check=True,
            timeout=15,
        ).stdout.splitlines()
        self.environment = {
            **os.environ,
            "HOME": str(self.root),
            "FPATH": os.pathsep.join(map(str, [self.insecure, self.secure, *default])),
        }
        workflow = yaml.safe_load((ROOT / ".github/workflows/packaging.yml").read_text())
        self.command = next(
            step["run"]
            for step in workflow["jobs"]["debian"]["steps"]
            if step.get("name") == "Check installed Debian Zsh completion"
        )

    def smoke(self):
        return subprocess.run(
            ["bash", "-c", self.command],
            env=self.environment,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            timeout=20,
            start_new_session=True,
        )

    def test_ci_discovers_trusted_completion_and_rejects_insecure_shadow(self):
        result = self.smoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertFalse((self.root / ".zcompdump").exists())

    def test_ci_fails_when_the_dwork_completion_itself_is_insecure(self):
        self.secure.chmod(0o777)
        result = self.smoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("initialization aborted", result.stderr)


if __name__ == "__main__":
    unittest.main()
