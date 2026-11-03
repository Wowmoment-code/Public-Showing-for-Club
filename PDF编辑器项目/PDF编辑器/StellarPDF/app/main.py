"""Application entry point for Stellar PDF."""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from .config import APP_NAME, APP_VERSION, DATA_DIR, ensure_dirs, ui_font_family
from .icons import app_icon
from .theme import STYLESHEET
from .ui.main_window import MainWindow


def _log(message: str) -> None:
    try:
        ensure_dirs()
        path = DATA_DIR / "startup.log"
        if path.exists() and path.stat().st_size > 256_000:
            path.unlink()
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {message}\n")
    except Exception:
        pass


def _install_exception_hook() -> None:
    def hook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            ensure_dirs()
            with open(DATA_DIR / "error.log", "a", encoding="utf-8") as fh:
                fh.write(f"\n===== {APP_NAME} {APP_VERSION} =====\n{text}\n")
        except Exception:
            pass
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                box = QMessageBox()
                box.setWindowTitle("星澜 PDF 遇到问题")
                box.setText(f"程序遇到一个错误：\n\n{exc_value}\n\n错误详情已写入日志。")
                box.setIcon(QMessageBox.Icon.Critical)
                # Non-modal: a hidden modal error box must never make the whole
                # application appear unclickable.
                box.setWindowModality(Qt.WindowModality.NonModal)
                box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
                box.show()
        except Exception:
            pass

    sys.excepthook = hook


def _ocr_selftest(args: list[str]) -> int:
    """Hidden diagnostic used to verify the packaged OCR runtime."""
    try:
        index = args.index("--ocr-selftest")
        source = args[index + 1]
        target = args[index + 2]
    except (ValueError, IndexError):
        return 2
    try:
        from .core.document import PdfDocument
        from .core.ocr import OcrEngine

        doc = PdfDocument()
        doc.open(source)
        engine = OcrEngine.instance()
        lines = engine.ocr_document(doc, pages=[0], dpi=200)
        engine.export_text(lines, target)
        with open(target + ".meta", "w", encoding="utf-8") as fh:
            fh.write(f"pages={doc.page_count}\nlines={len(lines)}\n")
        doc.close()
        _log(f"ocr selftest ok lines={len(lines)}")
        return 0
    except Exception as exc:
        _log(f"ocr selftest failed: {exc}")
        return 1


def main() -> int:
    _log(f"start frozen={getattr(sys, 'frozen', False)} args={sys.argv!r}")
    ensure_dirs()
    _log(f"data={DATA_DIR} resources={Path(__file__).resolve().parent}")
    if "--ocr-selftest" in sys.argv:
        return _ocr_selftest(sys.argv)
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "StellarStudio.StellarPDF.1"
            )
        except Exception:
            pass
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("Stellar Studio")
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    font = QFont(ui_font_family(), 9)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET)
    _install_exception_hook()

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    screenshot_path = None
    if "--screenshot" in sys.argv:
        try:
            index = sys.argv.index("--screenshot")
            screenshot_path = sys.argv[index + 1]
            if screenshot_path in args:
                args.remove(screenshot_path)
        except Exception:
            screenshot_path = None
    startup = args[0] if args and os.path.exists(args[0]) else None
    if startup is None and "--demo" in sys.argv:
        demo = Path(__file__).resolve().parent.parent / "sample" / "欢迎使用星澜PDF.pdf"
        if demo.exists():
            startup = str(demo)

    _log(f"startup={startup!r} screenshot={screenshot_path!r}")
    window = MainWindow(startup_path=startup)
    _log("window built")
    if screenshot_path:
        window.resize(1440, 900)
        window.show()
    else:
        # WPS opens its editor maximized; this also guarantees that the
        # titlebar controls and the right edge of the ribbon are on-screen
        # even on smaller/high-DPI displays.
        window.showMaximized()
    _log("window shown")
    if screenshot_path:
        def capture() -> None:
            try:
                _log("capture start")
                saved = window.grab().save(screenshot_path)
                _log(f"capture saved={saved}")
            finally:
                app.quit()

        QTimer.singleShot(2200, capture)
    code = app.exec()
    _log(f"event loop exited {code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
