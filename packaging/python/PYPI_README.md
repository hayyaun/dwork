# dwork

Switch development workspaces on Linux and WSL2: resume existing Compose
containers, stop other registered workspaces, wait for healthy dependencies, and confirm
before opening configured development terminals.

The Python distribution is **dwork-cli**. The installed command is **dwork**.
This project is unrelated to the separate PyPI distribution named dwork.

## Install from source today

```sh
pipx install git+https://github.com/hayyaun/dwork.git
# or
uv tool install git+https://github.com/hayyaun/dwork.git
```

Registry installation will become available after dwork-cli is published to PyPI.
Python 3.10+ is required. Docker/Compose and graphical terminals are external
requirements when those features are used. Native Windows is not supported;
install inside WSL2 instead.

## Use

```sh
cd your-project
dwork --dry-run
dwork
```

The first run asks before remembering the workspace. Unregistered projects stay
running. To remember without activating and switch from anywhere:

```sh
dwork register my-app
dwork list
dwork switch my-app
dwork forget my-app
```

`forget` removes only the registration. See
[remembered workspaces](https://github.com/hayyaun/dwork/blob/main/docs/workspaces/README.md).

Without a dwork.yml file, dwork uses your Compose configuration. It only starts
containers that already exist: it never creates, rebuilds, or removes them.

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

Each terminal asks (y/N) unless the task explicitly sets confirm: false.

[Configuration and examples](https://github.com/hayyaun/dwork#describe-your-workspace)
· [Installation](https://github.com/hayyaun/dwork/blob/main/docs/installation/README.md)
· [MIT license](https://github.com/hayyaun/dwork/blob/main/LICENSE)
