# Development

[Project home](../../README.md)

## Source layout

- [`dwork.sh`](../../dwork.sh): the Bash/Zsh function and public source entry point.
- [`lib/dwork.py`](../../lib/dwork.py): configuration, Compose switching, health
  prerequisites, per-session confirmation, and native Linux / Windows Terminal launching.
- [`.shell_functions`](../../.shell_functions): compatibility loader for older installs.
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
