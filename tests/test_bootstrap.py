"""Exercise the curl bootstrap without network access or a real installation."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
BOOTSTRAP = REPO / "install.sh"


@unittest.skipUnless(os.name == "posix", "The bootstrap requires a POSIX shell")
class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dwork bootstrap test ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bin = self.root / "bin with spaces"
        self.bin.mkdir()
        self.downloads = self.root / "downloads with spaces"
        self.downloads.mkdir()
        self.sentinel = self.downloads / "unrelated"
        self.sentinel.write_text("keep me\n")
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        for name in (".bashrc", ".zshrc"):
            (self.home / name).write_text("# keep my shell settings\n")
        self.log = self.root / "events.jsonl"
        self.env = {
            **os.environ,
            "PATH": str(self.bin),
            "HOME": str(self.home),
            "TMPDIR": str(self.downloads),
            "BOOTSTRAP_TEST_LOG": str(self.log),
        }
        for name in ("PYTHON", "PREFIX", "DESTDIR", "VENV", "MAKEFLAGS"):
            self.env.pop(name, None)
        for name in ("mktemp", "rm", "cat"):
            executable = shutil.which(name)
            self.assertIsNotNone(executable, name + " must be available for these tests")
            (self.bin / name).symlink_to(executable)
        self.write_tool(
            "python3",
            """sys.executable = sys.argv[0]
version = os.environ.get("BOOTSTRAP_TEST_PYTHON_VERSION")
if version:
    sys.version_info = tuple(int(item) for item in version.split(".")) + (0, "final", 0)
platform_name = os.environ.get("BOOTSTRAP_TEST_PLATFORM", "Linux")
sys.platform = {"Linux": "linux", "Darwin": "darwin"}.get(platform_name, platform_name)
if os.environ.get("BOOTSTRAP_TEST_PYTHON_FAIL"):
    raise SystemExit(1)
if os.environ.get("BOOTSTRAP_TEST_NO_VENV"):
    import builtins
    original_import = builtins.__import__
    def without_venv(name, *args, **kwargs):
        if name in ("ensurepip", "venv"):
            raise ImportError("venv intentionally unavailable")
        return original_import(name, *args, **kwargs)
    builtins.__import__ = without_venv
if sys.argv[1:2] == ["-c"]:
    exec(compile(sys.argv[2], "<bootstrap preflight>", "exec"))
else:
    exec(compile(sys.stdin.read(), "<bootstrap preflight>", "exec"))
""",
        )
        self.write_tool(
            "git",
            """target = Path(sys.argv[-1])
target.mkdir(parents=True)
(target / "partial-download").write_text("temporary clone data")
raise SystemExit(int(os.environ.get("BOOTSTRAP_TEST_GIT_EXIT", "0")))
""",
            record=True,
        )
        self.write_tool(
            "make",
            'raise SystemExit(int(os.environ.get("BOOTSTRAP_TEST_MAKE_EXIT", "0")))\n',
            record=True,
        )

    def write_tool(self, name, body, *, record=False):
        path = self.bin / name
        preamble = "import json, os, sys\nfrom pathlib import Path\n"
        if record:
            preamble += """with open(os.environ["BOOTSTRAP_TEST_LOG"], "a") as stream:
    stream.write(json.dumps({"tool": Path(sys.argv[0]).name, "args": sys.argv[1:],
                             "cwd": os.getcwd(), "venv": os.environ.get("VENV"),
                             "completion": os.environ.get("ZSH_COMPLETION_DIR")}) + "\\n")
"""
        path.write_text("#!" + sys.executable + "\n" + preamble + body)
        path.chmod(0o755)
        return path

    def run_bootstrap(self, *args, env=None):
        return subprocess.run(
            ["/bin/sh", str(BOOTSTRAP), *args],
            cwd=self.home,
            env=self.env if env is None else env,
            text=True,
            capture_output=True,
            timeout=10,
        )

    def events(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def assert_temporary_files_cleaned(self):
        self.assertEqual(list(self.downloads.iterdir()), [self.sentinel])
        self.assertEqual(self.sentinel.read_text(), "keep me\n")
        for name in (".bashrc", ".zshrc"):
            self.assertEqual((self.home / name).read_text(), "# keep my shell settings\n")

    def test_default_install_uses_https_main_and_removes_temporary_clone(self):
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        git, make = self.events()
        self.assertEqual(git["tool"], "git")
        self.assertEqual(
            git["args"][:-1],
            [
                "clone",
                "--depth",
                "1",
                "--branch",
                "main",
                "--",
                "https://github.com/hayyaun/dwork.git",
            ],
        )
        self.assertEqual(make["tool"], "make")
        self.assertEqual(make["cwd"], git["args"][-1])
        self.assertEqual(
            make["args"],
            [
                "install",
                "PYTHON=" + str(self.bin / "python3"),
                "PREFIX=" + str(self.home / ".local"),
            ],
        )
        self.assertFalse(Path(make["cwd"]).exists())
        self.assert_temporary_files_cleaned()

    def test_custom_python_prefix_and_make_controls_are_preserved(self):
        python = self.bin / "python with spaces"
        python.symlink_to(self.bin / "python3")
        prefix = self.root / "custom prefix with spaces"
        completion = str(prefix / "share/zsh/site-functions")
        self.env.update(
            PYTHON=str(python), PREFIX=str(prefix), VENV="0", ZSH_COMPLETION_DIR=completion
        )
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        make = self.events()[-1]
        self.assertEqual(
            make["args"], ["install", "PYTHON=" + str(python), "PREFIX=" + str(prefix)]
        )
        self.assertEqual(make["venv"], "0")
        self.assertEqual(make["completion"], completion)
        self.assert_temporary_files_cleaned()

    def test_help_and_unknown_arguments_never_download_or_install(self):
        for argument, successful in (("--help", True), ("-h", True), ("--unknown", False)):
            with self.subTest(argument=argument):
                result = self.run_bootstrap(argument)
                self.assertEqual(result.returncode == 0, successful, result.stderr)
                self.assertEqual(self.events(), [])
                self.assert_temporary_files_cleaned()

    def test_missing_dependencies_fail_before_downloading(self):
        for name in ("git", "make", "python3", "mktemp"):
            with self.subTest(dependency=name):
                tool = self.bin / name
                hidden = self.bin / (name + ".disabled")
                tool.rename(hidden)
                try:
                    result = self.run_bootstrap()
                finally:
                    hidden.rename(tool)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(name, result.stderr + result.stdout)
                self.assertEqual(self.events(), [])
                self.assert_temporary_files_cleaned()

    def test_unsupported_platform_and_python_fail_before_downloading(self):
        for platform_name, version in (
            ("FreeBSD", "3.14"),
            ("Linux", "3.9"),
            ("Darwin", "3.12"),
        ):
            with self.subTest(platform=platform_name, version=version):
                self.env.update(
                    BOOTSTRAP_TEST_PLATFORM=platform_name, BOOTSTRAP_TEST_PYTHON_VERSION=version
                )
                result = self.run_bootstrap()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.events(), [])
                self.assert_temporary_files_cleaned()

    def test_failed_python_preflight_never_downloads(self):
        self.env["BOOTSTRAP_TEST_PYTHON_FAIL"] = "1"
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.events(), [])
        self.assert_temporary_files_cleaned()

    def test_relative_python_path_stays_valid_after_entering_the_clone(self):
        python = self.home / "custom python"
        python.symlink_to(self.bin / "python3")
        self.env["PYTHON"] = "./custom python"
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PYTHON=" + str(python), self.events()[-1]["args"])
        self.assert_temporary_files_cleaned()

    def test_default_install_requires_venv_but_existing_system_mode_does_not(self):
        self.env["BOOTSTRAP_TEST_NO_VENV"] = "1"
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("venv", result.stderr)
        self.assertEqual(self.events(), [])
        self.assert_temporary_files_cleaned()
        self.env["VENV"] = "0"
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events()[-1]["venv"], "0")
        self.assert_temporary_files_cleaned()

    def test_macos_accepts_the_documented_python_minimum(self):
        self.env.update(
            BOOTSTRAP_TEST_PLATFORM="Darwin", BOOTSTRAP_TEST_PYTHON_VERSION="3.13", VENV="0"
        )
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([event["tool"] for event in self.events()], ["git", "make"])
        self.assert_temporary_files_cleaned()

    def test_clone_failure_cleans_partial_download_and_skips_make(self):
        self.env["BOOTSTRAP_TEST_GIT_EXIT"] = "23"
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([event["tool"] for event in self.events()], ["git"])
        self.assert_temporary_files_cleaned()

    def test_make_failure_cleans_clone_and_propagates_failure(self):
        self.env["BOOTSTRAP_TEST_MAKE_EXIT"] = "17"
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([event["tool"] for event in self.events()], ["git", "make"])
        self.assert_temporary_files_cleaned()

    def test_command_substitution_invocation_preserves_stdin(self):
        self.write_tool("make", "sys.stdout.write(sys.stdin.readline())\n", record=True)
        # Simulate the documented sh -c "$(curl ...)" entry point, retaining stdin.
        result = subprocess.run(
            ["/bin/sh", "-c", BOOTSTRAP.read_text()],
            cwd=self.home,
            env=self.env,
            input="input available to the installer\n",
            text=True,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("input available to the installer", result.stdout)
        self.assert_temporary_files_cleaned()
