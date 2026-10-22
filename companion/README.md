# dwork-tray

Optional, experimental native Linux/macOS and Windows-to-WSL tray companion.
This is a separate Python distribution; ordinary `dwork-cli` installs stay GUI-free.

From a checkout on native Linux/macOS, `make install TRAY=1` optionally includes
this separate package with the managed CLI install. It creates a separate companion
environment and launcher; it never launches the tray or enables login startup.
See [installation options and prerequisites](../docs/installation/README.md#optional-native-tray).

From the repository root, native Linux/macOS users install matching development
sources in a platform-appropriate virtual environment:

```sh
python -m pip install -e . -e ./companion
dwork-tray --check
dwork-tray
```

Linux needs PyGObject and AppIndicator/Ayatana introspection plus a compatible tray
host; GNOME may need indicator extension support. macOS needs Python 3.13+ and Cocoa.

An optional portable Windows ZIP includes the tray, terminal helper, and runtime.
It connects to the existing CLI in WSL; no separate Windows Python setup is needed.
From the extracted folder in PowerShell:

```powershell
.\dwork-tray.exe --wsl-distribution Ubuntu --wsl-python /home/YOU/dwork-env/bin/python
```

The folder may remain in Linux and run through its WSL UNC path. Windows Terminal
and Windows PowerShell provide the interactive operation window. See the guide for
selection options and verification limits.

The shared tray icon is [`src/dwork_tray/assets/tray.png`](src/dwork_tray/assets/tray.png).
Its sibling `tray.svg` is the editable design source.
Replace the PNG and restart for editable installs; see the
[icon guide](../docs/companion/README.md#tray-icon) for packaged copies.

The companion never answers CLI confirmations or owns workspace shutdown.
Linux/macOS login startup is disabled until explicitly enabled: use
`dwork-tray --autostart enable` or the **Start at login** menu checkbox. Check with
`--autostart status` and undo with `--autostart disable`; changes apply at the next
login and never launch or stop the current tray. Windows has an optional manual
Startup-folder shortcut instead; see the [startup guide](../docs/companion/README.md#startup-at-login-is-opt-in).
Quit closes only the tray. See [the companion guide](../docs/companion/README.md) for full setup,
timeout/running-state limits, login ownership, and UI verification requirements,
and the [JSON contract](../docs/json/README.md) for protocol details.
