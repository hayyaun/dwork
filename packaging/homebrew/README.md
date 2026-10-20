# Homebrew (Linux / WSL2)

`dwork.rb` is a complete tap formula for the existing v0.1.0 release, with fixed
source and PyYAML checksums. It uses Homebrew's documented Python virtualenv
helpers and the release's existing Make installer. The formula is Linux-only;
Homebrew installation does not add macOS terminal support.

## Test in a local tap

With Homebrew installed on Linux or WSL2:

```sh
brew tap-new hayyaun/dwork-test
cp packaging/homebrew/dwork.rb "$(brew --repository hayyaun/dwork-test)/Formula/dwork.rb"
brew style hayyaun/dwork-test/dwork
brew install --build-from-source hayyaun/dwork-test/dwork
brew test hayyaun/dwork-test/dwork
brew audit --strict hayyaun/dwork-test/dwork
```

The formula test parses a host-only YAML config and previews a workspace. It
never starts Docker, development servers, or GUI terminals.

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
