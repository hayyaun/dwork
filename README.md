# dotfiles

Shared shell functions for Bash and Zsh. Source one file from either shell's
startup file.

Currently includes **dwork**: switch between existing Docker Compose projects
without visiting the previous repository or creating new containers.

## Requirements

- Bash or Zsh on Linux, macOS, or WSL2.
- Docker CLI and access to a running Docker Engine.
- Docker Compose with support for
  `config --no-interpolate --no-env-resolution --format json`.
- Python 3, available as `python3`.

Checked with Docker Compose v5.0.0 on Ubuntu in WSL2, using both Bash and Zsh.

## Install

Clone or download this repository somewhere permanent. The examples below use
`~/projects/foss/dotfiles`; change that path if you put the repository elsewhere.

Add this line to **`~/.bashrc` for Bash** and/or **`~/.zshrc` for Zsh**:

```sh
[ -r "$HOME/projects/foss/dotfiles/.shell_functions" ] && . "$HOME/projects/foss/dotfiles/.shell_functions"
```

Both shells can source the same file. Do not source your whole Bash startup file
from Zsh, or vice versa.

Open a new terminal, or load the functions immediately in your current shell:

```sh
. "$HOME/projects/foss/dotfiles/.shell_functions"
```

The file defines functions; sourcing it does not start or stop containers.
It does not need executable permissions. Review shell files before sourcing them:
they execute in your shell.

Because your startup file points directly at the repository, repository updates
are available in new terminals. Source the file again to load an update in an
already-open terminal.

## dwork

Run from the directory where you normally run Docker Compose:

```sh
dwork --dry-run
dwork
```

The preview reads Docker and Compose state without changing containers.

`dwork`:

1. Reads the current Compose project name and service definitions.
2. Reports services that have no existing containers.
3. Stops running or restarting containers belonging to other Compose projects,
   except projects you explicitly keep running.
4. Starts current-project containers whose state is `created` or `exited`.

It uses `docker stop` and `docker start`. It never calls `docker compose up`,
creates containers, pulls images, builds images, recreates containers, or removes
containers, networks, or volumes. Current-project containers already running are
left running. Containers without a Compose project label are left alone.

### Compose options

Pass Compose global options after `dwork` (and after `--dry-run`, if used):

```sh
dwork -f compose.yaml -f compose.dev.yaml
dwork --dry-run -p my-project -f compose.yaml
dwork --project-directory ./backend
```

Use the same project name and Compose files you used when creating the containers.
Compose's normal file discovery searches the current directory and its parents;
it does not search every subdirectory of a repository.

Runtime environment values are already stored in existing containers.
`dwork` reads the Compose model with interpolation and service env-file resolution
disabled, so ordinary runtime variables do not require an `--env-file` argument.
If your project identity or file selection depends on an environment file,
provide the appropriate Compose options, for example:

```sh
dwork --env-file .env.local -p my-project
```

If a project name cannot be resolved safely, `dwork` exits before changing
containers.

### Keep shared projects running

Use a comma-separated list of exact Compose project names, without spaces:

```sh
export DWORK_KEEP_PROJECTS=infra,monitoring
```

Put that export in your shell startup file or a shared environment file if you
want it to persist. To keep a project only for one invocation:

```sh
DWORK_KEEP_PROJECTS=infra dwork
```

### Missing containers

A missing service produces a warning. `dwork` still switches existing containers;
it does not create the missing service. Optional profile services can also
produce warnings.

Create missing containers manually using your project's documented setup
commands and environment, then use `dwork` for subsequent switches.

### Limits and behavior

- Uses the Docker daemon/context selected by your Docker CLI. Check that context
  before switching; all other Compose projects on it are in scope unless kept.
- Matches containers by the standard `com.docker.compose.project` label. Separate
  repositories sharing a project name are treated as the same project.
- Starts containers individually, without Compose dependency ordering or health
  waits. Use your project's normal startup procedure when ordering is required.
- Starts all existing stopped containers in the target project, including exited
  job containers and containers for services no longer in the current file.
- Leaves paused or dead target containers alone and reports their state.
- Warns when a service has no container; does not check replica counts.
- Stops on a Docker failure. Changes already completed are not rolled back.

For command help:

```sh
dwork --help
```

## Remove

Remove the sourcing line from your shell startup files and open a new terminal.
To remove the function from your current shell:

```sh
unset -f dwork
```

## Docker references

- [Compose configuration](https://docs.docker.com/reference/cli/docker/compose/config/)
- [Compose project names](https://docs.docker.com/compose/how-tos/project-name/)
- [Start existing containers](https://docs.docker.com/reference/cli/docker/container/start/)
