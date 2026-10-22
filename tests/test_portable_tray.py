"""Portable entry point/resource/process boundaries; builds run only on Windows CI."""

import base64
from importlib import util
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "companion/src"))
from dwork_tray import platforms, windows_runtime, wsl
from dwork_tray.platforms import CompanionError


class PortableTrayTests(unittest.TestCase):
    def test_frozen_handoff_uses_sibling_helper_without_python_or_module_launch(self):
        with tempfile.TemporaryDirectory(prefix="dwork-portable-") as temporary:
            root = Path(temporary)
            helper = root / "dwork-tray-terminal.exe"
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(root / "dwork-tray.exe")),
            ):
                with self.assertRaisesRegex(CompanionError, "Extract the entire"):
                    wsl.operation_command("payload")
                helper.touch()
                self.assertEqual(wsl.operation_command("payload"), [str(helper), "payload"])
                with patch.object(
                    wsl, "windows_python", side_effect=AssertionError("external Python")
                ):
                    command = wsl.terminal_command("wt.exe", "powershell.exe", {"action": "down"})
                script = base64.b64decode(command[-1]).decode("utf-16-le")
                self.assertIn(str(helper).replace("'", "''"), script)
                self.assertNotIn("python.exe", script)
                self.assertNotIn("dwork_tray.wsl_terminal", script)

    def test_frozen_external_process_restores_dll_search_and_copies_environment(self):
        before = dict(os.environ)
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            path = os.pathsep.join(
                (str(bundle / "_internal"), str(bundle / "nested"), "/system-tools")
            )
            with (
                patch.object(sys, "platform", "win32"),
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(bundle / "dwork-tray.exe")),
                patch.dict(os.environ, {"PATH": path}),
                patch.object(
                    windows_runtime, "current_dll_directory", return_value="original-directory"
                ),
                patch.object(windows_runtime, "dll_directory") as dll,
            ):
                with self.assertRaisesRegex(ValueError, "child failed"):
                    with windows_runtime.system_process() as options:
                        self.assertEqual(options["env"]["PATH"], "/system-tools")
                        self.assertEqual(options["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1")
                        self.assertEqual(os.environ["PATH"], path)
                        raise ValueError("child failed")
                self.assertEqual(
                    [call.args for call in dll.call_args_list], [(None,), ("original-directory",)]
                )
        self.assertEqual(dict(os.environ), before)

    def test_source_process_preserves_existing_subprocess_options(self):
        with (
            patch.object(sys, "frozen", False, create=True),
            patch.object(windows_runtime, "dll_directory") as dll,
        ):
            with windows_runtime.system_process() as options:
                self.assertEqual(options, {})
            dll.assert_not_called()

    def test_portable_build_refuses_cross_compiling_without_writing(self):
        path = Path(__file__).resolve().parents[1] / "scripts/build-windows-tray.py"
        spec = util.spec_from_file_location("portable_builder", path)
        builder = util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with (
            patch.object(sys, "platform", "linux"),
            patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}),
            patch.object(Path, "mkdir") as mkdir,
        ):
            with self.assertRaisesRegex(RuntimeError, "cannot cross-compile"):
                builder.build(Path("unused"))
            mkdir.assert_not_called()


@unittest.skipUnless(util.find_spec("PIL"), "optional Pillow dependency is not installed")
class TrayIconTests(unittest.TestCase):
    def test_packaged_icon_loads_outside_the_working_directory(self):
        source = Path(__file__).resolve().parents[1] / "companion/src"
        with tempfile.TemporaryDirectory(prefix="dwork-icon-cwd-") as temporary:
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    "from dwork_tray.platforms import load_icon; "
                    "image = load_icon(); image.load(); "
                    "assert image.mode == 'RGBA' and image.width > 0 and image.height > 0",
                ],
                cwd=temporary,
                env={**os.environ, "PYTHONPATH": str(source)},
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_replacement_icon_is_converted_and_detached_from_its_file(self):
        from PIL import Image

        with tempfile.TemporaryDirectory(prefix="dwork-icon-replacement-") as temporary:
            root = Path(temporary)
            (root / "assets").mkdir()
            path = root / "assets/tray.png"
            replacement = Image.new("P", (32, 32), 1)
            replacement.putpalette([0, 0, 0, 25, 100, 200] + [0] * 762)
            replacement.putpixel((1, 1), 0)
            replacement.save(path, transparency=0)
            with patch.object(platforms, "__file__", str(root / "platforms.py")):
                image = platforms.load_icon()
            path.unlink()
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.size, (32, 32))
            self.assertEqual(image.getpixel((0, 0)), (25, 100, 200, 255))
            self.assertEqual(image.getpixel((1, 1)), (0, 0, 0, 0))

    def test_missing_or_invalid_icon_reports_its_path(self):
        with tempfile.TemporaryDirectory(prefix="dwork-icon-invalid-") as temporary:
            root = Path(temporary)
            (root / "assets").mkdir()
            path = root / "assets/tray.png"
            with patch.object(platforms, "__file__", str(root / "platforms.py")):
                for content in (None, b"invalid PNG"):
                    if content is not None:
                        path.write_bytes(content)
                    with self.subTest(content=content), self.assertRaises(CompanionError) as error:
                        platforms.load_icon()
                    self.assertIn(str(path), str(error.exception))
                    self.assertIn("valid PNG", str(error.exception))


if __name__ == "__main__":
    unittest.main()
