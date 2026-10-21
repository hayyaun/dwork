"""Check the public source entry point in Bash and Zsh; no Docker is used."""

from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class LoaderTests(unittest.TestCase):
    def shell(self, shell, script, interactive=False):
        args = [shell, "--noprofile", "--norc"] if shell == "bash" else [shell, "-f"]
        if interactive:
            args.append("-i")
        return subprocess.run([*args, "-c", script], cwd=REPO, capture_output=True, text=True)

    def test_noninteractive_source_does_not_generate_or_register_completion(self):
        for shell in ("bash", "zsh"):
            if not shutil.which(shell):
                continue
            with self.subTest(shell=shell):
                init = "autoload -Uz compinit; compinit -D -i; " if shell == "zsh" else ""
                script = (
                    init
                    + r"""
python3() { printf 'UNEXPECTED_GENERATION\n'; return 17; }
. ./dwork.sh
. ./dwork.sh
command -v dwork >/dev/null || exit 21
if [ -n "${BASH_VERSION:-}" ]; then
    if complete -p dwork >/dev/null 2>&1; then exit 22; fi
else
    [[ -z ${_comps[dwork]} ]] || exit 22
fi
printf 'READY\n'
"""
                )
                result = self.shell(shell, script)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "READY\n")

    def test_interactive_source_tolerates_missing_python_and_generation_failure(self):
        for shell in ("bash", "zsh"):
            if not shutil.which(shell):
                continue
            for dependency in (
                "PATH=/missing-dwork-test-bin",
                "python3() { printf 'GENERATION_FAILED\\n' >&2; return 19; }",
            ):
                with self.subTest(shell=shell, dependency=dependency):
                    init = "autoload -Uz compinit; compinit -D -i; " if shell == "zsh" else ""
                    script = (
                        init
                        + dependency
                        + r"""
. ./dwork.sh || exit 21
command -v dwork >/dev/null || exit 22
printf 'READY\n'
"""
                    )
                    result = self.shell(shell, script, interactive=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, "READY\n")
                    self.assertNotIn("GENERATION_FAILED", result.stderr)
                    self.assertNotIn("python3 is required", result.stderr)

    @unittest.skipUnless(shutil.which("zsh"), "Zsh is not installed")
    def test_zsh_requires_existing_compinit_then_registers_on_resourcing(self):
        script = r"""
. ./dwork.sh || exit 21
(( $+functions[compdef] == 0 )) || exit 22
(( $+functions[_dwork] == 0 )) || exit 23
autoload -Uz compinit
compinit -D -i
. ./dwork.sh || exit 24
[[ ${_comps[dwork]} == _dwork ]] || exit 25
printf 'READY\n'
"""
        result = self.shell("zsh", script, interactive=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "READY\n")

    def test_loads_from_another_directory_and_twice(self):
        for shell in ("bash", "zsh"):
            if not shutil.which(shell):
                continue
            with (
                self.subTest(shell=shell),
                tempfile.TemporaryDirectory(prefix="dwork loader ") as temp,
            ):
                directory = Path(temp).resolve()
                root = directory / "repo with spaces"
                root.mkdir()
                shutil.copy2(REPO / "dwork.sh", root / "dwork.sh")
                shutil.copytree(REPO / "lib", root / "lib")
                source = ". " + shlex.quote(str(root / "dwork.sh"))
                script = (
                    source
                    + "\n"
                    + source
                    + r"""
command -v dwork >/dev/null || exit 21
[ -z "${_dwork_file+set}${_dwork_dir+set}" ] || exit 22
printf 'WORKDIR:%s\n' "$PWD"
dwork --help
"""
                )
                result = subprocess.run(
                    [shell, "-c", script], cwd=directory, capture_output=True, text=True
                )
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
                    cwd=REPO,
                    capture_output=True,
                    text=True,
                )
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
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0)

    def test_relative_source_survives_directory_changes_and_resourcing(self):
        for shell in ("bash", "zsh"):
            if not shutil.which(shell):
                continue
            with (
                self.subTest(shell=shell),
                tempfile.TemporaryDirectory(prefix="dwork loader ") as temp,
            ):
                directory = Path(temp).resolve()
                checkout = directory / "checkout with spaces"
                checkout.mkdir()
                shutil.copy2(REPO / "dwork.sh", checkout / "dwork.sh")
                shutil.copytree(REPO / "lib", checkout / "lib")
                script = (
                    ". './checkout with spaces/dwork.sh'\ncd 'checkout with spaces'\n"
                    ". ./dwork.sh\ncd /tmp\ndwork --help\nprintf 'WORKDIR:%s\\n' \"$PWD\""
                )
                result = subprocess.run(
                    [shell, "-c", script], cwd=directory, capture_output=True, text=True
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Usage: dwork", result.stdout)
                self.assertIn("WORKDIR:/tmp", result.stdout)

    def test_does_not_replace_unrelated_user_functions(self):
        for shell in ("bash", "zsh"):
            if not shutil.which(shell):
                continue
            with self.subTest(shell=shell):
                script = (
                    "got() { printf personal; }\n. " + shlex.quote(str(REPO / "dwork.sh")) + "\ngot"
                )
                result = subprocess.run([shell, "-c", script], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "personal")


if __name__ == "__main__":
    unittest.main()
