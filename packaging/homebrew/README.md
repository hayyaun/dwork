# Homebrew (macOS / Linux / WSL2)

`dwork.rb` is a complete tap formula for the existing v0.1.0 release, with fixed
source and PyYAML checksums. It uses Homebrew's documented Python virtualenv
helpers and the release's existing Make installer. It also declares the supported
`--HEAD` option for the main branch. Both versions can install on macOS and Linux;
Apple Terminal support is in HEAD until a new stable release includes it. The
stable v0.1.0 URL/checksum is intentionally unchanged.

## Test in a local tap

With Homebrew installed on macOS, Linux, or WSL2:

```sh
brew tap-new hayyaun/dwork-test
cp packaging/homebrew/dwork.rb "$(brew --repository hayyaun/dwork-test)/Formula/dwork.rb"
brew style hayyaun/dwork-test/dwork
brew install --build-from-source hayyaun/dwork-test/dwork
brew test hayyaun/dwork-test/dwork
brew audit --strict hayyaun/dwork-test/dwork
```

To install the current main branch with Apple Terminal support after these changes
are merged, uninstall an existing stable installation and use:

```sh
brew uninstall hayyaun/dwork-test/dwork # only if already installed
brew install --HEAD hayyaun/dwork-test/dwork
brew test --HEAD hayyaun/dwork-test/dwork
```

HEAD tracks development source and is not a stable release. Apple Terminal opens
new windows; its supported scripting API cannot create tabs. The formula provides
Python 3.14, meeting macOS's Python 3.13 minimum for tracked tasks. Docker/Compose
and any optional graphical terminal are still installed separately.

The formula test parses a host-only YAML config and previews a workspace. It
never starts Docker, development servers, or GUI terminals.
Routine package CI tests the stable formula on Linux and Apple Silicon macOS.
Intel Homebrew verification runs for release tags and manual Package verification
runs. Source/package tests use macOS Python 3.13 routinely, adding Apple Silicon
and Intel Python 3.14 on tags/manual runs. Fetching remote HEAD would not verify
unpublished pull-request changes; the source tests use the actual checkout.

## Publish your tap

Create a public GitHub repository `hayyaun/homebrew-tap` and place the formula
at `Formula/dwork.rb`. Commit and push it, then test installation from that tap.
Only after it is published, advertise:

```sh
brew install hayyaun/tap/dwork
```

This project change does not create or publish that separate repository.
Homebrew/core inclusion is a different review process; an own tap works first.
For new releases update the source URL/checksum and tests, plus the Python
resource block when its dependency version changes. Once a tagged release has
pyproject.toml, the formula can adopt `virtualenv_install_with_resources`.

References: https://docs.brew.sh/Language-Specific-Formulae and
https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap.
