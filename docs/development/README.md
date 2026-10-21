# Development

[Project home](../../README.md)

## Source layout

- [`dwork.sh`](../../dwork.sh): the Bash/Zsh function and public source entry point.
- [`lib/dwork.py`](../../lib/dwork.py): thin entry point shared by source and installed commands.
- [`lib/dwork_cli.py`](../../lib/dwork_cli.py): argument routing, shell completion,
  diagnostics, and CLI error/interrupt handling.
- [`lib/dwork_config.py`](../../lib/dwork_config.py): YAML validation, Compose
  environment selection, and workspace discovery.
- [`lib/dwork_registry.py`](../../lib/dwork_registry.py): versioned registry,
  atomic updates, switch locking, ownership checks, and registration display.
- [`lib/dwork_docker.py`](../../lib/dwork_docker.py): Compose models, Docker
  inventory, health prerequisites, and container status/failure reporting.
- [`lib/dwork_terminals.py`](../../lib/dwork_terminals.py): command construction,
  per-session confirmation, and native Linux / Windows Terminal launching.
- [`lib/dwork_scan.py`](../../lib/dwork_scan.py): repository scanning, the
  Compose checkbox picker, and bulk registration.
- [`lib/dwork_workspaces.py`](../../lib/dwork_workspaces.py): switch and shutdown
  plans, protection policy, confirmations, and execution.
- [`lib/dwork_common.py`](../../lib/dwork_common.py): shared models, errors,
  terminal choices, and console formatting.
- [`lib/dwork_tasks.py`](../../lib/dwork_tasks.py): local task supervision and
  authenticated shutdown. Read-only diagnostics and previews never write registry state.
- [`tests/`](../../tests): behavior, loader, YAML, health, and launch-order tests.
- [`examples/`](../../examples/README.md): configurations developers can adapt.

- [`Makefile`](../../Makefile) and [installer](../../scripts/install.py): user
  installation, removal, and package staging.
- [`requirements.txt`](../../requirements.txt): isolated-install Python dependency.

## Tests

From the repository root:

```sh
make test
```

Tests use fake Docker and terminal launchers; they do not start containers,
development servers, or GUI terminals. Shell behavior is checked in Bash and
Zsh when those shells are installed. PyYAML is needed for configuration tests.
Registry tests isolate `XDG_STATE_HOME` in temporary directories. Existing switching
tests explicitly prepare registrations; `test_registry.py` covers first-run consent,
ownership boundaries, saved selections, target changes, missing directories, and locks.
`test_scan.py` covers recursive registration and exercises the checkbox picker in
a real pseudo-terminal, including keyboard navigation and terminal restoration.
`test_locked.py` checks live lock policy and protection during switching/shutdown.
`test_tasks.py` starts short-lived harmless processes to verify authenticated
controllers, process-group shutdown, protected workspaces, cancelled previews,
and returning a real pseudo-terminal to an ordinary usable shell.
Task supervision uses documented [POSIX process APIs](https://docs.python.org/3/library/os.html)
(`posix_spawn`, `waitid` with `WNOWAIT`, `killpg`, and terminal foreground groups)
and [Unix sockets](https://docs.python.org/3/library/socket.html), with no GUI process-tree parsing.

Installer tests use temporary prefixes with `VENV=0` and test Make targets,
ownership checks, paths with spaces, reinstall/uninstall, and DESTDIR staging.
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
The Make installer copies all Python modules in `lib/`, including the task
supervisor, so every distribution uses the same runtime.

Channel recipes, build instructions, and publication steps live under
[`packaging/`](../../packaging/README.md). Verify wheels and sdists with
`python scripts/verify-python-package.py` in a temporary tools venv containing
build and twine. Debian builds use `python3 scripts/build-deb.py`; Homebrew has
its own installed-behavior test. Packaging verification must not run real
project containers, development servers, or GUI tasks.
