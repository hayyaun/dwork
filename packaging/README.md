# Distribution packaging

- [AUR](aur/README.md): v0.3.0 recipe with native completion entries; submission pending.
- [Homebrew](homebrew/README.md): v0.3.0 formula, shared recipe template, and exact-checkout verification; public tap pending.
- [Python / PyPI](python/README.md): v0.4.1 wheel/sdist and console entry point; TestPyPI/PyPI publication pending.
- [Debian / Ubuntu](debian/README.md): v0.4.1-1 debhelper packaging; no signed apt repository.
- [Fedora and Arch](../docs/publishing/README.md#automated-github-release-assets): RPM/pacman builds with versions taken from the release tag; AUR publication is separate.

Verified v0.3.0 Python, Debian/Ubuntu, Fedora 44, and Arch packages are published in
[GitHub Releases](https://github.com/hayyaun/dwork/releases/tag/v0.3.0), with
[SHA256SUMS](https://github.com/hayyaun/dwork/releases/download/v0.3.0/SHA256SUMS).
The release points to commit `33310a7`. Historical release verification does not
prove that later checkout changes pass. Existing tags and downloads remain immutable.
`make install` stays supported. These recipes and CI jobs do not publish packages
to PyPI, a Homebrew tap, AUR, or an apt repository.

## Current verification paths

The current source prepares CLI 0.4.1 and separate companion 0.2.0. Native
companion dependencies target CLI 0.4.x; the portable Windows package embeds its
own runtime and uses the matching CLI in WSL. Published assets and pinned channel
recipes are updated only after the tagged release is built and verified.

`make quality` checks pinned Ruff lint/format rules, gradual mypy types, and stable
formula/template parity. Install the development-only `quality` extra first; see
[development checks](../docs/development/README.md#quality-baseline). `make test`
exercises runtime behavior, confirmations, authenticated task ownership, and safe
installation/removal. Static checks do not replace behavioral tests.

The [Package verification workflow](../.github/workflows/packaging.yml) builds
wheels/sdists from its checkout, verifies installed behavior outside the source
tree, and builds/lints/smoke-tests Debian packages. Homebrew has two source modes
on Linux and Apple Silicon macOS, adding Intel on tags/manual runs:

- **Stable:** pinned v0.3.0 archive, style, source installation, formula test, strict audit.
- **Checkout:** checksummed `git archive HEAD` matching the expected full CI commit,
  generated local formula, style, source installation, and formula test. No remote
  HEAD substitution or checksum bypass is used. This temporary source is not published.

The [shared Homebrew template](homebrew/dwork.rb.in) contains the same dependency,
installation, completion, caveat, and test definitions for both modes. Its stable
[source metadata](homebrew/stable.json) reproduces the checked-in `dwork.rb`; parity
is enforced by tests and quality checks. Checkout metadata records the full commit,
package version, archive name, and checksum. Local archive preparation has offline
regression tests; actual Homebrew installation still requires Homebrew and its dependencies.

Make/native completion files use their platform discovery directories. Ownership
hashes, interrupted-install recovery, linked destinations, and first-Tab behavior
remain covered by source tests. No shell startup files are edited. Package builds
verify completion placement and Zsh discovery separately from real GUI behavior.

Build prerequisites and supported publication steps live in the channel guides.
Report which revision, platform, source mode, and commands were verified, including
any unavailable checks. A successful old release run or stable Homebrew run is not
evidence that the checkout lane passed. Never present local archive preparation
or workflow syntax checks as a successful Homebrew installation.


An optional [portable Windows tray](windows/README.md) bundles the app and runtime
in a CI-built ZIP. Verified ZIP/checksum assets join draft releases.
