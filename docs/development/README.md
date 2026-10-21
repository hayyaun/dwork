# Development

[Project home](../../README.md)

## Source layout

- [`dwork.sh`](../../dwork.sh): the Bash/Zsh function and public source entry point.
  Interactive sourcing also loads completion; Zsh requires existing `compinit`.
- [`lib/dwork.py`](../../lib/dwork.py): thin entry point shared by source and installed commands.
- [`lib/dwork_cli.py`](../../lib/dwork_cli.py): argument routing, shell completion,
  diagnostics, and CLI error/interrupt handling.
- [`lib/dwork_config_parse.py`](../../lib/dwork_config_parse.py): data-only YAML
  decoding and immutable normalized configuration values.
- [`lib/dwork_config.py`](../../lib/dwork_config.py): path and Compose resolution,
  environment selection, deterministic initialization, and workspace discovery.
- [`lib/dwork_version.py`](../../lib/dwork_version.py): single version constant
  shared by `--version`, package metadata, and release-tag validation.
- [`lib/dwork_registry_store.py`](../../lib/dwork_registry_store.py): versioned
  registry validation, atomic persistence, state paths, and the operation lock.
- [`lib/dwork_registry_policy.py`](../../lib/dwork_registry_policy.py): pure
  ownership, service selection, lock protection, and tracked-command eligibility.
- [`lib/dwork_registry.py`](../../lib/dwork_registry.py): registration workflows,
  live YAML lock refresh, registration consent, and display.
- [`lib/dwork_docker.py`](../../lib/dwork_docker.py): Compose models, Docker
  inventory, health prerequisites, and container status reporting.
- [`lib/dwork_plans.py`](../../lib/dwork_plans.py): typed activation/shutdown
  snapshots, explicit action payloads, and per-action execution results.
- [`lib/dwork_launch.py`](../../lib/dwork_launch.py): immutable prepared terminal
  and browser commands and dispatch metadata.
- [`lib/dwork_terminal_launch.py`](../../lib/dwork_terminal_launch.py) and
  [`lib/dwork_browser_launch.py`](../../lib/dwork_browser_launch.py): launcher
  selection, argument construction, and dependency preflight.
- [`lib/dwork_terminals.py`](../../lib/dwork_terminals.py) and
  [`lib/dwork_browsers.py`](../../lib/dwork_browsers.py): per-entry consent,
  prepared command dispatch, and browser HTTP readiness.
- [`lib/dwork_process.py`](../../lib/dwork_process.py): shared checked subprocess
  runner for Docker and Windows dispatch helpers.
- [`lib/dwork_scan.py`](../../lib/dwork_scan.py): repository scanning, the
  Compose checkbox picker, and bulk registration.
- [`lib/dwork_workspaces.py`](../../lib/dwork_workspaces.py): switch and shutdown
  orchestration, launch preparation attachment, shared typed execution, confirmations, and
  partial-failure/recovery presentation.
  Switches exclude the selected registration; `down` uses the same path without
  an exclusion. Both stop commands before containers and recheck locks after prompts.
- [`lib/dwork_common.py`](../../lib/dwork_common.py): shared models, errors,
  terminal choices, and console formatting.
- [`lib/dwork_tasks.py`](../../lib/dwork_tasks.py): local task supervision and
  authenticated shutdown. Read-only diagnostics and previews never write registry state.
- [`tests/`](../../tests): behavior, loader, YAML, health, and launch-order tests.
- [`examples/`](../../examples/README.md): configurations developers can adapt.
- [`schemas/dwork.schema.json`](../../schemas/dwork.schema.json): editor completion,
  hover help, and structural validation for configuration version 1.

- [`Makefile`](../../Makefile) and [installer](../../scripts/install.py): user
  installation, removal, and package staging.
- [`requirements.txt`](../../requirements.txt): isolated-install Python dependency.

## Internal boundaries

`decode_config(text)` and `parse_config(mapping)` perform no filesystem, Compose,
registry, GUI, or network operations. The normalized frozen records use tuples so
later resolution cannot mutate the source configuration. `resolve_workspace` owns
working-directory checks, YAML-relative paths, Compose file precedence, resolved
project-name defaults, and service/health references. Discovery and saved Compose
environments remain in `dwork_config`; structural validation happens before external
resolution. Validation still checks directories and Compose references, and is distinct
from launch preflight. The schema, defaults, and accepted configuration remain version 1.

`dwork_registry_store` owns the existing JSON format, atomic replacement, and POSIX
operation lock. Reads never create state. It neither loads workspace YAML nor decides
which resources may stop. `dwork_registry_policy` evaluates supplied records without
I/O: Docker target identity, enabled members, selected services, temporary/YAML locks,
and tracked-command workspace/member identity. Registration and the existing live YAML
refresh stay in the registry facade. Missing configs retain cached lock policy;
unreadable policy protects the member. The operation lock still spans prompts and
mutations, and the final live policy recheck remains immediately before shutdown.

For live activation, `prepare_launches` attaches immutable commands returned by the
terminal/browser preflights to the copied plan. Preparation resolves the same launcher,
shell, supervisor identity, argv, cwd, and dispatch method that execution will use.
Windows Terminal is probed once per batch. Preparation creates no supervisor records,
launches no tasks/apps, and requests no HTTP pages. Dispatch uses these prepared values
without repeating launcher selection or rebuilding arguments after outgoing shutdown.
Terminal executable checks still use the invoking process's PATH or the task-relative
executable; login-shell PATH policy is unchanged. Native quoting and supported platform
interfaces are unchanged. Direct adapter calls can prepare on demand; the CLI prepares
all launch entries before consent, registry writes, or workload changes.

Prepared commands confer no permission. Activation/group/registration and individual
terminal/browser confirmations remain separate. Browser readiness follows browser consent
and terminal dispatch. Dry runs do not prepare launches; `doctor` checks dependencies
without launching or requesting HTTP, while `register`, `status`, and `validate` do not
check desktop dependencies. These boundaries introduce no new CLI/configuration fields,
registry migration, automatic fallback, readiness guarantee, or retry/resume API.

## Activation plans and results

`build_activation_plan` consumes resolved workspace paths, container snapshots,
and an ownership-filtered shutdown selection. It performs no I/O, prompts, probes,
or persistence. Its copied configuration and inventory keep task ownership metadata
inside the plan instead of mutating the loaded configuration. Actions explicitly
represent task shutdown, a container-stop batch, individual container starts,
health gates, terminal/background launches, and browser dispatch with optional
readiness. They contain data, not executable closures or display labels. Live launch actions also
carry prepared commands; the pure builder leaves those fields unset.

`switch_workspace` still validates registrations, target identity, and ownership
before building the plan. Dry runs render the planned resources without executing
them. Existing activation, discovered-group, first-registration, task, browser, and
shutdown confirmations remain separate. After plan-level consent, live locks are
rechecked and the approved shutdown selection replaces the preview selection;
newly protected resources never enter the executor. Registry writes remain in the
orchestrator under the existing operation lock.

`execute_activation` and `stop_workspaces` share the typed action executor. Order
remains outgoing tracked commands, one container-stop batch, container starts,
all health gates, terminal/background confirmations and launches, then browser
confirmations/readiness/dispatch. No action type authorizes itself: callers must
complete the existing ownership and consent checks first.

Each `ActionResult` records `pending`, `running`, `completed`, `already_finished`,
`skipped`, `failed`, or `interrupted`, with an optional error and supervisor PID.
Completed cleanup of a tracked command is distinct from stopping a container.
Declined tasks/browser entries are skipped and excluded from pending work; a failed
or interrupted action and all later actions remain unconfirmed. Launch completion
means dispatch returned, not that a server is ready. Original exceptions and CLI
exit codes are preserved. Reusing an execution result cannot replay commands.

Failure messages render these typed outcomes. Container recovery suggestions come
only from confirmed container-stop actions, never from parsing user-facing text,
task titles, or ANSI sequences. Completed container changes are not rolled back.
The models/results are internal and in-memory; they add no config keys, registry
fields, JSON CLI output, retry/resume interface, or new permissions. Python wheels
declare all parsing, storage, policy, planning, and preparation modules; Make/native installers copy
the same runtime module set.

## Tests

`test_boundaries.py` covers parsing without external access, immutable normalized inputs,
resolution defaults and Compose/path precedence, service and separator restrictions,
registry round trips without policy evaluation, and failed atomic replacement cleanup.
It also checks target/service/lock/task identity rules without filesystem or Docker
access. Prepared-launch regressions cover Linux, macOS, WSL, and detached tasks:
preflight performs no launches/HTTP, dispatch retains exact argv/cwd/supervisor metadata
and transport when environment/platform selection changes, Windows probes remain batched,
parent-PATH checks remain enforced, and prepared actions still require separate consent.


`test_plans.py` covers data-only planning, isolated input snapshots, action order,
existing service/job selection policy, missing-health preview/live behavior, and
lock changes between preview and execution. Its executor regressions cover separate
session consent, skipped actions, failures and interrupts at every action type,
completed task cleanup, supervisor PID results, opaque display labels, and replay
rejection. Existing CLI, group, ownership, shutdown, and real harmless process tests
remain the behavioral compatibility checks.

`test_list.py` covers aligned workspace tables, ANSI/plain output, service-filtered
container counts, group locks, offline/missing targets, compact host-only rows,
and paths with nonprinting characters. Registry and completion tests keep the
`list`/`ls` read-only behavior and header-free `--names` interface covered.

`test_config_commands.py` checks version reporting, deterministic initialization,
overwrite protection, and validation without registry/container operations.
`test_loader.py` checks that noninteractive sourcing never generates completion,
interactive optional loading tolerates missing dependencies, and Zsh requires
existing completion initialization. Real Tab tests also source `dwork.sh` twice
in interactive Bash/Zsh without a separate completion command.
`test_schema.py` validates the schema, shipped examples, and generated starters,
compares valid/invalid configurations and defaults against the real loader, and
checks that editor comments point to the schema's published identity. It uses
local schema references and a fake Compose model, without network requests.

From the repository root, install test dependencies in a virtual environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
make test
```

Tests use fake Docker and terminal launchers; they do not start containers,
development servers, or GUI terminals. Shell behavior is checked in Bash and
Zsh when those shells are installed. PyYAML is needed for configuration tests;
the `test` extra adds `jsonschema` for schema tests, without a runtime dependency.
CI installs this extra in source-test and release-test jobs. Update the schema,
its descriptions/defaults, and schema parity tests whenever config rules change.
The schema is included in source distributions. For editor verification before
publication, use the [local association](../configuration/README.md#editor-autocomplete),
then check field completion, `window` choices, hover help, and diagnostics for
an unknown key or a quoted boolean.
Registry tests isolate `XDG_STATE_HOME` in temporary directories. Existing switching
tests explicitly prepare registrations; `test_registry.py` covers first-run consent,
ownership boundaries, saved selections, target changes, missing directories, and locks.
The shared fixture also approves the single-workspace activation prompt for existing
behavior tests. Registry tests supply activation answers explicitly and cover rejection,
EOF, root `confirm`, nested invocation, and preservation of group/registration consent.
`test_scan.py` covers recursive registration and exercises the checkbox picker in
a real pseudo-terminal, including keyboard navigation and terminal restoration.
The restoration check compares all terminal settings except macOS's transient
`PENDIN` input-queue state. Completion tests reap their own interactive shells
after checking real Tab input. The shared fixture prepends fake Docker to `PATH`
for both direct imports and CLI subprocesses, regardless of host Docker availability;
confirmation tests select a fake native terminal adapter for the runner's OS.
`test_locked.py` checks live lock policy and protection during switching/shutdown.
`test_temporary_locks.py` checks batch lock/unlock validation, read-only previews,
YAML-policy precedence, whole-group protection, and survival across renaming,
re-registration, and missing directories. Completion tests exercise multiple
lock/unlock names with real Tab input in Bash and Zsh. Task tests verify that a
real harmless process survives both shutdown and a switch until explicitly unlocked.
`test_shutdown.py` checks common shutdown ownership and protection rules, paused
containers, batch ordering, host-only destinations, missing directories, and Docker
target isolation. `test_tasks.py` also verifies outgoing-command shutdown during
switches, selected group preservation, and activation aborts after controller failure.
`test_tasks.py` starts short-lived harmless processes to verify authenticated
controllers, process-group shutdown, protected workspaces, cancelled previews,
normal task completion during confirmation, and returning a real pseudo-terminal
to an ordinary usable shell. Shutdown recognizes completed cleanup only when a
controller connection disappears and the supervisor's token record is absent;
authentication, permission, and active-controller failures still abort the plan.
Task tests have a 30-second POSIX alarm that dumps blocked Python frames before
terminating the test process. This keeps native-terminal CI diagnostics bounded
without starting a watchdog thread before `pty.fork`.
PTY cleanup closes the master before reaping its child, following
[`pty.spawn`](https://github.com/python/cpython/blob/3.14/Lib/pty.py), and uses
bounded child-exit checks after HUP/KILL. This avoids holding a PTY open across
a blocking reap, which hung the macOS test cleanup.
Task supervision uses documented [POSIX process APIs](https://docs.python.org/3/library/os.html)
(`posix_spawn`, `waitid` with `WNOWAIT`, `killpg`, and terminal foreground groups)
and [Unix sockets](https://docs.python.org/3/library/socket.html), with no GUI process-tree parsing.
On macOS, an owned helper joins the command's process group and stays alive
through its final cleanup signal. This avoids treating a zombie-only group's
permission error as success. The supervisor retains the unreaped command until
cleanup, and a private pipe makes the helper clean up the group if its supervisor
exits. Group creation and joining use the documented
[`posix_spawn` process-group attribute](https://pubs.opengroup.org/onlinepubs/9799919799/functions/posix_spawn.html).

Installer tests use temporary prefixes with `VENV=0` and test Make targets,
ownership checks, paths with spaces, reinstall/uninstall, and DESTDIR staging.
They also check native completion paths, migration from older install markers,
preservation of modified/unrelated completions and shared directories, Zsh
discovery through `fpath`/`compinit`, and Bash discovery when `bash-completion`
is available. Real Tab tests cover the installed Zsh autoload entry as well as
explicitly sourced Bash/Zsh scripts, including the first completion request.
Native-file hashes are stored in the install marker; uninstall uses those
recorded paths, so distro-specific directory flags are not needed again.
Interrupted-upgrade regressions inject failures after each native completion or
launcher replacement and before the final marker commit, then exercise both retry
and uninstall. They also verify that edits made after interruption remain protected
and that linked license destinations cannot overwrite outside files. Pending
ownership records authorize only previously verified or installer-generated hashes;
atomic replacement prevents partial external files or truncated marker JSON.
The default venv installation is additionally smoke-tested in a temporary prefix.

Stage-one regressions also combine relative Bash/Zsh sourcing with later directory
changes, keep nested explicit Compose selections separate from YAML-relative paths,
reject huge integer timeouts through schema/runtime parity, and run a stalled fake
Docker executable against the health deadline. Task-discovery tests exercise
controller timeout, permission, missing-socket, identity, and protocol failures
before shutdown/activation, while preserving protected and selected tasks and
recognizing a supervisor record removed during completed cleanup.

## CI coverage

The Package verification workflow runs on pull requests and pushes to `main`.
Routine macOS coverage is two jobs on Apple Silicon (`macos-15`): source tests
and Python package verification on Python 3.13, plus Homebrew formula verification.
Linux keeps Python 3.10/3.14, Debian, and Homebrew coverage.

Pushing a release tag matching `vMAJOR.MINOR.PATCH`, or manually running
**Package verification** through `workflow_dispatch`, expands the matrix with
Apple Silicon Python 3.14, Intel Python 3.14, and Intel Homebrew checks. These
checks run alongside the separate draft-release workflow on release tags.
Intel-specific failures may therefore be detected at release/manual verification
rather than on every pull request. No workflow launches real GUI applications
or development servers.

## Agent skill

[`skills/dwork/`](../../skills/dwork/) is the portable, separately installable
skill for users generating configurations in their own projects. Keep its
bundled [configuration reference](../../skills/dwork/references/configuration.md)
consistent with the parser and [configuration docs](../configuration/README.md)
when changing supported fields or behavior. Keep references inside the skill
folder so installations work without the source checkout. Installation and
manual-copy instructions live in the [skill guide](../skills/README.md).

Before publishing changes, check local skill discovery without installing:

```sh
npx skills add ./skills/dwork --list
```

## Distribution packaging

[`pyproject.toml`](../../pyproject.toml) packages the `lib/dwork*.py` modules
using setuptools. `dwork:cli` is the console entry point and preserves source
CLI errors/interrupts. Both `dwork.sh` and the Make-installed launcher execute
the same thin `lib/dwork.py` entry point; its sibling imports resolve from `lib/`.
The project version is dynamic metadata read from `dwork_version.__version__`
using setuptools' documented `attr` configuration. Update that literal for a
release; the CLI does not depend on installed distribution metadata or TOML parsing.
The Make installer copies all Python modules in `lib/`, including the task
supervisor, so every distribution uses the same runtime.

Channel recipes, build instructions, and publication steps live under
[`packaging/`](../../packaging/README.md). Verify wheels and sdists with
`python scripts/verify-python-package.py` in a temporary tools venv containing
build and twine. Debian builds use `python3 scripts/build-deb.py`; Homebrew has
its own installed-behavior test. Packaging verification must not run real
project containers, development servers, or GUI tasks.
