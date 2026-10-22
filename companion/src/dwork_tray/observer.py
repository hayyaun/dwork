"""Bounded POSIX read helper; also executed from source inside selected WSL."""

import os
import signal
import subprocess
import sys


def capture_status():
    command = [sys.executable, "-m", "dwork", "list", "--json"]
    with subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        start_new_session=True,
    ) as process:
        try:
            output, errors = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            # Only our read-only child session, while its leader is unreaped.
            # This never targets a saved application PID or terminates a distro.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise
        return subprocess.CompletedProcess(command, process.returncode, output, errors)


def main():
    try:
        result = capture_status()
    except subprocess.TimeoutExpired:
        print(
            "dwork status timed out; inspect Docker/controller access with the CLI.",
            file=sys.stderr,
        )
        return 124
    except OSError as error:
        print("Cannot run the dwork status observer: " + str(error), file=sys.stderr)
        return 1
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
