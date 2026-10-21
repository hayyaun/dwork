# Browser launching

[Configuration](../configuration/README.md#browsers) · [Project home](../../README.md)

Use `browsers` in `dwork.yml` to open a page when a development application is
ready. The application may already be running, be resumed through Compose, or
be started by an explicitly configured terminal task.

```yaml
version: 1
compose:
  enabled: false
terminals:
  - title: Frontend
    command: [npm, run, dev]
browsers:
  - url: http://localhost:3000
    wait_for:
      url: http://localhost:3000/health
      timeout: 60
```

Each terminal and browser entry asks for confirmation separately. Omit
`wait_for.url` to probe the page being opened. Set `wait_for: false` to skip
readiness. Set `confirm: false` on an entry to explicitly disable its prompt.
Preview with `dwork --dry-run`; check opener prerequisites with `dwork doctor`.

On **macOS**, URLs open through `/usr/bin/open` in the default browser.
On **Linux**, URLs use `xdg-open` from `xdg-utils`, inside a graphical desktop
session. On **WSL**, URLs use the **Windows** default browser through
`powershell.exe`. Linux browsers are never selected as a WSL fallback.

## Select a browser or open immediately

Set `browser` per entry to override the default. On Linux use a browser executable
on `PATH` or an absolute executable path. On macOS use the app name or `.app`
path, dispatched through the supported `open -a` interface. On WSL use a Windows
`.exe` name that Windows can resolve, or a full Windows executable path; Linux
paths such as `/usr/bin/firefox` or `/mnt/c/...` are rejected. Examples:

```yaml
# Linux: browser: firefox
# macOS: browser: Firefox
# WSL: browser: 'C:\Program Files\Mozilla Firefox\firefox.exe'
browsers:
  - url: http://localhost:3000
    browser: default
    wait_for: false
    confirm: false
```

`browser: default` is also the behavior when the field is omitted. Supply one
installed browser application/executable, without extra flags or a shell command.
Linux launches the selected executable with the URL as one argument. WSL passes
the chosen Windows executable and quoted URL through PowerShell `Start-Process`.
No alternate/default browser is tried when an explicit selection fails.

`wait_for: false` skips all HTTP requests; `confirm: false` skips this browser's
prompt. They work independently and can be combined with a custom browser.
Terminal tasks also support `confirm: false`. Workspace/group/registration
confirmations are separate. The bundled skill emits `wait_for: false` in new
browser entries by default unless the user asks for readiness waiting.

Windows normally reaches services running in WSL at `localhost`; dwork keeps
your configured URL unchanged. Readiness is checked from the WSL distribution,
so it does not independently verify Windows firewall, localhost forwarding,
or browser-specific networking. If the page opens but cannot connect, check
[WSL networking](https://learn.microsoft.com/windows/wsl/networking#accessing-linux-networking-apps-from-windows-localhost).
An application on the Windows host may need a different probe URL from WSL;
configure `wait_for.url` explicitly rather than changing global networking.

Readiness accepts HTTP 200–399, including redirects without following them.
Requests are direct GETs with no body download, no environment proxies, and
normal HTTPS certificate checks. The timeout limits retries with short socket
timeouts; DNS resolution is controlled by the operating system. Poll only
endpoints where GET is safe. No server is started by the readiness check.

The selected browser controls tab/window reuse. Opening a URL does not make
dwork the owner of the browser, and `dwork down` leaves its windows open.
Opener success means dispatch, not proof that a GUI page rendered. Automated
tests use fake launchers and HTTP clients; a real desktop remains a manual check.

Supported interfaces:

- [xdg-open](https://portland.freedesktop.org/doc/xdg-open.html)
- [PowerShell Start-Process](https://learn.microsoft.com/powershell/module/microsoft.powershell.management/start-process)
- [macOS application launching](https://support.apple.com/guide/terminal/execute-commands-and-run-tools-apdb66b5242-0d18-49fc-9c47-a2498b7c91d5/mac)
- [Firefox URL arguments](https://firefox-source-docs.mozilla.org/browser/CommandLineParameters.html)
- [Windows tools from WSL](https://learn.microsoft.com/windows/wsl/filesystems#run-windows-tools-from-linux)
- [Python HTTP client](https://docs.python.org/3/library/http.client.html)
- macOS `man open` (installed system manual)
