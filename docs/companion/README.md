# Optional tray companion

[Project home](../../README.md) · [JSON interface](../json/README.md) · [Terminal launchers](../terminals/README.md)

`dwork-tray` is an optional, experimental Python companion for native Linux and
macOS, or a Windows host connected to one explicitly selected WSL distribution.
It lists registered workspaces, observed container/command counts, and lock
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
# Native Linux/macOS: from the checkout, in a virtual environment:
python -m pip install -e . -e ./companion
dwork-tray --check
dwork-tray
```

Do not install, launch, or enable login startup merely to generate `dwork.yml`.
`--help` works without a GUI backend. Native `--check` checks the backend and tray
host without running an icon, probing workspaces, or opening applications.
Windows `--check` also reads JSON status in the selected running WSL distribution;
it performs no workspace mutations. Neither proves desktop rendering. Source and
fake-UI tests pass without GUI dependencies.

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

An optional portable Windows ZIP bundles the tray, terminal helper, Python runtime,
and tray libraries. It connects to the existing CLI in WSL. No separate Windows
Python, pip, venv, or compiler setup is required to use it.

The **Portable Windows tray** CI workflow produces `release-assets-windows`, with
a ZIP and `SHA256SUMS.windows`; verified ZIPs also join draft releases. The extracted
`dwork-tray` folder contains `dwork-tray.exe`, `dwork-tray-terminal.exe`, and shared
`_internal` files. It may remain inside Linux and execute through its Windows UNC
path, such as `\\wsl.localhost\Ubuntu\home\YOU\...`.

From PowerShell in that folder, substitute the selected distribution and Linux
interpreter containing a CLI build with the version-1 JSON interface:

```powershell
.\dwork-tray.exe --wsl-distribution Ubuntu --wsl-python /home/YOU/dwork-env/bin/python --check
.\dwork-tray.exe --wsl-distribution Ubuntu --wsl-python /home/YOU/dwork-env/bin/python
```

The ZIP is unsigned and includes its source revision, checksum, and dependency
notices. The CLI and workspace execution remain inside WSL. A Linux tray inside
WSL/WSLg remains unsupported; native Windows workspace management is not added.
Restarting uses the same selection arguments; this version saves no preferences.

`--wsl-distribution NAME` and `--wsl-python /ABSOLUTE/LINUX/PATH` are required on
Windows. `--wsl-user USER` optionally chooses a Linux user; omission uses the
selected distribution's default user, including that user's registry/environment.
Use it explicitly if you need a fixed account. These options are rejected on native
Linux/macOS. The Windows host also requires `wsl.exe`, Windows Terminal (`wt.exe`),
and Windows PowerShell (`powershell.exe`). Missing tools produce guidance.

Status polling first lists running distribution names using `wsl.exe --list
--running --quiet`. A stopped/missing selected distribution clears stale actions
and reports an error; start it manually and choose **Refresh**. Operation handoff
also rechecks running state. A distribution can stop between the check and command
launch; WSL may start it in that race. Polling a running distribution performs real
commands and can keep it active; quit the tray to stop these observations. No WSL
shutdown/terminate command is used.

Workspace actions open a new Windows Terminal window. The bundled terminal helper
invokes the existing Linux `python -m dwork switch NAME` or `down` with normal
terminal input/output, then records completion only for refresh. Windows Terminal
receives a documented PowerShell `-EncodedCommand`; variable arguments are literal
quoted data encoded into that command, preserving spaces, quotes, Unicode, and
semicolons without interpreting workspace names as shell code. Portable builds call the
sibling `dwork-tray-terminal.exe`; source builds retain their module entry point.
Both preserve normal terminal input/output. No profiles,
execution-policy bypass, approval flags, or automated prompt responses are used.
The tray observes completion but never supervises/stops the operation terminal.
Windows login startup is not implemented: the menu item is absent and `--autostart`
returns guidance without writing settings.

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
to drain before the companion process exits. On Windows, this bounded POSIX helper
runs inside WSL from its packaged standard-library-only source; no companion install
is required there. The Windows bridge has a 25-second timeout and the running-list
query has a 5-second timeout. A bridge timeout stops only its owned Windows helper;
the Linux helper enforces its own 15-second cleanup deadline. If the WSL subsystem
itself is hung, remote cleanup cannot be guaranteed until it resumes. Terminal
handoff has a 10-second timeout; a timed-out handoff may already have opened the
requested terminal, so inspect it before retrying. Quit cannot undo a handoff already
in progress. Docker unavailable,
different-target, missing-directory, and unresolved-controller states are shown
without pretending unknown counts are zero. A failed protocol read clears stale menu
rows and shows the error. The CLI still performs its live validation before acting;
a changed/forgotten name cannot be activated through a stale ownership snapshot.

## Startup at login is opt-in

On native Linux/macOS, the menu checkbox or these explicit commands manage only
this installation's entry. Windows does not offer login-startup management:

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
outside the checkout, and checks non-GUI entry points. The portable Windows workflow tests extracted frozen entry points with external
Python absent from child PATH. Self-contained WSL/Terminal fixtures exercise status,
real PowerShell quoting, helper dispatch, declined confirmation input, exit codes,
and completion markers; these do not substitute for real WSL/desktop checks. A real
Windows-to-WSL status probe also verified a Linux interpreter path containing spaces
and Unicode JSON with a temporary harmless CLI fixture. macOS also checks the actual
pystray menu API without running an icon. None of these replaces manual GNOME/KDE
Cocoa display/Automation/login verification, or Windows tray/interactive terminal
verification on a real desktop. This WSL environment has GTK but
no AppIndicator/Ayatana namespaces, so it cannot verify a native tray display.

Supported interfaces: [pystray usage](https://pystray.readthedocs.io/en/latest/usage.html),
[AppHelper](https://pyobjc.readthedocs.io/en/latest/api/module-PyObjCTools.AppHelper.html),
[GLib idle dispatch](https://docs.gtk.org/glib/func.idle_add.html),
[Desktop autostart](https://specifications.freedesktop.org/autostart/latest/),
[Desktop Exec quoting](https://specifications.freedesktop.org/desktop-entry/1.0/exec-variables.html),
[Apple user agents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html),
[WSL commands](https://learn.microsoft.com/en-us/windows/wsl/basic-commands),
[Windows Terminal arguments](https://learn.microsoft.com/en-us/windows/terminal/command-line-arguments),
and [PowerShell EncodedCommand](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_powershell_exe).
