#!/usr/bin/env python3
"""Build a portable Windows bundle; official downloads are built on Windows CI."""

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def copy_licenses(destination):
    destination.mkdir()
    for name in ("pystray", "Pillow", "six", "pyinstaller", "pyinstaller-hooks-contrib"):
        distribution = metadata.distribution(name)
        found = False
        for entry in distribution.files or ():
            if not any(word in entry.name.lower() for word in ("license", "copying", "notice")):
                continue
            source = Path(distribution.locate_file(entry))
            if source.is_file():
                target = destination / name / "__".join(entry.parts)
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(source, target)
                found = True
        if not found:
            raise RuntimeError("Missing bundled dependency license: " + name)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("The Windows Python runtime LICENSE.txt is required.")
    shutil.copyfile(python_license, destination / "Python-LICENSE.txt")


def build(output):
    if sys.platform != "win32":
        raise RuntimeError(
            "Build the portable application on Windows (official downloads use Windows CI); PyInstaller cannot cross-compile it on Linux."
        )
    if sys.maxsize <= 2**32:
        raise RuntimeError("The portable Windows build requires the x64 Python CI runner.")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    version = metadata.version("dwork-tray")
    name = "dwork-tray-" + version + "-windows-x64"
    archive = output / (name + ".zip")
    if archive.exists():
        raise RuntimeError("Refusing to replace an existing portable archive: " + str(archive))
    with tempfile.TemporaryDirectory(prefix="dwork-portable-build-") as temporary:
        work = Path(temporary)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--clean",
                "--noconfirm",
                "--distpath",
                str(work / "dist"),
                "--workpath",
                str(work / "build"),
                str(ROOT / "packaging/windows/dwork-tray.spec"),
            ],
            cwd=ROOT,
            check=True,
        )
        app = work / "dist/dwork-tray"
        for file in (
            "dwork-tray.exe",
            "dwork-tray-terminal.exe",
            "_internal/dwork_tray/observer.py",
        ):
            if not (app / file).is_file():
                raise RuntimeError("Portable bundle is incomplete: " + file)
        shutil.copyfile(ROOT / "packaging/windows/README.txt", app / "README.txt")
        shutil.copyfile(ROOT / "LICENSE", app / "LICENSE")
        copy_licenses(app / "licenses")
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        (app / "build-info.json").write_text(
            json.dumps(
                {
                    "source_revision": revision,
                    "companion_version": version,
                    "python": sys.version,
                    "pyinstaller": metadata.version("pyinstaller"),
                    "platform": "windows-x64",
                    "requires_external_python": False,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        shutil.make_archive(str(output / name), "zip", root_dir=app.parent, base_dir=app.name)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / "SHA256SUMS.windows").write_text(
        digest + "  " + archive.name + "\n", encoding="ascii"
    )
    print(archive)
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/windows")
    args = parser.parse_args()
    try:
        build(args.output)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, "build-windows-tray: " + str(error) + "\n")


if __name__ == "__main__":
    main()
