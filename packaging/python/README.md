# Python / PyPI

The distribution name is `dwork-cli`; its command and entry module are `dwork`,
with sibling runtime modules declared explicitly in `pyproject.toml`. The unrelated PyPI name `dwork` is already taken. Availability of
`dwork-cli` was checked on 2026-10-20; it is not reserved until published.
The root `pyproject.toml` uses setuptools' supported flat-module layout and
maps the existing `lib/` directory, keeping source and Make installations intact.

## Build and validate

From the project root, use an isolated development environment:

```sh
python3 -m venv .venv-packaging
. .venv-packaging/bin/activate
python -m pip install build twine
python -m build
python -m twine check dist/*
python -m venv /tmp/dwork-wheel-test
/tmp/dwork-wheel-test/bin/python -m pip install dist/dwork_cli-0.5.0-py3-none-any.whl
/tmp/dwork-wheel-test/bin/dwork --help
```

Also install the sdist in a fresh venv and run a host-only dry-run from outside
the checkout. `scripts/verify-python-package.py` automates those checks using
an existing build/venv-capable interpreter; it downloads build dependencies
only inside its temporary environments.

## Publish

The 0.5.0 wheel and source distribution are available from
[GitHub Releases](https://github.com/hayyaun/dwork/releases/tag/v0.5.0). TestPyPI
and PyPI publication remain pending; these build recipes do not publish to them.
For a future release, first commit and tag
the exact source that was tested. Create PyPI and TestPyPI accounts and verify
the distribution name. Run `python -m twine upload --repository testpypi dist/*`
first and verify the uploaded package. For TestPyPI installation, install PyYAML
from normal PyPI first, then install dwork-cli with `--no-deps` from TestPyPI.
Use PyPI Trusted Publishing for automated uploads, with a protected GitHub
Environment and matching publisher configuration. Do not store API tokens in
this repository. Final PyPI upload is `python -m twine upload dist/*`.

After publication, users can run `pipx install dwork-cli` or
`uv tool install dwork-cli`. Until then, use the local wheel or a Git source URL.

Keep `__version__` in `lib/dwork_version.py` and the Debian changelog synchronized for new
releases. Never overwrite an existing Git tag or reuse a published PyPI version.
Setuptools reads that literal through the dynamic `attr` setting in `pyproject.toml`;
source, Make, and wheel installations report the same value with `dwork --version`.
