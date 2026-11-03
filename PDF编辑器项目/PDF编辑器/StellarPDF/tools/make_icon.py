"""Generate application PNG/ICO assets from the original SVG logo."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402


def main() -> None:
    svg = ROOT / "app" / "assets" / "logo.svg"
    renderer = QSvgRenderer(str(svg))
    image = QImage(1024, 1024, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, 1024, 1024))
    painter.end()
    png = ROOT / "app" / "assets" / "logo.png"
    image.save(str(png))
    pil = Image.open(png).convert("RGBA")
    ico = ROOT / "app" / "assets" / "app.ico"
    pil.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(png, ico, ico.stat().st_size)


if __name__ == "__main__":
    main()
