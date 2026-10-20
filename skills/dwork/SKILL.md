---
name: dwork
description: Create, review, or update dwork.yml for a project's development workspace. Use when the user asks to configure dwork, connect existing Compose services with host terminal commands, or troubleshoot a dwork configuration.
---

# Configure a dwork workspace

Help the user configure **their project**, not the dwork source repository.
dwork resumes existing Compose containers, stops other registered workspaces on
the same Docker target unless excluded, checks health prerequisites, and opens
host commands in terminals. Unregistered projects stay running.
It never creates, rebuilds, recreates, or removes containers.

## Discover the project's setup

Read [the bundled configuration reference](references/configuration.md) before
writing YAML. It includes the supported version, fields, and examples and works
without a dwork source checkout or network access.

Inspect the target project's instructions, development README, Compose files and
overrides, package scripts, Make targets, and relevant startup scripts. Check for
an existing `dwork.yml` in the target directory and its parents: the nearest one
is selected, and files are not merged. Preserve existing choices and comments
when updating it. In a monorepo, identify the intended workspace and existing
working directories before choosing where to put the file.

Use the project's documented development commands and actual Compose **service
names**, not container names. Determine which services run in containers and
which commands run on the host; avoid launching a second copy of an application
already running in Compose. Ask a focused question if multiple development modes
are plausible or commands/dependency requirements cannot be established. Do not
invent service names, commands, health checks, or folders.

## Write the configuration

- Use `version: 1` and only supported fields. Create `dwork.yml` in the intended
  workspace directory, usually beside its Compose file.
- Use top-level `locked: true` when the user wants the workspace kept running
  through switches and `dwork down`. It remains listed and can still be activated.
- For host-only work, set `compose.enabled: false` and omit Compose files,
  services, and health prerequisites. With Compose enabled, omit `files` when
  normal Compose discovery suffices; otherwise preserve the project's file order.
- Limit `compose.services` only when the user's workflow calls for a subset.
  A service filter does not prevent other registered workspaces from being stopped.
- Represent each terminal command as an executable/argument list and set `cwd`
  relative to `dwork.yml` when needed. Prefer existing scripts for compound shell
  commands; explain any additional script needed before creating it.
- Add `wait_for.healthy` only for required services with configured Docker health
  checks. Include them in `compose.services` if a service filter is present.
  A startup dependency alone does not prove a service has a health check.
- Keep the default per-terminal confirmation. Set `confirm: false` only when the
  user explicitly requests it. Prefer portable `launcher: auto` and `window: new`
  defaults unless the user requests a particular terminal setup.

Configure only what the user requested. Generating YAML does not authorize
installing dependencies, creating containers, changing Compose health checks,
starting development servers, or switching the live workspace.

## Verify and hand off

Check the YAML against the reference, command definitions, existing directories,
Compose service names, and health checks. If dwork is available, run
`dwork --dry-run` **from the directory containing the generated file**. This
previews operations without switching containers, waiting, prompting, or opening
terminals. Compose-enabled previews still need Docker/Compose and access to the
Docker daemon. Host-only previews do not need Docker.

Inspect warnings as well as the exit status: a successful dry run can still warn
about missing containers or blocked terminal launches. If dwork or a dependency
is unavailable, report what was checked statically and what remains unverified;
do not install anything or claim runtime validation. If the installed dwork
rejects a field, check its version/docs rather than bypassing validation.

Explain the chosen commands, services, prerequisites, and verification result.
Tell the user that a normal `dwork` invocation asks before registering a new
directory and can stop other registered workspaces before terminal confirmation;
`DWORK_KEEP_PROJECTS` can preserve registered shared projects. `dwork register NAME`
remembers without activating, `dwork list` shows remembered directories,
`dwork switch NAME` activates from anywhere, and `dwork forget NAME` removes only
the registration. Changed Compose identity or service selection requires explicit
re-registration. Generating config does not authorize changing the user's registry.
Leave running `dwork` to the user unless they explicitly ask you to switch.
