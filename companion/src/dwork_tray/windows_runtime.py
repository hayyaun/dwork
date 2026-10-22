"""Supported frozen-runtime handling when launching Windows system programs."""

from contextlib import contextmanager
import ctypes
import os
from pathlib import Path
import sys


def dll_directory(value):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
    kernel.SetDllDirectoryW.restype = ctypes.c_int
    if not kernel.SetDllDirectoryW(value):
        raise ctypes.WinError(ctypes.get_last_error())


def current_dll_directory():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetDllDirectoryW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p]
    kernel.GetDllDirectoryW.restype = ctypes.c_uint
    size = kernel.GetDllDirectoryW(0, None)
    buffer = ctypes.create_unicode_buffer(size + 1)
    kernel.GetDllDirectoryW(len(buffer), buffer)
    return buffer.value or None


@contextmanager
def system_process():
    # PyInstaller documents restoring the system DLL search before launching
    # external executables. This changes only this process and is restored even
    # on failure; no user PATH, registry, or installation settings are changed.
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        yield {}
        return
    previous = current_dll_directory()
    environment = dict(os.environ)
    bundle = Path(sys.executable).resolve().parent
    environment["PATH"] = os.pathsep.join(
        value
        for value in environment.get("PATH", "").split(os.pathsep)
        if not value or not Path(value).resolve().is_relative_to(bundle)
    )
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    dll_directory(None)
    try:
        yield {"env": environment}
    finally:
        dll_directory(previous)
