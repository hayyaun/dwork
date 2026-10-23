# Installation

[Project home](../../README.md) · [Usage](../usage/README.md)

For the short version, see the [installation overview](../../README.md#install).

## Requirements

Requirements: Git, Make, Python 3.10 or newer, and Python venv/pip support.
The one-line installation also needs curl.
On macOS, use Python 3.13 or newer for supervised terminal/background tasks;
the process-lifecycle API used by dwork is available there starting with 3.13.
On Ubuntu/WSL, install these prerequisites through your package manager if missing:

```sh
sudo apt install curl git make python3 python3-venv
```

On macOS with Homebrew, install Python and choose it explicitly:

```sh
brew install python@3.14
```

CLI 0.6.0 and the portable Windows companion 0.2.2 are published in
[GitHub release v0.6.0](https://github.com/hayyaun/dwork/releases/tag/v0.6.0);
see the [package options below](#python-homebrew-and-debian-packages).

## One-line installation

```sh
sh -c "$(curl -fsSL https://raw.githubusercontent.com/hayyaun/dwork/main/install.sh)"
```

This installs the latest source from `main`. The [bootstrap script](../../install.sh) checks Git, Make, and
Python, clones into a temporary directory, and runs the existing `make install`
target. It removes the temporary checkout on success or failure. The installed
command does not depend on that checkout. System dependencies and the optional
agent skill are not installed automatically.

`PREFIX` and `PYTHON` can be set for this command. On macOS with Homebrew:

```sh
PYTHON="$(brew --prefix python@3.14)/bin/python3.14" sh -c "$(curl -fsSL https://raw.githubusercontent.com/hayyaun/dwork/main/install.sh)"
```

For a custom destination:

```sh
PREFIX="$HOME/tools/dwork" sh -c "$(curl -fsSL https://raw.githubusercontent.com/hayyaun/dwork/main/install.sh)"
```

The script does not prompt to install the tray. A fresh ordinary install includes
only the CLI; set `TRAY=1` explicitly to also install the separate native companion,
as [shown below](#optional-native-tray). An already selected tray is retained on
updates even when `TRAY=1` is omitted. Tray installation never launches it or
changes login startup; startup is a separate user choice.

The bootstrap also preserves existing Make environment options such as `VENV`,
`BASH_COMPLETION_DIR`, and `ZSH_COMPLETION_DIR`. The same prefix and completion
directories must be used when updating an existing installation. `VENV=0` requires
you to provide PyYAML yourself, as with a direct Make installation.

The one-line command executes a script downloaded from `main`, then clones the
current `main` source and installs dependencies with pip. It uses your account's
permissions without invoking sudo; a Python environment isolates dependencies,
not the downloaded code's access to your files. Review the source if needed.
The script and later clone are separate downloads of a moving branch, so reviewing
only the script does not pin the project source to that revision.

To review the script before running it:

```sh
curl -fsSL https://raw.githubusercontent.com/hayyaun/dwork/main/install.sh -o install-dwork.sh
less install-dwork.sh
sh install-dwork.sh
```

## Install from a checkout

If you prefer to keep the source locally:

```sh
git clone https://github.com/hayyaun/dwork.git
cd dwork
make install
```

On macOS, run `make install PYTHON="$(brew --prefix python@3.14)/bin/python3.14"`
to avoid selecting an older system Python. Apple's Command Line Tools provide Git
and Make (`xcode-select --install` if they are missing).

## Windows tray for WSL2

The optional [portable Windows tray 0.2.2](https://github.com/hayyaun/dwork/releases/download/v0.6.0/dwork-tray-0.2.2-windows-x64.zip)
runs on the Windows host and connects to `dwork-cli` 0.6.x in a selected WSL
distribution. No separate Windows Python or development tooling is required.
Download the ZIP and release [SHA256SUMS](https://github.com/hayyaun/dwork/releases/download/v0.6.0/SHA256SUMS),
verify its hash, and extract the complete app folder. That folder can stay in Linux.

Follow the [Windows/WSL setup steps](../companion/README.md#set-up-the-portable-app)
to select the Linux interpreter, check the connection, and launch the EXE.
The guide also shows a [desktop shortcut for manual launch](../companion/README.md#start-it-again-without-remembering-the-arguments),
so the WSL arguments do not have to be remembered each time. Check Windows' hidden
notification icons (`^`) if the tray is not immediately visible.

`install.sh` installs the Linux CLI in WSL; it does not download or start this
Windows app. `TRAY=1` is for the native Linux/macOS companion and is rejected inside
WSL. Installing or launching the portable app does not enable Windows sign-in startup.

## Optional native tray

The default installer remains CLI-only. Companion 0.2.2 supports CLI 0.4.x, 0.5.x, and
0.6.x on native Linux/macOS; earlier companion 0.2.0 supports CLI 0.4.x.
Opt in to the separate `dwork-tray` package from source with:

```sh
TRAY=1 sh -c "$(curl -fsSL https://raw.githubusercontent.com/hayyaun/dwork/main/install.sh)"
```

From a checkout, the equivalent is:

```sh
make install TRAY=1
```

Use the same `PREFIX`, `PYTHON`, and completion-directory choices as your CLI
installation. This option requires `VENV=1` without `DESTDIR` staging. It installs
both local projects from the same source checkout into a separate managed
`PREFIX/share/dwork/tray-venv`, with a `PREFIX/bin/dwork-tray` launcher. It does not
require the checkout after installation. The CLI's own environment remains isolated
and does not gain GUI dependencies.

Native Linux needs matching system PyGObject, GTK 3, and AppIndicator or Ayatana
introspection packages, plus a compatible desktop tray host when launched. The
companion environment uses Python's `--system-site-packages` to see those bindings;
the selected Python must match them. macOS requires Python 3.13+; pip installs its
tray dependencies in the companion environment. The installer does not install OS
packages or desktop extensions. See [platform prerequisites](../companion/README.md#linux).
Missing Linux bindings produce guidance and leave a marked partial install that
can be retried after installing prerequisites, or removed with `make uninstall`.

**Installation does not launch the tray or change login startup.** When ready,
start the tray manually:

```sh
dwork-tray
```

### Start the tray at login (optional)

On native Linux/macOS, run these separately after installation, as your normal
user without sudo:

```sh
dwork-tray --autostart enable   # Start at the next graphical login
dwork-tray --autostart status   # Check whether this installation enabled it
```

Alternatively, select **Start at login** in the running tray's menu. To opt out:

```sh
dwork-tray --autostart disable
```

These commands do not start, restart, or stop the current tray. Start `dwork-tray`
manually to use it now. If the command directory is not on PATH, use the installed
full path, such as `~/.local/bin/dwork-tray --autostart enable`. Edited or linked
startup entries are protected; inspect conflicts rather than overwriting them.
[Platform files and Windows sign-in instructions](../companion/README.md#startup-at-login-is-opt-in)
are in the companion guide. Disable an opted-in entry before uninstalling or
moving the installation if you want that entry removed.

### Updating or removing the tray

Normal updates retain and update an already selected tray, even if
`TRAY=1` is omitted; `TRAY=0` does not remove it. To return that prefix to a CLI-only
installation, uninstall it and reinstall without the tray option. Uninstall removes
both managed launchers/environments, while leaving user login-startup settings alone.

For **WSL2**, an optional [portable Windows app](../companion/README.md#windows-and-wsl)
provides the tray on the Windows host without separately installing Windows Python.
`TRAY=1` is rejected inside WSL; the normal Linux CLI install remains available.

## Installed files

This is a user install; do not run it with sudo. It creates:

- `~/.local/bin/dwork`: a command usable from any shell and project directory.
- `~/.local/share/dwork/lib/dwork.py`: the runtime.
- `~/.local/share/dwork/venv/`: an isolated Python environment containing PyYAML.
- `~/.local/share/dwork/examples/` and `docs/`: the shipped guides and examples.
- With `TRAY=1`, `~/.local/bin/dwork-tray` and the separate
  `~/.local/share/dwork/tray-venv/` companion environment.
- `~/.local/share/bash-completion/completions/dwork` and
  `~/.local/share/zsh/site-functions/_dwork`: native completion files.

Completion is discovered when those paths are searched by the shell's existing
completion framework. Zsh commonly needs explicit setup for a user/custom prefix;
system packages and Homebrew select their platform's native directories.
[Shell completion and manual fallback](../completion/README.md) explains the
prerequisites. Older published packages may still require explicit sourcing.

The default install downloads PyYAML and its requirements using pip inside that
environment. It does not install into or alter your system Python. Shell startup
files and project configs are not edited.

If `~/.local/bin` is not on `PATH`, the installer prints the export line to add to
your shell startup file. For the default prefix:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

You can also invoke `~/.local/bin/dwork --help` directly.

To let a coding agent create `dwork.yml` for your projects, separately
[install the optional dwork skill](../skills/README.md). It supports Codex,
Claude Code, Cursor, and other agents through the skills CLI or manual copying.

If dependency setup or an upgrade is interrupted, retry `make install` with the
same prefix and completion directories, or remove the marked partial installation
with `make uninstall`. Current installers record the previous and planned generated
CLI/tray launcher and completion hashes before replacing those files atomically. This permits
recovery from a mixed old/new installation without accepting unrelated user edits.
Modified launchers/completions still block overwrite/removal. Reinstallation also
rejects linked license destinations before writing, preserving their targets.
Use the current installer for this recovery; older published installers may not
recognize an interrupted upgrade's pending ownership record.

## Python, Homebrew, and Debian packages

[GitHub release v0.6.0](https://github.com/hayyaun/dwork/releases/tag/v0.6.0)
provides verified packages. Check downloaded files against its
[SHA256SUMS](https://github.com/hayyaun/dwork/releases/download/v0.6.0/SHA256SUMS)
before installing. Public Homebrew tap, PyPI, AUR, and apt repository publication
remain pending; channel instructions are in [packaging/](../../packaging/README.md).

- Python: download the [wheel](https://github.com/hayyaun/dwork/releases/download/v0.6.0/dwork_cli-0.6.0-py3-none-any.whl)
  or [source distribution](https://github.com/hayyaun/dwork/releases/download/v0.6.0/dwork_cli-0.6.0.tar.gz).
  Install the local wheel with `pipx install ./dwork_cli-0.6.0-py3-none-any.whl`
  or `uv tool install ./dwork_cli-0.6.0-py3-none-any.whl`.
  The distribution is named `dwork-cli`, while the command remains `dwork`.
  Checkout installation with `pipx install .` or `uv tool install .` also works;
  registry installation by name must wait for publication.
- Homebrew: test the prepared v0.6.0 formula in a local tap using the
  [Homebrew guide](../../packaging/homebrew/README.md). Stable v0.6.0 includes
  macOS support; a public tap is separate and has not been published.
- Debian/Ubuntu: download the [`.deb`](https://github.com/hayyaun/dwork/releases/download/v0.6.0/dwork_0.6.0-1_all.deb)
  and install the verified local file with apt. To build it yourself, use
  `python3 scripts/build-deb.py`; see the
  [Debian guide](../../packaging/debian/README.md) for prerequisites.
- Fedora 44 and Arch: the release provides an
  [RPM](https://github.com/hayyaun/dwork/releases/download/v0.6.0/dwork-0.6.0-1.fc44.noarch.rpm)
  and [Arch package](https://github.com/hayyaun/dwork/releases/download/v0.6.0/dwork-0.6.0-1-any.pkg.tar.zst).
  These target Fedora 44 and the current Arch rolling distribution respectively.

Use one installation method at a time. Remove an old sourced function when
switching to an executable, as described below. The optional agent skill is
installed separately for every distribution method.

The optional [portable Windows tray 0.2.2 ZIP](https://github.com/hayyaun/dwork/releases/download/v0.6.0/dwork-tray-0.2.2-windows-x64.zip)
is also attached to v0.6.0 and covered by the same checksum manifest. It connects
to CLI 0.6.x in WSL; see [selection and launch](../companion/README.md#windows-and-wsl).

## Runtime dependencies

- Docker and Docker Compose for Compose workspaces. Compose must support
  `config --no-interpolate --no-env-resolution --format json`.
- Bash or Zsh as `SHELL` for terminal tasks.
- Native Linux: a graphical desktop and GNOME Terminal, Konsole, Xfce Terminal,
  or xterm (new windows only).
- WSL2: Windows Terminal and `powershell.exe`.
- macOS: Apple Terminal and `osascript`, both included with macOS. Visible tasks
  support `window: new`; use `window: none` for detached tasks. The first launch
  may ask permission for the calling application to control Terminal. See
  [macOS terminal behavior](../terminals/README.md#apple-terminal-on-macos).

PyYAML is installed by the default installer. Docker, shells, terminals, Make,
and system packages are not installed automatically.

## Custom prefix

Use an absolute prefix and the same value when uninstalling:

```sh
make install PREFIX="$HOME/tools/dwork"
make uninstall PREFIX="$HOME/tools/dwork"
```

The command goes in `PREFIX/bin` and managed files in `PREFIX/share/dwork`.
Use `PYTHON=/path/to/python3` to choose the interpreter. Install paths with spaces
are supported. The installer refuses unrelated existing files or modified launchers.

## Update or remove

For a one-line installation, rerun the same installer command to update to the
latest `main`. Reuse any `PREFIX`, `PYTHON`, or completion-directory choices.
For a source checkout, update it using your normal Git workflow, then run
`make install` again. The launcher does not depend on the source checkout after
installation.

Uninstall from a checkout with `make uninstall`. If you used the one-line installer
and have no checkout, obtain one first:

```sh
git clone https://github.com/hayyaun/dwork.git
cd dwork
make uninstall
```

Pass the original `PREFIX` for a custom destination, for example
`make uninstall PREFIX="$HOME/tools/dwork"`. On macOS, select your supported
Python with `PYTHON` as during installation.

It removes the managed launcher and installation directory, including the private
venv. Your project's `dwork.yml` files and shell startup files are untouched.
Package-manager installations should be removed with that package manager instead.

## Migrating from the sourced function

An existing shell function takes precedence over an installed executable.
Remove the old dwork sourcing line from `~/.bashrc` / `~/.zshrc`, then open a new
terminal or run:

```sh
unset -f dwork
```

The installed executable runs the same runtime and no longer needs sourcing.
The installer prints this reminder but does not edit those files itself.

## Manual sourcing still works

For a source-based setup, keep the checkout and add this to the appropriate rc file:

```sh
[ -r "$HOME/projects/foss/dwork/dwork.sh" ] && . "$HOME/projects/foss/dwork/dwork.sh"
```

Adjust the path to your clone. Load it in the current shell with:

```sh
. "$HOME/projects/foss/dwork/dwork.sh"
```

Keep `dwork.sh` and `lib/` together. This method uses the `python3` on your PATH;
install PyYAML separately for YAML support (Ubuntu: `sudo apt install python3-yaml`).
The current loader captures its absolute checkout directory when sourced. Relative
sourcing such as `. ./dwork.sh` remains usable after `cd` to another project;
sourcing again updates that location without changing the caller's directory.

The current loader enables completion automatically in interactive Bash and Zsh.
In Zsh, put the source line after Oh My Zsh or your existing `compinit` setup;
the loader does not initialize the completion system itself. If it was sourced
earlier, source it again after `compinit`. Noninteractive shells skip completion,
and missing Python/runtime dependencies do not interrupt shell startup.
See [source-based completion](../completion/README.md#source-based-installations).

To remove the source-based setup, remove its startup line and run `unset -f dwork`.

## Package-maintainer installation

Package managers should provide Python/PyYAML themselves and avoid network
downloads or private virtual environments while staging:

```sh
make install VENV=0 PREFIX=/usr DESTDIR="/absolute/path/to/pkgdir"
```

This installs into `DESTDIR/usr/bin` and `DESTDIR/usr/share/dwork` while the launcher
references the final `/usr/share/dwork` location, not the staging path.
It also stages Bash completion under `usr/share/bash-completion/completions` and
Zsh completion under `usr/share/zsh/site-functions`. For Debian/Ubuntu, add
`ZSH_COMPLETION_DIR=/usr/share/zsh/vendor-completions`; the Debian recipe already
does this. `BASH_COMPLETION_DIR` and `ZSH_COMPLETION_DIR` select supported final
directories under `PREFIX` and must not include `DESTDIR`.
The interpreter is the one used for `PYTHON` during installation; select the
distribution's runtime interpreter explicitly when needed.

`DESTDIR` with the default `VENV=1` is rejected because virtual environments are
not relocatable. `VENV=0` does not install Python dependencies; the package manager
or user must provide them.

See [publishing](../publishing/README.md) for AUR, Homebrew, and PyPI preparation.

## User workspace state

The optional `dwork scan` checkbox picker uses Python's curses module and needs an
interactive terminal. Standard Linux, macOS, and WSL Python builds usually provide it; if your
Python distributor omits curses, the command explains this and keeps the configured
workspaces it already registered. Other commands and `scan --dry-run` do not need
the picker. See [recursive scanning](../workspaces/README.md#scan-a-directory-tree).

The installer and uninstaller leave remembered workspaces in
`$XDG_STATE_HOME/dwork/workspaces.json` (default `~/.local/state/dwork/workspaces.json`).
Use `dwork forget NAME` before uninstalling to remove individual registrations
without touching their containers or project files.
See [workspace commands and storage](../workspaces/README.md).
