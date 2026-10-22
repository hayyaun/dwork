# Portable Windows tray

The optional ZIP includes the tray, terminal helper, Python runtime, libraries,
resources, notices, and source revision. It connects to the CLI in WSL and needs
no separately installed Windows Python. [Usage](../../docs/companion/README.md).

The `Portable Windows tray` workflow builds on Windows CI with Python 3.13 x64 and
PyInstaller 6.22.3. The documented multi-program spec collects two console-capable
entry points and shared runtime files. The tray hides only its own console; the
terminal helper inherits a terminal for the existing CLI confirmations. Frozen
handoff selects the sibling executable instead of an external Python interpreter.
The observer source is explicit bundle data; the standard pystray hook collects
its dynamic backends. External launches use PyInstaller's documented DLL-search
and child-environment handling, restoring process settings afterward.

CI tests the extracted ZIP with no external Python on child PATH. Harmless
self-contained WSL/Terminal fixtures exercise frozen status/resources, real
PowerShell quoting, helper dispatch, declined confirmation input, nonzero CLI
exit, and completion markers. These fixture checks do not verify real WSL or
visible desktop behavior. Successful builds upload `release-assets-windows`
(ZIP and `SHA256SUMS.windows`); draft releases reuse the verified assets.
