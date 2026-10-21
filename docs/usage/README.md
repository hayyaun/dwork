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
   For a remembered single workspace, asks to apply the plan unless the selected
   `dwork.yml` sets root-level `confirm: false`.
4. Uses the same shutdown path as `down`, excluding the selected registration and
   its group members: stops outgoing tracked commands first, then running,
   restarting, or paused managed containers on the current Docker target in one
   Docker stop call. Locks and `DWORK_KEEP_PROJECTS` protect both kinds of workload.
5. Starts selected-project containers whose state is `created` or `exited`.

It uses `docker stop` and `docker start`. It never calls `docker compose up`,
creates containers, pulls images, builds images, recreates containers, or removes
containers, networks, or volumes. Current-project containers already running are
left running. Containers without a Compose project label are left alone.
Unregistered Compose projects are also left running.

### Version, initialization, and validation

```sh
dwork --version
dwork init --dry-run
dwork init
dwork validate
```

`--version` prints `dwork VERSION` without reading project configuration, the
registry, or Docker. It reports the shared package version, including source and
Make installations; it is not a Git commit identifier.

`init` creates `dwork.yml` in the current directory. Its contents are deterministic:
`version: 1`, Compose enabled if a standard Compose filename exists locally,
and empty `terminals`/`browsers` lists. It does not parse Compose files, infer
commands, inspect parents or environment selections, or invoke Docker. Edit
custom Compose files and tasks afterward. Existing files, directories, and even
broken symlinks are never overwritten. `init --dry-run` previews the same YAML
without writing. Neither form registers or activates the workspace.

`validate` reuses normal config discovery and validation, including ancestor
configs and discovered children. It checks supported fields, types, task working
directories, and Compose service references. Compose-only workspaces are accepted.
It accepts the same Compose selection options as `doctor`, for example
`dwork validate -f compose.dev.yaml`. Compose-enabled validation runs only
`docker compose config`; the CLI is required, the daemon is not. Host-only
validation needs no Docker. It never reads/writes the registry, inspects containers,
checks health or desktop dependencies, prompts, or launches commands/browsers.
Success returns 0 and validation errors return 1. Use `doctor` for environment
diagnostics and `--dry-run` for the switch plan; `validate --dry-run` is unnecessary
and rejected. These commands were added after release 0.3.0.

### Remember and switch workspaces

```sh
dwork register my-app     # Save this workspace without starting or stopping anything
dwork scan                # Recursively register configured workspaces, then offer Compose selection
dwork list               # NAME / STATUS / LOCKED / PATH table (alias: ls)
dwork switch my-app      # Activate the saved workspace from anywhere
dwork switch my-app --dry-run
dwork rename my-app api   # Rename to an available workspace name
dwork down                # Stop all registered workloads on this Docker target
dwork forget my-app      # Remove only the registration
```

The name is optional for `register`; it defaults to the Compose project name,
or the directory name for a host-only workspace or a group of child workspaces.
`switch` uses saved Compose options and does not change your calling shell's directory.
See [workspace registration](../workspaces/README.md) for naming, Docker targets,
configuration changes, shared infrastructure, and moved directories.

`dwork scan` includes the current directory and its descendants. All valid
`dwork.yml` workspaces are added first. It then asks whether to review remaining
Compose-only directories in a checkbox picker: use arrow keys to move, Space to
toggle, and Enter to register the selected directories. Nothing is checked by
default; Esc cancels selection. The command never starts/stops containers or opens
development terminals. Use `dwork scan --dry-run` to preview without writing or
prompting. See [recursive scanning](../workspaces/README.md#scan-a-directory-tree).

### Stop all registered workloads

Plain `dwork` in a registered workspace and `dwork up` show the current workspace
plan and ask for confirmation before applying it. Root-level `confirm: false`
in `dwork.yml` skips that activation prompt only. `dwork down` shows the containers and tracked commands it will stop
and asks for confirmation when there is work to stop. Only `y` or `Y` proceeds; Enter, `n`, and
end-of-input cancel. `--dry-run` previews without prompting. Existing registration,
group, and terminal-task confirmations still apply.

```sh
dwork down --dry-run
dwork down
```

Run from any directory. `down` stops running, restarting, and paused containers
managed by all registered workspaces on the current Docker target in one Docker
stop call. Registered service selections and `DWORK_KEEP_PROJECTS` still apply;
workspaces with `locked: true` and unregistered projects stay running. It does not remove containers, networks,
volumes, or registrations. It also stops commands launched through this version of
dwork, leaving visible terminal windows at a shell prompt. Locked tasks and
`DWORK_KEEP_PROJECTS` exclusions remain running. The Docker daemon/WSL VM remain
running. Docker's normal stop signal and timeout behavior apply to containers.
See [tracked command shutdown](../terminals/README.md#tracked-commands-and-shutdown)
for process-group shutdown and tracking limits.

Both switches and `down` stop eligible registered workloads whose directories have
moved or disappeared, using saved ownership and the last known lock policy.
`down` does so without loading Compose models or requiring terminal dependencies;
it reads YAML lock policies. A batch error or
interruption reports the refreshed state of each selected container when available;
some containers may already have stopped. No rollback is attempted.

The shared shutdown behavior was added after release 0.3.0. Switching to a host-only
workspace still shuts down outgoing Compose containers on the current Docker target
when Compose registrations exist. With an entirely host-only registry, switching
and `down` need no Docker connection. Local tracked commands are considered across
registered workspaces regardless of their saved Docker target. Selected-workspace
tasks stay running; each activation still launches approved configured tasks again.

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
health, unmanaged target services, and missing managed services. Preview tracked
host commands with `dwork down --dry-run`. When `DOCKER_HOST` overrides the context endpoint,
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
registration consent. Already-registered single workspaces ask to apply the plan
on plain `dwork` unless root-level `confirm: false` is set. Explicit
`dwork switch NAME`, child-group switches, and individual task/browser entries
keep their existing confirmation behavior.

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
  before switching; only containers owned on that target are in scope. Tracked
  commands are local and stop across eligible registered workspaces regardless of
  their saved Docker targets.
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
