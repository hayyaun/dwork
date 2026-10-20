# Installation

[Project home](../../README.md) · [Usage](../usage/README.md)

## Recommended: make install

Requirements: Git, Make, Python 3.10 or newer, and Python venv/pip support.
On Ubuntu/WSL, install these prerequisites through your package manager if missing:

```sh
sudo apt install git make python3 python3-venv
```

Then:

```sh
git clone https://github.com/hayyaun/dwork.git
cd dwork
make install
```

This is a user install; do not run it with sudo. It creates:

- `~/.local/bin/dwork`: a command usable from any shell and project directory.
- `~/.local/share/dwork/lib/dwork.py`: the runtime.
- `~/.local/share/dwork/venv/`: an isolated Python environment containing PyYAML.
- `~/.local/share/dwork/examples/` and `docs/`: the shipped guides and examples.

The default install downloads PyYAML and its requirements using pip inside that
environment. It does not install into or alter your system Python. Shell startup
files and project configs are not edited.

If `~/.local/bin` is not on `PATH`, the installer prints the export line to add to
your shell startup file. For the default prefix:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

You can also invoke `~/.local/bin/dwork --help` directly.

If dependency setup is interrupted, retry `make install` with the same prefix.
A marked partial installation can also be removed with `make uninstall`.

## Runtime dependencies

- Docker and Docker Compose for Compose workspaces. Compose must support
  `config --no-interpolate --no-env-resolution --format json`.
- Bash or Zsh as `SHELL` for terminal tasks.
- Native Linux: a graphical desktop and GNOME Terminal, Konsole, Xfce Terminal,
  or xterm (new windows only).
- WSL2: Windows Terminal and `powershell.exe`.

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

The compatibility entry point `.shell_functions` loads only dwork. The unrelated
got function is no longer part of this project.

To remove the source-based setup, remove its startup line and run `unset -f dwork`.

## Package-maintainer installation

Package managers should provide Python/PyYAML themselves and avoid network
downloads or private virtual environments while staging:

```sh
make install VENV=0 PREFIX=/usr DESTDIR="/absolute/path/to/pkgdir"
```

This installs into `DESTDIR/usr/bin` and `DESTDIR/usr/share/dwork` while the launcher
references the final `/usr/share/dwork` location, not the staging path.
The interpreter is the one used for `PYTHON` during installation; select the
distribution's runtime interpreter explicitly when needed.

`DESTDIR` with the default `VENV=1` is rejected because virtual environments are
not relocatable. `VENV=0` does not install Python dependencies; the package manager
or user must provide them.

See [publishing](../publishing/README.md) for AUR, Homebrew, and PyPI preparation.
