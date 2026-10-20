# Distribution packaging

- [AUR](aur/README.md): validated v0.1.0 recipe, awaiting account registration.
- [Homebrew](homebrew/README.md): v0.1.0 formula ready for testing/publishing in a tap.
- [Python / PyPI](python/README.md): wheel/sdist and console entry point for v0.2.0.
- [Debian / Ubuntu](debian/README.md): debhelper build for v0.2.0-1.

`make install` remains supported. Packaging files do not by themselves publish
to registries or create external repositories/accounts. The existing v0.1.0 tag
is immutable; new Python/Debian metadata belongs to the next release.

## Current verification

On 2026-10-20, the combined checkout passed 70 tests. Python 3.12 wheel/sdist
builds passed strict twine checks; both artifacts installed in fresh venvs and
passed help, host-only YAML dry-run, and friendly-error checks outside the source
tree. Existing source/Make installation behavior remains covered by the tests.

Homebrew install/style/audit and Debian build/lint/install are pending CI. Local
container downloads failed with network/DNS errors, and the maintainer chose
CI instead of installing validation tools into the WSL host. The package workflow
has been added but has not been run in GitHub yet. No external channel was
published by these changes.
