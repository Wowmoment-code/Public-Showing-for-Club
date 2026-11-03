"""Entry point that also works in PyInstaller's windowed (no-console) mode."""
from __future__ import annotations

import os
import sys

# pythonw.exe and PyInstaller's windowed bootloader leave sys.stdout/stderr as
# None.  Some libraries emit import-time warnings, so give them a real sink
# before importing the application package.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
if sys.stdin is None:
    sys.stdin = open(os.devnull, "r", encoding="utf-8")

if sys.platform == "win32":
    # The release executable uses the console subsystem so that it starts
    # reliably even in restricted/headless environments.  Hide that console
    # when we own it (double-click launch), while leaving a terminal intact
    # when the program was started from PowerShell/cmd.
    try:
        import ctypes

        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            processes = (ctypes.c_ulong * 2)()
            count = ctypes.windll.kernel32.GetConsoleProcessList(processes, 2)
            if count <= 1:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass

from app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
