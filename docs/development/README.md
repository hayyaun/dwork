# Development

[Project home](../../README.md)

## Source layout

- [`dwork.sh`](../../dwork.sh): the Bash/Zsh function and public source entry point.
- [`lib/dwork.py`](../../lib/dwork.py): configuration, Compose switching, health
  prerequisites, and Windows Terminal launching.
- [`.shell_functions`](../../.shell_functions): compatibility loader for older installs.
- [`tests/`](../../tests): behavior, loader, YAML, health, and launch-order tests.
- [`examples/`](../../examples/README.md): configurations developers can adapt.

## Tests

From the repository root:

```sh
python3 -B -m unittest discover -s tests -v
```

Tests use fake Docker and terminal launchers; they do not start containers,
development servers, or Windows Terminal. Shell behavior is checked in Bash and
Zsh when those shells are installed. PyYAML is needed for configuration tests.
