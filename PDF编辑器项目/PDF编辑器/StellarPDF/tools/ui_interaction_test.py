"""Interaction diagnostics for ribbon state and window controls."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DEMO = ROOT / "sample" / "欢迎使用星澜PDF.pdf"

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolButton  # noqa: E402

from app.theme import STYLESHEET  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402


def pump(app, seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def report_buttons(window):
    disabled = []
    total = 0
    for action, buttons in window.ribbon._buttons.items():
        for button in buttons:
            total += 1
            if not button.isEnabled():
                disabled.append(action)
    print("ribbon buttons", total, "disabled", len(disabled), "unique actions", sorted(set(disabled))[:30])


def main():
    app = QApplication([])
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app.setStyleSheet(STYLESHEET)
    w = MainWindow()
    w.resize(1440, 900)
    w.show()
    pump(app)
    print("initial")
    report_buttons(w)
    print("initial maximize/minimize", w.isMaximized(), w.isMinimized())
    print("min button enabled", w.titlebar.btn_min.isEnabled(), "max", w.titlebar.btn_max.isEnabled())
    print("titlebar geometry", w.titlebar.geometry().getRect())
    print("min geom", w.titlebar.btn_min.geometry().getRect(), "max geom", w.titlebar.btn_max.geometry().getRect(), "close", w.titlebar.btn_close.geometry().getRect())
    # Direct click on window buttons.
    QTest.mouseClick(w.titlebar.btn_max, Qt.MouseButton.LeftButton)
    pump(app, 0.4)
    print("after max click", w.isMaximized(), w.windowState())
    QTest.mouseClick(w.titlebar.btn_max, Qt.MouseButton.LeftButton)
    pump(app, 0.4)
    print("after restore click", w.isMaximized(), w.windowState())
    QTest.mouseClick(w.titlebar.btn_min, Qt.MouseButton.LeftButton)
    pump(app, 0.4)
    print("after min click", w.isMinimized(), w.windowState())
    w.showNormal()
    pump(app, 0.2)

    w.open_path(str(DEMO))
    pump(app, 1.0)
    print("opened", w.doc_model.is_open, w.doc_model.page_count, w.viewer.current_page)
    print("title", w.titlebar.title_label.text(), "window", w.windowTitle())
    report_buttons(w)
    print("ribbon current", w.ribbon.current_tab(), "stack", w.ribbon.stack.currentIndex())
    # Click Home -> single view and check.
    btn = w.ribbon._buttons["view.single"][0]
    print("single enabled/visible", btn.isEnabled(), btn.isVisible(), btn.geometry().getRect())
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
    pump(app, 0.3)
    print("view mode after click", w.viewer.view_mode, "checked", btn.isChecked())
    # Click Edit tab and a command.
    QTest.mouseClick(w.ribbon.tabbar, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, w.ribbon.tabbar.tabRect(1).center())
    pump(app, 0.2)
    print("tab after click", w.ribbon.current_tab(), w.ribbon.stack.currentIndex())
    btn2 = w.ribbon._buttons["edit.watermark"][0]
    print("watermark enabled/visible", btn2.isEnabled(), btn2.isVisible(), btn2.geometry().getRect())
    # Do not click watermark (opens modal); inspect only.
    # Check statusbar zoom buttons.
    print("status zoom enabled", w.statusbar.btn_zoom_in.isEnabled())
    app.quit()


if __name__ == "__main__":
    main()
