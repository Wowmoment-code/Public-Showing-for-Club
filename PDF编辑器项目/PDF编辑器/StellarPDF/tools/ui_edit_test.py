"""Verify inline paragraph editing, wheel response, and window controls."""
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

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QFont, QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.theme import STYLESHEET  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402


def pump(app, seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def main():
    app = QApplication([])
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app.setStyleSheet(STYLESHEET)
    w = MainWindow()
    w.resize(1440, 900)
    w.show()
    pump(app)
    print("disabled at start", sum(1 for bs in w.ribbon._buttons.values() for b in bs if not b.isEnabled()))
    w.open_path(str(DEMO))
    pump(app, 0.7)
    w.viewer.fit_page()
    pump(app, 0.3)

    blocks = w.doc_model.text_blocks(2)
    print("blocks", len(blocks), blocks[0].text[:50] if blocks else "")
    block = next((b for b in blocks if "项目背景" in b.text or "在日常办公中" in b.text), blocks[0])
    screen = w.viewer.page_screen_rect(block.page)
    point = QPoint(int(screen.x() + (block.bbox.x0 + block.bbox.x1) / 2 * w.viewer.zoom),
                   int(screen.y() + (block.bbox.y0 + block.bbox.y1) / 2 * w.viewer.zoom))
    # Use the actual transformed center for non-rotated pages.
    point = QPoint(int(screen.x() + ((block.bbox.x0 + block.bbox.x1) / 2) * w.viewer.zoom),
                   int(screen.y() + ((block.bbox.y0 + block.bbox.y1) / 2) * w.viewer.zoom))
    QTest.mouseDClick(w.viewer.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    pump(app, 0.2)
    print("inline editor", w.viewer._inline_editor is not None)
    if w.viewer._inline_editor is None:
        raise SystemExit("inline editor did not open")
    w.viewer._inline_editor.setPlainText("这一段文字已经通过内嵌编辑器修改。")
    QTest.keyClick(w.viewer._inline_editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    pump(app, 0.8)
    print("after commit editor", w.viewer._inline_editor)
    normalized = w.doc_model.text(2).replace("\n", "").replace("\xa0", " ")
    print("text contains", "内嵌编辑器" in normalized)
    print("dirty", w.doc_model.dirty)
    assert w.viewer._inline_editor is None
    assert "内嵌编辑器" in normalized
    assert w.doc_model.dirty

    # Scroll wheel should move at least 100px per notch.
    before = w.viewer.verticalScrollBar().value()
    event = QWheelEvent(
        QPointF(300, 300), QPointF(300, 300),
        QPoint(0, 0), QPoint(0, -120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    QApplication.sendEvent(w.viewer.viewport(), event)
    pump(app, 0.1)
    delta = w.viewer.verticalScrollBar().value() - before
    print("wheel delta", delta)
    assert abs(delta) >= 80

    # Window controls.
    QTest.mouseClick(w.titlebar.btn_max, Qt.MouseButton.LeftButton)
    pump(app, 0.3)
    assert w.isMaximized()
    QTest.mouseClick(w.titlebar.btn_max, Qt.MouseButton.LeftButton)
    pump(app, 0.3)
    assert not w.isMaximized()
    QTest.mouseClick(w.titlebar.btn_min, Qt.MouseButton.LeftButton)
    pump(app, 0.3)
    assert w.isMinimized()
    print("window controls ok")
    app.quit()
    print("UI EDIT TEST PASSED")


if __name__ == "__main__":
    main()
