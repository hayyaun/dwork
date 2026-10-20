# Development

[Project home](../../README.md)

## Source layout

- [`dwork.sh`](../../dwork.sh): the Bash/Zsh function and public source entry point.
- [`lib/dwork.py`](../../lib/dwork.py): configuration, Compose switching, health
  prerequisites, per-session confirmation, and native Linux / Windows Terminal launching.
- [`tests/`](../../tests): behavior, loader, YAML, health, and launch-order tests.
- [`examples/`](../../examples/README.md): configurations developers can adapt.

- [`Makefile`](../../Makefile) and [installer](../../scripts/install.py): user
  installation, removal, and package staging.
- [`requirements.txt`](../../requirements.txt): isolated-install Python dependency.

## Tests

From the repository root:

```sh
make test
```

Tests use fake Docker and terminal launchers; they do not start containers,
development servers, or GUI terminals. Shell behavior is checked in Bash and
Zsh when those shells are installed. PyYAML is needed for configuration tests.

Installer tests use temporary prefixes with `VENV=0` and test Make targets,
ownership checks, paths with spaces, reinstall/uninstall, and DESTDIR staging.
The default venv installation is additionally smoke-tested in a temporary prefix.

## Agent skill

[`skills/dwork/`](../../skills/dwork/) is the portable, separately installable
skill for users generating configurations in their own projects. Keep its
bundled [configuration reference](../../skills/dwork/references/configuration.md)
consistent with the parser and [configuration docs](../configuration/README.md)
when changing supported fields or behavior. Keep references inside the skill
folder so installations work without the source checkout. Installation and
manual-copy instructions live in the [skill guide](../skills/README.md).

Before publishing changes, check local skill discovery without installing:

```sh
npx skills add ./skills/dwork --list
```

## Distribution packaging

[`pyproject.toml`](../../pyproject.toml) packages the existing `lib/dwork.py`
module using setuptools. `dwork:cli` is the console entry point and preserves
source CLI errors/interrupts. No duplicate runtime is maintained.

Channel recipes, build instructions, and publication steps live under
[`packaging/`](../../packaging/README.md). Verify wheels and sdists with
`python scripts/verify-python-package.py` in a temporary tools venv containing
build and twine. Debian builds use `python3 scripts/build-deb.py`; Homebrew has
its own installed-behavior test. Packaging verification must not run real
project containers, development servers, or GUI tasks.
