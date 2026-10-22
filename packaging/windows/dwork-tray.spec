# PyInstaller's documented Analysis/PYZ/EXE/COLLECT multi-program bundle.
from pathlib import Path

root = Path(SPECPATH).resolve().parents[1]
source = root / "companion/src"
excludes = ["gi", "PyObjCTools", "dwork", "dwork_common", "dwork_terminals"]
tray = Analysis(
    [str(root / "packaging/windows/tray_entry.py")],
    pathex=[str(source)],
    datas=[
        (str(source / "dwork_tray/observer.py"), "dwork_tray"),
        (str(source / "dwork_tray/assets/tray.png"), "dwork_tray/assets"),
    ],
    excludes=excludes,
)
terminal = Analysis(
    [str(root / "packaging/windows/terminal_entry.py")],
    pathex=[str(source)],
    excludes=excludes,
)
tray_exe = EXE(
    PYZ(tray.pure), tray.scripts, [],
    name="dwork-tray", exclude_binaries=True, console=True,
    hide_console="hide-early", upx=False,
)
terminal_exe = EXE(
    PYZ(terminal.pure), terminal.scripts, [],
    name="dwork-tray-terminal", exclude_binaries=True, console=True, upx=False,
)
COLLECT(
    tray_exe, terminal_exe, tray.binaries, tray.datas,
    terminal.binaries, terminal.datas,
    name="dwork-tray", upx=False,
)
