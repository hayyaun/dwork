# Installation

[Project home](../../README.md) · [Usage](../usage/README.md)

## Requirements

- Bash or Zsh, and Python 3.
- Docker CLI and Docker Compose for Compose workspaces. Compose must support
  `config --no-interpolate --no-env-resolution --format json`.
- PyYAML when using `dwork.yml`. On Ubuntu/WSL: `sudo apt install python3-yaml`.
- WSL2, Windows Terminal, and `powershell.exe` for terminal tasks, with Bash or
  Zsh configured as `SHELL`. Other platforms can use Compose-only workspaces.

Checked with Docker Compose v5.0.0 and Python 3.12 on Ubuntu in WSL2, using Bash
and Zsh. A dry run can describe terminal tasks without launching them.

## Source the function

Clone the repository somewhere permanent:

```sh
git clone https://github.com/hayyaun/dwork.git "$HOME/projects/foss/dwork"
```

Add this line to `~/.bashrc` for Bash or `~/.zshrc` for Zsh (or both):

```sh
[ -r "$HOME/projects/foss/dwork/dwork.sh" ] && . "$HOME/projects/foss/dwork/dwork.sh"
```

Open a new terminal, or load it immediately:

```sh
. "$HOME/projects/foss/dwork/dwork.sh"
```

Change the path if you cloned elsewhere. The shell startup files can share the
same entry point. Do not source your entire Bash startup file from Zsh or vice versa.

Sourcing defines `dwork` in the current shell; it does not start containers or
commands. Paths resolve relative to `dwork.sh`, independently of your current
directory. The entry point and `lib/` directory must stay together.

## Updates

Update your checkout using your normal Git workflow, then source `dwork.sh` again.
New terminals load the updated definition automatically.

The old `.shell_functions` file remains a compatibility entry point and loads
only `dwork`. New installations should source `dwork.sh` directly. The unrelated
`got` function is no longer part of this project.

## Remove

Remove the sourcing line from your shell startup files, then open a new terminal.
For the current shell:

```sh
unset -f dwork
```
