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
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
INSTALLER = REPO / "scripts/install.py"


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dwork-install-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.prefix = self.root / "prefix with spaces"

    def installer(self, action, *options, prefix=None):
        return subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                action,
                "--prefix",
                str(prefix or self.prefix),
                *options,
            ],
            cwd="/tmp",
            text=True,
            capture_output=True,
        )

    def test_make_install_and_uninstall_system_mode(self):
        command = [
            "make",
            "install",
            "VENV=0",
            "PREFIX=" + str(self.prefix),
            "PYTHON=" + sys.executable,
        ]
        result = subprocess.run(command, cwd=REPO, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        executable = self.prefix / "bin/dwork"
        self.assertTrue(os.access(executable, os.X_OK))
        self.assertFalse((self.prefix / "bin/dwork-tray").exists())
        self.assertFalse((self.prefix / "share/dwork/tray-venv").exists())
        result = subprocess.run(
            [str(executable), "--help"], cwd="/tmp", text=True, capture_output=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage: dwork", result.stdout)
        result = subprocess.run(
            [str(executable), "--version"], cwd="/tmp", text=True, capture_output=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        version = subprocess.check_output(
            [sys.executable, str(REPO / "lib/dwork.py"), "--version"], text=True
        )
        self.assertEqual(result.stdout, version)
        self.assertTrue((self.prefix / "share/dwork/examples/full-stack.yml").is_file())
        self.assertEqual(
            {module.name for module in (REPO / "lib").glob("*.py")},
            {module.name for module in (self.prefix / "share/dwork/lib").glob("*.py")},
        )
        self.assertIn(
            "complete -o", (self.prefix / "share/dwork/completions/dwork.bash").read_text()
        )
        self.assertIn(
            "compdef _dwork dwork", (self.prefix / "share/dwork/completions/_dwork").read_text()
        )
        self.assertEqual(
            (self.prefix / "share/dwork/completions/dwork.bash").read_bytes(),
            (self.prefix / "share/bash-completion/completions/dwork").read_bytes(),
        )
        native_zsh = (self.prefix / "share/zsh/site-functions/_dwork").read_text()
        self.assertTrue(native_zsh.startswith("#compdef dwork\n"))
        self.assertIn(shlex.quote(str(self.prefix / "share/dwork/completions/_dwork")), native_zsh)
        result = subprocess.run(
            ["make", "uninstall", "PREFIX=" + str(self.prefix), "PYTHON=" + sys.executable],
            cwd=REPO,
            text=True,
            capture_output=True,
        )
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
        result = self.installer(
            "install",
            "--venv",
            "0",
            "--destdir",
            str(stage),
            "--zsh-completion-dir",
            "/usr/share/zsh/vendor-completions",
            prefix=Path("/usr"),
        )
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
        result = self.installer(
            "install",
            "--venv",
            "0",
            "--bash-completion-dir",
            str(self.prefix / "etc/bash_completion.d"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.prefix / "etc/bash_completion.d/dwork").is_file())
        self.assertTrue((self.prefix / "share/zsh/site-functions/_dwork").is_file())
        self.assertEqual(self.installer("uninstall").returncode, 0)
        self.assertFalse((self.prefix / "etc/bash_completion.d/dwork").exists())

    @unittest.skipUnless(shutil.which("zsh"), "Zsh is not installed")
    def test_installed_zsh_completion_is_discovered_by_compinit(self):
        self.assertEqual(self.installer("install", "--venv", "0").returncode, 0)
        script = (
            "fpath=("
            + shlex.quote(str(self.prefix / "share/zsh/site-functions"))
            + " $fpath); autoload -Uz compinit; compinit -D -i; "
            + "print -r -- ${_comps[dwork]}"
        )
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
        for relative in (
            "share/bash-completion/completions/dwork",
            "share/zsh/site-functions/_dwork",
        ):
            with self.subTest(completion=relative):
                prefix = self.root / relative.split("/")[1]
                self.assertEqual(
                    self.installer("install", "--venv", "0", prefix=prefix).returncode, 0
                )
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
        record["completions"] = {
            relative: installer.digest((prefix / relative).read_text())
            for relative in record["completions"]
        }
        marker.write_text(json.dumps(record))
        original = installer.atomic_write

        def interrupt(path, text, mode=0o644):
            if point == "marker" and path == marker and "pending" not in json.loads(text):
                raise OSError("injected upgrade interruption")
            original(path, text, mode)
            if str(path.relative_to(prefix)) == point:
                raise OSError("injected upgrade interruption")

        with (
            patch.object(
                sys, "argv", [str(INSTALLER), "install", "--prefix", str(prefix), "--venv", "0"]
            ),
            patch.object(installer, "atomic_write", side_effect=interrupt),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            with self.assertRaisesRegex(OSError, "injected upgrade interruption"):
                installer.main()
        self.assertIn("pending", json.loads(marker.read_text()))

    def test_interrupted_upgrades_allow_retry_or_uninstall(self):
        points = (
            "share/bash-completion/completions/dwork",
            "share/zsh/site-functions/_dwork",
            "bin/dwork",
            "marker",
        )
        for index, point in enumerate(points):
            for action in ("install", "uninstall"):
                with self.subTest(point=point, recovery=action):
                    prefix = self.root / (str(index) + "-" + action)
                    self.interrupted_upgrade(prefix, point)
                    options = ("--venv", "0") if action == "install" else ()
                    result = self.installer(action, *options, prefix=prefix)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    if action == "install":
                        marker = json.loads(
                            (prefix / "share/dwork/.dwork-install.json").read_text()
                        )
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
        result = subprocess.run(
            [
                sys.executable,
                str(source / "scripts/install.py"),
                "install",
                "--prefix",
                str(prefix),
                "--venv",
                "0",
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("copied source", result.stderr)
        self.assertFalse(prefix.exists())

    def test_relative_prefix_is_rejected(self):
        result = self.installer("install", "--venv", "0", prefix=Path("relative"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute", result.stderr)


class TrayInstallTests(unittest.TestCase):
    """Fake only environment/dependency commands; real files exercise ownership."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dwork-tray-install-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.prefix = self.root / "prefix with spaces"
        self.args = SimpleNamespace(
            prefix=str(self.prefix),
            destdir="",
            venv="1",
            tray="1",
            bash_completion_dir="",
            zsh_completion_dir="",
        )
        spec = importlib.util.spec_from_file_location("dwork_tray_installer_test", INSTALLER)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.commands = []
        self.addCleanup(patch.stopall)
        patch.object(self.module.platform, "release", return_value="native-linux").start()
        patch.object(sys, "platform", "linux").start()
        patch.dict(os.environ, {"WSL_DISTRO_NAME": "", "HOME": str(self.root)}).start()
        patch.object(self.module, "checked", side_effect=self.checked).start()
        self.config = self.root / ".config/autostart"
        self.config.mkdir(parents=True)
        (self.config / "unrelated.desktop").write_text("keep existing startup settings")

    def checked(self, command):
        command = [str(arg) for arg in command]
        self.commands.append(command)
        if command[1:3] == ["-m", "venv"]:
            python = Path(command[-1]) / "bin/python"
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("not an executable: tests must never launch the tray")

    def install(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.module.install(self.args)
        return output.getvalue()

    def uninstall(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.module.uninstall(self.args)

    def test_opt_in_uses_a_separate_environment_and_exact_source_without_launching(self):
        output = self.install()
        core_environment, tray_environment = [c for c in self.commands if c[1:3] == ["-m", "venv"]]
        self.assertNotIn("--system-site-packages", core_environment)
        self.assertIn("--system-site-packages", tray_environment)
        self.assertEqual(self.commands[-1][-2:], [str(REPO), str(REPO / "companion")])
        self.assertIn("-m dwork_tray", (self.prefix / "bin/dwork-tray").read_text())
        self.assertIn(
            shlex.quote(str(self.prefix / "share/dwork/tray-venv/bin/python")),
            (self.prefix / "bin/dwork-tray").read_text(),
        )
        self.assertIn("not launched", output)
        self.assertEqual(list(self.config.iterdir()), [self.config / "unrelated.desktop"])
        # Only venv creation, dependency installation, and the non-GUI GI probe run.
        self.assertTrue(
            all(
                c[1:3] == ["-m", "venv"] or c[1:4] == ["-m", "pip", "install"] or c[1] == "-c"
                for c in self.commands
            )
        )

    def test_default_updates_retain_the_opted_in_tray_and_uninstall_removes_both(self):
        self.install()
        self.commands.clear()
        self.args.tray = "0"
        self.install()
        self.assertEqual(self.commands[-1][-2:], [str(REPO), str(REPO / "companion")])
        record = json.loads((self.prefix / "share/dwork/.dwork-install.json").read_text())
        self.assertTrue(record["tray"])
        other = self.prefix / "bin/another-tool"
        other.write_text("preserve")
        self.uninstall()
        self.assertFalse((self.prefix / "bin/dwork").exists())
        self.assertFalse((self.prefix / "bin/dwork-tray").exists())
        self.assertFalse((self.prefix / "share/dwork").exists())
        self.assertEqual(other.read_text(), "preserve")
        self.assertEqual(
            (self.config / "unrelated.desktop").read_text(), "keep existing startup settings"
        )

    def test_cli_only_install_preserves_an_unrelated_tray_command(self):
        self.args.tray = "0"
        path = self.prefix / "bin/dwork-tray"
        path.parent.mkdir(parents=True)
        path.write_text("separately installed companion")
        self.install()
        self.assertFalse((self.prefix / "share/dwork/tray-venv").exists())
        self.assertFalse(any(c[-1] == str(REPO / "companion") for c in self.commands))
        self.uninstall()
        self.assertEqual(path.read_text(), "separately installed companion")

    def test_macos_tray_uses_an_isolated_environment_and_requires_python_313(self):
        with patch.object(sys, "platform", "darwin"):
            with patch.object(sys, "version_info", (3, 12)):
                with self.assertRaisesRegex(self.module.InstallError, "3.13"):
                    self.install()
                self.assertFalse(self.prefix.exists())
            with patch.object(sys, "version_info", (3, 13)):
                self.install()
        environments = [c for c in self.commands if c[1:3] == ["-m", "venv"]]
        self.assertEqual(len(environments), 2)
        self.assertTrue(all("--system-site-packages" not in c for c in environments))
        self.assertFalse(any(c[1] == "-c" for c in self.commands))

    def test_linked_managed_tray_environment_is_rejected_before_writes(self):
        self.install()
        data = self.prefix / "share/dwork"
        marker = (data / ".dwork-install.json").read_bytes()
        environment = data / "tray-venv"
        outside = self.root / "outside-environment"
        environment.rename(outside)
        environment.symlink_to(outside, target_is_directory=True)
        self.commands.clear()
        with self.assertRaisesRegex(self.module.InstallError, "linked install path"):
            self.install()
        self.assertEqual(self.commands, [])
        self.assertEqual((data / ".dwork-install.json").read_bytes(), marker)
        self.assertTrue((outside / "bin/python").is_file())

    def test_make_forwards_the_explicit_tray_option(self):
        capture = self.root / "capture-python"
        capture.write_text("#!" + sys.executable + "\nimport sys\nprint(repr(sys.argv[1:]))\n")
        capture.chmod(0o755)
        result = subprocess.run(
            ["make", "install", "TRAY=1", "PYTHON=" + str(capture), "PREFIX=" + str(self.prefix)],
            cwd=REPO,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("'--tray', '1'", result.stdout)
        self.assertFalse(self.prefix.exists())

    def test_unrelated_or_linked_tray_launchers_are_rejected_before_writes(self):
        path = self.prefix / "bin/dwork-tray"
        path.parent.mkdir(parents=True)
        outside = self.root / "outside"
        outside.write_text("preserve")
        for linked in (False, True):
            with self.subTest(linked=linked):
                if linked:
                    path.symlink_to(outside)
                else:
                    path.write_text("unrelated")
                with self.assertRaises(self.module.InstallError):
                    self.install()
                self.assertFalse((self.prefix / "share/dwork").exists())
                self.assertEqual(self.commands, [])
                self.assertEqual(outside.read_text(), "preserve")
                path.unlink()

    def test_edited_or_linked_owned_launcher_blocks_update_and_uninstall(self):
        self.install()
        path = self.prefix / "bin/dwork-tray"
        original = path.read_bytes()
        marker = self.prefix / "share/dwork/.dwork-install.json"
        before = marker.read_bytes()
        outside = self.root / "personal-launcher"
        outside.write_text("user changes")
        for linked in (False, True):
            with self.subTest(linked=linked):
                path.unlink()
                if linked:
                    path.symlink_to(outside)
                else:
                    path.write_text("user changes")
                for action in (self.install, self.uninstall):
                    with self.assertRaises(self.module.InstallError):
                        action()
                    self.assertEqual(marker.read_bytes(), before)
                    self.assertTrue((self.prefix / "bin/dwork").is_file())
                    self.assertEqual(path.read_text(), "user changes")
                self.assertEqual(outside.read_text(), "user changes")
        path.unlink()
        path.write_bytes(original)

    def test_unsupported_modes_fail_before_any_environment_or_file_writes(self):
        for changes in ({"venv": "0"}, {"destdir": str(self.root / "stage")}):
            with self.subTest(changes=changes):
                args = SimpleNamespace(**{**vars(self.args), **changes})
                with self.assertRaises(self.module.InstallError):
                    self.module.install(args)
                self.assertFalse(self.prefix.exists())
                self.assertFalse((self.root / "stage").exists())
                self.assertEqual(self.commands, [])
        for distribution, kernel in (("Ubuntu", "generic"), ("", "microsoft-standard-WSL2")):
            with (
                patch.dict(os.environ, {"WSL_DISTRO_NAME": distribution}),
                patch.object(self.module.platform, "release", return_value=kernel),
            ):
                with self.assertRaisesRegex(self.module.InstallError, "portable Windows"):
                    self.install()
                self.assertFalse(self.prefix.exists())
                self.assertEqual(self.commands, [])

    def test_missing_desktop_dependencies_leave_a_recoverable_marked_install(self):
        def failing(command):
            self.checked(command)
            if str(command[1]) == "-c":
                raise subprocess.CalledProcessError(1, command)

        with patch.object(self.module, "checked", side_effect=failing):
            with self.assertRaisesRegex(self.module.InstallError, "prerequisites"):
                self.install()
        marker = self.prefix / "share/dwork/.dwork-install.json"
        self.assertIn("pending", json.loads(marker.read_text()))
        self.assertFalse((self.prefix / "bin/dwork-tray").exists())
        self.assertFalse((self.prefix / "bin/dwork").exists())
        self.args.tray = "0"
        self.install()
        self.assertTrue((self.prefix / "bin/dwork-tray").is_file())

    def test_interrupted_addition_of_tray_allows_retry_or_uninstall(self):
        for recovery in ("retry", "uninstall"):
            with self.subTest(recovery=recovery):
                self.args.prefix = str(self.root / recovery)
                prefix = Path(self.args.prefix)
                self.args.tray = "0"
                self.install()
                self.args.tray = "1"
                original = self.module.atomic_write

                def interrupt(path, text, mode=0o644):
                    original(path, text, mode)
                    if path == prefix / "bin/dwork-tray":
                        raise OSError("interrupted after tray launcher publication")

                with patch.object(self.module, "atomic_write", side_effect=interrupt):
                    with self.assertRaisesRegex(OSError, "interrupted"):
                        self.install()
                marker = prefix / "share/dwork/.dwork-install.json"
                self.assertIn("tray_launcher_sha256", json.loads(marker.read_text())["pending"])
                self.args.tray = "0"
                if recovery == "retry":
                    self.install()
                    self.assertTrue(json.loads(marker.read_text())["tray"])
                self.uninstall()
                self.assertFalse((prefix / "bin/dwork-tray").exists())
                self.assertFalse((prefix / "share/dwork").exists())


if __name__ == "__main__":
    unittest.main()
