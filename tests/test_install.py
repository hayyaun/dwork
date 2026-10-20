"""Installer tests use temporary prefixes and never change the user's install."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

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
        self.assertTrue((self.prefix / "share/dwork/examples/full-stack.yml").is_file())
        result = subprocess.run(["make", "uninstall", "PREFIX=" + str(self.prefix),
                                 "PYTHON=" + sys.executable], cwd=REPO,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(executable.exists())
        self.assertFalse((self.prefix / "share/dwork").exists())

    def test_reinstall_and_uninstall_preserve_unrelated_files(self):
        self.assertEqual(self.installer("install", "--venv", "0").returncode, 0)
        unrelated = self.prefix / "bin/another-tool"
        unrelated.write_text("preserve")
        self.assertEqual(self.installer("install", "--venv", "0").returncode, 0)
        result = self.installer("uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(unrelated.read_text(), "preserve")
        self.assertEqual(self.installer("uninstall").returncode, 0)

    def test_destdir_is_not_embedded_in_launcher(self):
        stage = self.root / "staging"
        result = self.installer("install", "--venv", "0", "--destdir", str(stage),
                                prefix=Path("/usr"))
        self.assertEqual(result.returncode, 0, result.stderr)
        launcher = stage / "usr/bin/dwork"
        self.assertIn("/usr/share/dwork/lib/dwork.py", launcher.read_text())
        self.assertNotIn(str(stage), launcher.read_text())
        self.assertTrue((stage / "usr/share/dwork/lib/dwork.py").is_file())
        result = self.installer("uninstall", "--destdir", str(stage), prefix=Path("/usr"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(launcher.exists())

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
