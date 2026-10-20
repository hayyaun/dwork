# dwork.yml

[Usage](../usage/README.md) · [Examples](../../examples/README.md) · [Project home](../../README.md)

Place `dwork.yml` in the repository or workspace directory. It is dwork's own
configuration, separate from Docker Compose.

## Example: database plus a host backend

```yaml
version: 1

compose:
  enabled: true
  services:
    - postgres

terminals:
  - title: Backend
    command: [make, run]
    cwd: .
    window: new
    wait_for:
      healthy: [postgres]
      timeout: 180
```

Invoking `dwork` reads the existing Compose model, switches existing containers,
waits for every existing container of the selected `postgres` service to be
running and healthy, then asks before opening a terminal window running `make run`.
It never creates missing containers.

Preview first:

```sh
dwork --dry-run
```

The preview lists container changes, health requirements, and terminal tasks.
It does not wait, prompt, or open terminals.

## Requirements

Without a config, Compose-only usage needs the existing Python/Docker setup.
Reading `dwork.yml` additionally requires PyYAML for the `python3` interpreter
used by dwork. On Ubuntu/WSL:

```sh
sudo apt install python3-yaml
```

Terminal tasks support native Linux desktops with GNOME Terminal, Konsole, Xfce
Terminal, or xterm, and WSL2 with Windows Terminal and Windows PowerShell.
Bash or Zsh must be configured as `SHELL`. Native emulators need a graphical
session; xterm supports new windows only. See [terminal launchers](../terminals/README.md).
Compose-only mode remains usable on other platforms, and dry runs do not open GUIs.

## Configuration selection

- The nearest `dwork.yml` in the current directory or its parents takes precedence
  over automatic Compose selection.
- `--project-directory`, or the directory of an explicit `-f`/`--file`, determines
  where to begin looking for `dwork.yml`.
- With no `dwork.yml`, the original Compose behavior remains: current/parent
  config first, then immediate-child discovery when no default config is available.
- Immediate-child discovery recognizes either `dwork.yml` or a standard Compose
  file. It still asks `(y/N)` before changing anything. Selected children are
  switched together and never stop one another.
- A selected but invalid `dwork.yml` fails with an error. It does not fall back to
  Compose or run part of the configuration.

`dwork.yml` is not merged with another dwork file. Unknown fields, duplicate keys,
and unsupported versions are errors.

## version

`version: 1` is required.

## locked

```yaml
version: 1
locked: true
```

`locked` is a boolean, defaulting to `false`. A locked workspace remains registered
and visible in `dwork list`, but its containers are excluded from both workspace
switch stops and `dwork down`. It can still be activated and its existing containers
started. Strings such as `"true"`, numbers, and null are rejected.

Changes to this setting take effect without re-registration. dwork reads the current
lock policy when planning switches, shutdowns, and listings. Registering or executing
a switch/shutdown records the latest policy; if the YAML file or directory later
disappears, the last recorded lock is retained. A readable, valid config with
`locked: false` (or with the option omitted) unlocks the workspace.

If a registered lock policy cannot be read or is invalid, dwork reports a warning
and protects that workspace until the config is fixed. Listing and previews do not
write lock snapshots. For a group of child workspaces, set `locked: true` in each
child that should stay running; unlocked children remain eligible to stop.

This option controls dwork's container operations; it does not supervise host
terminal processes or prevent someone from stopping containers directly with Docker.

## compose

```yaml
compose:
  enabled: true
  files: [compose.yaml, compose.dev.yaml]
  services: [postgres, redis]
```

- `enabled` is a boolean, defaulting to `true`. When false, dwork does not read
  Compose or inspect, stop, or start Docker containers for that workspace.
- `files` is an optional, nonempty list of Compose file paths relative to
  `dwork.yml`. Without it, Compose uses its normal discovery and overrides.
  Explicit `-f`/`--file` flags or `COMPOSE_FILE` take precedence over this list.
- `services` is an optional, nonempty list of Compose service names to manage.
  Without it, dwork preserves its existing behavior of managing all existing
  target-project containers. With it, other target-project services remain
  untouched, and missing-container warnings cover only selected services.
- Only other registered workspaces on the same Docker target may be stopped,
  respecting their registered service selections, `locked`, and `DWORK_KEEP_PROJECTS`.
  Unregistered projects stay running. See [remembered workspaces](../workspaces/README.md).
  When all selected workspaces disable Compose, no Docker commands are run.

When `enabled: false`, omit `files`, `services`, Compose CLI options, and health
prerequisites.

Reading Compose does not recreate containers or update their stored environment.
Environment values for existing containers do not need to be supplied again just
to start them.
After changing project identity, Compose selection, or managed services, explicitly
run `dwork register NAME` with the intended options before switching again.

## terminals

`terminals` is a list, defaulting to an empty list. Each item supports:

- `command`: a required, nonempty list of executable and argument strings, such as
  `[make, run]`. Commands use the user's Bash/Zsh login and interactive startup
  environment. Arguments are quoted; this is not an arbitrary shell snippet.
- `title`: an optional nonempty title. Defaults to `dwork: <project>`.
- `cwd`: an optional working directory relative to `dwork.yml`, defaulting to `.`.
  It must exist.
- `window`: `new` opens a new window; `current` requests an existing-window tab
  using the selected emulator's rules. Defaults to `new`. xterm supports `new` only.
  On Windows Terminal, `current` means the most recently used window, not necessarily
  the one containing your shell. See [troubleshooting current](../terminals/README.md#troubleshoot-current-on-windows-terminal--wsl).
- `launcher`: defaults to `auto`. Supported values are `auto`, `windows-terminal`,
  `gnome-terminal`, `konsole`, `xfce4-terminal`, and `xterm`. An explicit task
  setting overrides `DWORK_TERMINAL`; otherwise platform/desktop selection applies.
- `confirm`: a boolean, defaulting to `true`. Ask `(y/N)` before opening this
  session. Set `confirm: false` explicitly in this task to skip that prompt.
  Strings such as `"false"` and numbers are rejected.
- `wait_for`: optional health prerequisites described below.

Commands run in the foreground of their new terminal. dwork checks dependencies
and reports immediate launcher failures; it does not supervise later GUI startup,
the command, or its eventual exit status. Every invocation launches the configured tasks again. It does not detect
already-running host processes or close terminals from previous projects.

For pipelines or compound commands, put the command in a script and invoke that
script. Terminal values cannot contain newlines, NUL, or semicolons (Windows
Terminal reserves semicolons as command separators).

## Session confirmation

Every terminal session asks for confirmation by default, on both Linux and WSL.
The prompt shows the title, command, and working directory. Only `y` or `Y` opens
that session. Enter, `n`, any other response, or end-of-input skips it and continues
to the next configured terminal.

Set `confirm: false` on a specific task to open it without asking:

```yaml
version: 1
compose:
  enabled: false
terminals:
  - title: Frontend
    command: [npm, run, dev]
    confirm: false
```

The option applies only to that task. There is no environment-wide or implicit
bypass. An omitted `confirm` or explicit `confirm: true` asks every time.

Container switching and all health gates happen before the session prompts.
Declining a terminal does not roll back container changes. The parent-directory
`(y/N)` prompt approves workspace switching, not individual terminal launches;
sessions still ask afterward unless their own config opts out.

`--dry-run` does not prompt or launch. It shows `[confirmation required]` or
`[confirm: false]` beside each planned terminal. Ctrl+C cancels remaining work;
terminals already opened are not closed.

## wait_for

```yaml
wait_for:
  healthy: [postgres]
  timeout: 180
```

`healthy` is a nonempty list of service names from this workspace's Compose model.
When `compose.services` is set, health prerequisites must also appear there.
`timeout` defaults to 180 seconds and must be greater than zero and at most 3600.

The services must already have containers and Docker health checks. A missing
required container aborts before other projects are stopped; create it manually.
A paused, exited, dead, unhealthy, or missing-health-check container blocks terminal
launch. Containers still starting are polled until healthy or the timeout expires.

All configured health gates pass before any terminal opens. Failed stops, starts,
health checks, or launcher operations stop further work; completed container changes
are not rolled back.

## Host-only workspace

Disable Compose to run terminal tasks without Docker:

```yaml
version: 1
compose:
  enabled: false
terminals:
  - title: Frontend
    command: [npm, run, dev]
```

## Implementation references

- [PyYAML loaders](https://pyyaml.org/wiki/PyYAMLDocumentation)
- [Docker container health status](https://docs.docker.com/engine/containers/run/)
- [Windows Terminal CLI](https://learn.microsoft.com/windows/terminal/command-line-arguments)
- [PowerShell Start-Process argument quoting](https://learn.microsoft.com/powershell/module/microsoft.powershell.management/start-process)
