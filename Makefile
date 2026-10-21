PYTHON ?= python3
PREFIX ?= $(HOME)/.local
DESTDIR ?=
VENV ?= 1
BASH_COMPLETION_DIR ?= $(PREFIX)/share/bash-completion/completions
ZSH_COMPLETION_DIR ?= $(PREFIX)/share/zsh/site-functions

.PHONY: help install uninstall test quality format

help:
	@printf '%s\n' 'make install                   Install for the current user (no sudo)' 'make uninstall                 Remove this installation' 'make test                      Run the test suite' 'make quality                   Check lint, formatting, types, and formula parity' 'make format                    Format Python sources (writes files)' 'make install VENV=0 PREFIX=/usr DESTDIR=/path/to/stage  Package-manager staging'

install:
	@"$(PYTHON)" scripts/install.py install --prefix "$(PREFIX)" --destdir "$(DESTDIR)" --venv "$(VENV)" --bash-completion-dir "$(BASH_COMPLETION_DIR)" --zsh-completion-dir "$(ZSH_COMPLETION_DIR)"

uninstall:
	@"$(PYTHON)" scripts/install.py uninstall --prefix "$(PREFIX)" --destdir "$(DESTDIR)"

test:
	@"$(PYTHON)" -B -m unittest discover -s tests -v

quality:
	@"$(PYTHON)" -m ruff check lib scripts tests
	@"$(PYTHON)" -m ruff format --check lib scripts tests
	@"$(PYTHON)" -m mypy
	@"$(PYTHON)" scripts/prepare-homebrew-checkout.py --check-stable

format:
	@"$(PYTHON)" -m ruff format lib scripts tests
