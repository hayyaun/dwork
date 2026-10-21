"""Shared source and installed console entry point for dwork."""

import sys

from dwork_cli import cli


if __name__ == "__main__":
    sys.exit(cli())
