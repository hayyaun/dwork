<div align="center">

<img src="docs/assets/readme-hero.png" alt="dwork — switch your development workspace with one command" width="100%">

<p><strong>Your project. Its containers. Your terminals. One command.</strong></p>

<p>
  <a href="docs/installation/README.md"><img alt="Linux, macOS, and WSL2" src="https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20WSL2-3fb950?style=flat-square"></a>
  <a href="#install"><img alt="Install with curl" src="https://img.shields.io/badge/install-curl-3fb950?style=flat-square"></a>
  <a href="https://github.com/hayyaun/dwork/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/hayyaun/dwork?style=flat-square"></a>
</p>

<a href="#get-started">Get started</a> ·
<a href="examples/README.md">Examples</a> ·
<a href="docs/README.md">Documentation</a>

</div>

`dwork` switches your development workspace. It resumes a project's existing
containers, waits for healthy dependencies, and opens your commands and browser URLs.
Switches stop eligible registered workspaces; locked workspaces and unregistered
projects stay running. Use `dwork scan` to find and remember existing projects;
see [getting started](#get-started).

## Install

```sh
sh -c "$(curl -fsSL https://raw.githubusercontent.com/hayyaun/dwork/main/install.sh)"
```

Installs the latest `main` source for your user with isolated Python dependencies.
No `sudo` or shell sourcing required. If needed, the installer prints how to add
`~/.local/bin` to `PATH`.

You need Git, Make, curl, and Python with `venv` support: Python 3.10+ on Linux/WSL2,
or 3.13+ on macOS. Container workspaces also need Docker and Docker Compose;
terminal tasks need a [supported terminal](docs/terminals/README.md).

[Inspect the installer](install.sh) ·
[Install from a checkout, update, or uninstall](docs/installation/README.md) ·
[v0.5.0 release packages](https://github.com/hayyaun/dwork/releases/tag/v0.5.0) ·
[Releases and package checks](docs/publishing/README.md)

### Optional tray companion

View saved workspaces and switch between them from your desktop tray. To include
the separate tray package on **native Linux or macOS**:

```sh
TRAY=1 sh -c "$(curl -fsSL https://raw.githubusercontent.com/hayyaun/dwork/main/install.sh)"
```

[Tray prerequisites and manual launch](docs/installation/README.md#optional-native-tray).
Installation never launches the tray or enables login startup. After installing,
native Linux/macOS users can optionally enable it for their next graphical login:

```sh
dwork-tray --autostart enable
```

[Check or disable login startup](docs/companion/README.md#startup-at-login-is-opt-in).
An optional [portable Windows tray for WSL2](docs/companion/README.md#set-up-the-portable-app)
is available as a [ZIP in v0.5.0](https://github.com/hayyaun/dwork/releases/download/v0.5.0/dwork-tray-0.2.1-windows-x64.zip),
with no separate Windows Python installation;
[Windows sign-in startup uses an optional shortcut](docs/companion/README.md#windowswsl-start-at-sign-in-with-a-shortcut).

## Get started

Find existing projects from their parent directory:

```sh
cd ~/projects
dwork scan         # Remember dwork.yml workspaces; optionally select Compose projects
dwork list         # See the saved names
dwork switch my-app
```

Scanning registers projects without starting or stopping workloads. CLI 0.5.0+
also accepts `dwork scan .` or several roots, such as
`dwork scan ~/projects ~/work/client-projects`.
[Scanning rules and previews](docs/workspaces/README.md#scan-a-directory-tree).

To configure an individual project:

```sh
cd your-project
dwork init        # Create a starter dwork.yml without overwriting existing files
# Add your commands and browser URLs to dwork.yml
dwork validate    # Check the configuration
dwork --dry-run   # Preview the switch
dwork            # Confirm registration and activate this workspace
```

Already have a Compose project? You can run `dwork` without a `dwork.yml`.
It shows the plan and asks before switching. Terminal tasks and browser entries
have separate confirmations.

> dwork starts existing containers. It never creates, rebuilds, or removes them.
> Complete your project's initial setup and migrations first.

Remember a project and return to it from anywhere:

```sh
dwork register my-app  # Save this directory without switching
dwork list             # See remembered workspaces
dwork switch my-app    # Activate one from any directory
dwork lock my-app      # Keep it running through switches and shutdowns
dwork unlock my-app    # Release the temporary lock
dwork down             # Stop eligible registered workspaces and tracked commands
```

CLI 0.5.0+ also accepts explicit workspace names:

```sh
dwork up my-app docs    # Start these saved workspaces, keeping all others running
dwork down my-app       # Stop only this workspace's eligible workloads
```

Without names, `up` still switches to the current directory and `down` still stops
all eligible registered workloads. Existing confirmations, locks, and ownership
checks apply. Published v0.4.1 packages retain their earlier syntax.

### Reusable named groups (unreleased)

Current source after v0.5.0 can save a personal group of existing registered
workspaces, including projects in different directories:

```sh
dwork group create daily my-app docs
dwork up --group daily                 # Start members, keeping other workspaces running
dwork switch --group daily --dry-run   # Preview one switch to the whole group
```

`down --group daily` stops only eligible member workloads. A group switch protects
all selected members from its outgoing shutdown. Published v0.5.0 packages do not
include these group commands; see [group management and safeguards](docs/workspaces/README.md#reusable-named-groups).

[All commands](docs/usage/README.md) ·
[Workspace names, scanning, and locks](docs/workspaces/README.md)

## Describe your workspace

For a backend with a database, put this `dwork.yml` beside your Compose file:

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

**Start the database → wait for healthy → open the backend → open its URL when ready.**
Missing containers or failed health checks block dependent tasks.

[Copy a full-stack, Compose-only, or host-only example](examples/README.md) ·
[Configuration reference](docs/configuration/README.md)

## Let your coding agent set it up

Install the optional agent skill with Node.js 22.20+:

```sh
npx skills add hayyaun/dwork --skill dwork -g
```

Then ask your agent: **"Use the dwork skill to create dwork.yml for this project."**
The skill inspects your existing commands and Compose services.
[Agent setup and usage](docs/skills/README.md)

## Explore more

- [Bash and Zsh completion, including macOS Bash 3.2](docs/completion/README.md)
- [Terminal options and background tasks](docs/terminals/README.md)
- [Browser selection and readiness checks](docs/browsers/README.md)
- [Optional tray companion](docs/companion/README.md), including a portable Windows app for WSL and a [replaceable icon](docs/companion/README.md#tray-icon)
- [Development, tests, and package build prerequisites](docs/development/README.md)
- [All documentation](docs/README.md)
