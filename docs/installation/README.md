# Installation

[Project home](../../README.md) · [Usage](../usage/README.md)

## Recommended: make install

Requirements: Git, Make, Python 3.10 or newer, and Python venv/pip support.
On macOS, use Python 3.13 or newer for supervised terminal/background tasks;
the process-lifecycle API used by dwork is available there starting with 3.13.
On Ubuntu/WSL, install these prerequisites through your package manager if missing:

```sh
sudo apt install git make python3 python3-venv
```

On macOS with Homebrew, install Python and choose it explicitly:

```sh
brew install python@3.14
```

Then:

```sh
git clone https://github.com/hayyaun/dwork.git
cd dwork
make install
```

On macOS, run `make install PYTHON="$(brew --prefix python@3.14)/bin/python3.14"`
to avoid selecting an older system Python. Apple's Command Line Tools provide Git
and Make (`xcode-select --install` if they are missing).

This is a user install; do not run it with sudo. It creates:

- `~/.local/bin/dwork`: a command usable from any shell and project directory.
- `~/.local/share/dwork/lib/dwork.py`: the runtime.
- `~/.local/share/dwork/venv/`: an isolated Python environment containing PyYAML.
- `~/.local/share/dwork/examples/` and `docs/`: the shipped guides and examples.
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

If dependency setup is interrupted, retry `make install` with the same prefix.
A marked partial installation can also be removed with `make uninstall`.

## Python, Homebrew, and Debian packages

[GitHub release v0.3.0](https://github.com/hayyaun/dwork/releases/tag/v0.3.0)
provides verified packages. Check downloaded files against its
[SHA256SUMS](https://github.com/hayyaun/dwork/releases/download/v0.3.0/SHA256SUMS)
before installing. Public Homebrew tap, PyPI, AUR, and apt repository publication
remain pending; channel instructions are in [packaging/](../../packaging/README.md).

- Python: download the [wheel](https://github.com/hayyaun/dwork/releases/download/v0.3.0/dwork_cli-0.3.0-py3-none-any.whl)
  or [source distribution](https://github.com/hayyaun/dwork/releases/download/v0.3.0/dwork_cli-0.3.0.tar.gz).
  Install the local wheel with `pipx install ./dwork_cli-0.3.0-py3-none-any.whl`
  or `uv tool install ./dwork_cli-0.3.0-py3-none-any.whl`.
  The distribution is named `dwork-cli`, while the command remains `dwork`.
  Checkout installation with `pipx install .` or `uv tool install .` also works;
  registry installation by name must wait for publication.
- Homebrew: test the prepared v0.3.0 formula in a local tap using the
  [Homebrew guide](../../packaging/homebrew/README.md). Stable v0.3.0 includes
  macOS support; a public tap is separate and has not been published.
- Debian/Ubuntu: download the [`.deb`](https://github.com/hayyaun/dwork/releases/download/v0.3.0/dwork_0.3.0-1_all.deb)
  and install the verified local file with apt. To build it yourself, use
  `python3 scripts/build-deb.py`; see the
  [Debian guide](../../packaging/debian/README.md) for prerequisites.
- Fedora 44 and Arch: the release provides an
  [RPM](https://github.com/hayyaun/dwork/releases/download/v0.3.0/dwork-0.3.0-1.fc44.noarch.rpm)
  and [Arch package](https://github.com/hayyaun/dwork/releases/download/v0.3.0/dwork-0.3.0-1-any.pkg.tar.zst).
  These target Fedora 44 and the current Arch rolling distribution respectively.

Use one installation method at a time. Remove an old sourced function when
switching to an executable, as described below. The optional agent skill is
installed separately for every distribution method.

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

Update the checkout using your normal Git workflow, then run `make install` again.
The launcher does not depend on the source checkout after installation.

From a checkout, uninstall with:

```sh
make uninstall
```

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
