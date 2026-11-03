"""Exercise widgets, dialogs, and viewer interactions headlessly."""
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
OUT = ROOT / "screens"

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.theme import STYLESHEET  # noqa: E402
from app.ui import dialogs  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402


def pump(app, seconds=0.2):
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
    window.open_path(str(DEMO))
    pump(app, 1.0)
    assert window.doc_model.page_count == 6
    assert window.viewer.zoom > 0.5
    print("open ok", window.doc_model.page_count, round(window.viewer.zoom, 2))

    # View modes and navigation.
    for mode in ("single", "double", "single", "continuous"):
        window.ribbon.set_tab("home")
        window._set_view_mode(mode)
        pump(app, 0.1)
        assert window.viewer.view_mode == mode
    window.viewer.goto_page(2)
    pump(app)
    assert window.viewer.current_page == 2
    print("view modes ok")

    # Text selection via mouse drag.
    window.viewer.fit_page()
    pump(app)
    rect = window.viewer.page_screen_rect(2)
    start = QPoint(int(rect.x() + 60), int(rect.y() + 180))
    end = QPoint(int(rect.x() + 470), int(rect.y() + 280))
    window.set_tool("select")
    QTest.mousePress(window.viewer.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(window.viewer.viewport(), end, 50)
    QTest.mouseRelease(window.viewer.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    pump(app)
    print("selected chars", len(window.viewer.selected_text))
    assert len(window.viewer.selected_text) > 10
    window.viewer.copy_selection()
    print("clipboard", len(QApplication.clipboard().text()))

    # Highlight drag should create a PDF annotation through MainWindow.
    before = len(window.doc_model.all_annotations())
    window.set_tool("highlight", "annot.highlight")
    QTest.mousePress(window.viewer.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(window.viewer.viewport(), end, 60)
    QTest.mouseRelease(window.viewer.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    pump(app, 0.4)
    after = len(window.doc_model.all_annotations())
    print("annotations", before, "->", after)
    assert after > before
    assert window.doc_model.dirty

    # Search.
    window._perform_search("星澜")
    pump(app)
    assert len(window._search_hits) > 0
    print("search hits", len(window._search_hits))
    window.sidebar.show_panel("annots")
    pump(app)
    assert window.sidebar.annot_list.count() >= 1

    # Instantiate every dialog to catch construction/layout errors.
    span = window.doc_model.spans(2)[0]
    constructors = [
        lambda: dialogs.TextEditDialog(window, span),
        lambda: dialogs.TextInsertDialog(window),
        lambda: dialogs.WatermarkDialog(window, 6, 0),
        lambda: dialogs.WatermarkDialog(window, 6, 0, image=True),
        lambda: dialogs.BackgroundDialog(window, 6, 0),
        lambda: dialogs.HeaderFooterDialog(window, 6, 0, footer=True),
        lambda: dialogs.PageNumberDialog(window, 6, 0),
        lambda: dialogs.StampDialog(window),
        lambda: dialogs.SignatureDialog(window),
        lambda: dialogs.EncryptDialog(window),
        lambda: dialogs.PermissionDialog(window, 0),
        lambda: dialogs.PageSizeDialog(window, 6, 0),
        lambda: dialogs.CropDialog(window, 6, 0),
        lambda: dialogs.SplitDialog(window, 6, str(ROOT)),
        lambda: dialogs.InsertPagesDialog(window, 6, 0),
        lambda: dialogs.LinkDialog(window, 6, 0),
        lambda: dialogs.BookmarkDialog(window, 6, 0),
        lambda: dialogs.BlankPageDialog(window, 6, 0, (595, 842)),
        lambda: dialogs.ReplaceDialog(window, 6, 0),
        lambda: dialogs.OcrDialog(window, 6, 0),
        lambda: dialogs.ConvertOptionsDialog(window, "word", 6, 0),
        lambda: dialogs.ImageToPdfDialog(window, []),
        lambda: dialogs.FormFillDialog(window, []),
        lambda: dialogs.FormFieldDialog(window, "text"),
        lambda: dialogs.MetadataDialog(window, window.doc_model.metadata()),
        lambda: dialogs.AIDialog(window, "测试文本。", ""),
        lambda: dialogs.ShortcutsDialog(window),
        lambda: dialogs.AboutDialog(window),
        lambda: dialogs.CompareDialog(window, str(DEMO)),
        lambda: dialogs.BatchConvertDialog(window, str(ROOT)),
        lambda: dialogs.MovePageDialog(window, 6, 0),
        lambda: dialogs.MergeDialog(window, [str(DEMO)]),
        lambda: dialogs.TextResultDialog(window, "测试", "内容"),
    ]
    for factory in constructors:
        dlg = factory()
        dlg.show()
        pump(app, 0.02)
        dlg.close()
    print("dialogs ok", len(constructors))

    # Ribbon tabs and screenshots.
    for key in ("home", "edit", "page", "annot", "tools", "fill", "protect", "convert", "ai"):
        window.ribbon.set_tab(key)
        pump(app, 0.15)
        window.grab().save(str(OUT / f"final_tab_{key}.png"))
    print("tabs ok")

    # Undo/redo through MainWindow.
    window.ribbon.set_tab("home")
    window.undo()
    pump(app)
    assert len(window.doc_model.all_annotations()) == before
    window.redo()
    pump(app)
    assert len(window.doc_model.all_annotations()) == after
    print("undo/redo ui ok")

    # Save same-file copy and reopen.
    target = ROOT / "test_output" / "ui_saved.pdf"
    target.parent.mkdir(exist_ok=True)
    assert window._save_to(str(target))
    pump(app)
    assert window.doc_model.path == str(target)
    print("save ui ok")

    app.quit()
    print("UI SMOKE PASSED")


if __name__ == "__main__":
    main()
