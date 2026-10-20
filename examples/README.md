# dwork.yml examples

[Project home](../README.md) · [Configuration reference](../docs/configuration/README.md)

Choose an example, copy it into your project as `dwork.yml`, and adapt service
names, paths, and commands. These are examples of existing dwork features.

```sh
cp "$HOME/projects/foss/dwork/examples/backend-with-db.yml" ./dwork.yml
dwork --dry-run
```

Run `dwork` only when the preview matches what you want. It never creates missing
containers. Complete your normal project setup first.

## 1. Compose containers only

[Copy compose-only.yml](compose-only.yml)

```yaml
version: 1
compose:
  enabled: true
  services: [postgres, redis]
```

Starts existing stopped `postgres` and `redis` containers for this project, stops
other projects unless excluded, and opens no terminals. Your existing Compose
file supplies the service definitions. Omit `services` to manage all existing
current-project containers.

If you want the default Compose switching behavior, you can also skip `dwork.yml`
entirely.

## 2. Wait for a database, then run the backend

[Copy backend-with-db.yml](backend-with-db.yml)

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

Use this when the Compose file and backend Makefile live in the same directory.
dwork starts the existing PostgreSQL container if stopped, waits for its Docker
health check, then opens `make run` in a new terminal window.

If the database container is missing or cannot become healthy, the backend
terminal does not open. Create the container and apply migrations manually.

## 3. Backend and frontend in separate directories

[Copy full-stack.yml](full-stack.yml)

Expected layout:

```text
my-app/
  dwork.yml
  compose.yaml
  backend/Makefile
  frontend/package.json
```

The config launches `make run` in `backend/` and `npm run dev` in `frontend/`,
each in a new terminal window. Paths are relative to `dwork.yml`.

The backend has a PostgreSQL health prerequisite. All health gates pass before
any terminal is launched, so the frontend opens after that prerequisite as well.

Change `window: new` to `window: current` to open tabs in the most recently used
terminal window instead, using the selected emulator's rules (xterm has no tabs).

## 4. Frontend without Docker

[Copy host-only.yml](host-only.yml)

```yaml
version: 1
compose:
  enabled: false
terminals:
  - title: Frontend
    command: [npm, run, dev]
    window: current
```

Opens a terminal tab running `npm run dev` in the config directory. Compose is
not read, and Docker containers are not inspected, stopped, or started.

## Multiple Compose files

Add `files` when your project needs an override:

```yaml
version: 1
compose:
  enabled: true
  files: [compose.yaml, compose.dev.yaml]
  services: [postgres]
```

The file list is relative to `dwork.yml`. Explicit Compose file CLI arguments or
`COMPOSE_FILE` take precedence over the configured list.

## Independent child workspaces

You can instead put a `dwork.yml` in each immediate child directory:

```text
my-app/
  backend/
    dwork.yml
    compose.yaml
  frontend/
    dwork.yml
    package.json
```

When no default dwork/Compose config exists in `my-app/` or its parents, running
`dwork` there discovers both immediate children. It lists the projects and asks
`(y/N)` before switching them together. It does not search deeper directories.

Use the backend example in `backend/` and the host-only example in `frontend/`.

## Keep shared infrastructure running

Shared-project exclusions are an environment setting:

```sh
export DWORK_KEEP_PROJECTS=infra,monitoring
```

Use exact Compose project names. See the [usage guide](../docs/usage/README.md).

## Before using terminal tasks

Terminal tasks need PyYAML and either a supported Linux graphical terminal or
WSL2 + Windows Terminal. See [launcher selection](../docs/terminals/README.md).
Commands are
argument lists, not shell snippets. Put pipelines in a script and invoke that
script. Every `dwork` invocation opens the configured commands again; it does not
detect or close an already-running backend/frontend.

Use your own project's service names and scripts. The example dependencies are
not installed or created by dwork.
