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

## Commands and startup

Each adapter passes the command through your configured Bash or Zsh login and
interactive shell. Shell startup loads your normal environment; command arguments
are quoted rather than evaluated as shell snippets. The configured working
directory and title are passed through the emulator's supported interface.
xterm inherits the working directory from the launcher process.

Native emulator processes are detached so dwork can return while their terminals
stay open. dwork catches executable and immediate launcher failures, but does not
supervise GUI startup, commands, or terminals that exit later. The same health
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
