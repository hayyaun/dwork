#!/usr/bin/env python3
"""Windows CI verification of the extracted portable application (no user-host builds)."""

import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

FIXTURE = r"""import json, os, pathlib, subprocess, sys
args = sys.argv[1:]
if pathlib.Path(sys.executable).stem == "wt":
    pathlib.Path(os.environ["DWORK_FIXTURE_TERMINAL"]).write_text(json.dumps(args), encoding="utf-8")
    result = subprocess.run(args[5:], input=b"decline\n\n", capture_output=True)
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    raise SystemExit(0 if result.returncode == 7 else 99)
if args == ["--list", "--running", "--quiet"]:
    sys.stdout.buffer.write("Ubuntu Test\r\n".encode("utf-16-le"))
elif args[-3:-1] == ["-m", "dwork"] or ("-m" in args and "dwork" in args):
    pathlib.Path(os.environ["DWORK_FIXTURE_OPERATION"]).write_text(json.dumps(args), encoding="utf-8")
    answer = input("Fixture confirmation: ")
    raise SystemExit(7 if answer == "decline" else 98)
elif "-c" in args:
    assert "start_new_session=True" in args[-1] and "timeout=15" in args[-1]
    print(json.dumps({"schema_version":1,"scope":"registered","workspaces":[]}))
else:
    raise SystemExit(97)
"""

PROBE = r"""import json, os, pathlib, sys
from dwork_tray.wsl import WslTransport
transport = WslTransport("Ubuntu Test", "/home/test/env space/bin/python", "test")
assert transport.read_status()["schema_version"] == 1
marker = transport.open_operation("switch", "quotes ' ; $() & 工作", os.environ["DWORK_FIXTURE_MARKERS"])
assert marker.read_text() == "7", marker
assert pathlib.Path(sys.executable).with_name("dwork-tray-terminal.exe").is_file()
print("Frozen status/terminal handoff completed; declined input and exit status preserved.")
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, type=Path)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Run this verifier on Windows; official binary verification runs in CI.")
    app = args.app.resolve()
    with tempfile.TemporaryDirectory(prefix="dwork-frozen-check-") as temporary:
        root = Path(temporary)
        tools = root / "tools"
        tools.mkdir()
        fixture = root / "fixture.py"
        fixture.write_text(FIXTURE, encoding="utf-8")
        probe = root / "probe.py"
        probe.write_text(PROBE, encoding="utf-8")
        for entry, name, destination in (
            (fixture, "wsl", tools),
            (probe, "dwork-portable-probe", root / "probe"),
        ):
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "PyInstaller",
                    "--clean",
                    "--noconfirm",
                    "--onefile",
                    "--console",
                    "--noupx",
                    "--name",
                    name,
                    "--paths",
                    str(ROOT / "companion/src"),
                    "--add-data",
                    str(ROOT / "companion/src/dwork_tray/observer.py") + ":dwork_tray",
                    "--distpath",
                    str(destination),
                    "--workpath",
                    str(root / (name + "-build")),
                    "--specpath",
                    str(root),
                    str(entry),
                ],
                check=True,
            )
        shutil.copyfile(tools / "wsl.exe", tools / "wt.exe")
        # Copy the extracted release, including both EXEs and all runtime files.
        tested = root / "quoted ' café app"
        shutil.copytree(app, tested)
        shutil.copyfile(
            root / "probe/dwork-portable-probe.exe", tested / "dwork-portable-probe.exe"
        )
        markers = root / "markers"
        markers.mkdir()
        system = Path(os.environ["SystemRoot"]) / "System32"
        env = dict(os.environ)
        env["PATH"] = os.pathsep.join(
            (str(tools), str(system), str(system / "WindowsPowerShell/v1.0"))
        )
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env.update(
            {
                "DWORK_FIXTURE_OPERATION": str(root / "operation.json"),
                "DWORK_FIXTURE_TERMINAL": str(root / "terminal.json"),
                "DWORK_FIXTURE_MARKERS": str(markers),
            }
        )
        assert shutil.which("python.exe", path=env["PATH"]) is None
        assert shutil.which("py.exe", path=env["PATH"]) is None
        executable = tested / "dwork-tray.exe"
        subprocess.run([str(executable), "--help"], env=env, cwd=root, check=True, timeout=20)
        subprocess.run(
            [
                str(executable),
                "--wsl-distribution",
                "Ubuntu Test",
                "--wsl-python",
                "/home/test/env space/bin/python",
                "--check",
            ],
            env=env,
            cwd=root,
            check=True,
            timeout=30,
        )
        subprocess.run(
            [str(tested / "dwork-portable-probe.exe")], env=env, cwd=root, check=True, timeout=40
        )
        recorded = json.loads((root / "operation.json").read_text(encoding="utf-8"))
        assert recorded == [
            "--distribution",
            "Ubuntu Test",
            "--user",
            "test",
            "--cd",
            "~",
            "--exec",
            "/home/test/env space/bin/python",
            "-m",
            "dwork",
            "switch",
            "quotes ' ; $() & 工作",
        ], recorded
        terminal = json.loads((root / "terminal.json").read_text(encoding="utf-8"))
        script = base64.b64decode(terminal[-1]).decode("utf-16-le")
        assert "dwork-tray-terminal.exe" in script and "python.exe" not in script
        assert not list(markers.glob("*.json"))
    print(
        "Portable frozen app/resource/status/interactive helper checks passed with no external Python on child PATH. WSL and Terminal are harmless executable fixtures; real desktop verification remains separate."
    )


if __name__ == "__main__":
    main()
