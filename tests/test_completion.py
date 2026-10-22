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
        (self.root / "scan-root").mkdir()
        (self.root / "scan-file").write_text("")
        setup = "source " + shlex.quote(str(script)) + "\ndwork() { printf 'alpha\\nbeta\\n'; }\n"
        for words, index, expected in (
            ("dwork sw al", 2, ["alpha"]),
            ("dwork lock al", 2, ["alpha"]),
            ("dwork unlock alpha be", 3, ["beta"]),
            ("dwork up al", 2, ["alpha"]),
            ("dwork up alpha be", 3, ["beta"]),
            ("dwork up --dry-run be", 3, ["beta"]),
            ("dwork down alpha be", 3, ["beta"]),
            ("dwork down --dry-run al", 3, ["alpha"]),
            ("dwork up alpha --p", 3, [""]),
            ("dwork up --p", 2, ["--project-name", "--project-directory", "--profile"]),
            ("dwork scan scan-", 2, ["scan-root"]),
            ("dwork scan scan-root scan-", 3, ["scan-root"]),
            ("dwork scan -- -f scan-", 4, ["scan-root"]),
            ("dwork lock --dry-run be", 3, ["beta"]),
            ("dwork unlock alpha --d", 3, ["--dry-run"]),
            ("dwork rename al", 2, ["alpha"]),
            ("dwork sc", 1, ["scan"]),
            ("dwork scan --d", 2, ["--dry-run"]),
            ("dwork --v", 1, ["--version"]),
            ("dwork in", 1, ["init"]),
            ("dwork val", 1, ["validate"]),
            ("dwork init --d", 2, ["--dry-run"]),
            ("dwork validate --p", 2, ["--project-name", "--project-directory", "--profile"]),
            ("dwork -f comp", 2, ["compose dev.yaml"]),
        ):
            command = (
                setup
                + "COMP_WORDS=("
                + words
                + "); COMP_CWORD="
                + str(index)
                + "; _dwork_complete; printf '%s\\n' \"${COMPREPLY[@]}\""
            )
            result = subprocess.run(
                ["bash", "--noprofile", "--norc", "-c", command],
                cwd=self.root,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), expected)

    def test_group_completion_keeps_group_and_workspace_name_apis_separate(self):
        script = self.script("bash")
        queries = self.fixture.base / "completion-queries"
        setup = (
            "source "
            + shlex.quote(str(script))
            + "; dwork() { printf '%s\\n' \"$*\" >> "
            + shlex.quote(str(queries))
            + "; if [ \"$*\" = 'group list --names' ]; then printf 'daily\\npersonal\\n'; "
            + "elif [ \"$*\" = 'ls --names' ] || [ \"$*\" = 'list --names' ]; "
            + "then printf 'alpha\\nbeta\\n'; else return 77; fi; }; "
        )
        for words, index, expected, expected_queries in (
            ("dwork group sh", 2, ["show"], []),
            ("dwork group show da", 3, ["daily"], ["group list --names"]),
            ("dwork group delete da", 3, ["daily"], ["group list --names"]),
            ("dwork group add da", 3, ["daily"], ["group list --names"]),
            ("dwork group remove --dry-run da", 4, ["daily"], ["group list --names"]),
            ("dwork group create da", 3, [""], []),
            ("dwork group create new al", 4, ["alpha"], ["ls --names"]),
            ("dwork group add daily al", 4, ["alpha"], ["ls --names"]),
            ("dwork group add daily alpha be", 5, ["beta"], ["ls --names"]),
            ("dwork group remove daily --dry-run be", 5, ["beta"], ["ls --names"]),
            ("dwork group --dry-run create new al", 5, ["alpha"], ["ls --names"]),
            ("dwork group create new --dry-run al", 5, ["alpha"], ["ls --names"]),
            ("dwork group list --n", 3, ["--names"], []),
            ("dwork group list --d", 3, [""], []),
            ("dwork group show daily --d", 4, [""], []),
            ("dwork group delete daily --d", 4, ["--dry-run"], []),
            ("dwork group --dry-run --d", 3, [""], []),
            ("dwork group --dry-run li", 3, [""], []),
            ("dwork group add daily --dry-run --d", 5, [""], []),
            ("dwork up --g", 2, ["--group"], []),
            ("dwork down --dry-run --g", 3, ["--group"], []),
            ("dwork switch --dry-run --g", 3, ["--group"], []),
            ("dwork up --group da", 3, ["daily"], ["group list --names"]),
            ("dwork down --dry-run --group pe", 4, ["personal"], ["group list --names"]),
            ("dwork sw --group da", 3, ["daily"], ["group list --names"]),
            ("dwork up da", 2, [""], ["list --names"]),
            ("dwork up alpha --g", 3, [""], []),
            ("dwork down alpha --g", 3, [""], []),
            ("dwork switch alpha --g", 3, [""], []),
            ("dwork up -p dev --g", 4, [""], []),
            ("dwork up --group daily --g", 4, [""], []),
            ("dwork up --dry-run --group daily --d", 5, [""], []),
            ("dwork up alpha --group da", 4, [""], []),
        ):
            with self.subTest(words=words):
                queries.unlink(missing_ok=True)
                command = (
                    setup
                    + "COMP_WORDS=("
                    + words
                    + "); COMP_CWORD="
                    + str(index)
                    + "; _dwork_complete; printf '%s\\n' \"${COMPREPLY[@]}\""
                )
                result = subprocess.run(
                    ["bash", "--noprofile", "--norc", "-c", command],
                    cwd=self.root,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(), expected)
                self.assertEqual(
                    queries.read_text().splitlines() if queries.exists() else [], expected_queries
                )

    def test_interactive_bash_source_registers_completion_on_each_load(self):
        # In particular, exercise macOS's system Bash 3.2 with this test process's
        # Python so an unrelated interpreter cannot silently skip generation.
        generated = self.fixture.base / "completion-generations"
        command = (
            "python3() { printf 'generated\\n' >> "
            + shlex.quote(str(generated))
            + "; "
            + shlex.quote(sys.executable)
            + ' "$@"; }; '
        )
        load = "source " + shlex.quote(str(legacy.SOURCE)) + "; "
        command += load + "complete -p dwork || exit 21; "
        command += load + "complete -p dwork || exit 22"
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-i", "-c", command],
            cwd=self.root,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("-F _dwork_complete dwork"), 2)
        self.assertEqual(generated.read_text().splitlines(), ["generated", "generated"])

    def test_real_tab_completion_in_bash_and_zsh(self):
        import fcntl
        import pty
        import struct
        import termios

        (self.root / "scan-root").mkdir()
        for shell, mode in (
            ("bash", "manual"),
            ("zsh", "manual"),
            ("zsh", "installed"),
            ("bash", "installed"),
            ("bash", "source"),
            ("zsh", "source"),
        ):
            autoload = mode == "installed"
            if not shutil.which(shell):
                continue
            if (
                shell == "bash"
                and autoload
                and not Path("/usr/share/bash-completion/bash_completion").is_file()
            ):
                continue
            with self.subTest(shell=shell, mode=mode):
                script = self.script(shell)
                if mode == "source":
                    script = legacy.SOURCE
                if autoload:
                    prefix = self.fixture.base / (
                        "installed prefix" if shell == "zsh" else "installed-prefix"
                    )
                    installed = subprocess.run(
                        [
                            sys.executable,
                            str(legacy.SOURCE.parent / "scripts/install.py"),
                            "install",
                            "--prefix",
                            str(prefix),
                            "--venv",
                            "0",
                        ],
                        text=True,
                        capture_output=True,
                    )
                    self.assertEqual(installed.returncode, 0, installed.stderr)
                    script = prefix / "share/zsh/site-functions/_dwork"
                master, slave = pty.openpty()
                process = None
                try:
                    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 160, 0, 0))
                    env = dict(
                        os.environ,
                        TERM="xterm",
                        INPUTRC="/dev/null",
                        ZDOTDIR=str(self.fixture.base),
                    )
                    if autoload and shell == "bash":
                        env.update(
                            XDG_DATA_HOME=str(prefix / "share"),
                            BASH_COMPLETION_USER_DIR=str(prefix / "share/bash-completion"),
                            BASH_COMPLETION_USER_FILE="/dev/null",
                        )
                    args = (
                        ["bash", "--noprofile", "--norc", "-i"]
                        if shell == "bash"
                        else ["zsh", "-f"]
                    )
                    process = subprocess.Popen(
                        args, cwd=self.root, stdin=slave, stdout=slave, stderr=slave, env=env
                    )

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
                    setup = (
                        init
                        + load
                        + "dwork() { if [ \"$*\" = 'group list --names' ]; then printf 'daily\\npersonal\\n'; "
                        + 'elif [ "$1" = list ] || [ "$1" = ls ]; then printf \'alpha\\nbeta\\n\'; '
                        + "else printf 'EXECUTED:%s\\n' \"$*\"; fi; }; printf '\\nREADY\\n'\n"
                    )
                    os.write(master, setup.encode())
                    until(b"\r\nREADY\r\n")
                    for typed, result in (
                        (b"dwork sw al\t\n", b"EXECUTED:sw alpha"),
                        (b"dwork lock al\tbe\t\n", b"EXECUTED:lock alpha beta"),
                        (b"dwork up al\tbe\t\n", b"EXECUTED:up alpha beta"),
                        (b"dwork down --d\tal\tbe\t\n", b"EXECUTED:down --dry-run alpha beta"),
                        (b"dwork scan scan-r\t\n", b"EXECUTED:scan scan-root"),
                        (b"dwork unlock --d\tal\tbe\t\n", b"EXECUTED:unlock --dry-run alpha beta"),
                        (b"dwork sc\t--d\t\n", b"EXECUTED:scan --dry-run"),
                        (b"dwork rm be\t\n", b"EXECUTED:rm beta"),
                        (b"dwork rename al\tnew-name\n", b"EXECUTED:rename alpha new-name"),
                        (b"dwork gr\tli\t\n", b"EXECUTED:group list"),
                        (
                            b"dwork group cr\tnew-group al\tbe\t\n",
                            b"EXECUTED:group create new-group alpha beta",
                        ),
                        (
                            b"dwork group --d\tcr\tnew-group al\t\n",
                            b"EXECUTED:group --dry-run create new-group alpha",
                        ),
                        (
                            b"dwork group add dai\tal\tbe\t\n",
                            b"EXECUTED:group add daily alpha beta",
                        ),
                        (b"dwork group remove dai\tal\t\n", b"EXECUTED:group remove daily alpha"),
                        (b"dwork group sh\tdai\t\n", b"EXECUTED:group show daily"),
                        (b"dwork group del\tdai\t\n", b"EXECUTED:group delete daily"),
                        (b"dwork up --g\tdai\t\n", b"EXECUTED:up --group daily"),
                        (
                            b"dwork down --d\t--g\tdai\t\n",
                            b"EXECUTED:down --dry-run --group daily",
                        ),
                        (
                            b"dwork sw --g\tdai\t--d\t\n",
                            b"EXECUTED:sw --group daily --dry-run",
                        ),
                    ):
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
        for args in (
            "completion",
            "completion fish",
            "completion bash extra",
            "list --names extra",
        ):
            result, changes, calls = self.run_cli(args)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(calls, [])
            self.assertEqual(changes, [])
        self.assertFalse((self.fixture.base / "state").exists())


if __name__ == "__main__":
    unittest.main()
