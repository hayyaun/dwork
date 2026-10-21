# Distribution packaging

- [AUR](aur/README.md): v0.3.0 recipe with native completion entries, awaiting account registration.
- [Homebrew](homebrew/README.md): v0.1.0 formula ready for testing/publishing in a tap.
- [Python / PyPI](python/README.md): wheel/sdist and console entry point for v0.2.0.
- [Debian / Ubuntu](debian/README.md): debhelper build for v0.2.0-1.
- [Fedora and Arch release packages](../docs/publishing/README.md#automated-github-release-assets):
  native RPM and pacman builds, tests, and installation checks in disposable
  distro containers. Recipes live in `fedora/` and `arch/`; versions come from
  the release tag. No package repository or AUR publication is performed.

`make install` remains supported. Packaging files do not by themselves publish
to registries or create external repositories/accounts. The existing v0.1.0 tag
is immutable; new Python/Debian metadata belongs to the next release.

## Current verification

Current Make and native recipes install Bash completion in the standard loader
directory and a Zsh autoload entry in the distro's function path (Debian uses
`vendor-completions`; Fedora/Arch use `site-functions`). Homebrew selects its
completion helper paths and supports the existing tagged sourceable scripts.
No shell startup files are edited. Native-file ownership/removal and first-Tab
discovery are covered by source tests; distro smoke checks verify file placement
and Zsh registration. These changes apply to new package builds, not existing
release downloads. JSON Schema test dependencies are declared in native build
recipes as well as Python CI.

Native-completion verification on 2026-10-21 passed the full source suite
(262 tests, two skipped), followed by the final 19 installer/completion checks
after refining framework coverage. Arch's `makepkg --printsrcinfo` agrees with
the prepared AUR metadata. Fedora/Arch package rebuilds were attempted in
disposable containers but failed during repository DNS lookup, before building.
Debian's build is unavailable locally without `debhelper-compat (= 13)`, and
Homebrew is not installed here. Package-build and Homebrew verification therefore
remain CI checks before publication; no package was published or installed on
the host by this change.

On 2026-10-20, the combined checkout passed 70 tests. Python 3.12 wheel/sdist
builds passed strict twine checks; both artifacts installed in fresh venvs and
passed help, host-only YAML dry-run, and friendly-error checks outside the source
tree. Existing source/Make installation behavior remains covered by the tests.

Homebrew install/style/audit and Debian build/lint/install are pending CI. Local
container downloads failed with network/DNS errors, and the maintainer chose
CI instead of installing validation tools into the WSL host. The package workflow
has been added but has not been run in GitHub yet. No external channel was
published by these changes.

On 2026-10-21, the current source snapshot passed all 165 tests in both Fedora 44
and Arch base-devel containers. The native RPM and pacman packages built and
installed successfully, passed `rpm -V` / `pacman -Qk`, and completed installed
`--help` and host-only `--dry-run` checks as an ordinary user outside the source
tree. Workflow syntax, release dependencies, and checksum/upload handling for
all five package formats were checked locally, including rejection of missing
or modified assets. A tagged GitHub Actions release run is still needed to
validate the remote artifact-transfer and draft-creation steps.
