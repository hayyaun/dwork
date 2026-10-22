# Read-only JSON status interface

[Usage](../usage/README.md) · [Tray companion](../companion/README.md) · [Schema](../../schemas/status.schema.json)

```sh
dwork list --json
dwork status --json [Docker Compose global options]
```

`ls` and `ps` aliases work too. `list --names` and ordinary table/status output stay
unchanged. `--json` cannot be combined with `--names` or a status/list dry run. These
interfaces never prompt, register, acquire the operation lock, save policy, wait for
health/HTTP, start/stop workloads, or open applications.

A successful command emits exactly one JSON document on stdout. Diagnostics go to
stderr. Exit codes remain 0 (successful observation, including explicitly unavailable
Docker status), 1 (invalid configuration/registry, usage, or boundary failure), and
130 (interruption). On failure stdout need not contain JSON; inspect the exit code.

Version 1 has `schema_version: 1`, `scope` (`registered` or `current`), `docker`, and
`workspaces`. [The Draft-7 schema](../../schemas/status.schema.json) defines required
fields. Clients must ignore additive fields and display unknown status strings
without guessing lifecycle policy. Removing or changing required field meaning
requires a new schema version. The schema version is independent of package versions;
old published 0.3.0 builds do not contain this new interface.

- `list` reads saved registrations and current lock policy without changing ownership.
  Missing configs retain the cached lock, and unreadable lock policy protects members.
- `status` resolves the current workspace/group and Compose options without reading
  saved registrations. Its rows describe the current configuration, not a claim that
  the workspace is registered or authorized for shutdown.
- `docker.available` is `null` when no Compose target is needed, `true` when observed,
  and `false` when unavailable. `target` contains context/daemon identity or `null`;
  `error` contains the observation failure or `null`.
- Workspace rows contain name/path, directory availability, saved/resolved target,
  temporary protection, and members with enabled/service/lock/protection/keep policy.
  `protected` combines YAML and temporary locks; `kept` separately reflects
  `DWORK_KEEP_PROJECTS`. These flags confer no new ownership.
- Status strings currently include `host_only`, `containers`, `directory_unavailable`,
  `docker_unavailable`, and `different_target`. Container counts respect the current
  Docker target and registered service filters; running counts include restarting.
  `containers` is `null` when the target cannot be observed, otherwise an object with
  `running`/`total`. Unknown is distinct from zero.
- `tasks.running` counts matching workspace/member controller records. `unresolved`
  counts matching records whose controller could not be inspected. Forgotten or
  changed workspace/member identity is not counted as current ownership. No saved
  PID is signalled. Controller credentials, socket paths, command argv, saved Compose
  environment, and CLI options are not exported.

Status is a point-in-time observation, not a cached permission or application-ready
signal. The mutating CLI rechecks ownership, locks, and the existing confirmations
before executing the same operations as before. JSON adds no unattended mutation,
approval flag, retry/resume API, registry format, or configuration field.
