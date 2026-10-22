"""Interactive CLI wrapper in a user-visible terminal; completion only requests refresh."""

import base64
import json
from pathlib import Path
import subprocess
import sys


def run_operation(spec):
    action, name = spec["action"], spec.get("name")
    if (
        action not in ("switch", "down")
        or (action == "switch" and not isinstance(name, str))
        or (action == "down" and name is not None)
    ):
        raise ValueError("Unsupported operation")
    command = [sys.executable, "-m", "dwork", action] + ([name] if name is not None else [])
    code = 1
    try:
        # Inherit the real terminal. Never pipe input, answer prompts, or add flags.
        code = subprocess.call(command)
        return code
    except KeyboardInterrupt:
        code = 130
        return code
    finally:
        try:
            Path(spec["marker"]).write_text(str(code))
        except OSError:
            pass  # The companion may already have quit; CLI work is independent.


def main():
    code = run_operation(json.loads(base64.urlsafe_b64decode(sys.argv[1])))
    print("dwork finished (exit " + str(code) + ").")
    try:
        input("Press Enter to finish this operation.")
    except EOFError:
        pass
    return code


if __name__ == "__main__":
    raise SystemExit(main())
