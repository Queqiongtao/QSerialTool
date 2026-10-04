"""从代码生成应用图标（PNG + 多尺寸 ICO）。

图标是程序化绘制的几何图形，不依赖外部素材。修改图形后重新运行本脚本，
把生成结果与脚本一起提交：

    .\.venv\Scripts\python.exe scripts\generate_icon.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
    QPolygonF,
)

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "qserialtool" / "ui" / "assets"
ICO_SIZES = (16, 32, 48, 256)
ICO_MAX_EDGE = 256
CORNER_RADIUS = 56.0
STROKE_WIDTH = 20.0


def _draw_icon(size: int) -> QImage:
    """绘制圆角渐变底 + 白色双向箭头，代表串口收发。"""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    scale = size / 256.0
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gradient = QLinearGradient(0.0, 0.0, float(size), float(size))
        gradient.setColorAt(0.0, QColor("#3B82F6"))
        gradient.setColorAt(1.0, QColor("#1D4ED8"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(
            QRectF(0.0, 0.0, float(size), float(size)),
            CORNER_RADIUS * scale,
            CORNER_RADIUS * scale,
        )

        pen = QPen(QColor("#FFFFFF"))
        pen.setWidthF(STROKE_WIDTH * scale)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(
            QPointF(76.0 * scale, 104.0 * scale),
            QPointF(172.0 * scale, 104.0 * scale),
        )
        painter.drawLine(
            QPointF(180.0 * scale, 152.0 * scale),
            QPointF(84.0 * scale, 152.0 * scale),
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(158.0 * scale, 80.0 * scale),
                    QPointF(196.0 * scale, 104.0 * scale),
                    QPointF(158.0 * scale, 128.0 * scale),
                ]
            )
        )
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(98.0 * scale, 128.0 * scale),
                    QPointF(60.0 * scale, 152.0 * scale),
                    QPointF(98.0 * scale, 176.0 * scale),
                ]
            )
        )
    finally:
        painter.end()
    return image


def _png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("无法编码 PNG 图标。")
    return bytes(buffer.data())


def _ico_edge(size: int) -> int:
    """ICO 目录项用 0 表示 256 像素。"""
    return 0 if size >= ICO_MAX_EDGE else size


def _write_ico(path: Path, images: tuple[tuple[int, bytes], ...]) -> None:
    """写出 ICO 容器；每个尺寸以 PNG 编码条目存储。"""
    offset = 6 + 16 * len(images)
    entries = bytearray()
    payload = bytearray()
    for size, data in images:
        edge = _ico_edge(size)
        entries += struct.pack(
            "<BBBBHHII", edge, edge, 0, 0, 1, 32, len(data), offset + len(payload)
        )
        payload += data
    path.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + bytes(entries) + bytes(payload))


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    ASSETS.mkdir(parents=True, exist_ok=True)
    master = _draw_icon(256)
    if not master.save(str(ASSETS / "qserialtool.png"), "PNG"):
        raise RuntimeError("无法写出 PNG 图标。")
    _write_ico(
        ASSETS / "qserialtool.ico",
        tuple((size, _png_bytes(_draw_icon(size))) for size in ICO_SIZES),
    )
    del app
    print(f"wrote {ASSETS / 'qserialtool.png'}")
    print(f"wrote {ASSETS / 'qserialtool.ico'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
