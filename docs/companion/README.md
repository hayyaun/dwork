# Optional tray companion

[Project home](../../README.md) · [JSON interface](../json/README.md) · [Terminal launchers](../terminals/README.md)

`dwork-tray` is an optional, experimental Python companion for native Linux and
macOS, or a Windows host connected to one explicitly selected WSL distribution.
It lists registered workspaces, observed container/command counts, and lock
protection (including partially protected directory bundles). Selecting a workspace opens an operation terminal running the existing
`dwork switch NAME`. **Stop eligible workspaces…** opens `dwork down` separately.
The reusable CLI groups in 0.6.0+ do not add tray items: selection still switches
an individual registration, including its discovered children, and the stop item
retains its existing all-eligible scope.
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
pystray, Pillow, PyObjC, PyGObject, or a login entry. Companion 0.2.2
pairs with `dwork-cli` 0.4.x, 0.5.x, or 0.6.x on native Linux/macOS (`>=0.4.0,<0.7`);
the portable ZIP is published with CLI 0.6.0. Earlier companion 0.2.0 pairs with
CLI 0.4.x.
The Windows app connects to a matching CLI inside WSL. Version 0.4.0 includes
the version-1 JSON interface.
The source installer can include this separate package on native Linux/macOS:

```sh
make install TRAY=1
```

The [installation guide](../installation/README.md#optional-native-tray) also shows
the curl option, platform prerequisites, and managed files. Installation never
runs the tray or enables login startup. Launch `dwork-tray` manually when desired.
The default CLI-only install is unchanged. WSL users have the optional Windows app
[described below](#windows-and-wsl).

For source development, matching editable packages remain available:

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

[Release v0.6.0](https://github.com/hayyaun/dwork/releases/tag/v0.6.0) includes the
[portable tray 0.2.2 ZIP](https://github.com/hayyaun/dwork/releases/download/v0.6.0/dwork-tray-0.2.2-windows-x64.zip),
covered by the release
[SHA256SUMS](https://github.com/hayyaun/dwork/releases/download/v0.6.0/SHA256SUMS).
The **Portable Windows tray** CI workflow also produces `release-assets-windows`
with a ZIP and `SHA256SUMS.windows`; verified ZIPs join draft releases. The extracted
`dwork-tray` folder contains `dwork-tray.exe`, `dwork-tray-terminal.exe`, and shared
`_internal` files. It may remain inside Linux and execute through its Windows UNC
path, such as `\\wsl.localhost\Ubuntu\home\YOU\...`.

#### Set up the portable app

1. In the chosen WSL distribution, select a Python environment with `dwork-cli`
   0.5.x installed. From your Linux home directory, check that it works independently
   of a source checkout:

   ```sh
   cd ~
   /home/YOU/dwork-env/bin/python -m dwork --version
   /home/YOU/dwork-env/bin/python -m dwork list --json
   ```

   Replace the interpreter path with your environment's absolute Linux path.
   `install.sh` / `make install` launch a private runtime directly; their Python
   environment alone does not install the importable `dwork` module needed by this
   bridge. If needed, download and verify the CLI wheel from the same release,
   then install it in a separate **Linux** environment:

   ```sh
   python3 -m venv "$HOME/dwork-env"
   "$HOME/dwork-env/bin/python" -m pip install /path/to/dwork_cli-0.6.0-py3-none-any.whl
   ```

   An existing pipx/uv or editable development environment is also suitable when
   the two checks above pass. Registrations are shared through the chosen Linux
   user's state directory; installing another CLI environment does not register
   or activate workspaces.

2. Download the portable ZIP and `SHA256SUMS` linked above. Compare the ZIP's
   SHA-256 with its entry in the manifest before extracting it. For example,
   PowerShell provides `Get-FileHash .\dwork-tray-0.2.2-windows-x64.zip -Algorithm SHA256`;
   Linux provides `sha256sum dwork-tray-0.2.2-windows-x64.zip`.
   Extract the **complete** `dwork-tray` folder to a stable location. Keep the
   sibling helper and `_internal` directory together with the EXE.

3. Start the selected distribution deliberately and confirm Windows Terminal and
   Windows PowerShell are available. From PowerShell in the extracted folder, run:

   ```powershell
   .\dwork-tray.exe --wsl-distribution Ubuntu --wsl-python /home/YOU/dwork-env/bin/python --wsl-user YOU --check
   .\dwork-tray.exe --wsl-distribution Ubuntu --wsl-python /home/YOU/dwork-env/bin/python --wsl-user YOU
   ```

   Substitute your distribution, interpreter, and Linux user. For a folder kept
   in Linux, PowerShell can invoke the full UNC path from any directory:

   ```powershell
   & '\\wsl.localhost\Ubuntu\home\YOU\apps\dwork-tray\dwork-tray.exe' --wsl-distribution Ubuntu --wsl-python /home/YOU/dwork-env/bin/python --wsl-user YOU
   ```

`--check` reads status without opening the tray or activating a workspace. On an
ordinary launch, look in the Windows notification area, including its **Show hidden
icons** (`^`) overflow menu. Opening the tray menu lists registered workspaces;
**Quit tray** removes only the tray icon.

#### Start it again without remembering the arguments

Use the same launch command after **Quit tray** or a Windows restart; this version
saves no selection preferences. You can create an ordinary **desktop shortcut**
whose target is the quoted EXE path followed by the same WSL arguments:

```text
"\\wsl.localhost\Ubuntu\home\YOU\apps\dwork-tray\dwork-tray.exe" --wsl-distribution Ubuntu --wsl-python "/home/YOU/dwork-env/bin/python" --wsl-user YOU
```

Set the shortcut's **Start in** to the extracted app folder. Double-click it when
wanted. A desktop shortcut does not enable login startup; [sign-in startup](#windowswsl-start-at-sign-in-with-a-shortcut)
is a separate opt-in choice. The extracted app may stay in Linux; a shortcut only
points to it. Quit the previous instance before launching another copy or updating.
For an update, extract the new complete ZIP into a new folder, run `--check`, then
update your launch command or shortcut target. Keep the old folder until the new
copy works; a source-code update does not replace an extracted app.

The ZIP is unsigned and includes its source revision, checksum, and dependency
notices. The CLI and workspace execution remain inside WSL. A Linux tray inside
WSL/WSLg remains unsupported; native Windows workspace management is not added.

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

## Tray icon

The shared icon is a separate PNG at
[`companion/src/dwork_tray/assets/tray.png`](../../companion/src/dwork_tray/assets/tray.png).
The editable [SVG source](../../companion/src/dwork_tray/assets/tray.svg) defines
the two perspective window frames; the runtime reads the exported PNG only.
Replace the PNG with your artwork using the same filename. A square PNG with
transparent background and bold, simple shapes reads best at small tray sizes.
The included artwork is a 256-pixel light outline for dark tray backgrounds.
Pillow loads it as RGBA; no drawing-code changes are needed. The icon is loaded
relative to the companion package, independent of the working directory.

Restart the tray after replacing the image. Editable/source installs use this
file directly; rebuild and reinstall a wheel to distribute repository changes.
The portable Windows ZIP includes the image at
`_internal/dwork_tray/assets/tray.png` inside the extracted app folder. You can
also replace that extracted PNG and restart without rebuilding. Changing the
repository file does not update previously extracted or installed copies.
Missing or unreadable images report their path and stop tray startup.

If the icon still looks old, check the executable's extracted folder and
`build-info.json` revision. Source changes do not update a frozen Windows EXE.
Older portable builds draw their icon in code and need a new complete ZIP;
copying a PNG beside those EXEs has no effect. Quit the old tray and launch the
updated extracted app. Builds with the file loader support replacing their
`_internal/dwork_tray/assets/tray.png` and restarting.

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

Startup means the user's graphical login, not a boot-time system service.
Installing through `install.sh`, `make`, or pip never enables it.

### Native Linux/macOS: one command or menu checkbox

After installing the companion, run as your normal user without sudo:

```sh
dwork-tray --autostart enable   # Enable for the next graphical login
dwork-tray --autostart status   # Prints enabled or disabled
```

Or launch `dwork-tray` manually and select **Start at login** in its menu.
To disable startup, uncheck that item or run:

```sh
dwork-tray --autostart disable
```

The commands work without opening an icon. They do not start the tray now; launch
`dwork-tray` manually if desired. Disabling affects future logins and does not stop
an existing tray. For the default managed install, the command is
`~/.local/bin/dwork-tray`; custom prefixes use `PREFIX/bin/dwork-tray`.
Startup entries use the installed companion interpreter, so removal of the curl
installer's temporary clone does not break them.

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
Quit does not disable an opted-in next-login start. Updates at the same prefix
retain the entry. Disable startup with the current installation before moving its
interpreter or uninstalling if you want the entry removed; uninstall deliberately
leaves user login-startup settings untouched.

### Windows/WSL: start at sign-in with a shortcut

The Windows companion does not manage login entries: it omits the menu checkbox
and refuses `--autostart` without writing settings. Windows can independently run
the portable app at sign-in using a shortcut in the current user's Startup folder.
This is an optional manual Windows setting; `install.sh` in WSL does not create it.

1. Keep the complete extracted `dwork-tray` folder in a stable location and check
   that your normal manual launch works with the selected WSL arguments.
2. Press **Win+R**, enter `shell:startup`, and press Enter. This opens your own
   Startup folder; no administrator access or all-users folder is needed.
3. Choose **New → Shortcut**. Use your actual executable path, distribution,
   Linux interpreter, and optional Linux user. For example, a Linux-hosted app:

   ```text
   "\\wsl.localhost\Ubuntu\home\YOU\apps\dwork-tray\dwork-tray.exe" --wsl-distribution Ubuntu --wsl-python "/home/YOU/dwork-env/bin/python" --wsl-user YOU
   ```

4. Name it **dwork tray**. In shortcut **Properties**, set **Start in** to the
   extracted app folder (the same path without `dwork-tray.exe` or arguments).
   Use an ordinary shortcut target, without PowerShell's `&` prefix.
5. The shortcut runs at your next Windows sign-in. Delete only this shortcut from
   `shell:startup` to disable it. Quit tray closes the current instance but leaves
   the shortcut in place. Update its target if you move the app or change WSL paths.

A Windows-hosted extracted app folder can be used instead; its target is the full
Windows path to `dwork-tray.exe` with the same WSL arguments. The tray's running-state
checks still apply: if the selected distribution is unavailable, start it deliberately
and choose **Refresh**. Launch order at sign-in is not guaranteed. Accessing an EXE
through `\\wsl.localhost` can itself auto-start the distribution serving that path
on Windows 11, before the tray performs its checks. Account for that when choosing
where the shortcut points; it is separate from tray polling or workspace activation.

This uses [Windows' supported Startup-folder mechanism](https://support.microsoft.com/en-US/Windows/Experience/Startup-Boot/configure-startup-applications-in-windows)
and ordinary [Shell Links](https://learn.microsoft.com/en-us/windows/win32/shell/links).
Microsoft documents [WSL UNC access and automatic distribution startup](https://learn.microsoft.com/en-us/windows/dev-environment/wsl-interop).

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
