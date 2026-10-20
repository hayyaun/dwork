# dwork

**Switch your development workspace with one command.**

`dwork` is a Bash/Zsh function that stops other projects' Docker Compose containers
and resumes the existing containers for your current project. Add a `dwork.yml` to
choose services, wait for healthy dependencies, and open your development commands
in new terminals.

```sh
cd your-project
dwork --dry-run   # See the plan
dwork             # Switch the workspace
```

## What it does

- Uses Docker Compose by default; configuration is optional.
- Starts existing stopped containers and warns about containers you need to create.
- Keeps designated shared projects running.
- Reads `dwork.yml` to enable or disable Compose and select services.
- Opens configured commands in native Linux terminals or Windows Terminal after
  Docker health checks pass.
- Discovers immediate child workspaces and asks `(y/N)` before switching them together.

It never creates, rebuilds, or removes containers. Normal project setup and
migrations remain explicit steps.

## Install

Clone somewhere permanent:

```sh
git clone https://github.com/hayyaun/dwork.git "$HOME/projects/foss/dwork"
```

Add this line to `~/.bashrc` for Bash and/or `~/.zshrc` for Zsh:

```sh
[ -r "$HOME/projects/foss/dwork/dwork.sh" ] && . "$HOME/projects/foss/dwork/dwork.sh"
```

Load it in your current terminal:

```sh
. "$HOME/projects/foss/dwork/dwork.sh"
```

Adjust the path if you clone elsewhere. Keep `dwork.sh` and `lib/` together.
Sourcing defines the function; it does not start anything.

**Requirements:** Bash or Zsh and Python 3. Compose mode needs Docker and Docker
Compose. YAML configs additionally need PyYAML. Opening terminals supports
**native Linux desktops** (GNOME Terminal, Konsole, Xfce Terminal, or xterm) and
**WSL2 + Windows Terminal + Windows PowerShell**. Auto-selection and overrides are
covered in the [launcher guide](docs/terminals/README.md). GUI behavior on native
Linux is covered by fake-launcher tests; the development environment is WSL2.

## Example: database first, backend next

Place this `dwork.yml` beside your Compose file:

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

When you invoke `dwork`, it starts your existing PostgreSQL container if stopped,
waits for Docker to report it healthy, then opens `make run` in a new terminal
window in this directory.

The Compose service must be named `postgres` and have a health check. Create its
container and complete your project's setup first. Each invocation opens the
configured commands again; stop an already-running backend before launching another.

## Documentation

- [Installation](docs/installation/README.md): requirements, sourcing, updates, and removal.
- [Usage](docs/usage/README.md): switching, previews, shared services, and limits.
- [Configuration](docs/configuration/README.md): the complete `dwork.yml` format.
- [Terminal launchers](docs/terminals/README.md): Linux desktop selection, WSL,
  machine overrides, and window/tab support.
- [Examples](examples/README.md): Compose-only, backend, full-stack, and host-only workspaces.
- [Development](docs/development/README.md): source layout and tests.
- [Sharing dwork](docs/promotion/README.md): a short introduction you can adapt.

Start with `dwork --dry-run` or `dwork --help`.
