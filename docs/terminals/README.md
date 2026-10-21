# Terminal launchers

[Project home](../../README.md) · [Configuration](../configuration/README.md)

Terminal tasks work on native Linux desktops and WSL. Existing configs keep
`launcher: auto` behavior by default, so you can share one config across machines.

## Automatic selection

- On WSL, `auto` chooses Windows Terminal via Windows PowerShell.
- On native Linux, it prefers the installed terminal for `XDG_CURRENT_DESKTOP`:
  GNOME Terminal for GNOME, Konsole for KDE, or Xfce Terminal for Xfce.
- If that preference is unavailable, it checks GNOME Terminal, Konsole, Xfce
  Terminal, and then xterm, in that order.
- xterm is considered only for `window: new`, since it has no tab interface.
- An unsuccessful launch is reported; dwork does not retry by opening a different
  application.

Native launchers require a graphical session: `DISPLAY` or `WAYLAND_DISPLAY`.
xterm specifically needs `DISPLAY`, including XWayland. Headless/SSH sessions
without graphical forwarding can still use Compose-only configs.

## Choose a launcher for your machine

Use an environment variable to keep a shared project config portable:

```sh
export DWORK_TERMINAL=konsole
dwork --dry-run
```

Supported values are `auto`, `windows-terminal`, `gnome-terminal`, `konsole`,
`xfce4-terminal`, and `xterm`. This is a launcher name, not a shell command.

## Choose a launcher for one task

A task can override the machine setting:

```yaml
version: 1
compose:
  enabled: false
terminals:
  - title: Frontend
    command: [npm, run, dev]
    launcher: gnome-terminal
    window: new
```

Selection precedence: explicit task launcher, then `DWORK_TERMINAL`, then automatic
platform/desktop selection. A task's `launcher: auto` allows the environment setting
to choose. The same native launchers can be explicitly selected in WSLg when the
emulator is installed and a graphical session is available.

## Confirmation before each session

Both native Linux and Windows Terminal sessions ask `(y/N)` by default, immediately
before launch and after health prerequisites pass. The prompt includes the title,
command, and working directory. Declining, pressing Enter, or end-of-input skips
that session and continues to the next one.

Set `confirm: false` on a task in `dwork.yml` to opt out for that session only.
The machine launcher setting does not bypass confirmation. Dry runs show the
confirmation policy without asking or opening terminals. See
[session confirmation](../configuration/README.md#session-confirmation).

## Windows and tabs

- GNOME Terminal: `window: new` opens a window; `current` opens a tab in the
  last-opened window.
- Konsole: `new` starts a separate instance; `current` requests an existing-window tab.
- Xfce Terminal: `new` opens a window; `current` requests an active-window tab.
- xterm: new windows only. An explicit xterm request with `window: current` is an
  error, caught before container switching.
- Windows Terminal: `new` opens a window; `current` targets the most recently used
  window.

Existing-window selection follows each terminal application's documented rules.
This does not guarantee the window containing the dwork invocation is the target.

### Troubleshoot `current` on Windows Terminal / WSL

The task setting is **`window: current`**, under `terminals`:

```yaml
terminals:
  - title: Backend
    command: [make, run]
    window: current
```

`terminal: current` is not a supported configuration field. `current` opens a new
tab in an existing window; it does not run inside or replace the tab containing
your shell.

dwork passes `wt.exe -w 0 new-tab ...`. Microsoft's documented meaning of `0` is
**the most recently used Windows Terminal window**, not the window containing the
calling shell. If another window becomes most recently used while dwork waits for
health checks or confirmation, the new tab can open there. If no eligible window
exists, Windows Terminal can create a new one.

For the existing behavior, make the intended Windows Terminal window active before
accepting the task prompt. When invoking dwork from an IDE terminal or another
terminal application, `current` still refers to a Windows Terminal window.
The documented CLI supports explicit window IDs/names, but this dwork adapter
currently exposes only `new` and `current`; it does not guarantee exact calling-window
targeting.

Reference: [Windows Terminal window selection](https://learn.microsoft.com/en-us/windows/terminal/command-line-arguments#options-and-commands).

## Detached background tasks

```yaml
version: 1
compose:
  enabled: false
terminals:
  - title: Worker
    command: [make, worker]
    window: none
```

`window: none` runs the task detached without opening a window or tab. It works in
headless Linux/WSL sessions and does not require a GUI, Windows Terminal, PowerShell,
or a native terminal emulator. The task's `launcher` and `DWORK_TERMINAL` are not used.
An available Bash or Zsh shell and the command executable are still required.

The command runs in its configured directory through a noninteractive login shell
(`-lc`). Arguments are quoted as with visible tasks. It inherits the environment,
but interactive shell startup files/aliases are not loaded just to launch it. Ensure
the executable is on PATH or use an existing script that initializes its environment.

All health gates pass first, and the task still asks `(y/N)` unless it explicitly
sets `confirm: false`. The prompt says "Run background task"; previews say "Would
run detached". Declining or previewing never starts it.

Input, standard output, and standard error are redirected to the null device.
dwork starts a detached supervisor, reports its PID, and returns after a short
immediate-failure check. A command that exits unsuccessfully immediately is reported
as a failure; run it manually to inspect its output. A successful launch does not
guarantee later readiness or success, and there is no implicit log file.

Every activation starts another copy if approved. These commands are tracked and
stopped by `dwork down`, following the same lock and exclusion rules as visible tasks.

## Tracked commands and shutdown

New visible and detached tasks run under a small local supervisor. Run
`dwork down --dry-run` to see their workspace name, task title, command, PID, and
whether they will stop or remain protected. `dwork down` shows the same plan and
requires confirmation before stopping tasks, then containers. Cancelling leaves
both running. Ordinary workspace switches continue to leave existing host tasks alone.

`locked: true` protects that workspace's tasks, including individual locked children
of a workspace group. `DWORK_KEEP_PROJECTS` also protects tasks belonging to those
project names. Locks are checked again after confirmation. Renaming a workspace
preserves its tracked tasks; `forget` relinquishes management without stopping them.
Re-registering the same directory restores management when the project identity matches.

For visible tasks, dwork stops the command and leaves the window/tab open at an
ordinary Bash or Zsh shell prompt. Work subsequently started in that shell is outside
dwork's tracking. Terminal input and Ctrl+C continue to reach the running command.
Detached tasks have no window to preserve. A command's normal completion also
returns visible tasks to a shell prompt.

Shutdown sends SIGTERM to the command's process group, allowing up to five seconds
for its main process to exit, then kills any remaining group members. Children
that stay in that group stop too. Configure foreground commands: programs that
daemonize, create other sessions/process groups, launch Windows processes, or
delegate work to external services need their own lifecycle tools.

Tracking is local to the Linux installation/WSL distribution and user. Host tasks
are considered across all registered workspaces locally, regardless of their saved
Docker context; container shutdown remains scoped to the current Docker target.
Host-only workspaces need no Docker connection. If registered Compose workspaces
exist, Docker must be reachable to build the complete shutdown plan.

Private records live beside the workspace registry in `dwork/tasks/*.json` beneath
the state directory. Each supervisor uses an authenticated Unix socket in a private
temporary directory. Shutdown contacts the live supervisor; it never kills a process
solely because its PID appears in a record. Finished records are removed; stale or
unreachable records cannot authorize a stop. A controller failure during shutdown
reports incomplete work and leaves later tasks and containers alone. After a supervisor crash, manage any
surviving command manually. Commands launched by older dwork versions are untracked;
restart them through this version to enable tracking. There is no restart policy,
deduplication, or readiness check beyond the existing health prerequisites.

## Commands and startup

Each adapter passes the command through your configured Bash or Zsh login and
interactive shell. Shell startup loads your normal environment; command arguments
are quoted rather than evaluated as shell snippets. The configured working
directory and title are passed through the emulator's supported interface.
xterm inherits the working directory from the launcher process.

Native emulator processes are detached so dwork can return while their terminals
stay open. dwork catches executable and immediate launcher failures; GUI startup
is not monitored for later failures. The same health
prerequisites run before terminals launch on either platform.

Dependencies are checked before container changes. `--dry-run` never opens a
terminal or requires a graphical session. It describes configured commands;
automatic emulator selection is finalized when you invoke the real switch.

## Verification scope

Automated tests use fake emulators and verify native adapter arguments, shell
quoting, health-before-launch ordering, headless rejection, and detached process
handling. WSL launching has its own regression tests. A real native Linux desktop
is not available in the development environment, so GUI behavior has not been
visually verified there.

## Official interfaces

- [GNOME Terminal manual](https://github.com/GNOME/gnome-terminal/blob/master/man/gnome-terminal.xml)
- [Konsole command-line options](https://docs.kde.org/stable_kf6/en/konsole/konsole/command-line-options.html)
- [Konsole profile title property](https://github.com/KDE/konsole/blob/master/src/profile/Profile.cpp)
- [Xfce Terminal command-line options](https://docs.xfce.org/apps/xfce4-terminal/command-line)
- [xterm manual](https://invisible-island.net/xterm/manpage/xterm.html)
