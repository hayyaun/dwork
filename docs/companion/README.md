# Optional tray companion

[Project home](../../README.md) · [JSON interface](../json/README.md) · [Terminal launchers](../terminals/README.md)

`dwork-tray` is an optional, experimental Python companion for native Linux and
macOS. It lists registered workspaces, observed container/command counts, and lock
protection (including partially protected groups). Selecting a workspace opens an operation terminal running the existing
`dwork switch NAME`. **Stop eligible workspaces…** opens `dwork down` separately.
**Quit tray** closes only the companion: commands, containers, browsers, operation
terminals, and login-startup settings remain unchanged.

The CLI owns registration, target identity, service selection, locking, live lock
rechecks, confirmations, supervision, and execution. Tray status cannot authorize
shutdown. Terminal input is inherited normally; the companion never answers prompts
or adds an approval flag. Explicit `switch` keeps its existing CLI confirmation
behavior, including configured task/browser opt-outs; it does not acquire the plain
`dwork`/`up` activation prompt. Existing registrations are required. Activation can
launch another copy of configured commands, as it does from the CLI.

## Install and run deliberately

The companion is a **separate distribution** under [`companion/`](../../companion/).
Ordinary CLI installs retain only their existing dependencies; they do not install
pystray, Pillow, PyObjC, PyGObject, or a login entry. Use matching development sources
until releases containing the version-1 JSON interface and companion are published:

```sh
# From the checkout, in a virtual environment chosen for your platform:
python -m pip install -e . -e ./companion
dwork-tray --check
dwork-tray
```

Do not install, launch, or enable login startup merely to generate `dwork.yml`.
`--help` works without a GUI backend. `--check` checks the supported native backend
and tray host without running the icon event loop, probing workspaces, or opening
applications. It cannot prove that a desktop will render the icon correctly. Source
and fake-UI tests pass without GUI dependencies.

### Linux

A graphical native Linux session, user D-Bus session, PyGObject/GTK introspection,
and AppIndicator or Ayatana AppIndicator are required. The app uses pystray's
supported `appindicator` backend, which tries Ayatana if AppIndicator is absent.
It also checks for a registered StatusNotifier visualization host. It does not
fall back to Xorg's limited menu support or to legacy GTK icons that may be invisible.
An incompatible `PYSTRAY_BACKEND` is reported rather than silently overridden.

On GNOME, compatible AppIndicator/Ayatana extension support may need to be enabled
by the user. KDE and other desktops need a working StatusNotifier host. No extension
or system package is installed or enabled automatically. Missing support produces
clear guidance; the CLI stays usable. Native Linux desktop compatibility remains
an explicit manual verification requirement, not a promise based on importing GTK.

Use your distribution's compatible Python and GI packages. For example, where system
PyGObject and indicator introspection packages are installed, Python's documented
`venv --system-site-packages` option can expose them to that interpreter's venv.
Alternatively install PyGObject using its supported build prerequisites. Follow your
distribution and [pystray's virtualenv guidance](https://pystray.readthedocs.io/en/latest/faq.html);
do not copy GI modules between incompatible interpreters or bypass backend checks.

### macOS

Use Python 3.13+ (matching dwork's tracked-command requirements). Pystray uses Cocoa;
its icon event loop runs on the main thread. CLI status/command work runs on a worker,
and UI updates return through public `PyObjCTools.AppHelper.callAfter`. Linux uses
public `GLib.idle_add` for the corresponding dispatch. Operation terminals use the
existing Apple Terminal adapter and retain its Automation permission requirements.
No UI keystroke automation or private native API is used.

### Windows and WSL

Windows-host support is a later phase. This first companion refuses native Windows
and WSL sessions with guidance to continue using the CLI in WSL. It does not execute
native Windows workspaces or manage Windows processes. The future host adapter must
call the same JSON/CLI interface in an explicitly selected WSL distribution through
`wsl.exe`, using Windows Terminal for interactive operations.

## Refresh and failures

Status refreshes on startup, every 15 seconds by default, on **Refresh**, and after
an operation terminal reports CLI completion. Use `--interval SECONDS` for 5–3600.
The private completion marker only triggers a fresh read; it grants no ownership,
permissions, or readiness guarantees. An operation already requested can continue
when the tray quits. The wrapper leaves the result visible until Enter finishes the operation; the
terminal may close or remain at a shell prompt according to its native behavior.

Status subprocesses use no stdin and have a 15-second timeout. Their separate
owned process session is cleaned up on timeout before the observer is reaped; this
never targets application task PIDs or interprets saved controller records. Quit
removes the icon immediately; an in-flight observation may take up to its timeout
to drain before the companion process exits. Docker unavailable,
different-target, missing-directory, and unresolved-controller states are shown
without pretending unknown counts are zero. A failed protocol read clears stale menu
rows and shows the error. The CLI still performs its live validation before acting;
a changed/forgotten name cannot be activated through a stale ownership snapshot.

## Startup at login is opt-in

The menu checkbox or these explicit commands manage only this installation's entry:

```sh
dwork-tray --autostart status
dwork-tray --autostart enable
dwork-tray --autostart disable
```

Nothing is enabled on installation or ordinary launch. Linux uses
`$XDG_CONFIG_HOME/autostart/dwork-tray.desktop` (default `~/.config`); relative
`XDG_CONFIG_HOME` is ignored. macOS uses
`~/Library/LaunchAgents/org.dwork.tray.plist`, restricted to Aqua sessions, with
`RunAtLoad` and no `KeepAlive`. These commands take effect at the next login and
never bootstrap, stop, or restart a currently running companion. macOS may also
expose the Python executable under System Settings → Login Items.

Enable uses exclusive creation; an existing identical entry is left intact. Edited,
linked, or other-installation entries are refused on enable/disable. Inspect the
reported path and resolve the conflict deliberately; do not bypass that protection.
An interpreter/venv move requires reviewing the existing entry before changing it.
Linux login executable paths containing `=` or `%` are rejected with guidance
(the native desktop launcher rejected the percent-path probe); manual tray launch
remains available. Standard Desktop Entry quoting and `TryExec` are used for other
supported paths, without a shell shim.
Quit does not disable an opted-in next-login start.

## Verification scope

The public pystray 0.19.5 menu prototype validates dynamic descriptors, per-workspace
callbacks, disabled states, and login/quit items without displaying an icon. Tests
exercise protocol privacy, target/service scoping, UI scheduling, operation handoff,
refresh, Quit behavior, login opt-in, and preservation of edited/linked entries.
Package CI builds the separate distribution, installs matching CLI/companion wheels
outside the checkout, and checks non-GUI entry points. macOS also checks the actual
pystray menu API without running an icon. None of these replaces manual GNOME/KDE
and Cocoa display/Automation/login verification. This WSL environment has GTK but
no AppIndicator/Ayatana namespaces, so it cannot verify a native tray display.

Supported interfaces: [pystray usage](https://pystray.readthedocs.io/en/latest/usage.html),
[AppHelper](https://pyobjc.readthedocs.io/en/latest/api/module-PyObjCTools.AppHelper.html),
[GLib idle dispatch](https://docs.gtk.org/glib/func.idle_add.html),
[Desktop autostart](https://specifications.freedesktop.org/autostart/latest/),
[Desktop Exec quoting](https://specifications.freedesktop.org/desktop-entry/1.0/exec-variables.html),
[Apple user agents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html).
