# dwork-tray

Optional, experimental native Linux/macOS and Windows-to-WSL tray companion.
This is a separate Python distribution; ordinary `dwork-cli` installs stay GUI-free.

From the repository root, native Linux/macOS users install matching development
sources in a platform-appropriate virtual environment:

```sh
python -m pip install -e . -e ./companion
dwork-tray --check
dwork-tray
```

Linux needs PyGObject and AppIndicator/Ayatana introspection plus a compatible tray
host; GNOME may need indicator extension support. macOS needs Python 3.13+ and Cocoa.

On Windows, install only `./companion` in a Windows Python 3.10+ venv; the core CLI
must be installed in the chosen WSL interpreter, not on Windows. From PowerShell:

```powershell
# Substitute your Windows venv interpreter and matching Linux CLI interpreter.
& .\tray-venv\Scripts\python.exe -m pip install ./companion
& .\tray-venv\Scripts\python.exe -m dwork_tray --wsl-distribution Ubuntu --wsl-python /home/YOU/dwork-env/bin/python --check
& .\tray-venv\Scripts\python.exe -m dwork_tray --wsl-distribution Ubuntu --wsl-python /home/YOU/dwork-env/bin/python
```

Windows also needs `wsl.exe`, `wt.exe`, and Windows PowerShell. Start the selected
distribution yourself before launching/checking; polling does not deliberately
start stopped distributions. `--wsl-user` selects a Linux user explicitly; omission
uses that distribution's default user. Native Windows workspace execution and
Windows login startup are outside this version.

The companion never answers CLI confirmations or owns workspace shutdown.
Linux/macOS login startup is disabled until explicitly enabled. Quit closes only
the tray. See [the companion guide](../docs/companion/README.md) for full setup,
timeout/running-state limits, login ownership, and UI verification requirements,
and the [JSON contract](../docs/json/README.md) for protocol details.
