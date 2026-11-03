"""Capture repeatable UI screenshots for visual inspection during development."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.theme import STYLESHEET  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "screens"
DEMO = ROOT / "sample" / "欢迎使用星澜PDF.pdf"


def pump(app, seconds=0.25):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    app = QApplication([])
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    pump(app)
    window.grab().save(str(OUT / "welcome.png"))
    window.open_path(str(DEMO))
    pump(app, 1.5)
    window.grab().save(str(OUT / "home.png"))
    for key in ("edit", "page", "annot", "tools", "fill", "protect", "convert", "ai"):
        window.ribbon.set_tab(key)
        pump(app, 0.2)
        window.grab().save(str(OUT / f"tab_{key}.png"))
    app.quit()


if __name__ == "__main__":
    main()
