# dwork roadmap

## Milestone 1: visibility and confidence

- [x] Add read-only `dwork status`: workspace selection, Docker context, container states, health, and missing services.
- [x] Add read-only `dwork doctor`: configuration/Compose compatibility, Docker access, shell and terminal dependencies, with actionable fixes.
- [x] Show the Docker target, affected projects, protected projects, and full plan before every switch; preserve existing confirmation rules.
- [x] Report completed actions, the failed step, remaining work, and recovery commands after partial failures or interruption.

## Switching policies

- [x] Add persistent per-workspace protection with `locked: true`, respecting it during switches and shutdowns while retaining `DWORK_KEEP_PROJECTS`.
- [x] Confirm plain workspace activation before applying its plan; use a root-level `confirm` boolean (default `true`) with `confirm: false` to opt out, preserving separate registration, group, task/browser, and shutdown confirmations.

## Workspace groups (idea)

- [ ] Explore named groups of registered workspaces, including projects in different directories, that go up/down together without stopping one another.
- [ ] Plan group activation as one combined switch and provide group-scoped shutdown, preserving locks, `DWORK_KEEP_PROJECTS`, and the existing-container-only promise.
- [ ] Decide member activation behavior, overlapping/nested membership, host-task lifecycle, Docker-target restrictions, and rename/forget handling before implementation.

## Repeatable terminal sessions

- [ ] Give tasks stable IDs and explicit reuse, skip, or launch-another behavior.
- [x] Track dwork-launched commands with authenticated supervisors for safe shutdown; avoid matching arbitrary processes by command text or trusting saved PIDs alone.

## Recovery

- [ ] Evaluate opt-in rollback separately: restoring containers cannot undo application side effects.

## Configuration experience

- [x] Add deterministic, non-overwriting `dwork init` with a preview and standalone read-only `dwork validate`.
- [ ] Improve field-level errors and publish a JSON Schema for editor autocomplete, potentially through SchemaStore.

## Profiles and selection

- [ ] Add backend-only, full-stack, and debugging profiles without duplicated configuration.
- [ ] Allow selecting individual tasks and individual discovered child workspaces.

## Container startup

- [ ] Explicitly handle exited jobs, one-off containers, and services removed from the current Compose model.
- [ ] Evaluate dependency-aware startup using documented Compose interfaces, including `compose start --wait`, with compatibility checks.

## CLI and releases

- [x] Add Bash/Zsh shell completions for commands, options, registered workspace names, and file paths.
- [x] Document existing exit codes: 0 for success, 1 for failures, and 130 for interruption.
- [x] Add `--version` with one version source shared by source/Make installs, package metadata, and release validation.
- [ ] Add JSON output and explicit noninteractive behavior preserving confirmation controls.
- [x] Add source and package CI for Linux and macOS.
- [x] Add a tag-triggered workflow to build and verify Python, Debian, Fedora, and Arch release assets, generate checksums, and create a draft GitHub release.
- [ ] Add a project changelog and real Linux/WSL desktop smoke tests.

## Packaging publication

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
