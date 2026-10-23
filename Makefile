PYTHON ?= python3
PREFIX ?= $(HOME)/.local
DESTDIR ?=
VENV ?= 1
TRAY ?= 0
BASH_COMPLETION_DIR ?= $(PREFIX)/share/bash-completion/completions
ZSH_COMPLETION_DIR ?= $(PREFIX)/share/zsh/site-functions

.PHONY: help install uninstall test quality format serve

help:
	@printf '%s\n' 'make install                   Install for the current user (no sudo)' 'make install TRAY=1            Also install the optional native tray (no launch/startup)' 'make uninstall                 Remove this installation' 'make test                      Run the test suite' 'make quality                   Check lint, formatting, types, and formula parity' 'make format                    Format Python sources (writes files)' 'make serve                     Preview site at http://localhost:8000' 'make install VENV=0 PREFIX=/usr DESTDIR=/path/to/stage  Package-manager staging'

install:
	@"$(PYTHON)" scripts/install.py install --prefix "$(PREFIX)" --destdir "$(DESTDIR)" --venv "$(VENV)" --tray "$(TRAY)" --bash-completion-dir "$(BASH_COMPLETION_DIR)" --zsh-completion-dir "$(ZSH_COMPLETION_DIR)"

uninstall:
	@"$(PYTHON)" scripts/install.py uninstall --prefix "$(PREFIX)" --destdir "$(DESTDIR)"

test:
	@"$(PYTHON)" -B -m unittest discover -s tests -v

quality:
	@"$(PYTHON)" -m ruff check lib scripts tests companion/src
	@"$(PYTHON)" -m ruff format --check lib scripts tests companion/src
	@"$(PYTHON)" -m mypy
	@"$(PYTHON)" scripts/prepare-homebrew-checkout.py --check-stable

format:
	@"$(PYTHON)" -m ruff format lib scripts tests companion/src

serve:
	@"$(PYTHON)" -m http.server 8000 --directory site
