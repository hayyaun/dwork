# Shell functions

[Project home](../../README.md) · [dwork guide](dwork/README.md)

[`.shell_functions`](../../.shell_functions) is the shared entry point for Bash
and Zsh. It sources individual [function modules](../../functions/README.md).
Source this entry point from either shell's startup file to load the functions.

## File layout

- [`.shell_functions`](../../.shell_functions): resolves the repository location
  and sources each function module.
- [`functions/dwork.sh`](../../functions/dwork.sh): defines `dwork`.
- [`functions/got.sh`](../../functions/got.sh): defines `got`.
- [`functions/README.md`](../../functions/README.md): lists modules and explains
  how to add another function.

The loader resolves paths relative to itself, so your current working directory
can be anywhere. Keep the loader and `functions/` directory together when moving
or copying the repository.

## What sourcing does

Sourcing executes the file in the current shell, so functions become available as
commands in that shell. It does not launch Docker or switch projects until you
invoke a function such as `dwork` or `got`.

Bash and Zsh normally read different startup files. Each startup file sources
this same shared file, so the function definitions stay in one place.

## Requirements

- Bash or Zsh.
- Functions may need additional tools; see [dwork requirements](dwork/README.md#requirements).

## Install

Clone or download this repository somewhere permanent. The examples below use
`~/projects/foss/shellfunx`; change that path if you put the repository elsewhere.

Add this line to **`~/.bashrc` for Bash** and/or **`~/.zshrc` for Zsh**:

```sh
[ -r "$HOME/projects/foss/shellfunx/.shell_functions" ] && . "$HOME/projects/foss/shellfunx/.shell_functions"
```

Both shells can source the same file. Do not source your whole Bash startup file
from Zsh, or vice versa.

Open a new terminal, or load the functions immediately in your current shell:

```sh
. "$HOME/projects/foss/shellfunx/.shell_functions"
```

The file defines functions; sourcing it does not start or stop containers.
It does not need executable permissions. Review shell files before sourcing them:
they execute in your shell.

Because your startup file points directly at the repository, repository updates
are available in new terminals. Source the file again to load an update in an
already-open terminal.

## Available functions

- [dwork](dwork/README.md): stop other Compose projects and start existing stopped
  containers belonging to the current project.

- [got](got/README.md): stage changes, commit with a subject and optional body,
  and push.

## Remove

Remove the sourcing line from your shell startup files and open a new terminal.
To remove the function from your current shell:

```sh
unset -f dwork got
```

