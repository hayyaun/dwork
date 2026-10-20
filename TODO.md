# dwork roadmap

## Milestone 1: visibility and confidence

- [x] Add read-only `dwork status`: workspace selection, Docker context, container states, health, and missing services.
- [x] Add read-only `dwork doctor`: configuration/Compose compatibility, Docker access, shell and terminal dependencies, with actionable fixes.
- [x] Show the Docker target, affected projects, protected projects, and full plan before every switch; preserve existing confirmation rules.
- [x] Report completed actions, the failed step, remaining work, and recovery commands after partial failures or interruption.

## Switching policies

- [ ] Add persistent policies for shared infrastructure and projects dwork may stop; retain `DWORK_KEEP_PROJECTS`.

## Repeatable terminal sessions

- [ ] Give tasks stable IDs and explicit reuse, skip, or launch-another behavior.
- [ ] Track owned sessions reliably; avoid matching arbitrary processes by command text.

## Recovery

- [ ] Evaluate opt-in rollback separately: restoring containers cannot undo application side effects.

## Configuration experience

- [ ] Add deterministic `dwork init` and standalone `dwork validate`.
- [ ] Improve field-level errors and publish a JSON Schema for editor autocomplete, potentially through SchemaStore.

## Profiles and selection

- [ ] Add backend-only, full-stack, and debugging profiles without duplicated configuration.
- [ ] Allow selecting individual tasks and individual discovered child workspaces.

## Container startup

- [ ] Explicitly handle exited jobs, one-off containers, and services removed from the current Compose model.
- [ ] Evaluate dependency-aware startup using documented Compose interfaces, including `compose start --wait`, with compatibility checks.

## CLI and releases

- [ ] Add `--version`, shell completions, JSON output, documented exit codes, and explicit noninteractive behavior preserving confirmation controls.
- [ ] Add CI, automated releases, a changelog, and real Linux/WSL desktop smoke tests.

## Packaging publication

- [ ] Review, commit, and push the prepared Homebrew, PyPI, and Debian packaging changes.
- [ ] Run the package verification workflow and resolve failures, including the pending Homebrew and Debian checks.
- [ ] Tag and publish the tested release matching the Python and Debian package versions.
- [ ] Create and publish the Homebrew tap, then verify installation from it.
- [ ] Publish `dwork-cli` to TestPyPI, verify installation, then publish to PyPI.
- [ ] Build and verify Debian/Ubuntu packages and attach them to the matching release; evaluate a signed apt repository or PPA later.
- [ ] When AUR registration reopens, create the account, add an SSH public key, recheck package-name availability, and submit the prepared recipe.
- [ ] Update installation instructions only after each channel is published and verified.

Keep the existing-container-only promise. Builds, deployments, and a large GUI are outside the current roadmap.
