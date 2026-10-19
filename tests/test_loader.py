"""Loader checks for both supported shells; no Docker daemon is used."""
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]

class LoaderTests(unittest.TestCase):
    def test_loads_from_another_directory_and_twice(self):
        for shell in ("bash", "zsh"):
            if not shutil.which(shell):
                continue
            with self.subTest(shell=shell), tempfile.TemporaryDirectory(prefix="shellfunx loader ") as temp:
                root = Path(temp) / "repo with spaces"
                root.mkdir()
                shutil.copy2(REPO / ".shell_functions", root / ".shell_functions")
                shutil.copytree(REPO / "functions", root / "functions")
                source = ". " + shlex.quote(str(root / ".shell_functions"))
                script = source + "\n" + source + r"""
command -v dwork >/dev/null || exit 21
[ -z "${_shellfunx_file+set}${_shellfunx_dir+set}" ] || exit 22
printf 'WORKDIR:%s\n' "$PWD"
dwork --help
"""
                result = subprocess.run([shell, "-c", script], cwd=temp,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("WORKDIR:" + temp, result.stdout)
                self.assertIn("Never creates", result.stdout)

    def test_relative_source_path(self):
        for shell in ("bash", "zsh"):
            if not shutil.which(shell):
                continue
            with self.subTest(shell=shell):
                result = subprocess.run(
                    [shell, "-c", ". ./.shell_functions\ndwork --help"],
                    cwd=REPO, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Usage: dwork", result.stdout)

    def test_module_can_be_sourced_directly(self):
        for shell in ("bash", "zsh"):
            if not shutil.which(shell):
                continue
            with self.subTest(shell=shell):
                result = subprocess.run(
                    [shell, "-c", ". " + shlex.quote(str(REPO / "functions/dwork.sh")) + "\ndwork --help"],
                    cwd="/tmp", capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_module_is_an_error(self):
        for shell in ("bash", "zsh"):
            if not shutil.which(shell):
                continue
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as temp:
                source = Path(temp) / ".shell_functions"
                shutil.copy2(REPO / ".shell_functions", source)
                result = subprocess.run(
                    [shell, "-c", ". " + shlex.quote(str(source))],
                    capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)

if __name__ == "__main__":
    unittest.main()
