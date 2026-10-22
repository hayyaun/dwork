# dwork.yml configuration reference

This reference ships with the dwork skill for use in the user's project.
It describes configuration version 1. Full upstream documentation:
https://github.com/hayyaun/dwork/blob/main/docs/configuration/README.md

## File and field rules

Shell completion is separate from YAML editor completion. Updated native package
builds install Bash/Zsh completion files in the platform's discovery directories.
They are automatic when `bash-completion` or Zsh's `compinit` already searches
those directories; Homebrew's `brew shellenv` should run before `compinit`.
The current `dwork.sh` enables completion automatically when sourced interactively;
Zsh requires it after Oh My Zsh/`compinit`. If sourced earlier, source it again
after initialization. It does not run `compinit` or generate completion in
noninteractive shells; missing Python/runtime dependencies quietly skip optional
loading. Python installations, older source/release packages, and custom prefixes
may still need `source <(dwork completion zsh)` after `compinit`, or the Bash
equivalent. Preserve existing shell choices; changing a shell startup file
requires the user's authorization.

Use the exact filename `dwork.yml`. The nearest file in the current directory or
its parents wins; files are not merged. `--project-directory` or an explicit
Compose `-f`/`--file` changes the search origin. Unknown fields, duplicate keys,
and unsupported versions are errors. Use YAML booleans (`true`, `false`), not
quoted strings, and quote argument strings such as `"3000"` or `"yes"` that YAML
might otherwise interpret as numbers or booleans.

For editor completion, hover help, and structural diagnostics, preserve or add:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/hayyaun/dwork/main/schemas/dwork.schema.json
version: 1
```

`dwork init` and upstream examples include this comment. A schema-capable YAML
extension fetches it; dwork ignores the comment and does not fetch schemas.
The URL tracks `main` and requires publication there, so verify the installed
runtime supports suggested fields. A release tag containing the schema can
replace `main`. For offline/unpublished work, replace the URL with a local schema
path relative to `dwork.yml`, or use the editor's `yaml.schemas` association
without a conflicting modeline. SchemaStore discovery is not registered yet.
Static completion does not discover Compose service names or check directories;
keep using `dwork validate` and environment diagnostics.

Only these top-level fields are supported:

- `version`: required integer `1`.
- `confirm`: optional root-level boolean, default `true`; require plan confirmation
  for plain `dwork` in a registered single workspace and `dwork up`. Set `false`
  to skip that activation prompt only.
  Registration, discovered-group, terminal/browser, and `down` confirmations are
  separate. Child opt-outs do not approve a parent group. Explicit
  `dwork switch NAME` keeps its existing confirmation behavior. This field was
  added after 0.3.0; check installed-runtime support before generating it.
- `locked`: optional boolean, default `false`; keep this workspace's containers
  and tracked host commands running during switches and `dwork down`, while still
  listing and allowing activation. Both operations apply the same protection rules.
- `compose`: optional mapping; Compose is enabled by default.
- `terminals`: optional list of terminal tasks, default `[]`.
- `browsers`: optional list of browser URLs, default `[]`.

`dwork.yml` may describe a personal workspace rather than shared project setup.
Consider `/dwork.yml` in the root `.gitignore` (or the actual nested path) with
the user's approval. Preserve intentional team configs and examples; ignore
rules do not untrack a file already in Git. `.git/info/exclude` is an option
when the ignore preference should apply only to one clone.

## Compose

- `enabled`: boolean, default `true`. Set `false` for a host-only workspace;
  omit `files`, `services`, Compose CLI options, and health prerequisites then.
- `files`: optional nonempty list of Compose file paths relative to `dwork.yml`.
  Omit for normal Compose discovery. Explicit CLI `-f`/`--file` or `COMPOSE_FILE`
  takes precedence over this list.
  Explicit Compose file/environment selections retain the invocation directory,
  including beneath an ancestor `dwork.yml`; saved switches restore that context.
  YAML-owned `compose.files` and terminal `cwd` remain relative to `dwork.yml`.
- `services`: optional nonempty list of service names in the Compose model.
  Omit to manage all existing target-project containers. When specified, other
  services in the target project are untouched.

dwork starts existing containers; it does not create them or apply new Compose
settings to them. Initial container creation, migrations, and rebuilds are
separate setup steps. Only other registered workspaces on the same Docker target
may be stopped, respecting their registered service selections and the comma-separated
`DWORK_KEEP_PROJECTS` environment variable. Unregistered projects stay running.
The first normal run asks before registering a new directory, independently of
root `confirm`. Later plain `dwork` asks to apply the plan
unless root `confirm: false` is set; only `y`/`Y` accepts, and EOF cancels.
`--dry-run` previews the policy without asking. `dwork register NAME`
remembers without activating; `dwork list`, `dwork switch NAME`, and `dwork forget NAME`
list, activate, and forget remembered directories. `list`/`ls` use an aligned
`NAME`, `STATUS`, `LOCKED`, `PATH` table; the lock column contains `yes` for one
locked member, protected project names for groups, or `-`. Local CLI locks show
`temporary`, plus any YAML-protected project names when both apply. Use `list --names`
for sorted names only, without a table or Docker status queries. Changed Compose identity,
selection options, or managed services requires explicit re-registration.
`dwork down` stops registered container workloads on the current Docker target and
locally tracked host commands, respecting service selections and `DWORK_KEEP_PROJECTS`,
without removing containers or volumes. It shows a plan and requires confirmation.
Visible terminal windows remain open at a shell prompt; browser windows also
remain open. `dwork down --dry-run`
previews without stopping anything or prompting. Commands launched by older versions
are not tracked. Tracking does not follow commands that daemonize into other groups
or sessions. Switches share the shutdown planner and executor with `down`, excluding
the selected registration and all its group members. Outgoing commands stop before
the batch container stop and any destination startup. A shutdown failure aborts
activation. This switch behavior was added after 0.3.0; check installed-runtime support.
Tasks already running in the selected workspace stay running, and approved configured
tasks are still launched again. Missing outgoing directories retain their saved
ownership and last known lock policy for shutdown in both operations.
`locked: true` protects a workspace from both operations. Lock changes are read
without re-registration; a missing config retains the last recorded policy, and an
unreadable/invalid lock policy protects the workspace with a warning. To unlock,
use a readable valid config with `locked: false` or omit the field. Any separate
temporary CLI lock still applies.

`dwork lock NAME...` protects one or more registered workspaces without changing
YAML. `dwork unlock NAME...` removes only these local locks, preserving YAML
`locked: true` and `DWORK_KEEP_PROJECTS`. They protect containers and tracked
commands, including every registered member of a group. A temporary lock lasts
until explicitly released, survives shell restarts, renaming, and re-registration,
and is discarded by `forget`. It is stored in the local registry; users sharing
no registry do not share this policy. These commands require a runtime containing
this feature (added after 0.3.0); older versions do not enforce the registry flag.
They work from any directory without Docker or workspace-directory access.
`--dry-run` before or after the names previews without writing state. All names
are validated before any changes; an unknown name fails the whole request.

`dwork scan` recursively registers `dwork.yml` workspaces, then offers a Space/Enter
checkbox picker for unregistered Compose-only directories. It does not activate
anything. `dwork scan --dry-run` previews without writing or prompting.
Scanning stops below repository/project markers such as `.git`, `dwork.yml`,
Compose files, or project manifests. Start a scan inside a nested directory to
find workspaces below an existing repository boundary.
Switching to a host-only workspace still shuts down eligible outgoing Compose
containers on the current Docker target when Compose registrations exist. Docker
is unnecessary only when the selected workspace and entire registry are host-only.
Local tracked commands are considered across saved Docker targets; container
shutdown stays scoped to the current Docker target.

## Terminal tasks

Each item in `terminals` supports:

- `command`: required nonempty list of nonempty strings: executable followed by
  arguments, e.g. `[npm, run, dev]`. It is not a shell command string.
- `title`: optional nonempty string, default `dwork: <project>`.
- `cwd`: optional existing directory relative to `dwork.yml`, default `.`.
- `window`: `new` (default), `current` (request an existing-window tab), or `none`
  (detached background task with output discarded and no window).
  On Windows Terminal, `current` selects the most recently used window, not
  necessarily the calling shell's window. The field is `window`, not `terminal`.
- `launcher`: `auto` (default), `apple-terminal`, `windows-terminal`, `gnome-terminal`,
  `konsole`, `xfce4-terminal`, or `xterm`. Apple Terminal and xterm support new
  windows only. `window: none` does not use a launcher. Explicit task
  settings override `DWORK_TERMINAL`.
- `confirm`: boolean, default `true`. Only explicit `false` skips that task's
  confirmation prompt.
- `wait_for`: optional mapping described below.

Visible commands use the user's Bash/Zsh login and interactive startup environment
and run in the foreground in the selected terminal window or tab. Use an existing script for pipelines or
compound commands. Terminal titles, resolved working directories, and command
arguments cannot contain NUL, newlines, or semicolons. Repeated dwork invocations
launch tasks again without deduplication. Commands are supervised for outgoing
workspace shutdown and `down`, which respect workspace locks, terminate their
process groups, and preserve terminal windows. Detached commands use noninteractive
login shell startup.

Terminal launching supports Linux graphical desktops with the listed native
emulators, macOS with Apple Terminal, or WSL2 with Windows Terminal and Windows
PowerShell. `auto` chooses the matching platform/desktop launcher. Native Windows
execution is not supported; use WSL2. Commands require Bash or Zsh as `SHELL`.
Linux/WSL require Python 3.10+; tracked terminal/background commands on macOS
require Python 3.13+. Apple Terminal uses its scripting interface and may require
macOS Automation permission; tab creation is not supported. A dry run does not
require a GUI.

## Health prerequisites

`wait_for` supports:

- `healthy`: nonempty list of services in this workspace's Compose model. Each
  must have existing containers and Docker health checks. If `compose.services`
  is present, every prerequisite must also be listed there.
- `timeout`: number of seconds greater than zero and at most 3600; default 180.
  The deadline includes every Docker health inspection. A stalled inspection fails
  the gate and blocks further launches. Terminal/browser timeout validation also
  rejects extremely large integers as ordinary configuration errors.

All health gates pass before any terminal opens. Missing containers or missing
health checks block launch. Container switching happens before terminal prompts;
declining a terminal does not undo switching. Completed changes are not rolled
back after a later failure.

Current activation plans and results are typed internal data, with no additional
configuration or registry fields. Execution still stops outgoing commands before
containers, starts existing destination containers, passes every health gate, and
then handles the separate terminal/browser confirmations. Locks are rechecked after
plan-level consent. Declined entries are skipped, completed supervisor cleanup is
already finished, and failed/interrupted work remains unconfirmed. A successful
dispatch is not a readiness guarantee; only confirmed container stops justify
container recovery suggestions. Do not invent a JSON-output or resume command.

Initial task discovery reports unresolved owned, unprotected outgoing controllers
and blocks shutdown/activation before workloads change, including in previews.
Selected, locked, kept, forgotten, and ownership-changed tasks keep their exclusions.
Preserve controller records while diagnosing failures; never signal saved PIDs or
delete records to bypass the check. Only completed supervisor cleanup removes them.

## Browser URLs and HTTP readiness

Each item in `browsers` supports:

- `url`: required absolute HTTP or HTTPS URL, including its scheme. Credentials,
  backslashes, whitespace, control characters, and literal non-ASCII characters
  are rejected. Percent-encode spaces and non-ASCII path/query characters.
- `browser`: optional string, default `default` for the OS default browser. On
  Linux choose an executable name on PATH or an absolute executable path; on
  macOS choose an application name such as `Firefox`/`Google Chrome` or an `.app`
  path. On WSL choose a Windows `.exe` name or an absolute Windows path such as
  `'C:\Program Files\Mozilla Firefox\firefox.exe'`; Linux/WSL `/mnt/c` paths
  are not accepted. Supply one installed program, without extra flags.
- `confirm`: boolean, default `true`. Only explicit `false` skips that entry's
  confirmation. Decline or EOF skips its readiness check and browser opening.
- `wait_for`: optional mapping with `url` (defaults to the browser page URL) and
  `timeout` (defaults to 60 seconds, greater than zero and at most 3600).
  `wait_for: false` skips the HTTP probe and opens immediately after confirmation.

Skill authoring default: explicitly write `wait_for: false` in new browser
entries unless the user asks to enable HTTP readiness. The runtime's omitted-field
default is still a 60-second readiness wait, so do not omit the field when following
this skill preference. Re-enable with `wait_for: {timeout: 60}`, optionally adding
a separate `url`. Keep confirmation enabled unless the user also asks to skip it.
Preserve an existing explicitly requested readiness requirement when editing
unrelated fields.

All terminal tasks dispatch first, then browser entries run in configured order.
An existing server, a configured terminal/background task, or Compose can serve
the page; browser readiness itself does not start a server. Declining a terminal
does not skip browser entries: an existing server might already serve the URL.

Probes use a direct GET and accept HTTP 200–399 without following redirects or
reading the body. HTTP proxy environment variables are not used. TLS certificates
are verified; authentication failures and server errors do not count as ready.
Use a safe GET endpoint. Short socket timeouts and a monotonic retry deadline
bound retries; OS DNS resolution can exceed the deadline.

macOS uses its default browser through `open`, or selects an app with `open -a`.
Graphical Linux uses `xdg-open` (`xdg-utils`) by default or the chosen executable.
WSL always uses the Windows default or selected Windows browser through
`powershell.exe` and does not fall back to a Linux browser if interop fails.
Keep a localhost URL unchanged for a service in WSL. The probe runs in WSL and
does not verify Windows firewall/localhost forwarding; a Windows-hosted server
may need an explicit different `wait_for.url` reachable from WSL.

The selected browser decides tab/window reuse; no window-mode field is supported.
Explicit browser selection never falls back to a different browser on failure.
Repeated activations open the configured URLs again. A failed
probe/opener stops further browser entries; completed task/container changes
remain in place. `down` does not close browser windows.

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

## Example: frontend followed by a browser

Use only when the project defines `npm run dev` serving port 3000. If it is already
running or served by Compose, omit the terminal to avoid a duplicate server:

```yaml
version: 1
compose:
  enabled: false
terminals:
  - title: Frontend
    command: [npm, run, dev]
browsers:
  - url: http://localhost:3000
    wait_for: false
```

The terminal and browser keep separate default confirmation prompts. Only when
the user asks for readiness, replace `false` with `wait_for: {timeout: 60}`;
for a different health endpoint, add `url` within that mapping. Terminal
`wait_for.healthy` names Compose services; browser `wait_for.url` names an HTTP
endpoint. Do not interchange these fields.

## Preview

Configuration helpers added after 0.3.0:

- `dwork --version` reports the shared package version without reading workspace state.
- `dwork init [--dry-run]` creates/previews a deterministic local starter. Standard
  local Compose filenames enable Compose; otherwise it is disabled. Task/browser
  lists are empty. It refuses existing paths, including links, and never registers
  or launches anything. Edit custom Compose selections and project commands explicitly.
- `dwork validate` reuses normal discovery/schema checks, validates task working
  directories and Compose service references, and returns 0/1 for success/failure.
  It does not read/write the registry, inspect containers, wait, or launch apps.
  Compose-enabled validation requires the Compose CLI but no daemon. Host-only
  validation needs no Docker. Use `doctor` for environment checks.

Run `dwork --dry-run` in the workspace directory. Compose-enabled previews read
the Compose model and inspect Docker containers, but never stop/start containers,
wait for health/HTTP readiness, or open terminals/browsers. Read warnings even when the command succeeds:
missing containers may still block a real launch. YAML loading requires PyYAML
in dwork's Python environment (included by the default `make install`).

Current source separates data parsing, external path/Compose resolution, registry
storage/policy, and launch preparation/dispatch. These are internal boundaries with
unchanged YAML/registry formats and consent rules. Real activation prepares launcher
commands and supervisor identity before workload changes and reuses those arguments at
dispatch. Preparation neither starts a supervisor nor writes task records. Terminal
command checks still use the invoking PATH or a task-relative executable, even when
a login shell could find additional programs. Set `SHELL`/`DWORK_TERMINAL` before the
invocation. A prepared command still requires the applicable confirmations and final
lock recheck; it does not prove server readiness or browser rendering.

`dwork doctor` checks configuration, Docker (when enabled), shell/command/terminal
dependencies, and browser opener availability. It does not request HTTP pages,
prompt, or open applications. `register` and `status` also do not probe/open
browsers. Field validation depends on the installed runtime: older releases may
lack these capabilities. Check the installed release's documentation; a feature
present only on main requires a release that includes it, or Homebrew's supported
`--HEAD` option when deliberately choosing development source.

Upstream routine macOS CI covers Apple Silicon with Python 3.13 source/package
tests and separate stable-release and exact-checkout Homebrew jobs. The checkout
lane records a full commit and archive checksum; remote `--HEAD` or a stable install
does not substitute for that evidence. Pinned Ruff/mypy checks are development-only;
they neither authorize activation nor replace confirmation/ownership regression tests. Python 3.14 and Intel checks run on release tags or manual
Package verification runs. Do not describe passing routine CI as Intel validation
or real GUI verification.

## Optional tray and JSON observations

The separate development `dwork-tray` package targets native Linux/macOS and a
Windows host connected to one explicitly selected WSL distribution.
It lists saved workspaces, refreshes status periodically/after operations, and opens
existing CLI commands in operation terminals. Native Linux requires AppIndicator or
Ayatana plus compatible tray-host support; macOS requires Python 3.13+ and Cocoa.
A dependency/menu test is not proof of desktop rendering. An optional portable Windows ZIP bundles the tray, helper, and runtime. It connects
to the matching CLI in a selected Linux interpreter; no separate Windows Python
setup is needed. The extracted folder may remain on Linux and execute through its
Windows UNC path. The app accepts explicit selection with `--wsl-distribution NAME`
and `--wsl-python /ABS/PATH`, optionally `--wsl-user USER`; omission uses the
selected distribution's default user and registry. `wsl.exe`, Windows Terminal,
and Windows PowerShell are required. No native Windows workspace execution occurs.
The Linux tray itself remains unsupported inside WSL/WSLg.

The replaceable tray image is `companion/src/dwork_tray/assets/tray.png`, loaded
relative to the package rather than the working directory. Its sibling `tray.svg`
is editable artwork; export it to PNG after changes because SVG is not read at
runtime. Source/editable users
replace the PNG and restart; distributed wheels/ZIPs need rebuilding to include
repository artwork changes. An extracted Windows ZIP also permits replacing
`_internal/dwork_tray/assets/tray.png` directly before restarting. Do not imply
that editing the checkout updates an existing installed or extracted copy.

Windows `--check` validates the backend and reads selected WSL JSON status without
an icon or mutations. Polling checks running names first and reports stopped/missing
distributions; start one deliberately and Refresh. Do not silently start it or
change the selected/default distribution. A check/launch race can still start one
that stopped in between, and polling can keep a running distribution active.
Quit stops observations; it never terminates a distribution. The Linux observer
bounds its own read session; a hung WSL subsystem can delay remote cleanup. A
terminal-handoff timeout may occur after opening, so inspect before retrying.

The default CLI install includes no GUI dependencies. Companion installation,
launch, and login startup are separate choices, not implied by generating YAML.
Login startup is offered only on native Linux/macOS, disabled until an explicit
menu toggle or `dwork-tray --autostart enable`; disable removes only an exact entry
owned by that installation. Windows omits the menu item and refuses `--autostart`
without writes. Edited or
linked entries require deliberate inspection. Quit tray does not stop workloads,
close operation terminals, or disable next-login startup. Stop remains a separate
explicit CLI action, preserving registration/locking/ownership/confirmation rules.

Builds containing this feature offer `dwork list --json` and `dwork status --json`
(with Compose global options for current status). Successful stdout is one version-1
JSON document. Diagnostics remain on stderr, and 0/1/130 exit codes remain. Docker
unavailable/different-target counts are unknown (`null`), not zero. Task credentials,
sockets, command arguments, and saved environment/options are not exported. Status
is an observation, not authorization or readiness. Older 0.3.0 releases do not have
this API; never scrape formatted tables as a substitute or add unattended approvals.
