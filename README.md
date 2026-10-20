<div align="center">

<img src="docs/assets/readme-hero.png" alt="dwork — switch your development workspace with one command" width="100%">

<p><strong>Your project. Its containers. Your terminals. One command.</strong></p>

<p>
  <a href="docs/installation/README.md"><img alt="Linux and WSL2" src="https://img.shields.io/badge/platform-Linux%20%7C%20WSL2-3fb950?style=flat-square"></a>
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
Build/install instructions are available; registry and tap publication is pending.

<details>
<summary>Requirements and other installation options</summary>

- Python 3.10+, Git, Make, and Python's `venv` support.
- Docker + Docker Compose when using containers.
- A supported graphical terminal for terminal tasks: GNOME Terminal, Konsole,
  Xfce Terminal, or xterm on Linux; Windows Terminal + PowerShell on WSL2.

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

```sh
cd your-project
dwork --dry-run   # Preview the plan
dwork             # First run: confirm registration, then switch
```

No `dwork.yml`? Your existing Compose project is the default.
After the first registration, run `dwork` in that project to switch back to it.
Each configured terminal still asks for confirmation.

Remember a project without switching, give it a name, and return from anywhere:

```sh
dwork register my-app       # Remember this directory; start/stop nothing
dwork list                  # Show remembered directories and status
dwork switch my-app         # Activate it from any directory
dwork switch my-app --dry-run
dwork down                  # Stop all registered workspace containers
dwork forget my-app         # Forget it; leave containers and files alone
```

`switch` uses the saved directory and Compose options; your current shell stays
where it is. [Workspace registration and switching →](docs/workspaces/README.md)

Use `dwork down --dry-run` to preview shutdown. `down` respects
`DWORK_KEEP_PROJECTS` and keeps containers, networks, and volumes for next time.

> [!NOTE]
> dwork starts existing containers. It never creates, rebuilds, or removes them.
> Complete your project's initial setup and migrations first.

## Describe your workspace

Put `dwork.yml` beside your Compose file:

```yaml
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
```

**Start the database → wait for healthy → confirm → open the backend.**

Each terminal asks `(y/N)`. Set `confirm: false` on a task to explicitly skip its
prompt. Missing containers and failed health checks block dependent terminals.

[Copy an example →](examples/README.md) Backend, full-stack, Compose-only, or host-only.

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
[Development](docs/development/README.md) ·
[Publish packages](docs/publishing/README.md)

Native Linux GUI launchers have automated fake-launcher coverage; real desktop
GUI behavior has not been visually verified in the WSL development environment.
