# dwork-tray

Optional, experimental native Linux/macOS tray companion. This is a separate Python
distribution; the ordinary `dwork-cli` installation stays GUI-free.

From the repository root, use matching development sources in a platform-appropriate
virtual environment:

```sh
python -m pip install -e . -e ./companion
dwork-tray --check
dwork-tray
```

Linux needs PyGObject and AppIndicator/Ayatana introspection plus a compatible tray
host; GNOME may need indicator extension support. macOS needs Python 3.13+ and Cocoa.
Windows-host/WSL transport is planned separately; native Windows workspaces are not
supported. The companion never answers CLI confirmations or owns workspace shutdown.
Startup at login is disabled until explicitly enabled. Quit closes only the tray.

See [the companion guide](../docs/companion/README.md) for platform prerequisites,
login-entry ownership, UI verification limits, and the [JSON contract](../docs/json/README.md).
