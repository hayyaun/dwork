"""Opt-in per-user login entries; preserve entries owned by another install or edits."""

from pathlib import Path
import os
import plistlib
import sys

from dwork_tray.platforms import CompanionError, native_platform


def entry():
    platform = native_platform()
    if platform == "win32":
        raise CompanionError("Windows login startup is not implemented; no settings were changed.")
    command = [str(Path(sys.executable).absolute()), "-m", "dwork_tray"]
    if platform == "darwin":
        path = Path.home() / "Library/LaunchAgents/org.dwork.tray.plist"
        content = plistlib.dumps(
            {
                "Label": "org.dwork.tray",
                "ProgramArguments": command,
                "RunAtLoad": True,
                "LimitLoadToSessionType": "Aqua",
                "KeepAlive": False,
            }
        )
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", ""))
        if not base.is_absolute():
            base = Path.home() / ".config"
        path = base / "autostart/dwork-tray.desktop"

        if "=" in command[0] or "%" in command[0]:
            raise CompanionError(
                "Linux login executable paths containing = or % are unsupported by the desktop launcher. Use a compatible installation path or start the tray manually; no login entry was changed."
            )

        def quoted(value):
            if any(c in value for c in "\0\r\n"):
                raise CompanionError("Login command paths cannot contain control characters.")
            value = value.replace("%", "%%")
            for char in ("\\", '"', "`", "$"):
                value = value.replace(char, "\\" + char)
            return '"' + value.replace("\\", "\\\\") + '"'

        executable = " ".join(quoted(value) for value in command)
        content = (
            "[Desktop Entry]\nType=Application\nName=dwork tray\nExec="
            + executable
            + "\nTryExec="
            + command[0].replace("\\", "\\\\")
            + "\nTerminal=false\nX-Dwork-Managed=true\n"
        ).encode()
    return path, content


def state():
    path, content = entry()
    if path.is_symlink():
        raise CompanionError("Login entry is a symlink; leaving it unchanged: " + str(path))
    if not path.exists():
        return False
    if path.read_bytes() != content:
        raise CompanionError(
            "Login entry was edited or belongs to another installation; leaving it unchanged: "
            + str(path)
        )
    return True


def set_enabled(enabled):
    path, content = entry()
    present = state()
    if enabled and not present:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(content)
    elif not enabled and present:
        path.unlink()
    return path
