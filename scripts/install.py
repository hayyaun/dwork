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
import tempfile

SOURCE = Path(__file__).resolve().parents[1]
MARKER = ".dwork-install.json"
LICENSE_FILES = ("LICENSE", "LICENSE.md", "COPYING")
COMPLETION_FILES = {
    "share/bash-completion/completions/dwork",
    "etc/bash_completion.d/dwork",
    "share/zsh/site-functions/_dwork",
    "share/zsh/vendor-completions/_dwork",
}


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


def atomic_write(path, text, mode=0o644):
    """Publish a complete file; an interrupted replacement keeps old or new data."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_marker(data, record):
    atomic_write(data / MARKER, json.dumps(record, indent=2) + "\n", 0o600)


def completion_path(root, relative):
    if relative not in COMPLETION_FILES:
        raise InstallError("Unrecognized completion path: " + str(relative))
    path = root / relative
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise InstallError("Completion paths must remain inside PREFIX/DESTDIR.")
    for item in (path, *path.parents):
        if item == root:
            break
        if item.is_symlink():
            raise InstallError("Refusing a linked completion path: " + str(item))
    return path


def completion_locations(prefix, root, bash_directory, zsh_directory):
    locations = {}
    for shell, directory, default, filename in (
        ("bash", bash_directory, "share/bash-completion/completions", "dwork"),
        ("zsh", zsh_directory, "share/zsh/site-functions", "_dwork"),
    ):
        directory = Path(directory) if directory else prefix / default
        try:
            relative = str((directory / filename).relative_to(prefix))
        except ValueError:
            raise InstallError("Completion directories must be inside PREFIX.")
        locations[shell] = (relative, completion_path(root, relative))
    return locations


def ownership(data, launcher, prefix):
    if not data.exists():
        if launcher.exists():
            raise InstallError("Refusing to overwrite an unrelated executable: " + str(launcher))
        return None
    marker = data / MARKER
    if not marker.is_file():
        raise InstallError("Refusing to modify an unrecognized install directory: " + str(data))
    record = json.loads(marker.read_text())
    if (
        record.get("tool") != "dwork"
        or record.get("format") != 1
        or record.get("prefix") != str(prefix)
    ):
        raise InstallError("Installation marker does not match this PREFIX.")
    pending = record.get("pending", {})
    if not isinstance(pending, dict):
        raise InstallError("Invalid pending installation ownership record.")
    if launcher.exists():
        if not launcher.is_file() or digest(launcher.read_text()) not in (
            record.get("launcher_sha256"),
            pending.get("launcher_sha256"),
        ):
            raise InstallError(
                "Installed launcher was modified; refusing to overwrite or remove it."
            )
        record["launcher_sha256"] = digest(launcher.read_text())
    completions = record.get("completions", {})
    pending_completions = pending.get("completions", {})
    if not isinstance(completions, dict) or not isinstance(pending_completions, dict):
        raise InstallError("Invalid completion ownership record.")
    current_completions = {}
    for relative in completions.keys() | pending_completions.keys():
        path = completion_path(data.parent.parent, relative)
        expected = (completions.get(relative), pending_completions.get(relative))
        current = digest(path.read_text()) if path.is_file() else None
        if path.exists() and (not path.is_file() or current not in expected):
            raise InstallError(
                "Installed completion was modified; refusing to overwrite or remove it: "
                + str(path)
            )
        current_completions[relative] = (
            current or pending_completions.get(relative) or completions[relative]
        )
    # A retry journals only the verified current contents plus its own new files.
    # It cannot expand ownership to arbitrary edits made after an interruption.
    record["completions"] = current_completions
    record.pop("pending", None)
    return record


def checked(command):
    subprocess.run([str(arg) for arg in command], check=True)


def install(args):
    prefix, root, data, launcher = paths(args.prefix, args.destdir)
    if args.venv == "1" and args.destdir:
        raise InstallError(
            "DESTDIR staging requires VENV=0; virtual environments are not relocatable."
        )
    for name in ("docs", "examples"):
        try:
            data.resolve().relative_to((SOURCE / name).resolve())
        except ValueError:
            continue
        raise InstallError(
            "Install location cannot be inside copied source documentation/examples."
        )
    previous = ownership(data, launcher, prefix)
    locations = completion_locations(
        prefix, root, args.bash_completion_dir, args.zsh_completion_dir
    )
    previous_completions = previous.get("completions", {}) if previous else {}
    if previous_completions and set(previous_completions) != {
        relative for relative, _ in locations.values()
    }:
        raise InstallError(
            "Completion directories changed; uninstall this PREFIX before changing them."
        )
    for relative, path in locations.values():
        if path.exists() and relative not in previous_completions:
            raise InstallError("Refusing to overwrite an unrelated completion: " + str(path))
    # Do not follow user-added links while updating managed code or environments.
    for name in (
        "lib",
        "docs",
        "examples",
        "completions",
        "venv",
        "venv/bin",
        "README.md",
        "requirements.txt",
        MARKER,
        *LICENSE_FILES,
    ):
        path = data / name
        if path.is_symlink():
            raise InstallError("Refusing to update a linked install path: " + str(path))
    for name in ("lib", "docs", "examples", "completions"):
        path = data / name
        if path.is_dir() and any(item.is_symlink() for item in path.rglob("*")):
            raise InstallError("Refusing to update an install tree containing links: " + str(path))
    runtime_data = prefix / "share" / "dwork"
    interpreter = runtime_data / "venv/bin/python" if args.venv == "1" else Path(sys.executable)
    launcher_text = (
        "#!/bin/sh\n# Installed by dwork; managed by make install/uninstall.\nexec "
        + shlex.quote(str(interpreter))
        + " "
        + shlex.quote(str(runtime_data / "lib/dwork.py"))
        + ' "$@"\n'
    )
    record = {
        "tool": "dwork",
        "format": 1,
        "prefix": str(prefix),
        "launcher_sha256": digest(launcher_text),
        "venv": args.venv == "1",
    }
    scripts = {
        shell: subprocess.check_output(
            [sys.executable, str(SOURCE / "lib/dwork.py"), "completion", shell], text=True
        )
        for shell in locations
    }
    # Zsh autoload expects a function body. Keep the public sourceable script
    # intact and delegate to it on the first completion request.
    native_scripts = dict(
        scripts,
        zsh="#compdef dwork\nsource "
        + shlex.quote(str(runtime_data / "completions/_dwork"))
        + '\n_dwork "$@"\n',
    )
    record["completions"] = {
        relative: digest(native_scripts[shell]) for shell, (relative, _) in locations.items()
    }
    data.mkdir(parents=True, exist_ok=True)
    # Journal generated hashes before replacing owned files. After interruption,
    # only the previous or planned contents authorize retry/uninstall.
    journal = dict(previous or record)
    journal["pending"] = {key: record[key] for key in ("launcher_sha256", "completions")}
    write_marker(data, journal)
    try:
        if args.venv == "1":
            env_python = data / "venv/bin/python"
            if not env_python.is_file():
                try:
                    checked([sys.executable, "-m", "venv", data / "venv"])
                except subprocess.CalledProcessError:
                    raise InstallError(
                        "Cannot create the Python environment. On Ubuntu, install python3-venv and retry."
                    )
            checked(
                [
                    env_python,
                    "-m",
                    "pip",
                    "install",
                    "--quiet",
                    "--disable-pip-version-check",
                    "-r",
                    SOURCE / "requirements.txt",
                ]
            )
        (data / "lib").mkdir(exist_ok=True)
        for module in sorted((SOURCE / "lib").glob("*.py")):
            shutil.copy2(module, data / "lib" / module.name)
        shutil.copy2(SOURCE / "requirements.txt", data / "requirements.txt")
        shutil.copy2(SOURCE / "README.md", data / "README.md")
        completions = data / "completions"
        completions.mkdir(exist_ok=True)
        for shell, filename in (("bash", "dwork.bash"), ("zsh", "_dwork")):
            (completions / filename).write_text(scripts[shell])
            _, target = locations[shell]
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(target, native_scripts[shell])
        for name in ("examples", "docs"):
            if (SOURCE / name).is_dir():
                shutil.copytree(SOURCE / name, data / name, dirs_exist_ok=True)
        for name in LICENSE_FILES:
            if (SOURCE / name).is_file():
                shutil.copy2(SOURCE / name, data / name)
        launcher.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(launcher, launcher_text, 0o755)
        write_marker(data, record)
    except (OSError, subprocess.CalledProcessError, InstallError):
        # Keep a marked partial install for a safe retry; never remove user files.
        raise
    print("Installed dwork: " + str(launcher))
    if not args.destdir:
        bindir = str(prefix / "bin")
        if bindir not in os.environ.get("PATH", "").split(os.pathsep):
            print("Add the command directory to PATH in your shell startup file:")
            print("  export PATH=" + shlex.quote(bindir) + ':"$PATH"')
        print(
            "If you previously sourced dwork.sh, remove that startup line and run: unset -f dwork"
        )
        print("Examples: " + str(data / "examples"))
        print("Installed shell completions:")
        for shell, (relative, _) in locations.items():
            print("  " + shell + ": " + str(prefix / relative))
        print("Discovery requires bash-completion or a Zsh fpath directory scanned by compinit.")
        print("For custom prefixes without discovery, enable Bash completion in ~/.bashrc:")
        print("  source " + shlex.quote(str(runtime_data / "completions/dwork.bash")))
        print("For Zsh, add this after compinit in ~/.zshrc:")
        print("  source " + shlex.quote(str(runtime_data / "completions/_dwork")))
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
    for relative in record.get("completions", {}):
        completion_path(root, relative).unlink(missing_ok=True)
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
            command.add_argument("--bash-completion-dir", default="")
            command.add_argument("--zsh-completion-dir", default="")
    args = parser.parse_args()
    return install(args) if args.command == "install" else uninstall(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (InstallError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print("dwork installer: " + str(error), file=sys.stderr)
        sys.exit(1)
