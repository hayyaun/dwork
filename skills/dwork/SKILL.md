---
name: dwork
description: Create, review, or update dwork.yml for a project's development workspace. Use when configuring dwork with existing Compose services, terminal or background commands, browser readiness, or troubleshooting workspace configuration.
---

# Configure a dwork workspace

Help the user configure **their project**, not the dwork source repository.
dwork resumes existing Compose containers, stops other registered workspaces on
the same Docker target unless excluded, checks health prerequisites, and opens
host commands in terminals or the background, then opens configured browser URLs
with optional HTTP readiness. Unregistered projects stay running. Host commands are
tracked for `dwork down`; ordinary workspace switches leave them running.
It never creates, rebuilds, recreates, or removes containers.

## Discover the project's setup

The macOS and browser options in this skill require dwork 0.3.0 or newer.
Check the installed package version or source tag before using them with an
older installation; updating the skill alone does not update dwork.

Read [the bundled configuration reference](references/configuration.md) before
writing YAML. It includes the supported version, fields, and examples and works
without a dwork source checkout or network access.

Inspect the target project's instructions, development README, Compose files and
overrides, package scripts, Make targets, and relevant startup scripts. Check for
an existing `dwork.yml` in the target directory and its parents: the nearest one
is selected, and files are not merged. Preserve existing choices and comments
when updating it. In a monorepo, identify the intended workspace and existing
working directories before choosing where to put the file.

Use the project's documented development commands and actual Compose **service
names**, not container names. Determine which services run in containers and
which commands run on the host; avoid launching a second copy of an application
already running in Compose. Identify the user's platform and shell: Linux,
macOS, and WSL have different terminal launchers; WSL browser URLs must open on
Windows. Derive browser URLs, ports, and any health endpoint from project scripts,
Compose port mappings, documentation, or the user's choices. Ask a focused question if multiple development modes
are plausible or commands/dependency requirements cannot be established. Do not
invent service names, commands, health checks, or folders.

## Write the configuration

- Use `version: 1` and only supported fields. Create `dwork.yml` in the intended
  workspace directory, usually beside its Compose file.
- Use top-level `locked: true` when the user wants the workspace kept running
  through switches and `dwork down`. It remains listed and can still be activated.
- For host-only work, set `compose.enabled: false` and omit Compose files,
  services, and health prerequisites. With Compose enabled, omit `files` when
  normal Compose discovery suffices; otherwise preserve the project's file order.
- Limit `compose.services` only when the user's workflow calls for a subset.
  A service filter does not prevent other registered workspaces from being stopped.
- Represent each terminal command as an executable/argument list and set `cwd`
  relative to `dwork.yml` when needed. Prefer existing scripts for compound shell
  commands; explain any additional script needed before creating it.
- Add `wait_for.healthy` only for required services with configured Docker health
  checks. Include them in `compose.services` if a service filter is present.
  A startup dependency alone does not prove a service has a health check.
- Keep the default per-terminal confirmation. Set `confirm: false` only when the
  user explicitly requests it. Prefer portable `launcher: auto` and `window: new`
  defaults unless the user requests a particular terminal setup. Apple Terminal
  and xterm support new windows only; do not emulate tabs with UI keystrokes.
- Use `window: none` only for commands the user wants detached with output
  discarded. Tracked terminal/background commands need Python 3.13+ on macOS;
  Linux/WSL require Python 3.10+. `down` stops their process groups and leaves
  visible terminal windows at a shell prompt.
- Add `browsers` only for requested application pages. Keep per-browser
  confirmation enabled unless the user explicitly opts out. Browser entries run
  after all terminal tasks are dispatched; their HTTP wait is separate from
  terminal Compose health gates. Write `wait_for: false` explicitly in new browser
  entries by default. Enable HTTP readiness only when the user explicitly asks
  for it; then use `wait_for: {timeout: 60}` for the page URL, or add `url` for
  a requested dedicated health endpoint. Preserve existing explicitly requested
  readiness requirements when updating other fields. Readiness and `confirm`
  are independent; disabling waiting does not disable confirmation.
  Omit `browser` or use `browser: default` unless the user selects another browser.
  For a custom selection, use a Linux executable, a macOS app name/path, or a
  Windows `.exe` name/absolute Windows path on WSL. Never launch a Linux browser
  from WSL. Supply one application without command-line flags. Do not promise
  browser window/tab behavior that the selected browser controls.

## Consider keeping workspace configuration private

`dwork.yml` can contain personal workspace choices and does not have to be shared.
When creating or updating it, inspect the project's ignore rules and whether the
file is already tracked. Consider adding `/dwork.yml` to the repository-root
`.gitignore` for a personal root workspace (or the matching path for a nested
workspace). Explain the suggestion and obtain approval for changing ignore rules
unless the user already authorized it. Preserve intentionally shared/team configs
and tracked examples. An ignore rule does not untrack an existing file; do not
remove it from Git's index without an explicit request. If only this user's clone
should ignore the file, offer `.git/info/exclude` instead of a shared ignore rule.

Configure only what the user requested. Generating YAML does not authorize
installing dependencies, creating containers, changing Compose health checks,
starting development servers, or switching the live workspace.

## Verify and hand off

Check the YAML against the reference, command definitions, existing directories,
Compose service names, and health checks. If dwork is available, run
`dwork --dry-run` **from the directory containing the generated file**. This
previews operations without switching containers, waiting, prompting, or opening
terminals or browsers. Compose-enabled previews still need Docker/Compose and access to the
Docker daemon. Host-only previews do not need Docker.

Inspect warnings as well as the exit status: a successful dry run can still warn
about missing containers or blocked terminal launches. If dwork or a dependency
is unavailable, report what was checked statically and what remains unverified;
do not install anything or claim runtime validation. If the installed dwork
rejects a field, check its version/docs rather than bypassing validation.
Use `dwork doctor` for dependency diagnostics when needed; it checks opener
availability without probing HTTP or launching applications. A dry run or doctor
success does not prove that a server will become ready or a GUI will render.

Explain the chosen commands, services, prerequisites, and verification result.
Tell the user that a normal `dwork` invocation asks before registering a new
directory and can stop other registered workspaces before terminal confirmation;
`DWORK_KEEP_PROJECTS` can preserve registered shared projects. `dwork register NAME`
remembers without activating, `dwork list` shows remembered directories,
`dwork switch NAME` activates from anywhere, and `dwork forget NAME` removes only
the registration. Changed Compose identity or service selection requires explicit
re-registration. Each browser asks separately after terminals; a declined terminal
does not cancel browser entries. Readiness timeouts stop further browser openings
without undoing completed task/container actions. `down` leaves browser windows
open. Generating config does not authorize changing the user's registry.
Leave live activation to the user unless they request it. For an explicit
request to open a page or run a workspace, inspect the dry-run plan and proceed
only with effects within that request's authorized scope. A browser-opening
request alone does not authorize unrelated container switches, command launches,
or a new registration; explain and ask about any additional effects first.
