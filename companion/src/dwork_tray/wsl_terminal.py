"""Windows Terminal entry point; inherits the terminal for CLI confirmations."""

import base64
import json
from pathlib import Path
import subprocess
import sys

from dwork_tray.client import validate_operation
from dwork_tray.platforms import CompanionError
from dwork_tray.wsl import executable, wsl_command


def run_operation(spec):
    if sys.platform != "win32":
        raise CompanionError("This terminal entry point runs on the Windows host only.")
    action, name = spec["action"], spec.get("name")
    validate_operation(action, name)
    command = wsl_command(
        executable("wsl.exe"), spec["distribution"], spec["python"], spec.get("user")
    )
    command += ["-m", "dwork", action] + ([name] if name is not None else [])
    code = 1
    try:
        # A real terminal, no piped input, approval flags, or answers to prompts.
        code = subprocess.call(command)
        return code
    except KeyboardInterrupt:
        code = 130
        return code
    finally:
        try:
            Path(spec["marker"]).write_text(str(code), encoding="utf-8")
        except OSError:
            pass  # Quit may have removed the private completion directory.


def main():
    try:
        code = run_operation(json.loads(base64.urlsafe_b64decode(sys.argv[1])))
        print("dwork finished (exit " + str(code) + ").")
    except (CompanionError, OSError, ValueError, KeyError) as error:
        print("dwork-tray: " + str(error), file=sys.stderr)
        code = 1
    try:
        input("Press Enter to finish this operation.")
    except (EOFError, KeyboardInterrupt):
        pass
    return code


if __name__ == "__main__":
    raise SystemExit(main())
