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

The preview lists container changes, health requirements, terminal tasks, and
browser URLs. It does not wait, prompt, or open applications.

## Requirements

Without a config, Compose-only usage needs the existing Python/Docker setup.
Reading `dwork.yml` additionally requires PyYAML for the `python3` interpreter
used by dwork. On Ubuntu/WSL:

```sh
sudo apt install python3-yaml
```

Terminal tasks support native Linux desktops with GNOME Terminal, Konsole, Xfce
Terminal, or xterm, macOS with Apple Terminal, and WSL2 with Windows Terminal
and Windows PowerShell. macOS terminal/background tasks require Python 3.13 or newer.
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
switch stops and `dwork down`. Its tracked host commands also stay running on `down`.
It can still be activated and its existing containers
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

This option protects dwork-managed containers and tracked host commands. It does
not prevent someone from stopping them directly with Docker or operating-system tools.

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
  environment for visible terminals, and a noninteractive login shell for `window: none`.
  Arguments are quoted; this is not an arbitrary shell snippet.
- `title`: an optional nonempty title. Defaults to `dwork: <project>`.
- `cwd`: an optional working directory relative to `dwork.yml`, defaulting to `.`.
  It must exist.
- `window`: `new` opens a new window; `current` requests an existing-window tab
  using the selected emulator's rules; `none` runs detached in the background without
  a GUI, with input/output discarded. Defaults to `new`. xterm supports `new` only
  for visible terminals; Apple Terminal also supports `new` only. `none` does
  not use a terminal launcher.
  On Windows Terminal, `current` means the most recently used window, not necessarily
  the one containing your shell. See [troubleshooting current](../terminals/README.md#troubleshoot-current-on-windows-terminal--wsl).
- `launcher`: defaults to `auto`. Supported values are `auto`, `apple-terminal`, `windows-terminal`,
  `gnome-terminal`, `konsole`, `xfce4-terminal`, and `xterm`. An explicit task
  setting overrides `DWORK_TERMINAL`; otherwise platform/desktop selection applies.
- `confirm`: a boolean, defaulting to `true`. Ask `(y/N)` before opening this
  session. Set `confirm: false` explicitly in this task to skip that prompt.
  Strings such as `"false"` and numbers are rejected.
- `wait_for`: optional health prerequisites described below.

Visible commands run in the foreground of their new terminal. dwork checks dependencies
and reports immediate launcher failures. New commands are supervised and stopped
by `dwork down`, while their terminal windows remain open at a shell prompt.
It does not monitor later GUI startup or deduplicate tasks: every invocation
launches the configured tasks again. See [tracked commands](../terminals/README.md#tracked-commands-and-shutdown).

For detached execution, use `window: none`; `confirm` and health gates still apply.
`launcher` is not used in that mode. See [background task behavior](../terminals/README.md#detached-background-tasks).

For pipelines or compound commands, put the command in a script and invoke that
script. Terminal values cannot contain newlines, NUL, or semicolons (Windows
Terminal reserves semicolons as command separators).

## Session confirmation

Every terminal session asks for confirmation by default on Linux, macOS, and WSL.
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

## browsers

Open application pages after the configured terminal tasks have launched:

```yaml
version: 1
compose:
  enabled: false
terminals:
  - title: Frontend
    command: [npm, run, dev]
browsers:
  - url: http://localhost:3000
    wait_for:
      timeout: 60
```

`browsers` defaults to an empty list. Each entry supports:

- `url`: a required absolute HTTP or HTTPS URL. Credentials, whitespace,
  backslashes, and control characters are rejected. Percent-encode spaces and
  non-ASCII characters in paths and queries.
- `browser`: defaults to `default` (the OS default). On Linux, use an executable
  name on `PATH` or an absolute executable path, such as `firefox`. On macOS, use
  an application name or `.app` path, such as `Firefox`, `Google Chrome`, or
  `/Applications/Firefox.app`. On WSL, use a Windows `.exe` name or absolute
  Windows path, such as `firefox.exe` or
  `'C:\Program Files\Mozilla Firefox\firefox.exe'`. The browser must already
  be installed. This is one program/application, without command-line flags.
- `confirm`: a boolean, defaulting to `true`. Ask before waiting or opening.
  Only `y`/`Y` approves; declining or EOF skips that URL. Explicit `false`
  skips this entry's confirmation.
- `wait_for`: defaults to polling `url` with a 60-second retry deadline.
  Set `url` inside this mapping to probe a separate health endpoint, and
  `timeout` to a number greater than zero and at most 3600 seconds. Use
  `wait_for: false` to open immediately without making an HTTP request.

To choose a browser and skip both readiness and confirmation on Linux:

```yaml
browsers:
  - url: http://localhost:3000
    browser: firefox
    wait_for: false
    confirm: false
```

On macOS use `browser: Firefox`; on WSL use a Windows executable/path as above.
Omit `browser` to keep the default. `wait_for: false` and `confirm: false` are
independent. A terminal's `confirm: false` skips its session prompt as well;
workspace registration and `up`/group confirmations still apply.

Readiness uses a direct HTTP GET and accepts statuses 200–399. It does not
follow redirects, download the response body, or use HTTP proxy environment
variables. HTTPS certificates are verified. Retries use a monotonic deadline
and short socket timeouts; system DNS resolution can exceed that deadline.
Authentication failures and server errors keep waiting until timeout.

All terminal tasks are dispatched first, then browser entries run in order.
The browser wait does not start or restart a development server: use an existing
server or a terminal task you explicitly configure. If a terminal is declined,
the browser still waits for its URL, which may already be served elsewhere.
On timeout or opener failure, remaining browser entries are not opened;
already-started tasks and containers remain running. Ctrl+C stops the remaining
waits. Repeated activations open the configured URLs again.

Default URLs use `open` on macOS, `xdg-open` in a Linux desktop session, and
Windows PowerShell `Start-Process` on WSL. A custom selection uses `open -a` on
macOS, the selected executable on Linux, or a Windows executable through
PowerShell on WSL. WSL never falls
back to a Linux browser when Windows interop is unavailable. The browser decides
whether to reuse a tab or window; dwork does not force a new window or close
browser windows during `down`. See [browser launching](../browsers/README.md).

`--dry-run`, `register`, `status`, and `doctor` never poll readiness or open a
browser. `doctor` checks Linux executable availability and the platform opener
or Windows interop requirement. macOS application lookup and Windows executable
resolution are reported during dispatch; doctor does not launch them to test.

## Implementation references

- [PyYAML loaders](https://pyyaml.org/wiki/PyYAMLDocumentation)
- [Docker container health status](https://docs.docker.com/engine/containers/run/)
- [Windows Terminal CLI](https://learn.microsoft.com/windows/terminal/command-line-arguments)
- [PowerShell Start-Process argument quoting](https://learn.microsoft.com/powershell/module/microsoft.powershell.management/start-process)
