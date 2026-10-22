# dwork roadmap

## Milestone 1: visibility and confidence

- [x] Add read-only `dwork status`: workspace selection, Docker context, container states, health, and missing services.
- [x] Add read-only `dwork doctor`: configuration/Compose compatibility, Docker access, shell and terminal dependencies, with actionable fixes.
- [x] Show the Docker target, affected projects, protected projects, and full plan before every switch; preserve existing confirmation rules.
- [x] Report completed actions, the failed step, remaining work, and recovery commands after partial failures or interruption.
- [x] Introduce typed activation plans, explicit lifecycle actions, and execution results; share shutdown execution, derive recovery from action identity, preserve consent/ownership/lock behavior, and cover planning plus every action's failure/interruption outcomes.

- [x] Separate data-only configuration parsing from path/Compose resolution, registry persistence from pure ownership/protection policy, and launch preparation from dispatch; retain confirmation and live lock checks and cover the boundaries with regression tests.

- [x] Add pinned Ruff lint/format and gradual mypy checks in local/CI quality gates; verify the exact checkout through Homebrew alongside stable-release checks using one recipe template, checksum manifests, and offline archive regressions.

## Switching policies

- [x] Add persistent per-workspace protection with `locked: true`, respecting it during switches and shutdowns while retaining `DWORK_KEEP_PROJECTS`.
- [x] Add local temporary `dwork lock NAME...` / `unlock NAME...` protection until explicitly released; preserve YAML locks, support groups and previews, show it in `ls`, and complete names in Bash/Zsh.
- [x] Confirm plain workspace activation before applying its plan; use a root-level `confirm` boolean (default `true`) with `confirm: false` to opt out, preserving separate registration, group, task/browser, and shutdown confirmations.
- [x] Share shutdown planning and execution between workspace switches and `down`: stop outgoing tracked commands before containers, exclude the selected registration during switches, and apply the same ownership, lock, service, and Docker-target rules.

## Workspace groups (idea)

- [ ] Explore named groups of registered workspaces, including projects in different directories, that go up/down together without stopping one another.
- [ ] Plan group activation as one combined switch and provide group-scoped shutdown, preserving locks, `DWORK_KEEP_PROJECTS`, and the existing-container-only promise.
- [ ] Decide member activation behavior, overlapping/nested membership, host-task lifecycle, Docker-target restrictions, and rename/forget handling before implementation.

## Repeatable terminal sessions

- [ ] Give tasks stable IDs and explicit reuse, skip, or launch-another behavior.
- [x] Track dwork-launched commands with authenticated supervisors for safe shutdown; avoid matching arbitrary processes by command text or trusting saved PIDs alone.

## Recovery

- [x] Harden initial task discovery, nested Compose path resolution, relative shell sourcing, Docker health deadlines, and oversized timeout validation without changing confirmation or ownership policy; add focused regressions.
- [x] Reject linked license destinations and make interrupted installer upgrades recoverable through atomic generated-file replacement and pending ownership hashes, preserving edited-file protection.
- [ ] Evaluate opt-in rollback separately: restoring containers cannot undo application side effects.

## Configuration experience

- [x] Add deterministic, non-overwriting `dwork init` with a preview and standalone read-only `dwork validate`.
- [x] Add a version-1 JSON Schema, schema/loader parity tests, explicit editor association, and schema comments in `dwork init` and examples.
- [ ] Improve runtime field-level errors and submit the schema to SchemaStore for automatic filename discovery.

## Profiles and selection

- [ ] Add backend-only, full-stack, and debugging profiles without duplicated configuration.
- [ ] Allow selecting individual tasks and individual discovered child workspaces.

## Container startup

- [ ] Explicitly handle exited jobs, one-off containers, and services removed from the current Compose model.
- [ ] Evaluate dependency-aware startup using documented Compose interfaces, including `compose start --wait`, with compatibility checks.

## CLI and releases

- [x] Shorten the main README into a getting-started guide and add a curl one-line
  source installer that reuses the managed Make installation, with cleanup,
  prerequisite checks, and detailed update/removal instructions.
- [x] Show `dwork list`/`ls` as an aligned workspace table with status, lock, and path columns; preserve the names-only completion API.
- [x] Add Bash/Zsh shell completions for commands, options, registered workspace names, and file paths.
- [x] Install native completion files for Debian/Ubuntu, Fedora/Arch, Homebrew, and Make prefixes; test framework discovery, first-Tab Zsh autoload, staging, and safe ownership/removal. Python and unsearched prefixes keep explicit setup.
- [x] Load completion automatically when `dwork.sh` is sourced in interactive Bash/Zsh, respecting existing Zsh initialization, noninteractive use, and missing dependencies; test repeated sourcing and real Tab input.
- [x] Document existing exit codes: 0 for success, 1 for failures, and 130 for interruption.
- [x] Add `--version` with one version source shared by source/Make installs, package metadata, and release validation.
- [ ] Add explicit noninteractive mutation behavior preserving confirmation controls. Read-only version-1 list/status JSON is complete; no unattended mutation/approval mode was added.
- [x] Add source and package CI for Linux and macOS.
- [x] Add a tag-triggered workflow to build and verify Python, Debian, Fedora, and Arch release assets, generate checksums, and create a draft GitHub release.
- [ ] Add a project changelog and real Linux/WSL desktop smoke tests.

## Optional tray companion

- [x] Keep the tray as a separate package in this repository and offer explicit `TRAY=1` native source installation, with a separate environment, retained update selection, protected launcher/removal, regression tests, and visible README/install guidance; installation never launches it or enables startup.

- [x] Move the static tray icon into a replaceable packaged PNG, retain native/frozen resource loading, and cover image loading and package inclusion.

- [x] Add a separate experimental native Linux/macOS companion package, read-only JSON protocol/schema, shared menu/worker logic, supported native UI dispatch, operation-terminal CLI handoff, periodic/completion refresh, opt-in protected login entries, Quit-only semantics, and regression/package checks.
- [ ] Verify actual indicator display/menu/operation terminals/login startup on native GNOME/KDE and Cocoa hosts; headless/menu/unit checks are not full desktop validation.
- [x] Add a separate Windows-host transport for one explicitly selected WSL distribution/user/interpreter, running-state checks, bounded read observer, Windows Terminal handoff, preserved CLI confirmations/ownership, regression tests, and Windows package CI; no native Windows workspace execution.
- [ ] Verify Windows tray rendering, real interactive Windows Terminal confirmations/completion, and Windows/WSL suspend/resume manually; transport/quoting/package tests do not prove GUI behavior.
- [x] Make native startup enable/status/disable and the tray menu checkbox easy to discover, document an optional manual Windows Startup-folder shortcut with explicit WSL arguments/UNC caveats, and explain that install.sh treats installation and startup as separate choices.
- [ ] Consider app-managed opt-in Windows login startup after native tray/terminal verification, with explicit target preferences and protected ownership of startup entries. Manual OS shortcut setup is documented; no Windows autostart API was added.

## Packaging publication

- [x] Fix headless Windows-transport source tests and strict Homebrew completion-path auditing, with regressions and unchanged runtime prerequisites.
- [ ] Verify and publish 0.4.0 with companion 0.2.0, then update pinned channel recipes to the immutable release archive.

- [x] Prepare and commit Homebrew, PyPI, and Debian packaging support.
- [x] Verify Python wheel/sdist builds and installation locally, including installed CLI checks outside the source tree.
- [x] Build and verify Fedora 44 RPM and Arch packages locally, including installation, file integrity, and installed CLI checks outside the source tree.
- [x] Complete packaging review and verify the prepared changes are pushed before tagging a release.
- [x] Run the package verification workflow and resolve failures. The expanded run for 33310a7 passed source/Python package checks on Linux, Apple Silicon, and Intel, plus Debian and all three Homebrew jobs. The updated 0.3.0 formula also passed routine Linux/macOS verification.
- [x] Tag the tested commit matching the Python and Debian package versions, then validate remote artifact transfer and draft creation in the release workflow. Tag v0.3.0 points to 33310a7; all package builds, artifact checksums, and draft creation passed.
- [x] Review and publish the resulting [GitHub release](https://github.com/hayyaun/dwork/releases/tag/v0.3.0) and its verified assets. All five public package downloads match SHA256SUMS.
- [ ] Create and publish the Homebrew tap, then verify installation from it.
- [ ] Publish `dwork-cli` to TestPyPI, verify installation, then publish to PyPI.
- [x] Build and verify Debian/Ubuntu packages and attach them to the matching release (0.3.0-1).
- [ ] Evaluate a signed apt repository or PPA.
- [ ] When AUR registration reopens, create the account, add an SSH public key, recheck package-name availability, and submit the prepared recipe.
- [ ] Update installation instructions only after each channel is published and verified. GitHub 0.3.0 downloads are documented; registry, tap, AUR, and apt publication remain pending.

Keep the existing-container-only promise. Builds, deployments, and a large GUI are outside the current roadmap.

- [x] Validate the portable Windows ZIP in CI and launch it on a real Windows host from the Linux filesystem; bundled helper/resources and no-external-Python fixture checks pass. Real interactive desktop behavior remains a separate check above.
