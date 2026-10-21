# Development

[Project home](../../README.md)

## Source layout

- [`dwork.sh`](../../dwork.sh): the Bash/Zsh function and public source entry point.
  Interactive sourcing also loads completion; Zsh requires existing `compinit`.
- [`lib/dwork.py`](../../lib/dwork.py): thin entry point shared by source and installed commands.
- [`lib/dwork_cli.py`](../../lib/dwork_cli.py): argument routing, shell completion,
  diagnostics, and CLI error/interrupt handling.
- [`lib/dwork_config.py`](../../lib/dwork_config.py): YAML validation, Compose
  environment selection, deterministic initialization, and workspace discovery.
- [`lib/dwork_version.py`](../../lib/dwork_version.py): single version constant
  shared by `--version`, package metadata, and release-tag validation.
- [`lib/dwork_registry.py`](../../lib/dwork_registry.py): versioned registry,
  atomic updates, switch locking, ownership checks, and registration display.
- [`lib/dwork_docker.py`](../../lib/dwork_docker.py): Compose models, Docker
  inventory, health prerequisites, and container status/failure reporting.
- [`lib/dwork_terminals.py`](../../lib/dwork_terminals.py): command construction,
  per-session confirmation, and native Linux / Windows Terminal launching.
- [`lib/dwork_scan.py`](../../lib/dwork_scan.py): repository scanning, the
  Compose checkbox picker, and bulk registration.
- [`lib/dwork_workspaces.py`](../../lib/dwork_workspaces.py): switch and shutdown
  plans, shared shutdown selection/execution, protection policy, and confirmations.
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

## Tests

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
The default venv installation is additionally smoke-tested in a temporary prefix.

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
