# Remembered workspaces

[Project home](../../README.md) · [Usage](../usage/README.md) · [Configuration](../configuration/README.md)

dwork switches between workspaces you have registered. It leaves unregistered
Compose projects and containers without Compose labels running.

## First use

Run `dwork --dry-run` in your project to preview its plan. Run `dwork` when ready.
If the directory is new, dwork shows the proposed name and absolute path, explains
that future switches may stop its managed containers and tracked commands, and asks:

```text
Register and switch? (y/N)
```

Only `y` or `Y` accepts. Any other response or end-of-input cancels without
registering the workspace, changing containers, or opening terminals. The usual
terminal confirmations are separate. Once remembered, the directory does not
require registration consent again.
Plain `dwork` then shows the plan and asks before activating the remembered
workspace. Set root-level `confirm: false` in its `dwork.yml` to skip that
activation prompt; it also applies to `dwork up` and takes effect without
re-registration. Registration, discovered-group, terminal/browser, and `down`
confirmations remain separate. Explicit `dwork switch NAME` keeps its existing
confirmation behavior.
If activation later fails, an accepted registration remains remembered; use
`dwork forget NAME` if you no longer want dwork to manage it.

Registrations belong to your user account; dwork does not write them into the repo.
There is no migration that automatically claims all your existing Docker projects.

## Register without activating

```sh
cd ~/projects/my-app
dwork register
# Or choose your own short name:
dwork register app
```

`register` reads and validates the configuration, resolves its Compose identity and
Docker target when enabled, and saves it. It does not start or stop containers,
wait for health checks, check GUI dependencies, or open terminals. Running the
explicit command authorizes registration without another prompt.

Names are unique across the registry. They may contain letters, digits, dots,
underscores, and hyphens, and must start with a letter or digit. The default is the
Compose project name for a single Compose workspace, otherwise the directory name.
For directories whose default names contain spaces, choose a name explicitly.
Registering an existing directory updates its entry and can rename it.

Ordinary parent-config discovery remembers the configuration directory, so running
from a nested directory or a symlink does not create another registration. Explicit
Compose options or file-selection environment variables preserve the invocation
directory so relative paths keep their meaning.

## Scan a directory tree

```sh
cd ~/projects
dwork scan --dry-run
dwork scan
```

Searches the starting directory and descends through collections of projects.
When it finds a repository/project marker, it checks that directory for `dwork.yml`
or Compose files, then stops descending there and continues with sibling directories.
The boundary markers are:

- Version control: `.git` (file or directory), `.hg`, `.svn`.
- Workspace files: `dwork.yml`, `compose.yaml`, `compose.yml`, `docker-compose.yaml`,
  `docker-compose.yml`.
- Project manifests: `package.json`, `pyproject.toml`, `setup.py`, `Cargo.toml`,
  `go.mod`, `composer.json`, `Gemfile`, `pom.xml`, `build.gradle`, `build.gradle.kts`,
  `settings.gradle`, `settings.gradle.kts`, `mix.exs`, `pubspec.yaml`.

This is a filename-based heuristic, not proof that a repository has no nested
workspaces. It also applies to the starting directory. To find workspaces below
a detected boundary, start another scan from the desired subdirectory.

Symlinked directories and these exact directory names are
skipped at every depth, without traversing their contents:

- Version control: `.git`, `.hg`, `.svn`.
- Dependencies and environments: `node_modules`, `bower_components`, `vendor`, `.venv`, `venv`.
- Caches: `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.tox`, `.nox`,
  `.cache`, `.npm`, `.pnpm-store`, `.yarn`, `.gradle`.
- Generated output: `.next`, `.nuxt`, `.svelte-kit`, `.angular`, `build`, `dist`,
  `out`, `target`, `coverage`, `htmlcov`.

Other directories are searched without a depth limit until a boundary is found. The explicitly chosen
starting directory is always searched, even if its name is in the skip list;
run the scan inside a skipped directory if you intentionally keep projects there.
The preview reports configured workspaces and Compose candidates without prompting
or writing anything.
While searching in a terminal, updating grey rows show the current directory's
parent chain, indented by depth below the scan root. For example, `bbb/b2` shows
`bbb` and an indented `b2` on separate rows. Old rows are cleared when moving to
another branch; very deep paths are clipped to the terminal height.
Updates are limited to ten per second and the final directory is always
shown. Progress is omitted from redirected output; `NO_COLOR` disables its grey styling.

The normal command registers all valid configured workspaces first. Once that
phase is saved, it asks whether to review unregistered directories containing a
standard Compose filename but no `dwork.yml`. Accepting opens a checkbox picker:

- Up/Down arrows move between directories (j/k also work).
- Space toggles the current directory; all start unchecked.
- Enter registers only the selected directories.
- Esc or q cancels the Compose selection.

Declining the prompt, sending end-of-input, or cancelling the picker keeps the
configured registrations already added. Scanning never switches containers, waits
for health checks, launches project commands, or creates project config files.
The picker uses Python's documented curses support in an interactive terminal.
If no usable terminal/curses support exists, the command explains the problem and
keeps the first phase; run `dwork register` in individual Compose directories instead.

Recognized Compose filenames are `compose.yaml`, `compose.yml`, `docker-compose.yaml`,
and `docker-compose.yml`. A directory is offered once even if it has several files.
Already registered directories are kept with their existing names and selection
options. New registry names get a numeric suffix when needed. Duplicate Compose
project ownership, invalid configs, and unreadable directories are reported;
valid additions are kept and the command exits with status 1 if any were skipped
because of an error.

Each newly scanned directory is registered independently. When scanning directly
inside a nested project, selecting its Compose directory does not silently select
its parent's `dwork.yml`. Activate it
with `dwork switch NAME` or by running `dwork` in that registered directory. Scanning
uses each directory's own config and normal Compose discovery, without applying
the calling shell's Compose-selection environment to every discovered project.

## List

```sh
dwork list
```

`dwork list` and its `ls` alias show a table sorted by workspace name, with
`NAME`, `STATUS`, `LOCKED`, and `PATH` columns. Paths are absolute and appear last,
so long paths do not push the status and lock columns out of alignment. Each
workspace occupies one row; nonprinting characters in cells are escaped.
`STATUS` includes the count of running/restarting managed containers on the
current Docker target, or a concise `host-only` label. `LOCKED` is `yes` for a
protected single workspace, the protected project names for a group, or `-` when
none are locked. Terminal colors do not affect column widths; redirected output
and `NO_COLOR` output stay plain.

Use `down --dry-run` to inspect tracked host commands; host-only listings show
this hint once below the table. `dwork ls --names` (also `list --names`) remains
sorted names only, with no header or status queries, for shell completion and
scripts. An empty registry keeps the registration hint instead of empty rows. Missing
directories, other Docker targets, and unavailable Docker status are identified.
Listing still works when Docker is offline; it never registers, switches, or opens
terminals. It does not change Docker contexts to inspect other targets.

## Switch from anywhere

```sh
dwork switch app --dry-run
dwork switch app
```

The saved directory, Compose CLI options, and Compose-selection environment are
used. Configuration files are read again, so terminal commands and health gates
come from the current files. All existing health and terminal confirmations apply.
Your calling shell's working directory stays unchanged.

Switching uses the same shutdown policy as `down`, excluding the selected
registration and all its group members. It stops outgoing tracked commands first,
then stops outgoing running, restarting, or paused containers in one Docker batch,
then starts the selected workspace. A shutdown failure stops further activation.
This shared lifecycle was added after release 0.3.0. Tasks already running in the
selected workspace are preserved; approved configured tasks still launch again.

For example, remember a custom Compose selection once:

```sh
dwork register app -p my-app -f compose.yaml -f compose.dev.yaml
```

Later `dwork switch app` reuses that selection. The saved environment covers
`COMPOSE_FILE`, `COMPOSE_PROJECT_NAME`, `COMPOSE_PROFILES`, `COMPOSE_ENV_FILES`,
`COMPOSE_PATH_SEPARATOR`, and `COMPOSE_DISABLE_ENV_FILE`. dwork stores selection
values and file paths, not the contents of environment files or your shell's full
environment. Keep sensitive values out of CLI arguments. Your other current
environment settings, including `DWORK_KEEP_PROJECTS` and `DWORK_TERMINAL`, still apply.

`switch` accepts a name and optional `--dry-run`; change the saved Compose options
by running `register` again in the intended directory with those options.

When immediate child workspaces are discovered from a parent directory, the parent
is registered as one workspace containing those children. Switching it activates
the group together and retains the group confirmation prompt. A child Compose
project cannot also be claimed by a separate registration on the same Docker target.

## What can stop

dwork identifies a Docker target using the context name and Docker daemon ID.
Only other registered workspaces on that same target are eligible for container
shutdown, using saved ownership even if their directories are unavailable.
Their registered `compose.services` selection is respected;
when omitted, all containers in that Compose project are managed. Workspaces with
`locked: true` are excluded from stop plans, including `dwork down`.

Use unique Compose project names across repositories and Git worktrees. Registering
two directories that claim the same project on the same target fails before any
container changes. Docker identifies project membership through its Compose label;
if an unregistered repo deliberately shares that project name, its containers are
part of the same project and cannot be separated by directory registration.

Unregistered shared infrastructure already stays running. To protect a registered
project as well, use the existing exclusion:

```sh
export DWORK_KEEP_PROJECTS=infra,monitoring
```

Put this in your shell startup file to make the policy persistent. It protects those
projects during switches; it does not prevent explicitly activating them.

For a project-level policy, set top-level `locked: true` in its `dwork.yml`.
`dwork list` shows `yes` in the `LOCKED` column; groups with protected children
show their project names in that column.
It stays registered and can still be activated normally. The current lock policy
is read without requiring re-registration; switches/shutdowns record it so the
last known lock is retained if a config or directory disappears. Invalid or
unreadable policy protects the workspace with a warning. A valid config with
`locked: false` or no `locked` key unlocks it. See [locked](../configuration/README.md#locked).

Tracked commands from other eligible registered workspaces stop during switching,
regardless of their saved Docker target. Container shutdown stays scoped to the
current Docker target. Switching to a host-only workspace also stops eligible
outgoing Compose containers when Compose registrations exist; an entirely host-only
registry makes no Docker calls. Terminal windows remain open at a shell prompt,
and browser windows stay open.

## Configuration or location changes

A changed Compose identity, Docker target, workspace membership, service selection,
or selection options requires explicit re-registration before switching. dwork
stops with an explanation instead of silently accepting new ownership. Run
`dwork register NAME` with the intended options, then preview again.

Switching never silently selects a saved Docker context. Select the intended target
using your normal Docker configuration first. Registering the same directory on a
different target replaces its old registration; there is one entry per directory.

After moving a directory:

```sh
dwork forget app
cd ~/projects/new-location
dwork register app
```

Unavailable registered directories are shown in `list`. Both switches and `down`
use their last registered ownership and lock policy to shut down eligible workloads.
An unavailable directory cannot be activated. Restore it or forget and re-register
it; dwork does not guess its new location.

## Stop all workspaces

```sh
dwork down --dry-run
dwork down
```

Stops all registered container workloads on the current Docker target together,
including workloads from unavailable directories. It respects recorded service
selections and `DWORK_KEEP_PROJECTS`. Unregistered containers and containers on other
Docker targets are untouched, and locked workspaces remain running. Containers, networks, volumes,
and registrations are retained.

`down` works from any directory. It reads workspace lock policies without loading
Compose models or opening terminals.
Like switching, it stops locally tracked dwork commands before containers, leaving visible terminal windows open
at a shell prompt. Locked tasks and `DWORK_KEEP_PROJECTS` exclusions remain running.
The plan lists affected commands and protected tasks before confirmation.
See [task lifecycle details](../terminals/README.md#tracked-commands-and-shutdown).
The Docker daemon and WSL VM remain running; this command releases the stopped workloads' resources,
not a guaranteed amount of host-visible memory.

Docker receives one `stop` call with all selected container IDs. If it fails or is
interrupted, dwork refreshes the selected containers' states and reports partial
completion when possible. Preview first to inspect the scope; the explicit `down`
command shows the stop plan and asks `Stop all listed containers and tracked commands? (y/N)`.
Only `y` or `Y` proceeds; Enter, another answer, or end-of-input cancels.
`--dry-run` does not prompt. If no containers or tracked commands need stopping, no confirmation is needed.

## Rename

```sh
dwork rename app api
```

Changes the saved workspace name to an available name. Use `api` for subsequent
`switch`, `forget`, and `rename` commands. Names are case-sensitive, must start
with a letter or digit, and may contain letters, digits, dots, underscores, and
hyphens. An already registered name (including the current name) is rejected.

Renaming works from any directory, even if the workspace directory is unavailable
or Docker is offline. It preserves the directory, Compose identity, options, and
lock policy; containers, terminals, and project files are unaffected.

## Forget

```sh
dwork forget app
```

Removes only that registration. It never stops containers, closes terminals, or
changes project files. Future switches no longer manage that workspace until it
is registered again. An unknown name fails with a suggestion to run `dwork list`.

## Storage and concurrent invocations

The registry is `$XDG_STATE_HOME/dwork/workspaces.json`, defaulting to
`~/.local/state/dwork/workspaces.json`. Relative `XDG_STATE_HOME` values are ignored
according to the XDG directory rules. Registrations contain canonical absolute
paths, selection options, and resolved project identities. They are local state,
not a portable project configuration.

Updates replace the registry atomically. A per-user file lock prevents concurrent
registrations, scans, renames, forget operations, switches, and shutdowns from interleaving; a second mutating
invocation reports that another operation is in progress. Read-only commands do not
create registry or lock files. A malformed registry blocks registry operations and
switching without overwriting the file; restore or repair it before retrying.
`status` and `doctor` remain usable independently to inspect the current directory.

Uninstalling dwork leaves this user state in place for a later reinstall.

References: [Docker daemon information](https://docs.docker.com/reference/cli/docker/system/info/),
[XDG state directories](https://specifications.freedesktop.org/basedir/0.8/).
