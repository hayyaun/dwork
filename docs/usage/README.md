# dwork

[Project home](../../README.md) · [Installation](../installation/README.md)

Switch development workspaces from your current directory: existing Compose
containers by default, or a [dwork.yml configuration](../configuration/README.md)
with optional health-gated terminal commands.

Implementation: [shell function](../../dwork.sh) and
[Python runtime](../../lib/dwork.py).

## Requirements

- Bash or Zsh on Linux, macOS, or WSL2.
- Docker CLI and access to a running Docker Engine.
- Docker Compose with support for
  `config --no-interpolate --no-env-resolution --format json`.
- Python 3, available as `python3`.

Checked with Docker Compose v5.0.0 on Ubuntu in WSL2, using both Bash and Zsh.
First follow the [installation instructions](../installation/README.md).

Optional YAML and terminal requirements are covered in the
[configuration guide](../configuration/README.md#requirements).

## Usage

Run from the directory where you normally run Docker Compose:

```sh
dwork --dry-run
dwork
```

The preview reads configuration and container state without changing containers,
waiting for health checks, opening terminals, or registering directories.

`dwork`:

1. Reads the current Compose project name and service definitions, or discovers
   projects in immediate subdirectories when no default config is available.
2. Reports services that have no existing containers.
3. On a new workspace, asks before remembering its directory and Compose identity.
   Declining or end-of-input cancels without switching.
4. Stops running or restarting managed containers belonging to other registered
   workspaces on the same Docker target, except projects you explicitly keep running.
5. Starts selected-project containers whose state is `created` or `exited`.

It uses `docker stop` and `docker start`. It never calls `docker compose up`,
creates containers, pulls images, builds images, recreates containers, or removes
containers, networks, or volumes. Current-project containers already running are
left running. Containers without a Compose project label are left alone.
Unregistered Compose projects are also left running.

### Remember and switch workspaces

```sh
dwork register my-app     # Save this workspace without starting or stopping anything
dwork list               # Registered names, directory paths, and container status
dwork switch my-app      # Activate the saved workspace from anywhere
dwork switch my-app --dry-run
dwork down                # Stop all registered workloads on this Docker target
dwork forget my-app      # Remove only the registration
```

The name is optional for `register`; it defaults to the Compose project name,
or the directory name for a host-only workspace or a group of child workspaces.
`switch` uses saved Compose options and does not change your calling shell's directory.
See [workspace registration](../workspaces/README.md) for naming, Docker targets,
configuration changes, shared infrastructure, and moved directories.

### Stop all registered workloads

```sh
dwork down --dry-run
dwork down
```

Run from any directory. `down` stops running, restarting, and paused containers
managed by all registered workspaces on the current Docker target in one Docker
stop call. Registered service selections and `DWORK_KEEP_PROJECTS` still apply;
unregistered projects stay running. It does not remove containers, networks,
volumes, or registrations, and it does not stop host terminal commands or the
Docker daemon/WSL VM. Docker's normal stop signal and timeout behavior apply.

Unlike a workspace switch, explicit `down` also stops registered workloads whose
directories have moved or disappeared. It uses the saved ownership, without
loading project configs or requiring terminal dependencies. A batch error or
interruption reports the refreshed state of each selected container when available;
some containers may already have stopped. No rollback is attempted.

### Colored output

Workspace and terminal-task names have consistent colors across invocations.
Starts and healthy running states are green, stops and failures red, and warnings
or pending health states yellow. Status words remain visible so color is optional.
Terminal prompts highlight the task title and command while keeping `(y/N)` consent.

Colors are automatic only when the output stream is a terminal. Pipes, captured
output, and logs stay plain. Set `NO_COLOR=1` to disable colors; `TERM=dumb` also
disables them. Standard output and standard error are checked independently.

### dwork.yml

A workspace can define its own Compose toggle, service selection, and terminal
commands in `dwork.yml`. For example, start an existing database container and
open `make run` in a new terminal only after its health check passes.
See the [schema, examples, and defaults](../configuration/README.md).

### Inspect and diagnose

```sh
dwork status
dwork doctor
dwork status -f compose.dev.yaml -p my-project
```

Both commands are read-only: they never stop/start containers, wait for health,
prompt, or launch terminal tasks. They use the same workspace discovery and
Compose options as switching.

`status` shows the Docker context, selected workspaces, container states and
health, unmanaged target services, and missing managed services. Host command
sessions are not tracked. When `DOCKER_HOST` overrides the context endpoint,
dwork reports the override without printing its potentially sensitive value.

`doctor` checks configuration and required Compose flags, Docker access, and each
configured command's shell and terminal dependencies. It reports fixes and exits
with status 1 on failed checks (0 when checks pass). Missing containers and health
states are displayed; required health services must exist and have health checks.
Passing doctor is not a guarantee that stopped services will become healthy.
If configuration cannot load, fix it first and rerun doctor. For host-only
workspaces Docker checks are skipped. Terminal checks do not open a GUI.

Every normal switch now prints its full plan, affected projects, and the
`DWORK_KEEP_PROJECTS` exclusions before executing. New directories require
registration consent; already-registered directories do not ask again. Child-group
switches and individual terminal tasks keep their existing confirmations.

If execution fails or is interrupted, dwork reports confirmed completed actions,
the failed step and actions not confirmed complete, and refreshes the running
Compose container inventory when possible. It suggests inspection, retry-preview,
and recovery commands; it never rolls back automatically. An operation that
failed or was interrupted may still have changed state. Recovery commands are
suggestions only, and should use the same Docker target and Compose options.
Exit status remains 1 for failures and 130 for interruption.

### Compose options

Pass Compose global options after `dwork` (and after `--dry-run`, if used):

```sh
dwork -f compose.yaml -f compose.dev.yaml
dwork --dry-run -p my-project -f compose.yaml
dwork --project-directory ./backend
```

Use the same project name and Compose files you used when creating the containers.
Compose first searches the current directory and its parents. When that finds no
configuration, `dwork` can discover immediate subdirectories as described below.

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

### Run from a repository root

If there is no default dwork/Compose config in the current directory or its parents,
`dwork` checks each **immediate subdirectory** for `dwork.yml` or a standard Compose filename:
`compose.yaml`, `compose.yml`, `docker-compose.yaml`, or `docker-compose.yml`.

For example, from a repository containing `backend/compose.yaml` and
`frontend/compose.yaml`, it lists both projects and the planned container changes,
then asks:

```text
Switch all listed projects together? (y/N)
```

Enter `y` or `Y` to switch. Enter, `n`, any other answer, or end-of-input cancels
without changing containers. Both projects are selected as a group; they do not
stop each other. Missing containers still produce warnings and are never created.

Discovery is only one directory level deep: `backend/nested/compose.yaml` is not
included. Symlinked directories and `.git` are skipped. Compose handles the config
and override files within each matching directory.

`dwork --dry-run` lists the same projects and planned changes without prompting
or changing containers. You can preview from a parent directory first.

Explicit Compose options or `COMPOSE_FILE` / `COMPOSE_ENV_FILES` keep normal Compose
selection in control, without child discovery on failure. Existing invalid configs
and dotenv files also block fallback, so configuration errors do not silently
select other projects. Use `-f backend/compose.yaml` to select a child explicitly
in that situation.

All selected configs and the container inventory are read before any changes.
A failed child config or duplicate project name aborts the whole switch.
The parent directory is remembered as one named workspace with all discovered
children. On its first activation, both the group-switch prompt and registration
prompt must be accepted. `dwork register NAME` can remember the group without
switching or prompting. Later `dwork switch NAME` still confirms the group switch.

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

Unregistered infrastructure already stays running. This exclusion also protects
projects that belong to registered workspaces. Service selections recorded for
other workspaces are respected: dwork stops only their managed services.

### Missing containers

A missing service produces a warning. `dwork` still switches existing containers;
it does not create the missing service. Optional profile services can also
produce warnings.

Create missing containers manually using your project's documented setup
commands and environment, then use `dwork` for subsequent switches.

### Limits and behavior

- Uses the Docker daemon/context selected by your Docker CLI. Check that context
  before switching; only other registered workspaces on that target are in scope.
- Matches containers by the standard `com.docker.compose.project` label. Separate
  registered directories cannot claim the same Compose project on the same target.
  Use distinct Compose project names for repositories and Git worktrees. An
  unregistered repository using the same name still shares that Docker project;
  directory registration cannot distinguish containers within a shared project name.
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

## Development checks

See [development and tests](../development/README.md).

## Docker references

- [Compose configuration](https://docs.docker.com/reference/cli/docker/compose/config/)
- [Compose project names](https://docs.docker.com/compose/how-tos/project-name/)
- [Start existing containers](https://docs.docker.com/reference/cli/docker/container/start/)
