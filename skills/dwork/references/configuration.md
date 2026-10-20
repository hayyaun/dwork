# dwork.yml configuration reference

This reference ships with the dwork skill for use in the user's project.
It describes configuration version 1. Full upstream documentation:
https://github.com/hayyaun/dwork/blob/main/docs/configuration/README.md

## File and field rules

Use the exact filename `dwork.yml`. The nearest file in the current directory or
its parents wins; files are not merged. `--project-directory` or an explicit
Compose `-f`/`--file` changes the search origin. Unknown fields, duplicate keys,
and unsupported versions are errors. Use YAML booleans (`true`, `false`), not
quoted strings, and quote argument strings such as `"3000"` or `"yes"` that YAML
might otherwise interpret as numbers or booleans.

Only these top-level fields are supported:

- `version`: required integer `1`.
- `compose`: optional mapping; Compose is enabled by default.
- `terminals`: optional list of terminal tasks, default `[]`.

## Compose

- `enabled`: boolean, default `true`. Set `false` for a host-only workspace;
  omit `files`, `services`, Compose CLI options, and health prerequisites then.
- `files`: optional nonempty list of Compose file paths relative to `dwork.yml`.
  Omit for normal Compose discovery. Explicit CLI `-f`/`--file` or `COMPOSE_FILE`
  takes precedence over this list.
- `services`: optional nonempty list of service names in the Compose model.
  Omit to manage all existing target-project containers. When specified, other
  services in the target project are untouched.

dwork starts existing containers; it does not create them or apply new Compose
settings to them. Initial container creation, migrations, and rebuilds are
separate setup steps. Only other registered workspaces on the same Docker target
may be stopped, respecting their registered service selections and the comma-separated
`DWORK_KEEP_PROJECTS` environment variable. Unregistered projects stay running.
The first normal run asks before registering a new directory. `dwork register NAME`
remembers without activating; `dwork list`, `dwork switch NAME`, and `dwork forget NAME`
list, activate, and forget remembered directories. Changed Compose identity,
selection options, or managed services requires explicit re-registration.
`dwork down` stops all registered container workloads on the current Docker target,
respecting service selections and `DWORK_KEEP_PROJECTS`, without removing containers
or volumes. `dwork down --dry-run` previews without stopping anything.
With Compose disabled for all selected workspaces, no Docker commands run.

## Terminal tasks

Each item in `terminals` supports:

- `command`: required nonempty list of nonempty strings: executable followed by
  arguments, e.g. `[npm, run, dev]`. It is not a shell command string.
- `title`: optional nonempty string, default `dwork: <project>`.
- `cwd`: optional existing directory relative to `dwork.yml`, default `.`.
- `window`: `new` (default) or `current` (request an existing-window tab).
  On Windows Terminal, `current` selects the most recently used window, not
  necessarily the calling shell's window. The field is `window`, not `terminal`.
- `launcher`: `auto` (default), `windows-terminal`, `gnome-terminal`, `konsole`,
  `xfce4-terminal`, or `xterm`. xterm supports new windows only. Explicit task
  settings override `DWORK_TERMINAL`.
- `confirm`: boolean, default `true`. Only explicit `false` skips that task's
  confirmation prompt.
- `wait_for`: optional mapping described below.

Commands use the user's Bash/Zsh login and interactive startup environment and
run in the foreground in a new terminal. Use an existing script for pipelines or
compound commands. Terminal titles, resolved working directories, and command
arguments cannot contain NUL, newlines, or semicolons. Repeated dwork invocations
launch tasks again: dwork does not detect already-running host processes,
supervise commands, or close old terminals.

Terminal launching supports Linux graphical desktops with the listed native
emulators, or WSL2 with Windows Terminal and Windows PowerShell. It is not a
native Windows/macOS terminal launcher. A dry run does not require a GUI.

## Health prerequisites

`wait_for` supports:

- `healthy`: nonempty list of services in this workspace's Compose model. Each
  must have existing containers and Docker health checks. If `compose.services`
  is present, every prerequisite must also be listed there.
- `timeout`: number of seconds greater than zero and at most 3600; default 180.

All health gates pass before any terminal opens. Missing containers or missing
health checks block launch. Container switching happens before terminal prompts;
declining a terminal does not undo switching. Completed changes are not rolled
back after a later failure.

## Example: host-only frontend

Use only if the project actually defines `npm run dev` in this directory:

```yaml
version: 1
compose:
  enabled: false
terminals:
  - title: Frontend
    command: [npm, run, dev]
```

## Example: container database and host backend

Assumes Compose defines a `postgres` service with a health check, its container
already exists, and `backend/` contains a `make run` target:

```yaml
version: 1
compose:
  services: [postgres]
terminals:
  - title: Backend
    command: [make, run]
    cwd: backend
    wait_for:
      healthy: [postgres]
      timeout: 180
```

For Compose-only configuration, omit `terminals`; for automatic Compose-only
behavior, a `dwork.yml` is not required at all.

## Preview

Run `dwork --dry-run` in the workspace directory. Compose-enabled previews read
the Compose model and inspect Docker containers, but never stop/start containers,
wait for health, or open terminals. Read warnings even when the command succeeds:
missing containers may still block a real launch. YAML loading requires PyYAML
in dwork's Python environment (included by the default `make install`).
