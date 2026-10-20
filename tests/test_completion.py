"""Shell completion is read-only, dynamic, and works with real Tab input."""
import json
import os
from pathlib import Path
import select
import shlex
import shutil
import subprocess
import time
import unittest

import test_dwork as legacy


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def run_cli(self, args, **kwargs):
        return self.fixture.run_dwork("bash", args, register_current=False, **kwargs)

    def script(self, shell):
        result, changes, calls = self.run_cli("completion " + shell)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        self.assertEqual(calls, [])
        path = self.fixture.base / ("completion." + shell)
        path.write_text(result.stdout)
        return path

    def test_names_api_reads_only_registry_and_aliases_work(self):
        self.fixture.model(self.root, "main")
        result, _, _ = self.run_cli("reg app")
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.fixture.base / "state/dwork/workspaces.json"
        before = state.read_bytes()
        (self.root / "dwork.yml").write_text("version: invalid\n")
        for args in ("list --names", "ls --names"):
            result, changes, calls = self.run_cli(args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "app\n")
            self.assertEqual(calls, [])
            self.assertEqual(changes, [])
            self.assertEqual(state.read_bytes(), before)
        (self.root / "dwork.yml").unlink()
        for args in ("up --dry-run", "sw app --dry-run", "ps"):
            result, changes, _ = self.run_cli(args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(changes, [])
        result, changes, calls = self.run_cli("rm app")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])
        self.assertEqual(changes, [])
        self.assertEqual(json.loads(state.read_text())["workspaces"], [])

    def test_bash_prefix_flags_and_file_paths_with_spaces(self):
        script = self.script("bash")
        (self.root / "compose dev.yaml").write_text("")
        setup = ("source " + shlex.quote(str(script))
                 + "\ndwork() { printf 'alpha\\nbeta\\n'; }\n")
        for words, index, expected in (("dwork sw al", 2, ["alpha"]),
                                       ("dwork rename al", 2, ["alpha"]),
                                       ("dwork sc", 1, ["scan"]),
                                       ("dwork scan --d", 2, ["--dry-run"]),
                                       ("dwork -f comp", 2, ["compose dev.yaml"])):
            command = setup + "COMP_WORDS=(" + words + "); COMP_CWORD=" + str(index) + "; _dwork_complete; printf '%s\\n' \"${COMPREPLY[@]}\""
            result = subprocess.run(["bash", "--noprofile", "--norc", "-c", command],
                                    cwd=self.root, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), expected)

    def test_real_tab_completion_in_bash_and_zsh(self):
        import fcntl
        import pty
        import struct
        import termios
        for shell in ("bash", "zsh"):
            if not shutil.which(shell):
                continue
            with self.subTest(shell=shell):
                script = self.script(shell)
                master, slave = pty.openpty()
                process = None
                try:
                    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 160, 0, 0))
                    env = dict(os.environ, TERM="xterm", INPUTRC="/dev/null", ZDOTDIR=str(self.fixture.base))
                    args = ["bash", "--noprofile", "--norc", "-i"] if shell == "bash" else ["zsh", "-f"]
                    process = subprocess.Popen(args, cwd=self.root, stdin=slave, stdout=slave, stderr=slave, env=env)
                    def until(marker):
                        output = b""
                        deadline = time.monotonic() + 10
                        while marker not in output and time.monotonic() < deadline:
                            if select.select([master], [], [], 0.1)[0]:
                                output += os.read(master, 65536)
                        self.assertIn(marker, output, output.decode(errors="replace"))
                    init = "autoload -Uz compinit; compinit -D -i; " if shell == "zsh" else ""
                    setup = init + "source " + shlex.quote(str(script)) + "; dwork() { if [ \"$1\" = list ]; then printf 'alpha\\nbeta\\n'; else printf 'EXECUTED:%s\\n' \"$*\"; fi; }; printf '\\nREADY\\n'\n"
                    os.write(master, setup.encode())
                    until(b"\r\nREADY\r\n")
                    for typed, result in ((b"dwork sw al\t\n", b"EXECUTED:sw alpha"),
                                          (b"dwork sc\t--d\t\n", b"EXECUTED:scan --dry-run"),
                                          (b"dwork rm be\t\n", b"EXECUTED:rm beta"),
                                          (b"dwork rename al\tnew-name\n", b"EXECUTED:rename alpha new-name")):
                        os.write(master, typed)
                        until(result)
                    os.write(master, b"exit\n")
                    process.wait(timeout=3)
                finally:
                    if process is not None and process.poll() is None:
                        process.kill()
                        process.wait()
                    os.close(master)
                    os.close(slave)

    def test_unsupported_shell_and_names_options_are_errors_without_side_effects(self):
        for args in ("completion", "completion fish", "completion bash extra", "list --names extra"):
            result, changes, calls = self.run_cli(args)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(calls, [])
            self.assertEqual(changes, [])
        self.assertFalse((self.fixture.base / "state").exists())


if __name__ == "__main__":
    unittest.main()
