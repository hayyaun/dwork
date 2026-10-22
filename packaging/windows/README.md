# Portable Windows tray

The optional ZIP includes the tray, terminal helper, Python runtime, libraries,
resources, notices, and source revision. It connects to the CLI in WSL and needs
no separately installed Windows Python. [Installation and connection check](../../docs/companion/README.md#set-up-the-portable-app)
and [manual launch shortcut](../../docs/companion/README.md#start-it-again-without-remembering-the-arguments)
are in the companion guide; installing or launching the ZIP does not enable startup.
[Release v0.6.0](https://github.com/hayyaun/dwork/releases/tag/v0.6.0) includes
[dwork-tray 0.2.2 for Windows x64](https://github.com/hayyaun/dwork/releases/download/v0.6.0/dwork-tray-0.2.2-windows-x64.zip),
covered by its [SHA256SUMS](https://github.com/hayyaun/dwork/releases/download/v0.6.0/SHA256SUMS).

The `Portable Windows tray` workflow builds on Windows CI with Python 3.13 x64 and
PyInstaller 6.22.3. The documented multi-program spec collects two console-capable
entry points and shared runtime files. The tray hides only its own console; the
terminal helper inherits a terminal for the existing CLI confirmations. Frozen
handoff selects the sibling executable instead of an external Python interpreter.
The observer source and `dwork_tray/assets/tray.png` are explicit bundle data; the standard pystray hook collects
its dynamic backends. External launches use PyInstaller's documented DLL-search
and child-environment handling, restoring process settings afterward.

The extracted icon is `_internal/dwork_tray/assets/tray.png`. Replacing that PNG
and restarting changes the tray image without rebuilding the app. To distribute
repository artwork changes, rebuild the ZIP. This changes the notification-area
image; the executable's Explorer icon is separate.

CI tests the extracted ZIP with no external Python on child PATH. Its `--check`
probe also loads the bundled PNG without displaying an icon. Harmless
self-contained WSL/Terminal fixtures exercise frozen status/resources, real
PowerShell quoting, helper dispatch, declined confirmation input, nonzero CLI
exit, and completion markers. These fixture checks do not verify real WSL or
visible desktop behavior. Successful builds upload `release-assets-windows`
(ZIP and `SHA256SUMS.windows`); draft releases reuse the verified assets.
