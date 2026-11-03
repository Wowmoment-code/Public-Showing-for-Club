"""Exercise every non-dialog command twice and log uncaught UI errors."""
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
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.theme import STYLESHEET  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

SAFE = [
    "edit.copy", "edit.select_all", "edit.find",
    "edit.undo", "edit.redo", "edit.text", "edit.image",
    "edit.textbox", "edit.link", "edit.delete_object",
    "view.continuous", "view.single", "view.double", "view.fullscreen",
    "view.zoom_in", "view.zoom_out", "view.fit_width", "view.fit_page", "view.actual_size",
    "tool.select", "tool.hand",
    "annot.highlight", "annot.underline", "annot.strike", "annot.squiggly",
    "annot.area_highlight", "annot.sticky", "annot.note", "annot.textbox",
    "annot.ink", "annot.rect", "annot.ellipse", "annot.arrow", "annot.line",
    "annot.manage",
    "page.rotate_left", "page.rotate_right", "page.select_all", "page.invert_selection",
    "tools.search", "tools.bookmark", "tools.attachment",
    "tools.measure", "tools.area", "tools.screenshot",
    "form.fill",
    "protect.redact",
]


def pump(app, seconds=0.05):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def main():
    app = QApplication([])
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app.setStyleSheet(STYLESHEET)
    w = MainWindow()
    w.resize(1440, 900)
    w.show()
    pump(app)
    errors = []
    original = w._log_ui_error
    w._log_ui_error = lambda where, exc: (errors.append((where, repr(exc))), original(where, exc))
    w.open_path(str(DEMO))
    pump(app, 0.5)
    for action in SAFE:
        # Some actions intentionally open a modal; skip those here.
        if action == "form.fill":
            continue
        for attempt in range(2):
            w.handle_command(action)
            pump(app, 0.04)
        buttons = w.ribbon._buttons.get(action, [])
        if buttons and not buttons[0].isEnabled():
            errors.append((action, "button disabled after click"))
    print("errors", errors)
    print("tool", w.viewer.tool, "view", w.viewer.view_mode, "page", w.viewer.current_page)
    print("ribbon disabled", sum(1 for bs in w.ribbon._buttons.values() for b in bs if not b.isEnabled()))
    print("dirty", w.doc_model.dirty, "pages", w.doc_model.page_count)
    # Ensure a tool can be selected again after using another.
    w.handle_command("tool.select")
    pump(app)
    print("selected tool", w.viewer.tool, "select checked", w.ribbon._buttons["tool.select"][0].isChecked())
    app.quit()
    assert not errors, errors
    print("COMMAND SMOKE PASSED")


if __name__ == "__main__":
    main()
