"""User install/uninstall and network-free package staging for dwork."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

SOURCE = Path(__file__).resolve().parents[1]
MARKER = ".dwork-install.json"

class InstallError(Exception):
    pass

def paths(prefix_text, destdir_text):
    prefix_input = Path(prefix_text).expanduser()
    if not prefix_input.is_absolute():
        raise InstallError("PREFIX must be absolute.")
    prefix = prefix_input.resolve()
    if destdir_text:
        stage = Path(destdir_text).expanduser().resolve()
        root = stage / str(prefix).lstrip("/")
    else:
        root = prefix
    data = root / "share" / "dwork"
    launcher = root / "bin" / "dwork"
    for path in (data, launcher):
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            raise InstallError("Install paths must remain inside PREFIX/DESTDIR.")
        if path.is_symlink():
            raise InstallError("Refusing to replace a symlink: " + str(path))
    return prefix, root, data, launcher

def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()

def ownership(data, launcher, prefix):
    if not data.exists():
        if launcher.exists():
            raise InstallError("Refusing to overwrite an unrelated executable: " + str(launcher))
        return None
    marker = data / MARKER
    if not marker.is_file():
        raise InstallError("Refusing to modify an unrecognized install directory: " + str(data))
    record = json.loads(marker.read_text())
    if record.get("tool") != "dwork" or record.get("format") != 1 or record.get("prefix") != str(prefix):
        raise InstallError("Installation marker does not match this PREFIX.")
    if launcher.exists() and (not launcher.is_file() or digest(launcher.read_text()) != record.get("launcher_sha256")):
        raise InstallError("Installed launcher was modified; refusing to overwrite or remove it.")
    return record

def checked(command):
    subprocess.run([str(arg) for arg in command], check=True)

def install(args):
    prefix, root, data, launcher = paths(args.prefix, args.destdir)
    if args.venv == "1" and args.destdir:
        raise InstallError("DESTDIR staging requires VENV=0; virtual environments are not relocatable.")
    for name in ("docs", "examples"):
        try:
            data.resolve().relative_to((SOURCE / name).resolve())
        except ValueError:
            continue
        raise InstallError("Install location cannot be inside copied source documentation/examples.")
    previous = ownership(data, launcher, prefix)
    # Do not follow user-added links while updating managed code or environments.
    for name in ("lib", "docs", "examples", "venv", "venv/bin", "README.md", "requirements.txt", MARKER):
        path = data / name
        if path.is_symlink():
            raise InstallError("Refusing to update a linked install path: " + str(path))
    for name in ("lib", "docs", "examples"):
        path = data / name
        if path.is_dir() and any(item.is_symlink() for item in path.rglob("*")):
            raise InstallError("Refusing to update an install tree containing links: " + str(path))
    runtime_data = prefix / "share" / "dwork"
    interpreter = runtime_data / "venv/bin/python" if args.venv == "1" else Path(sys.executable)
    launcher_text = ("#!/bin/sh\n# Installed by dwork; managed by make install/uninstall.\nexec "
                     + shlex.quote(str(interpreter)) + " "
                     + shlex.quote(str(runtime_data / "lib/dwork.py")) + ' "$@"\n')
    record = {"tool": "dwork", "format": 1, "prefix": str(prefix),
              "launcher_sha256": digest(launcher_text), "venv": args.venv == "1"}
    data.mkdir(parents=True, exist_ok=True)
    # Record ownership before dependency setup, so an interrupted first install
    # can be safely retried or explicitly uninstalled.
    if previous is None:
        (data / MARKER).write_text(json.dumps(record, indent=2) + "\n")
    try:
        if args.venv == "1":
            env_python = data / "venv/bin/python"
            if not env_python.is_file():
                try:
                    checked([sys.executable, "-m", "venv", data / "venv"])
                except subprocess.CalledProcessError:
                    raise InstallError("Cannot create the Python environment. On Ubuntu, install python3-venv and retry.")
            checked([env_python, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                     "-r", SOURCE / "requirements.txt"])
        (data / "lib").mkdir(exist_ok=True)
        shutil.copy2(SOURCE / "lib/dwork.py", data / "lib/dwork.py")
        shutil.copy2(SOURCE / "requirements.txt", data / "requirements.txt")
        shutil.copy2(SOURCE / "README.md", data / "README.md")
        for name in ("examples", "docs"):
            if (SOURCE / name).is_dir():
                shutil.copytree(SOURCE / name, data / name, dirs_exist_ok=True)
        for name in ("LICENSE", "LICENSE.md", "COPYING"):
            if (SOURCE / name).is_file():
                shutil.copy2(SOURCE / name, data / name)
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text(launcher_text)
        launcher.chmod(0o755)
        (data / MARKER).write_text(json.dumps(record, indent=2) + "\n")
    except (OSError, subprocess.CalledProcessError, InstallError):
        # Keep a marked partial install for a safe retry; never remove user files.
        raise
    print("Installed dwork: " + str(launcher))
    if not args.destdir:
        bindir = str(prefix / "bin")
        if bindir not in os.environ.get("PATH", "").split(os.pathsep):
            print("Add the command directory to PATH in your shell startup file:")
            print("  export PATH=" + shlex.quote(bindir) + ':"$PATH"')
        print("If you previously sourced dwork.sh, remove that startup line and run: unset -f dwork")
        print("Examples: " + str(data / "examples"))
    return 0

def uninstall(args):
    prefix, root, data, launcher = paths(args.prefix, args.destdir)
    record = ownership(data, launcher, prefix)
    if record is None:
        print("No dwork installation found at " + str(prefix))
        return 0
    # Resolve and re-check the exact bounded target before recursive removal.
    expected = (root.resolve() / "share" / "dwork").resolve()
    if data.is_symlink() or data.resolve() != expected or not (data / MARKER).is_file():
        raise InstallError("Refusing to remove a directory outside the expected install location.")
    if launcher.exists():
        launcher.unlink()
    shutil.rmtree(data)
    print("Removed dwork from " + str(prefix))
    print("Project dwork.yml files and shell startup files were left in place.")
    return 0

def main():
    if os.name != "posix":
        raise InstallError("Use make install from Linux, WSL, or another POSIX environment.")
    if sys.version_info < (3, 10):
        raise InstallError("The installer requires Python 3.10 or newer.")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "uninstall"):
        command = commands.add_parser(name)
        command.add_argument("--prefix", default=str(Path.home() / ".local"))
        command.add_argument("--destdir", default="")
        if name == "install":
            command.add_argument("--venv", choices=("0", "1"), default="1")
    args = parser.parse_args()
    return install(args) if args.command == "install" else uninstall(args)

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (InstallError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print("dwork installer: " + str(error), file=sys.stderr)
        sys.exit(1)
