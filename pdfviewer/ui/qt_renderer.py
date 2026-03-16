#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qt Renderer - Converts PIL Images to Qt objects.

This module provides functions to convert PIL Image objects
to Qt QPixmap and QImage. This is the UI layer that bridges
the core renderer (PIL) with the Qt UI.
"""

from typing import Optional

from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt

# PIL
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def pil_to_qimage(pil_image: "Image.Image") -> QImage:
    """
    Convert a PIL Image to QImage.

    Args:
        pil_image: PIL Image (RGB or RGBA mode)

    Returns:
        QImage

    Raises:
        ImportError: If PIL is not installed
        ValueError: If image mode is not supported
    """
    if not HAS_PIL:
        raise ImportError("PIL (Pillow) is required")

    if pil_image.mode == "RGB":
        # RGB image
        data = pil_image.tobytes("raw", "RGB")
        qimage = QImage(data, pil_image.width, pil_image.height,
                       pil_image.width * 3, QImage.Format_RGB888)
        return qimage.copy()  # Make a copy to own the data

    elif pil_image.mode == "RGBA":
        # RGBA image with alpha
        data = pil_image.tobytes("raw", "RGBA")
        qimage = QImage(data, pil_image.width, pil_image.height,
                       pil_image.width * 4, QImage.Format_RGBA8888)
        return qimage.copy()

    elif pil_image.mode == "L":
        # Grayscale
        data = pil_image.tobytes("raw", "L")
        qimage = QImage(data, pil_image.width, pil_image.height,
                       pil_image.width, QImage.Format_Grayscale8)
        return qimage.copy()

    else:
        # Convert other modes to RGB
        rgb_image = pil_image.convert("RGB")
        data = rgb_image.tobytes("raw", "RGB")
        qimage = QImage(data, rgb_image.width, rgb_image.height,
                       rgb_image.width * 3, QImage.Format_RGB888)
        return qimage.copy()


def pil_to_qpixmap(pil_image: "Image.Image") -> QPixmap:
    """
    Convert a PIL Image to QPixmap.

    Args:
        pil_image: PIL Image

    Returns:
        QPixmap
    """
    qimage = pil_to_qimage(pil_image)
    return QPixmap.fromImage(qimage)


def qimage_to_pil(qimage: QImage) -> "Image.Image":
    """
    Convert a QImage to PIL Image.

    Args:
        qimage: QImage

    Returns:
        PIL Image (RGB mode)
    """
    if not HAS_PIL:
        raise ImportError("PIL (Pillow) is required")

    # Convert to RGB888 format if needed
    if qimage.format() != QImage.Format_RGB888:
        qimage = qimage.convertToFormat(QImage.Format_RGB888)

    # Get image data
    width = qimage.width()
    height = qimage.height()
    ptr = qimage.bits()
    ptr.setsize(qimage.byteCount())

    # Create PIL Image
    return Image.frombytes("RGB", (width, height), ptr.asstring())


def render_page_to_pixmap(doc_path: str, page_idx: int, zoom: float = 1.0,
                          dpi_scale: float = 1.0,
                          clip_rect: Optional[tuple] = None) -> QPixmap:
    """
    Render a PDF page directly to QPixmap.

    This is a convenience function that combines core renderer
    with Qt conversion.

    Args:
        doc_path: Path to the PDF file
        page_idx: Page index to render
        zoom: Zoom factor
        dpi_scale: DPI scaling factor
        clip_rect: Optional clipping rectangle

    Returns:
        QPixmap of the rendered page
    """
    from pdfviewer.core.renderer_base import render_page_to_pil

    pil_image = render_page_to_pil(doc_path, page_idx, zoom, dpi_scale, clip_rect)
    return pil_to_qpixmap(pil_image)


def render_thumbnail_to_pixmap(doc_path: str, page_idx: int,
                               max_size: int = 128) -> QPixmap:
    """
    Render a page thumbnail to QPixmap.

    Args:
        doc_path: Path to the PDF file
        page_idx: Page index to render
        max_size: Maximum dimension of the thumbnail

    Returns:
        QPixmap thumbnail
    """
    from pdfviewer.core.renderer_base import render_thumbnail_to_pil

    pil_image = render_thumbnail_to_pil(doc_path, page_idx, max_size)
    return pil_to_qpixmap(pil_image)


def create_pixmap_from_bytes(image_data: bytes, format: str = "PNG") -> QPixmap:
    """
    Create QPixmap from image bytes.

    Args:
        image_data: Image data as bytes
        format: Image format ("PNG", "JPEG", etc.)

    Returns:
        QPixmap
    """
    if not HAS_PIL:
        # Fallback: try direct QPixmap loading
        pixmap = QPixmap()
        pixmap.loadFromData(image_data)
        return pixmap

    # Use PIL to load and convert
    from io import BytesIO
    pil_image = Image.open(BytesIO(image_data))
    return pil_to_qpixmap(pil_image)
