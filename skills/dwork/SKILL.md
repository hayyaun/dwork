---
name: dwork
description: Create, review, or update dwork.yml and manage requested personal dwork workspace groups. Use for existing Compose services, terminal or background commands, browser readiness, workspace configuration, or group troubleshooting.
---

# Configure a dwork workspace

Help the user configure **their project**, not the dwork source repository.
dwork resumes existing Compose containers, stops other registered workspaces on
the same Docker target unless excluded, checks health prerequisites, and opens
host commands in terminals or the background, then opens configured browser URLs
with optional HTTP readiness. Unregistered projects stay running. Host commands are
tracked for shutdown. Switches and `dwork down` share the same shutdown rules:
stop eligible registered host commands before containers, excluding the selected
registrations and all their discovered child members during a switch. Destination startup
begins after shutdown succeeds. Locks and `DWORK_KEEP_PROJECTS` protect both.
It never creates, rebuilds, recreates, or removes containers.

## Discover the project's setup

The [project quick start](https://github.com/hayyaun/dwork#get-started) covers
finding and switching workspaces; use the bundled reference for advanced commands.

Use `dwork --version` when supported (available in 0.4.0+); older releases may
require checking installed package metadata or the source tag. `dwork init`
creates only a deterministic minimal config, detects standard local Compose
filenames, and refuses overwrites. It does not infer project commands. Use
`init --dry-run` to preview without writing; generating a starter does not
authorize activation. Prefer `dwork validate` for standalone schema/path/service
checks before a switch preview. Compose validation needs its CLI, not the daemon;
it does not check running containers or desktop prerequisites.

The macOS and browser options in this skill require dwork 0.3.0 or newer.
Check the installed package version or source tag before using them with an
older installation; updating the skill alone does not update dwork.
Stopping outgoing tracked commands during switches is available in 0.4.0+;
verify the installed runtime includes this behavior before promising it.
CLI 0.5.0+ adds positional `scan PATH...`, start-only `up NAME...`, and selected
`down NAME...`. Check the installed command's help before using them;
published v0.4.1 packages lack these additions. See the bundled
reference for their scope and unchanged confirmation/ownership rules.
CLI 0.6.0+ adds flat reusable groups of registered
workspaces. Check installed `--help` before using `group` or `--group`; published
v0.5.0 packages lack them. Read [reusable group guidance](references/configuration.md#reusable-named-groups)
when requested. Group edits change personal registry state, not YAML, and require
a request to manage those groups; generating configuration alone does not authorize them.
When installation is needed, check which package channels are actually published.
A prepared Homebrew formula in the repository does not mean its public tap is
available; follow the [installation guide](https://github.com/hayyaun/dwork/blob/main/docs/installation/README.md)
for the selected release and platform, including tray prerequisites and optional startup.
The repository's curl one-line installer runs the latest `main` source through
`make install` from a temporary checkout. It needs curl, Git, Make, and Python
with venv/pip support (3.10+ on Linux/WSL2, 3.13+ on macOS), and accepts `PREFIX`
and `PYTHON` environment choices. It leaves shell startup files alone and prints
any needed PATH setup. Its temporary checkout is removed; uninstall requires a
fresh or existing checkout and `make uninstall` with the same prefix. Do not
confuse a checkout of `main` with a versioned release package.
Companion 0.2.2 pairs with CLI 0.4.x, 0.5.x, or 0.6.x on native Linux/macOS;
companion 0.2.1 pairs with CLI 0.4.x or 0.5.x;
earlier companion 0.2.0 pairs with CLI 0.4.x.
Updating the skill alone does not update either package. The native source installer offers `TRAY=1` (also `make install TRAY=1`) to include
`dwork-tray` as a separate package/environment. This is an explicit installation
choice, not implied by YAML work. It neither launches the tray nor enables login
startup. Native Linux requires matching system desktop bindings; WSL instead has
the optional portable Windows app. Updates retain a previously selected tray;
`TRAY=0` does not remove it. On native Linux/macOS, the separate user action
`dwork-tray --autostart enable` (or **Start at login**) enables the next graphical
login; status/disable use the same flag. Do not enable it merely because the tray
was installed. Windows can use a user-created Startup-folder shortcut with explicit
WSL arguments; the Windows app itself still refuses `--autostart`. See the companion
reference for prerequisites, startup ownership, and UNC-path caveats.
Native package builds with the updated installer place completion files in the
platform's discovery directories; the shell still needs its completion framework
enabled. Current `dwork.sh` enables completion when sourced interactively; Zsh
requires sourcing after Oh My Zsh/`compinit`. Python installs, older source
checkouts, and prefixes outside the shell's search path need explicit setup.
Do not assume older published assets include the new paths or loader behavior;
see the bundled reference before suggesting a shell change.
CLI 0.6.0 packages and the optional portable Windows tray 0.2.2 are available from
[GitHub Releases](https://github.com/hayyaun/dwork/releases/tag/v0.6.0); select the
appropriate platform package and verify its checksum before installation.
Source build/test prerequisites differ from installed runtime dependencies:
Git is required by the source installer and package regression tests, but the
CLI wheel and native packages do not require it at runtime.

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
- Preserve the editor schema comment emitted by `dwork init` and the shipped
  examples. For new hand-written files, include the schema modeline documented
  in the bundled reference. It enables editor completion without adding a YAML
  field. Check installed-runtime support for fields suggested by the `main`
  schema; continue using `dwork validate` for paths and Compose references.
- Use top-level `locked: true` when the user wants the workspace kept running
  through switches and `dwork down`. It remains listed and can still be activated.
- For temporary local protection, use `dwork lock NAME...` with registered names
  instead of editing YAML. It lasts until `dwork unlock NAME...`, survives shell
  restarts, and protects every child of a registered directory bundle. Unlocking preserves
  YAML locks and `DWORK_KEEP_PROJECTS`. Check runtime support (0.4.0+),
  preview with `--dry-run`, and obtain authorization before changing local locks.
- Keep workspace activation confirmation enabled by default. Use root-level
  `confirm: false` only when the user explicitly opts out and the installed
  runtime supports it (0.4.0+). It skips the plain `dwork`/`up` plan
  prompt only; registration, discovered groups, tasks, browsers, and `down` keep
  their separate consent controls.
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
  Linux/WSL require Python 3.10+. Switching away or `down` stops eligible process
  groups and leaves visible terminal windows at a shell prompt. Selected-workspace
  tasks remain running; activation still launches approved configured tasks again.
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
Compose service names, and health checks. When supported, run `dwork validate`
to check configuration without registration or workload inspection. Then, if dwork is available, run
`dwork --dry-run` **from the directory containing the generated file**. This
previews operations without switching containers, waiting, prompting, or opening
terminals or browsers. Compose-enabled previews still need Docker/Compose and access to the
Docker daemon. Host-only activation also needs Docker when Compose registrations
exist, to shut down outgoing containers on the current target. An entirely
host-only registry needs no Docker. Local tracked commands are considered across
saved Docker targets; container shutdown stays scoped to the current target.

Inspect warnings as well as the exit status: a successful dry run can still warn
about missing containers or blocked terminal launches. For installation evidence,
distinguish stable-release checks from exact-checkout checks; a successful stable Homebrew run does not validate unpublished code. Quality
tools are development-only and are not prerequisites for generating workspace YAML.
If dwork or a dependency is unavailable, report what was checked statically and what remains unverified;
do not install anything or claim runtime validation. If the installed dwork
rejects a field, check its version/docs rather than bypassing validation.
Use `dwork doctor` for dependency diagnostics when needed; it checks opener
availability without probing HTTP or launching applications. A dry run or doctor
success does not prove that a server will become ready or a GUI will render.
For task shutdown failures, record the platform, Python/package versions, and
exact error. Preserve the authenticated task-controller records; do not replace
`dwork down` with signals sent to saved PIDs.
Current builds also block initial planning/previews when an eligible owned task's
controller is unreachable. Protected or selected tasks retain their exclusions.
Restore controller access before retrying; never delete records to bypass a block.

Configuration parsing/resolution, registry storage/policy, and launch preparation/dispatch
are separate internal boundaries. A successful parse is not full validation; validation
still resolves directories and Compose references. Live preflight prepares commands before
workload changes, but grants no consent and proves no application readiness. Set launcher
and shell environment choices before invoking dwork. See the bundled reference for
verification scope.

Typed activation plans/actions/results are an internal refactor, not new YAML
fields or a resume API. Reusable groups have their own versioned local-state rules
in the bundled reference. A rendered
plan does not authorize execution. Keep registration/group/activation consent
separate from task/browser consent, and retain the live lock recheck before stops.
When explaining partial failures, distinguish completed, already-finished, skipped,
and unconfirmed work. A dispatched task does not prove server readiness. Restore
containers only when the reported action actually stopped a container; never infer
recovery commands by parsing task titles or display labels. Existing commands and
exit codes remain the interface for configuration and troubleshooting.

When diagnosing nested invocations, distinguish the invocation directory from the
directory containing `dwork.yml`: explicit Compose file/environment selections
retain invocation-relative meaning, while YAML `compose.files` and terminal `cwd`
remain YAML-relative. Current source loaders also support relative sourcing followed
by directory changes. Terminal health timeouts include Docker inspection time;
terminal/browser timeouts must be numeric, greater than zero, and at most 3600.
For an interrupted Make upgrade, use the current installer with the same prefix
and completion directories to retry, or uninstall the marked partial installation.
Do not bypass ownership hashes or linked-path rejection to force recovery; genuine
launcher/completion edits remain protected. These hardening changes are included in 0.4.0; verify the actual installed
runtime before recommending recovery for older versions.

For the optional tray companion, keep it separate from workspace configuration.
The native Linux/macOS and Windows-to-WSL companion needs GUI dependencies; ordinary CLI
installs remain lightweight. Never install/launch it or enable login startup merely
to generate YAML. Use its explicit `--check` diagnostic for backend guidance when
requested. Linux needs AppIndicator/Ayatana and compatible indicator host support;
GNOME extensions and system dependencies require their own authorization. An optional portable Windows application bundles its runtime and connects to WSL,
without a separate Windows Python setup. It accepts explicit `--wsl-distribution` and absolute
Linux `--wsl-python` arguments; `--wsl-user` selects an account or omission uses
the distribution default. Install the core CLI only in the selected WSL interpreter.
For requested Windows/WSL setup or relaunch, follow the
[portable setup steps](https://github.com/hayyaun/dwork/blob/main/docs/companion/README.md#set-up-the-portable-app)
and [manual restart options](https://github.com/hayyaun/dwork/blob/main/docs/companion/README.md#start-it-again-without-remembering-the-arguments),
with the interpreter/user checks in the bundled reference.
Do not bypass stopped-distribution checks, scrape tables, or manage native Windows
workspaces. Windows `--check` also reads WSL status; Windows app-managed login startup is absent; an explicitly requested manual
Startup-folder shortcut remains available.
Tray actions use the existing CLI in terminals and keep its confirmation semantics;
Quit closes only the tray. Native Linux/macOS login startup is opt-in and edited/linked entries remain
protected. Version-1 `list --json`/`status --json` are read-only observations, not
approval or ownership tokens. Old published 0.3.0 builds lack these new interfaces;
check runtime support instead of scraping tables or bypassing checks.

Explain the chosen commands, services, prerequisites, and verification result.
Tell the user that a normal `dwork` invocation asks before registering a new
directory and asks to apply the plan on later activations unless root
`confirm: false` is set. It stops other eligible registered commands before their
containers and before terminal confirmation; missing outgoing directories do not
remove their saved ownership from the shutdown plan.
`DWORK_KEEP_PROJECTS` can preserve registered shared projects. `dwork register NAME`
remembers without activating, `dwork list` shows a `NAME`/`STATUS`/`LOCKED`/`PATH`
table of remembered directories,
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
