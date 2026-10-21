"""Shell completion is read-only, dynamic, and works with real Tab input."""
import json
import os
from pathlib import Path
import select
import shlex
import shutil
import subprocess
import sys
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
                                       ("dwork --v", 1, ["--version"]),
                                       ("dwork in", 1, ["init"]),
                                       ("dwork val", 1, ["validate"]),
                                       ("dwork init --d", 2, ["--dry-run"]),
                                       ("dwork validate --p", 2, ["--project-name", "--project-directory", "--profile"]),
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
        for shell, mode in (("bash", "manual"), ("zsh", "manual"),
                            ("zsh", "installed"), ("bash", "installed"),
                            ("bash", "source"), ("zsh", "source")):
            autoload = mode == "installed"
            if not shutil.which(shell):
                continue
            if shell == "bash" and autoload and not Path("/usr/share/bash-completion/bash_completion").is_file():
                continue
            with self.subTest(shell=shell, mode=mode):
                script = self.script(shell)
                if mode == "source":
                    script = legacy.SOURCE
                if autoload:
                    prefix = self.fixture.base / ("installed prefix" if shell == "zsh" else "installed-prefix")
                    installed = subprocess.run([
                        sys.executable, str(legacy.SOURCE.parent / "scripts/install.py"),
                        "install", "--prefix", str(prefix), "--venv", "0",
                    ], text=True, capture_output=True)
                    self.assertEqual(installed.returncode, 0, installed.stderr)
                    script = prefix / "share/zsh/site-functions/_dwork"
                master, slave = pty.openpty()
                process = None
                try:
                    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 160, 0, 0))
                    env = dict(os.environ, TERM="xterm", INPUTRC="/dev/null", ZDOTDIR=str(self.fixture.base))
                    if autoload and shell == "bash":
                        env.update(XDG_DATA_HOME=str(prefix / "share"),
                                   BASH_COMPLETION_USER_DIR=str(prefix / "share/bash-completion"),
                                   BASH_COMPLETION_USER_FILE="/dev/null")
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
                    load = "source " + shlex.quote(str(script)) + "; "
                    if mode == "source":
                        load += load  # Re-sourcing must leave completion usable.
                    if autoload:
                        if shell == "zsh":
                            init = "fpath=(" + shlex.quote(str(script.parent)) + " $fpath); " + init
                            load = ""
                        else:
                            load = "source /usr/share/bash-completion/bash_completion; "
                    setup = init + load + "dwork() { if [ \"$1\" = list ]; then printf 'alpha\\nbeta\\n'; else printf 'EXECUTED:%s\\n' \"$*\"; fi; }; printf '\\nREADY\\n'\n"
                    os.write(master, setup.encode())
                    until(b"\r\nREADY\r\n")
                    for typed, result in ((b"dwork sw al\t\n", b"EXECUTED:sw alpha"),
                                          (b"dwork sc\t--d\t\n", b"EXECUTED:scan --dry-run"),
                                          (b"dwork rm be\t\n", b"EXECUTED:rm beta"),
                                          (b"dwork rename al\tnew-name\n", b"EXECUTED:rename alpha new-name")):
                        os.write(master, typed)
                        until(result)
                finally:
                    # Completion assertions are finished. Reap the test-owned
                    # interactive shell without depending on its exit prompt.
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
