"""Small Qt image conversion helpers."""
from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage


def qimage_png(image: QImage) -> bytes:
    """Encode a QImage as PNG bytes without a temporary file."""
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    try:
        image.save(buffer, "PNG")
    finally:
        buffer.close()
    return bytes(data)
