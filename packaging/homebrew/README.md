# Homebrew (macOS / Linux / WSL2)

`dwork.rb` is generated from `dwork.rb.in` and `stable.json` and is a complete tap formula for the v0.5.0 tag, with fixed
source and PyYAML checksums. It uses Homebrew's documented Python virtualenv
helpers and the shared Make installer. Stable v0.5.0 supports Apple Terminal on
macOS, native Linux terminals, and Windows Terminal from WSL2. The formula also
declares the supported `--HEAD` option for development builds of the main branch.
The v0.5.0 tagged source archive is available independently of release build
assets. The [v0.5.0 GitHub release](https://github.com/hayyaun/dwork/releases/tag/v0.5.0)
is published.
The separate public Homebrew tap has not been published.

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

For an optional development build of the current main branch, uninstall an
existing stable installation and use:

```sh
brew uninstall hayyaun/dwork-test/dwork # only if already installed
brew install --HEAD hayyaun/dwork-test/dwork
brew test --HEAD hayyaun/dwork-test/dwork
```

HEAD tracks development source and is not a stable release. Both stable and HEAD
use Apple Terminal's new windows; its supported scripting API cannot create tabs.
The formula provides Python 3.14, meeting macOS's Python 3.13 minimum for tracked
tasks. Docker/Compose and any optional graphical terminal are still installed
separately.

The shared formula uses Homebrew's documented `pkgshare` path for fallback
completion sources, preserving the same installed paths while passing strict
formula auditing. The formula installs completions through Homebrew's
`bash_completion` and `zsh_completion` directories for both the tagged source and HEAD. The Zsh entry
autoloads the sourceable completion script and delegates the first Tab request.
No dwork-specific sourcing line is needed once Homebrew's shell completion
integration is enabled. Evaluate `brew shellenv` before Oh My Zsh/`compinit`;
Bash needs its Homebrew completion framework loaded. See
[Homebrew shell completion](https://docs.brew.sh/Shell-Completion).
Formula tests check that both installed completion entries exist.

The formula test parses a host-only YAML config and previews a workspace. It
never starts Docker, development servers, or GUI terminals.
Routine package CI tests stable and exact-checkout formulas on Linux and Apple Silicon macOS.
Intel Homebrew verification runs for release tags and manual Package verification
runs. Source/package tests use macOS Python 3.13 routinely, adding Apple Silicon
and Intel Python 3.14 on tags/manual runs. Fetching remote HEAD would not verify
unpublished pull-request changes; the dedicated checkout formula lane verifies them.

## Verify the checked-out revision

The package workflow retains stable style/install/test/strict-audit checks and adds
an independent checkout style/install/test lane. Each source mode runs on Linux and
Apple Silicon routinely, and on Intel for tags/manual runs. The checkout lane uses
an archive of the exact clean checked-out commit, including a pull request's merge
commit, rather than downloading the current remote main branch.

With a **clean committed checkout**, generate the temporary source outside it:

```sh
python3 scripts/prepare-homebrew-checkout.py \
  --output /tmp/dwork-homebrew-checkout \
  --expected-revision "$(git rev-parse HEAD)"
cat /tmp/dwork-homebrew-checkout/source.json
```

The output must be new or empty. The helper refuses staged, unstaged, and untracked
changes, a short/wrong revision, in-checkout output, or stable-formula drift before
writing source files. It uses `git archive`, SHA-256, and Homebrew's normal archive
`url`/`version`/`sha256` fields; it starts no server and changes no Git state. The
manifest records the full revision and checksum; archive URLs encode spaces safely.
Copy its `dwork.rb` into a separate temporary tap and run the same `brew style`,
`brew install --build-from-source`, and `brew test` commands as above. Do this in a
disposable CI/test environment; an installed stable package can conflict with it.
Archive preparation alone does not install or validate Homebrew. The local archive
URL is for verification, so publishing audit remains on the stable-release lane.
Do not publish the generated checkout formula or treat it as a release.

When maintaining the recipe, edit `dwork.rb.in`; edit `stable.json` for a new stable
source URL/version/checksum. Regenerate the standalone tap formula and check parity:

```sh
python3 scripts/prepare-homebrew-checkout.py --render-stable > packaging/homebrew/dwork.rb
python3 scripts/prepare-homebrew-checkout.py --check-stable
```

Both source modes use that template so installation and test logic stay aligned.
Stable keeps its original URL-inferred version; checkout archives set the package
version explicitly because their filenames identify commits.
The standalone stable formula continues to work when copied into a public tap.
Source changes do not update the v0.5.0 tagged archive or authorize installation,
activation, or any ownership/confirmation changes.

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
resource block when its dependency version changes.

References: https://docs.brew.sh/Language-Specific-Formulae and
https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap.
