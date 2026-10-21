<div align="center">

<img src="docs/assets/readme-hero.png" alt="dwork — switch your development workspace with one command" width="100%">

<p><strong>Your project. Its containers. Your terminals. One command.</strong></p>

<p>
  <a href="docs/installation/README.md"><img alt="Linux, macOS, and WSL2" src="https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20WSL2-3fb950?style=flat-square"></a>
  <a href="docs/installation/README.md"><img alt="Python 3.10 or newer" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&amp;logo=python&amp;logoColor=white"></a>
  <a href="#install"><img alt="Install with make install" src="https://img.shields.io/badge/install-make%20install-3fb950?style=flat-square"></a>
  <a href="https://github.com/hayyaun/dwork/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/hayyaun/dwork?style=flat-square"></a>
</p>

<a href="examples/README.md">Examples</a> ·
<a href="docs/configuration/README.md">Configuration</a> ·
<a href="docs/terminals/README.md">Terminal support</a> ·
<a href="docs/README.md">All docs</a>

</div>

`dwork` switches your development workspace: resume this project's existing
containers, wait for healthy dependencies, and open your configured commands in
new terminals. Only other workspaces you have registered with dwork may be stopped.
Unregistered projects stay running.

[Version 0.3.0](https://github.com/hayyaun/dwork/releases/tag/v0.3.0) adds macOS support through Apple Terminal and browser launching
with custom browser selection, optional readiness checks, and confirmation controls.
See [release publishing and package formats](docs/publishing/README.md).

## Install

```sh
git clone https://github.com/hayyaun/dwork.git
cd dwork
make install
```

Installs a standalone `dwork` command for your user, with isolated Python
dependencies. No `sudo` or shell sourcing required. If needed, the installer prints
the line to add `~/.local/bin` to `PATH`.

[Python, Homebrew, and Debian packaging →](packaging/README.md)
Build/install instructions are available, including a Homebrew formula pinned to
0.3.0 for Linux, macOS, and WSL2. Registry and tap publication is pending.
Verified Python, Debian/Ubuntu, Fedora 44, and Arch packages with checksums are
available from the [0.3.0 release](https://github.com/hayyaun/dwork/releases/tag/v0.3.0).

<details>
<summary>Requirements and other installation options</summary>

- Python 3.10+ on Linux/WSL2, Python 3.13+ on macOS, Git, Make, and Python's `venv` support.
- Docker + Docker Compose when using containers.
- A supported graphical terminal for terminal tasks: GNOME Terminal, Konsole,
  Xfce Terminal, or xterm on Linux; Apple Terminal on macOS (new windows only);
  Windows Terminal + PowerShell on WSL2.

On Ubuntu, the installer prerequisites are `git make python3 python3-venv`.
[Custom prefixes, manual sourcing, migration, and uninstall →](docs/installation/README.md)

</details>

## Let your agent configure it

Install the optional dwork skill for your coding agents (Node.js 22.20+):

```sh
npx skills add hayyaun/dwork --skill dwork -g
```

Choose Codex, Claude Code, Cursor, or another supported agent, then open your
project and ask: **"Use the dwork skill to create dwork.yml for this project."**
The agent inspects your existing commands and Compose services and previews the
configuration when dwork is available. The skill is separate from `make install`.

[All-agent installation, manual setup, and usage →](docs/skills/README.md)

## Use it

Check the version, generate a starter, and validate it:

```sh
dwork --version
dwork init --dry-run  # Preview a minimal local dwork.yml
dwork init           # Create it without overwriting existing files
dwork validate       # Check configuration without switching
```

`init` enables Compose only when a standard Compose filename exists in the current
directory; otherwise it creates a host-only config. Commands and browser URLs start
empty. `validate` checks schema, working directories, and Compose references without
registering, inspecting containers, or opening applications. Compose-enabled validation
needs Docker Compose CLI, but not a running Docker daemon. Use `doctor` to check
runtime and desktop prerequisites. These helpers were added after release 0.3.0.

```sh
cd your-project
dwork --dry-run   # Preview the plan
dwork             # First run: confirm registration, then switch
```

No `dwork.yml`? Your existing Compose project is the default.
After the first registration, run `dwork` in that project to switch back to it.
It shows the plan and asks for confirmation before switching. Set root-level
`confirm: false` in `dwork.yml` to skip this activation prompt. Each configured
terminal and browser still uses its own confirmation setting.

Remember a project without switching, give it a name, and return from anywhere:

```sh
dwork register my-app       # Remember this directory; start/stop nothing
dwork scan                  # Find workspaces recursively; optionally select Compose directories
dwork list                  # Show remembered directories and status
dwork switch my-app         # Activate it from any directory
dwork switch my-app --dry-run
dwork rename my-app api      # Change its saved name to an available name
dwork down                  # Stop registered containers and dwork-launched commands
dwork forget my-app         # Forget it; leave containers and files alone
```

`scan` skips dependency, cache, and build directories such as `node_modules`,
`.venv`, and `dist`. It stops descending at repo markers such as `.git`, `dwork.yml`,
or `package.json`, then moves to the next project.
[Skip list and repo markers →](docs/workspaces/README.md#scan-a-directory-tree)

`switch` uses the saved directory and Compose options; your current shell stays
where it is. It shuts down other eligible registered workspaces before activating
the selected one. The selected workspace, including all members of a discovered
group, stays running. [Workspace registration and switching →](docs/workspaces/README.md)

Use `dwork down --dry-run` to preview shutdown. `down` respects
`DWORK_KEEP_PROJECTS` and locked workspaces, and keeps containers, networks, and volumes for next time.

Switching and `down` share shutdown rules: stop tracked commands first, then
registered containers in one Docker batch. `switch` excludes the selected workspace;
`down` excludes none. This shared lifecycle was added after release 0.3.0.
Tracked terminal commands stop while their windows stay open at a shell prompt.
Detached tasks (`window: none`) stop too. Commands started outside dwork or by
versions without task tracking are not tracked. [Task lifecycle details →](docs/terminals/README.md#tracked-commands-and-shutdown)

Keep a workspace running through every switch and `down` by adding this to its `dwork.yml`:

```yaml
locked: true
```

It still appears in `dwork list` and can be activated normally.

Short forms: `ls` = `list`, `sw` = `switch`, `reg` = `register`, `rm` = `forget`,
`ps` = `status`, and `up` activates the current workspace.

`dwork` and `dwork up` confirm the activation plan unless root-level
`confirm: false` opts out. First-time registration and discovered-group consent
remain separate. `dwork down` always confirms when there is work to stop.
Enter or `n` cancels; `--dry-run` previews without prompting.

## Tab completion

Native package builds and the Homebrew formula install completion files in the
standard shell directories. With Bash's `bash-completion` framework or Zsh's
`compinit` already configured, reopen your shell to discover them automatically.
This applies to builds containing the updated packaging; older release assets
may still need the manual setup below.

For manual sourcing, Python packages, or a prefix outside your shell's completion
search path, enable once in your shell startup file:

```sh
# Bash (~/.bashrc)
source <(dwork completion bash)

# Zsh (~/.zshrc, after compinit)
source <(dwork completion zsh)
```

Then use `dwork <Tab>` for commands and `dwork sw <Tab>` for registered workspaces.
[Setup and completion details →](docs/completion/README.md)

> [!NOTE]
> dwork starts existing containers. It never creates, rebuilds, or removes them.
> Complete your project's initial setup and migrations first.

## Describe your workspace

Put `dwork.yml` beside your Compose file:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/hayyaun/dwork/main/schemas/dwork.schema.json
version: 1
compose:
  enabled: true
  services: [postgres]

terminals:
  - title: Backend
    command: [make, run]
    wait_for:
      healthy: [postgres]
      timeout: 180

browsers:
  - url: http://localhost:3000
    wait_for:
      timeout: 60
```

**Start the database → wait for healthy → confirm → open the backend.**

Each terminal asks `(y/N)`. Set `confirm: false` on a task to explicitly skip its
prompt. Missing containers and failed health checks block dependent terminals.

Browser entries ask separately and open the default or selected browser. WSL
always uses a Windows browser. The server can already be running or be started
by a terminal task. Set `browser` to a Linux executable, macOS application name,
or Windows `.exe` name/path on WSL. Set `wait_for: false` to skip readiness and
`confirm: false` to skip that browser's prompt. Terminal tasks also accept
`confirm: false`. These options are independent:

```yaml
browsers:
  - url: http://localhost:3000
    browser: default
    wait_for: false
    confirm: false
```

The bundled agent skill writes browser entries without readiness waiting by
default, unless you explicitly request it. [Browser configuration →](docs/browsers/README.md)

Set `window: none` on a task to run it silently in the background without opening
a terminal. Confirmation still applies. [Detached tasks →](docs/terminals/README.md#detached-background-tasks)

`dwork.yml` can be personal workspace configuration. Consider adding `/dwork.yml`
to the project's `.gitignore` when its commands, ports, terminal choices, or lock
policy are specific to your setup. Keep it tracked when the team intentionally
shares that configuration; an ignore rule does not untrack an existing file.

[Copy an example →](examples/README.md) Backend, full-stack, Compose-only, or host-only.

`dwork init` and the shipped examples include an editor schema comment. With a
schema-capable YAML extension, it enables field/value completion, hover help,
and configuration diagnostics. Existing files can add the same comment.
[Editor setup, local/offline association, and validation limits →](docs/configuration/README.md#editor-autocomplete)

## A few useful controls

- Keep shared infrastructure running: `DWORK_KEEP_PROJECTS=infra,monitoring dwork`.
- Choose your Linux terminal: `DWORK_TERMINAL=konsole dwork`.
- Run from a monorepo root: immediate child workspaces are listed for confirmation.
- Names and status messages are colored in terminals; set `NO_COLOR=1` for plain text.

## More

[Install & uninstall](docs/installation/README.md) ·
[Usage](docs/usage/README.md) ·
[Configuration](docs/configuration/README.md) ·
[Terminal launchers](docs/terminals/README.md) ·
[Browser launching](docs/browsers/README.md) ·
[Development](docs/development/README.md) ·
[Publish packages](docs/publishing/README.md)

Linux, macOS, and WSL launchers have automated fake-launcher coverage; real desktop
GUI behavior has not been visually verified in the WSL development environment.
Routine macOS CI runs source/package tests on Python 3.13 and Homebrew verification
on Apple Silicon. Release tags and manual package verification also cover Python
3.14 and Intel Macs. [CI coverage →](docs/development/README.md#ci-coverage)
