"""Check the public source entry point in Bash and Zsh; no Docker is used."""
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
            with self.subTest(shell=shell), tempfile.TemporaryDirectory(prefix="dwork loader ") as temp:
                directory = Path(temp).resolve()
                root = directory / "repo with spaces"
                root.mkdir()
                shutil.copy2(REPO / "dwork.sh", root / "dwork.sh")
                shutil.copytree(REPO / "lib", root / "lib")
                source = ". " + shlex.quote(str(root / "dwork.sh"))
                script = source + "\n" + source + r"""
command -v dwork >/dev/null || exit 21
[ -z "${_dwork_file+set}${_dwork_dir+set}" ] || exit 22
printf 'WORKDIR:%s\n' "$PWD"
dwork --help
"""
                result = subprocess.run([shell, "-c", script], cwd=directory,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("WORKDIR:" + str(directory), result.stdout)
                self.assertIn("Never creates", result.stdout)

    def test_relative_source_path(self):
        for shell in ("bash", "zsh"):
            if not shutil.which(shell):
                continue
            with self.subTest(shell=shell):
                result = subprocess.run(
                    [shell, "-c", ". ./dwork.sh\ndwork --help"],
                    cwd=REPO, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Usage: dwork", result.stdout)

    def test_missing_runtime_is_an_error_when_invoked(self):
        for shell in ("bash", "zsh"):
            if not shutil.which(shell):
                continue
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as temp:
                source = Path(temp) / "dwork.sh"
                shutil.copy2(REPO / "dwork.sh", source)
                result = subprocess.run(
                    [shell, "-c", ". " + shlex.quote(str(source)) + "\ndwork --help"],
                    capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)

    def test_does_not_replace_unrelated_user_functions(self):
        for shell in ("bash", "zsh"):
            if not shutil.which(shell):
                continue
            with self.subTest(shell=shell):
                script = "got() { printf personal; }\n. " + shlex.quote(str(REPO / "dwork.sh")) + "\ngot"
                result = subprocess.run([shell, "-c", script], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "personal")

if __name__ == "__main__":
    unittest.main()
