# Publishing dwork

[Project home](../../README.md) · [Installation](../installation/README.md)

Packaging support is implemented; external publication is a separate step.
`make install` never publishes to a registry, apt repository, or Homebrew tap.

## Release preparation

1. Keep the MIT license and copyright notice in distributions.
2. Commit the exact source being released. The current Python metadata and Debian
   changelog prepare 0.2.0; the existing v0.1.0 tag remains unchanged.
3. Run `make test`, Python wheel/sdist verification, and the relevant channel build.
4. Tag the tested commit and publish the matching GitHub release. Never rewrite
   existing release tags or reuse a published PyPI version.
5. Update fixed source URLs, checksums, versions, and channel metadata together.

## Channel guides

- [AUR](../../packaging/aur/README.md): v0.1.0 PKGBUILD and generated .SRCINFO,
  validated on Arch. AUR account registration was temporarily closed on
  2026-10-20; recheck availability before submission. Push recipes to AUR's
  separate SSH Git repository, not package binaries.
- [Homebrew](../../packaging/homebrew/README.md): v0.1.0 Linux/WSL formula with
  pinned PyYAML. Publish it in `hayyaun/homebrew-tap/Formula/dwork.rb` after testing.
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
