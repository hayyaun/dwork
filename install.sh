#!/bin/sh
# Download the current source and reuse the managed user installer.
set -eu

fail() {
    printf 'dwork installer: %s\n' "$*" >&2
    exit 1
}

if [ "$#" -gt 0 ]; then
    if [ "$#" -eq 1 ] && { [ "$1" = --help ] || [ "$1" = -h ]; }; then
        cat <<'EOF'
Install the latest dwork source from GitHub (main).

Usage: sh install.sh
       TRAY=1 sh install.sh  # Also install the optional native Linux/macOS tray

Requires Git, Make, and Python with venv/pip support.
Python 3.10+ is required on Linux/WSL2; macOS needs Python 3.13+.
Set PREFIX to choose an install prefix (default: $HOME/.local).
Set PYTHON to choose a Python executable (default: python3).
Existing make install environment options are also supported.
TRAY=1 requires VENV=1 and native Linux/macOS; WSL uses the portable Windows app.
The tray is never launched and login startup is never enabled by installation.
No sudo is used and shell startup files are not edited.
EOF
        exit 0
    fi
    fail 'Unknown arguments. Run sh install.sh --help for usage.'
fi

for tool in git make mktemp; do
    command -v "$tool" >/dev/null 2>&1 || fail "Missing $tool; install it and retry."
done

python=${PYTHON:-python3}
command -v "$python" >/dev/null 2>&1 || fail "Cannot find Python: $python. Set PYTHON to its executable."
# Keep the interpreter path valid after entering the temporary checkout, without
# resolving venv symlinks back to the system interpreter.
python=$("$python" -c '
import os
import platform
import sys

if sys.platform not in ("linux", "darwin"):
    raise SystemExit("dwork installer: Use Linux, WSL2, or macOS.")
minimum = (3, 13) if sys.platform == "darwin" else (3, 10)
if sys.version_info < minimum:
    version = ".".join(map(str, minimum))
    raise SystemExit("dwork installer: Python " + version + "+ required; choose it with PYTHON.")
tray = os.environ.get("TRAY", "0")
if tray not in ("0", "1"):
    raise SystemExit("dwork installer: TRAY must be 0 or 1.")
if tray == "1":
    if os.environ.get("VENV", "1") != "1" or os.environ.get("DESTDIR"):
        raise SystemExit("dwork installer: TRAY=1 requires VENV=1 without DESTDIR staging.")
    if sys.platform == "linux" and (
        os.environ.get("WSL_DISTRO_NAME") or "microsoft" in platform.release().lower()
    ):
        raise SystemExit(
            "dwork installer: TRAY=1 is for native Linux/macOS. "
            "For WSL, use the optional portable Windows tray; see "
            "https://github.com/hayyaun/dwork/blob/main/docs/companion/README.md#windows-and-wsl"
        )
if os.environ.get("VENV", "1") != "0":
    try:
        import ensurepip
        import venv
    except ImportError:
        raise SystemExit(
            "dwork installer: Python venv/pip support is required. "
            "On Ubuntu/WSL install python3-venv, or choose another PYTHON."
        )
print(os.path.abspath(sys.executable))
') || exit 1

prefix=${PREFIX:-"$HOME/.local"}
workdir=$(mktemp -d "${TMPDIR:-/tmp}/dwork-install.XXXXXXXX") || fail 'Cannot create a temporary directory.'
trap 'rm -rf -- "$workdir"' 0
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

printf 'Installing dwork from main into %s\n' "$prefix"
git clone --depth 1 --branch main -- https://github.com/hayyaun/dwork.git "$workdir/source"
(
    cd "$workdir/source"
    make install "PYTHON=$python" "PREFIX=$prefix"
)
