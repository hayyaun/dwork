"""Console-capable portable tray entry; the bootloader hides only its own console."""

from dwork_tray.app import cli

raise SystemExit(cli())
