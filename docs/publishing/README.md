# Publishing dwork

[Project home](../../README.md) · [Installation](../installation/README.md)

[GitHub release v0.3.0](https://github.com/hayyaun/dwork/releases/tag/v0.3.0)
is published with verified Python wheel/source, Debian/Ubuntu, Fedora 44, and Arch
packages, plus [SHA256SUMS](https://github.com/hayyaun/dwork/releases/download/v0.3.0/SHA256SUMS).
The public downloads have been checked against those checksums.

Public Homebrew tap, PyPI, AUR, and apt repository publication remain pending.
`make install` never publishes to any of those channels.

## Release preparation

The source-test CI step runs each test file with unittest's `--failfast` option,
then fails if any file failed. This reports each file's first traceback before
later interactive tests can block diagnostics. A successful run still executes
the full suite; `make test` locally reports all failures in one run.

1. Keep the MIT license and copyright notice in distributions.
2. Commit the exact source being released. Synchronize the Python metadata and
   Debian upstream version with the intended tag; keep existing tags unchanged.
3. Run `make test`, Python wheel/sdist verification, and the relevant channel build.
4. Tag the tested commit and publish the matching GitHub release. Never rewrite
   existing release tags or reuse a published PyPI version.
5. Update fixed source URLs, checksums, versions, and channel metadata together.

## Automated GitHub release assets

`.github/workflows/release.yml` runs when a stable `vMAJOR.MINOR.PATCH` tag is
pushed. The tag must match `__version__` in `lib/dwork_version.py` (also used by
the CLI and setuptools' dynamic package version) and the upstream
version in `packaging/debian/changelog` (for example, `v0.3.0`, `0.3.0`, and
`0.3.0-1`). Commit the version changes and workflow before tagging that commit:

```sh
git tag -a v0.3.0 -m "Release 0.3.0"
git push origin v0.3.0
```

The workflow runs source tests, builds and smoke-tests the Python wheel and
source distribution, then builds, lints, installs, and smoke-tests the Debian
package on Ubuntu 24.04. Two more jobs build from the tagged Git checkout in
`fedora:44` and `archlinux:base-devel` containers using `rpmbuild` and `makepkg`.
Both run the source tests as an ordinary build user, install the package with
the distro package manager, verify its installed files, and smoke-test `--help`
and a host-only `--dry-run` as that user outside the source tree. Arch performs
a full system upgrade before building, as required for its rolling packages.

All three package jobs must pass before the release job can run. Each records
checksums after verification; the release job checks these again after downloading
the artifacts. It collects the exact verified `.whl`, `.tar.gz`, `.deb`, `.rpm`,
and `.pkg.tar.zst` files,
creates `SHA256SUMS` covering all five packages, and attaches all six files to
a draft GitHub Release with generated notes.
Only the final draft job receives repository write permission; it uses
the built-in `GITHUB_TOKEN`, so no extra release secret is needed.

Review the notes and assets in GitHub Releases before publishing the draft.
Download all assets into one directory and run `sha256sum --check SHA256SUMS` to
verify their checksums. The `.deb` uses system Python and PyYAML; the wheel also
requires Python. The RPM targets Fedora 44; the Arch package targets the current
Arch rolling distribution. `noarch`/`any` describe architecture-independent
application code, not compatibility with every RPM/pacman-based distribution.
These packages use distro Python and PyYAML and are not standalone executables.

The release recipes live in `packaging/fedora` and `packaging/arch`. Version
values come from the validated tag; the Arch source checksum is calculated from
the local tagged Git archive and verified by makepkg. The existing
`packaging/aur` recipe is separate and is not changed or published by this flow.
The packages are unsigned; SHA-256 checksums verify file integrity, not publisher
identity. Package signing and repository publication need separate setup.

The workflow does not overwrite existing releases. If an upload fails after a
draft is created, delete that incomplete draft in GitHub (keep its tag) before
rerunning the failed job. Never move an existing release tag. PyPI publication,
Homebrew/AUR updates, and apt repository publication remain separate manual work.

## Channel guides

- [AUR](../../packaging/aur/README.md): v0.1.0 PKGBUILD and generated .SRCINFO,
  validated on Arch. AUR account registration was temporarily closed on
  2026-10-20; recheck availability before submission. Push recipes to AUR's
  separate SSH Git repository, not package binaries.
- [Homebrew](../../packaging/homebrew/README.md): the prepared stable v0.3.0
  formula supports Linux, macOS, and WSL2 with pinned PyYAML. Its source URL and
  checksum match the v0.3.0 tag archive. Test it before publishing it in the
  separate `hayyaun/homebrew-tap/Formula/dwork.rb` repository.
- [PyPI](../../packaging/python/README.md): `dwork-cli` wheel/sdist and `dwork`
  console command. TestPyPI first; Trusted Publishing is recommended for CI.
  The separate PyPI name `dwork` belongs to an unrelated project.
- [Debian/Ubuntu](../../packaging/debian/README.md): staged debhelper builds,
  local .deb installation, GitHub release assets, and later signed apt/PPA uploads.

The package verification workflow builds/tests artifacts but does not publish
or store registry credentials. Publication still requires the relevant account,
repository, signing configuration, and a verified matching release.

## Other channels

Snap/Flatpak need a separate host-integration design for project paths, Docker,
and desktop terminals. They are not included in this packaging work. Native
Windows package managers are not a target: dwork runs inside WSL2 on Windows.

References: [Python packaging](https://packaging.python.org/en/latest/flow/),
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/),
[Homebrew taps](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap),
[Debian maintainer guide](https://www.debian.org/doc/manuals/maint-guide/),
[Launchpad PPAs](https://ubuntu.com/docs/launchpad/user/Packaging/PPA/).
