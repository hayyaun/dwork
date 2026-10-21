"""Installer tests use temporary prefixes and never change the user's install."""
import json
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import shlex
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
INSTALLER = REPO / "scripts/install.py"

class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dwork-install-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.prefix = self.root / "prefix with spaces"

    def installer(self, action, *options, prefix=None):
        return subprocess.run([sys.executable, str(INSTALLER), action,
                               "--prefix", str(prefix or self.prefix), *options],
                              cwd="/tmp", text=True, capture_output=True)

    def test_make_install_and_uninstall_system_mode(self):
        command = ["make", "install", "VENV=0", "PREFIX=" + str(self.prefix),
                   "PYTHON=" + sys.executable]
        result = subprocess.run(command, cwd=REPO, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        executable = self.prefix / "bin/dwork"
        self.assertTrue(os.access(executable, os.X_OK))
        result = subprocess.run([str(executable), "--help"], cwd="/tmp",
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage: dwork", result.stdout)
        result = subprocess.run([str(executable), "--version"], cwd="/tmp",
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        version = subprocess.check_output([sys.executable, str(REPO / "lib/dwork.py"), "--version"], text=True)
        self.assertEqual(result.stdout, version)
        self.assertTrue((self.prefix / "share/dwork/examples/full-stack.yml").is_file())
        self.assertEqual(
            {module.name for module in (REPO / "lib").glob("*.py")},
            {module.name for module in (self.prefix / "share/dwork/lib").glob("*.py")},
        )
        self.assertIn("complete -o", (self.prefix / "share/dwork/completions/dwork.bash").read_text())
        self.assertIn("compdef _dwork dwork", (self.prefix / "share/dwork/completions/_dwork").read_text())
        self.assertEqual((self.prefix / "share/dwork/completions/dwork.bash").read_bytes(),
                         (self.prefix / "share/bash-completion/completions/dwork").read_bytes())
        native_zsh = (self.prefix / "share/zsh/site-functions/_dwork").read_text()
        self.assertTrue(native_zsh.startswith("#compdef dwork\n"))
        self.assertIn(shlex.quote(str(self.prefix / "share/dwork/completions/_dwork")), native_zsh)
        result = subprocess.run(["make", "uninstall", "PREFIX=" + str(self.prefix),
                                 "PYTHON=" + sys.executable], cwd=REPO,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(executable.exists())
        self.assertFalse((self.prefix / "share/dwork").exists())
        self.assertFalse((self.prefix / "share/bash-completion/completions/dwork").exists())
        self.assertFalse((self.prefix / "share/zsh/site-functions/_dwork").exists())

    def test_reinstall_and_uninstall_preserve_unrelated_files(self):
        self.assertEqual(self.installer("install", "--venv", "0").returncode, 0)
        unrelated = self.prefix / "bin/another-tool"
        unrelated.write_text("preserve")
        other_completion = self.prefix / "share/zsh/site-functions/_another_tool"
        other_completion.write_text("preserve completion")
        self.assertEqual(self.installer("install", "--venv", "0").returncode, 0)
        result = self.installer("uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(unrelated.read_text(), "preserve")
        self.assertEqual(other_completion.read_text(), "preserve completion")
        self.assertEqual(self.installer("uninstall").returncode, 0)

    def test_destdir_is_not_embedded_in_launcher(self):
        stage = self.root / "staging"
        result = self.installer("install", "--venv", "0", "--destdir", str(stage),
                                "--zsh-completion-dir", "/usr/share/zsh/vendor-completions",
                                prefix=Path("/usr"))
        self.assertEqual(result.returncode, 0, result.stderr)
        launcher = stage / "usr/bin/dwork"
        self.assertIn("/usr/share/dwork/lib/dwork.py", launcher.read_text())
        self.assertNotIn(str(stage), launcher.read_text())
        self.assertTrue((stage / "usr/share/zsh/vendor-completions/_dwork").is_file())
        native_zsh = (stage / "usr/share/zsh/vendor-completions/_dwork").read_text()
        self.assertIn("/usr/share/dwork/completions/_dwork", native_zsh)
        self.assertNotIn(str(stage), native_zsh)
        self.assertTrue((stage / "usr/share/bash-completion/completions/dwork").is_file())
        self.assertFalse((stage / "usr/share/zsh/site-functions/_dwork").exists())
        self.assertEqual(
            {module.name for module in (REPO / "lib").glob("*.py")},
            {module.name for module in (stage / "usr/share/dwork/lib").glob("*.py")},
        )
        result = self.installer("uninstall", "--destdir", str(stage), prefix=Path("/usr"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(launcher.exists())
        self.assertFalse((stage / "usr/share/zsh/vendor-completions/_dwork").exists())

    def test_homebrew_completion_layout(self):
        result = self.installer("install", "--venv", "0", "--bash-completion-dir",
                                str(self.prefix / "etc/bash_completion.d"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.prefix / "etc/bash_completion.d/dwork").is_file())
        self.assertTrue((self.prefix / "share/zsh/site-functions/_dwork").is_file())
        self.assertEqual(self.installer("uninstall").returncode, 0)
        self.assertFalse((self.prefix / "etc/bash_completion.d/dwork").exists())

    @unittest.skipUnless(shutil.which("zsh"), "Zsh is not installed")
    def test_installed_zsh_completion_is_discovered_by_compinit(self):
        self.assertEqual(self.installer("install", "--venv", "0").returncode, 0)
        script = ("fpath=(" + shlex.quote(str(self.prefix / "share/zsh/site-functions"))
                  + " $fpath); autoload -Uz compinit; compinit -D -i; "
                  + "print -r -- ${_comps[dwork]}")
        result = subprocess.run(["zsh", "-f", "-c", script], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "_dwork")

    def test_upgrade_from_legacy_marker_adds_native_completions(self):
        self.assertEqual(self.installer("install", "--venv", "0").returncode, 0)
        marker = self.prefix / "share/dwork/.dwork-install.json"
        record = json.loads(marker.read_text())
        for relative in record.pop("completions"):
            (self.prefix / relative).unlink()
        marker.write_text(json.dumps(record))
        result = self.installer("install", "--venv", "0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.prefix / "share/zsh/site-functions/_dwork").is_file())
        self.assertEqual(self.installer("uninstall").returncode, 0)

    def test_modified_completions_are_preserved_before_any_removal(self):
        for relative in ("share/bash-completion/completions/dwork", "share/zsh/site-functions/_dwork"):
            with self.subTest(completion=relative):
                prefix = self.root / relative.split("/")[1]
                self.assertEqual(self.installer("install", "--venv", "0", prefix=prefix).returncode, 0)
                path = prefix / relative
                path.write_text("my edited completion")
                for action in ("install", "uninstall"):
                    args = ("--venv", "0") if action == "install" else ()
                    result = self.installer(action, *args, prefix=prefix)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("completion was modified", result.stderr)
                    self.assertEqual(path.read_text(), "my edited completion")
                    self.assertTrue((prefix / "bin/dwork").is_file())

    def test_unrelated_native_completion_blocks_install_without_writes(self):
        path = self.prefix / "share/zsh/site-functions/_dwork"
        path.parent.mkdir(parents=True)
        path.write_text("unrelated completion")
        result = self.installer("install", "--venv", "0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrelated completion", result.stderr)
        self.assertEqual(path.read_text(), "unrelated completion")
        self.assertFalse((self.prefix / "share/dwork").exists())

    def test_native_completion_links_and_invalid_directories_are_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        directory = self.prefix / "share/zsh"
        directory.mkdir(parents=True)
        (directory / "site-functions").symlink_to(outside, target_is_directory=True)
        self.assertNotEqual(self.installer("install", "--venv", "0").returncode, 0)
        self.assertFalse((outside / "_dwork").exists())
        (directory / "site-functions").unlink()
        for target in (str(outside), str(self.prefix / "unrelated"), "relative"):
            with self.subTest(target=target):
                result = self.installer("install", "--venv", "0", "--zsh-completion-dir", target)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.prefix / "share/dwork").exists())

    def test_staging_venv_is_rejected_without_writes(self):
        stage = self.root / "staging"
        result = self.installer("install", "--destdir", str(stage), prefix=Path("/usr"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("VENV=0", result.stderr)
        self.assertFalse(stage.exists())

    def test_unrelated_launcher_or_directory_are_not_overwritten(self):
        path = self.prefix / "bin/dwork"
        path.parent.mkdir(parents=True)
        path.write_text("my command")
        result = self.installer("install", "--venv", "0")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(path.read_text(), "my command")
        path.unlink()
        data = self.prefix / "share/dwork"
        data.mkdir(parents=True)
        (data / "personal").write_text("keep")
        self.assertNotEqual(self.installer("install", "--venv", "0").returncode, 0)
        self.assertNotEqual(self.installer("uninstall").returncode, 0)
        self.assertEqual((data / "personal").read_text(), "keep")

    def test_modified_launcher_is_preserved(self):
        self.assertEqual(self.installer("install", "--venv", "0").returncode, 0)
        executable = self.prefix / "bin/dwork"
        executable.write_text("my edited launcher")
        self.assertNotEqual(self.installer("uninstall").returncode, 0)
        self.assertNotEqual(self.installer("install", "--venv", "0").returncode, 0)
        self.assertEqual(executable.read_text(), "my edited launcher")

    def test_reinstall_rejects_license_links_before_writing(self):
        self.assertEqual(self.installer("install", "--venv", "0").returncode, 0)
        data = self.prefix / "share/dwork"
        marker = (data / ".dwork-install.json").read_bytes()
        for name in ("LICENSE", "LICENSE.md", "COPYING"):
            with self.subTest(name=name):
                outside = self.root / ("unrelated-" + name)
                outside.write_text("personal content")
                path = data / name
                previous = path.read_bytes() if path.exists() else None
                path.unlink(missing_ok=True)
                path.symlink_to(outside)
                result = self.installer("install", "--venv", "0")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("linked install path", result.stderr)
                self.assertEqual(outside.read_text(), "personal content")
                self.assertEqual((data / ".dwork-install.json").read_bytes(), marker)
                path.unlink()
                if previous is not None:
                    path.write_bytes(previous)

    def interrupted_upgrade(self, prefix, point):
        self.assertEqual(self.installer("install", "--venv", "0", prefix=prefix).returncode, 0)
        marker = prefix / "share/dwork/.dwork-install.json"
        record = json.loads(marker.read_text())
        # Model a previous release with different generated external files.
        for relative in record["completions"]:
            path = prefix / relative
            path.write_text(path.read_text() + "\n# previous release\n")
        launcher = prefix / "bin/dwork"
        launcher.write_text(launcher.read_text() + "\n# previous release\n")
        spec = importlib.util.spec_from_file_location("dwork_installer_test", INSTALLER)
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        record["launcher_sha256"] = installer.digest(launcher.read_text())
        record["completions"] = {relative: installer.digest((prefix / relative).read_text())
                                 for relative in record["completions"]}
        marker.write_text(json.dumps(record))
        original = installer.atomic_write
        def interrupt(path, text, mode=0o644):
            if point == "marker" and path == marker and "pending" not in json.loads(text):
                raise OSError("injected upgrade interruption")
            original(path, text, mode)
            if str(path.relative_to(prefix)) == point:
                raise OSError("injected upgrade interruption")
        with patch.object(sys, "argv", [str(INSTALLER), "install", "--prefix", str(prefix), "--venv", "0"]), \
                patch.object(installer, "atomic_write", side_effect=interrupt), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(OSError, "injected upgrade interruption"):
                installer.main()
        self.assertIn("pending", json.loads(marker.read_text()))

    def test_interrupted_upgrades_allow_retry_or_uninstall(self):
        points = ("share/bash-completion/completions/dwork", "share/zsh/site-functions/_dwork",
                  "bin/dwork", "marker")
        for index, point in enumerate(points):
            for action in ("install", "uninstall"):
                with self.subTest(point=point, recovery=action):
                    prefix = self.root / (str(index) + "-" + action)
                    self.interrupted_upgrade(prefix, point)
                    options = ("--venv", "0") if action == "install" else ()
                    result = self.installer(action, *options, prefix=prefix)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    if action == "install":
                        marker = json.loads((prefix / "share/dwork/.dwork-install.json").read_text())
                        self.assertNotIn("pending", marker)
                        self.assertEqual(self.installer("uninstall", prefix=prefix).returncode, 0)
                    self.assertFalse((prefix / "bin/dwork").exists())
                    self.assertFalse((prefix / "share/dwork").exists())

    def test_interrupted_upgrade_still_preserves_user_edits(self):
        self.interrupted_upgrade(self.prefix, "share/bash-completion/completions/dwork")
        for relative in ("bin/dwork", "share/bash-completion/completions/dwork"):
            with self.subTest(relative=relative):
                path = self.prefix / relative
                original = path.read_bytes()
                path.write_text("personal edit after interruption")
                for action in ("install", "uninstall"):
                    options = ("--venv", "0") if action == "install" else ()
                    result = self.installer(action, *options)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("was modified", result.stderr)
                    self.assertEqual(path.read_text(), "personal edit after interruption")
                path.write_bytes(original)

    def test_symlink_escape_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.prefix.mkdir()
        (self.prefix / "share").symlink_to(outside, target_is_directory=True)
        result = self.installer("install", "--venv", "0")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((outside / "dwork").exists())

    def test_install_inside_copied_source_is_rejected(self):
        source = self.root / "source"
        (source / "scripts").mkdir(parents=True)
        (source / "docs").mkdir()
        import shutil
        shutil.copy2(INSTALLER, source / "scripts/install.py")
        prefix = source / "docs/nested-prefix"
        result = subprocess.run([sys.executable, str(source / "scripts/install.py"),
                                 "install", "--prefix", str(prefix), "--venv", "0"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("copied source", result.stderr)
        self.assertFalse(prefix.exists())

    def test_relative_prefix_is_rejected(self):
        result = self.installer("install", "--venv", "0", prefix=Path("relative"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute", result.stderr)

if __name__ == "__main__":
    unittest.main()
