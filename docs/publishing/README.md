# Publishing dwork

[Project home](../../README.md) · [Installation](../installation/README.md)

This is a release guide, not a claim that marketplace packages already exist.
No AUR package, Homebrew formula, or PyPI release is published by `make install`.

## Prepare an upstream release first

1. The project uses the MIT license in `LICENSE`. Use `MIT` in package metadata
   and include the copyright notice with distributions.
2. Commit the source, installer, requirements, documentation, and hero image.
3. Run `make test` and an isolated install/uninstall check.
4. Choose a version, tag the commit (for example `v0.1.0`), and publish a GitHub release.
   This example version is illustrative, not an existing release.
5. Record the archive URL and SHA-256 checksum. Use fixed release archives for
   stable packages, not a moving main-branch download.

GitHub Releases plus `make install` is the simplest first distribution route.
Marketplace package names must be checked separately; a GitHub repo name does not
reserve them.

## AUR: Arch User Repository

AUR distributes build recipes (`PKGBUILD` and metadata), rather than hosting your
application's built package. Prepare and test the recipe on Arch Linux.

### Account and package repository

Create an AUR account and add your SSH public key to its profile. Check that the
desired package name is available. For an available `dwork` package name:

```sh
git -c init.defaultBranch=master clone ssh://aur@aur.archlinux.org/dwork.git
cd dwork
```

This is a separate packaging Git repository from `hayyaun/dwork`.

### Write PKGBUILD

Set the actual version, release archive URL, checksum, description, upstream URL,
architecture, and selected SPDX license identifier. dwork is pure Python, so
`arch=('any')` is appropriate for its code.

Runtime dependencies should include Arch's `python` and `python-yaml`. Use `make`
as a build dependency. Docker/Compose and supported GUI terminals can be optional
dependencies because host-only and Compose-only workflows are supported.

The `package()` function can use the supported staging install:

```sh
package() {
    cd "$srcdir/dwork-$pkgver"
    make install VENV=0 PREFIX=/usr DESTDIR="$pkgdir" PYTHON=/usr/bin/python
}
```

The extracted directory name must match your release archive. Install the selected
license where Arch's license guidelines require it. Do not create a venv or run
pip from the package installation function; distribution dependencies provide YAML.

### Build, inspect, and submit

In the packaging repository on Arch:

```sh
makepkg --printsrcinfo > .SRCINFO
makepkg -s
```

Review the package contents and test the executable on Arch; a clean build
environment is preferable. Then publish the recipe and metadata:

```sh
git add PKGBUILD .SRCINFO
git commit -m "Add dwork package"
git push origin master
```

Do not commit the generated package archive. For updates, change the version,
source checksum, and package release as appropriate, regenerate `.SRCINFO`,
rebuild/test, and push the packaging commit.

A stable `dwork` recipe should use tagged releases. A separately named
`dwork-git` recipe follows the development branch and needs proper VCS versioning.

References:
[ArchWiki submission guidelines](https://wiki.archlinux.org/title/AUR_submission_guidelines),
[PKGBUILD manual](https://man.archlinux.org/man/PKGBUILD.5.en),
[makepkg manual](https://man.archlinux.org/man/makepkg.8.en).

## Homebrew: start with your own tap

A third-party tap is the straightforward starting point for a new project; a
`homebrew/core` submission is a separate acceptance/review process.

1. Create a repository such as `hayyaun/homebrew-tap`.
2. Add a formula under `Formula/dwork.rb`.
3. Point it at a fixed release archive and its SHA-256.
4. Declare Python and YAML dependencies/resources. Use Homebrew's normal Python
   dependency handling rather than downloading dependencies with pip during
   installation.
5. Add a test such as `dwork --help` and build/test on supported platforms.
6. Publish the tap.

Users can then install the formula by its fully qualified tap name:

```sh
brew install hayyaun/tap/dwork
```

That command is a future distribution example; the tap/formula has not been created.
Until a macOS terminal adapter exists, terminal launching remains Linux/WSL only;
do not advertise native macOS terminal support.

References:
[Create and maintain a tap](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap),
[Adding software](https://docs.brew.sh/Adding-Software-to-Homebrew),
[Python for formula authors](https://docs.brew.sh/Python-for-Formula-Authors).

## PyPI: optional, after adding Python packaging

The PyPI name `dwork` is already used by an unrelated project. Choose an available
distribution name; the installed command can still be `dwork`.

Before publishing, add a `pyproject.toml`, package metadata, a console-script entry
point, and the declared PyYAML dependency. Build and validate a wheel and sdist,
try TestPyPI first, then publish to PyPI. GitHub Actions Trusted Publishing avoids
maintaining a long-lived upload token.

Once published, users could install with `pipx` or `uv tool install`. Python
packaging and publication are not implemented by the current Make installer.

References:
[Existing PyPI dwork project](https://pypi.org/project/dwork/),
[Packaging flow](https://packaging.python.org/en/latest/flow/),
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/).

## Debian/Ubuntu, Snap, and other channels

- A Debian/Ubuntu package can use the staged install, declare `python3` and
  `python3-yaml`, and ship through your own apt repository/PPA before pursuing
  distribution inclusion. Test against each supported distribution release.
  See [Launchpad PPAs](https://ubuntu.com/docs/launchpad/user/Packaging/PPA/).
- Snap or Flatpak are not the first route recommended here: dwork needs access to
  host projects, Docker, and desktop terminals, so confinement and host integration
  need separate design and testing. Nothing in this repository currently claims
  that integration.

Recommended order: tagged GitHub release, AUR recipe, Linux Homebrew tap, then
optional PyPI packaging and distribution-specific packages.
