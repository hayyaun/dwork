PYTHON ?= python3
PREFIX ?= $(HOME)/.local
DESTDIR ?=
VENV ?= 1

.PHONY: help install uninstall test

help:
	@printf '%s\n' 'make install                   Install for the current user (no sudo)' 'make uninstall                 Remove this installation' 'make test                      Run the test suite' 'make install VENV=0 PREFIX=/usr DESTDIR=/path/to/stage  Package-manager staging'

install:
	@"$(PYTHON)" scripts/install.py install --prefix "$(PREFIX)" --destdir "$(DESTDIR)" --venv "$(VENV)"

uninstall:
	@"$(PYTHON)" scripts/install.py uninstall --prefix "$(PREFIX)" --destdir "$(DESTDIR)"

test:
	@"$(PYTHON)" -B -m unittest discover -s tests -v
