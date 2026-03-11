#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rendering functions for PDF pages.

This module provides pure rendering functions that convert PDF pages
to pixmaps. These functions have minimal dependencies and can be used
in both UI and worker threads.
"""

from typing import Optional, Tuple

# PDF engine: PyMuPDF (compatible with both old and new versions)
try:
    import fitz  # PyMuPDF < 1.23
except ImportError:
    import pymupdf as fitz  # PyMuPDF >= 1.23

# Qt imports for pixmap creation
from PyQt5.QtGui import QImage, QPixmap


def render_page(doc: fitz.Document, page_idx: int, zoom: float = 1.0,
                dpi_scale: float = 1.0, clip_rect: Optional[Tuple] = None) -> QPixmap:
    """
    Render a PDF page to a QPixmap.

    Args:
        doc: fitz.Document instance
        page_idx: Page index to render
        zoom: Zoom factor (1.0 = 100%)
        dpi_scale: DPI scaling factor
        clip_rect: Optional clipping rectangle (x, y, w, h) in screen coordinates

    Returns:
        QPixmap of the rendered page
    """
    page = doc[page_idx]
    mat = fitz.Matrix(zoom * dpi_scale, zoom * dpi_scale)

    if clip_rect and zoom > 2.0:
        # Calculate PDF coordinates for clipping
        x, y, w, h = clip_rect
        pdf_x = x / (zoom * dpi_scale)
        pdf_y = y / (zoom * dpi_scale)
        pdf_w = w / (zoom * dpi_scale)
        pdf_h = h / (zoom * dpi_scale)

        clip = fitz.Rect(pdf_x, pdf_y, pdf_x + pdf_w, pdf_y + pdf_h)
        pix = page.get_pixmap(matrix=mat, alpha=False,
                             colorspace=fitz.csRGB, clip=clip)
    else:
        pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)

    # Convert to QImage
    img = QImage(
        pix.samples,
        pix.width,
        pix.height,
        pix.stride,
        QImage.Format_RGB888 if pix.n == 3 else QImage.Format_ARGB32
    ).copy()

    return QPixmap.fromImage(img)


def render_thumbnail(doc: fitz.Document, page_idx: int,
                     max_size: int = 128) -> QPixmap:
    """
    Render a page thumbnail.

    Args:
        doc: fitz.Document instance
        page_idx: Page index to render
        max_size: Maximum dimension of the thumbnail

    Returns:
        QPixmap thumbnail
    """
    page = doc[page_idx]
    rect = page.rect

    # Calculate scale to fit within max_size
    scale = min(max_size / rect.width, max_size / rect.height)
    mat = fitz.Matrix(scale, scale)

    pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)

    img = QImage(
        pix.samples,
        pix.width,
        pix.height,
        pix.stride,
        QImage.Format_RGB888 if pix.n == 3 else QImage.Format_ARGB32
    ).copy()

    return QPixmap.fromImage(img)


def render_page_to_image(doc: fitz.Document, page_idx: int,
                         zoom: float = 1.0, dpi_scale: float = 1.0) -> QImage:
    """
    Render a PDF page to a QImage.

    Args:
        doc: fitz.Document instance
        page_idx: Page index to render
        zoom: Zoom factor
        dpi_scale: DPI scaling factor

    Returns:
        QImage of the rendered page
    """
    page = doc[page_idx]
    mat = fitz.Matrix(zoom * dpi_scale, zoom * dpi_scale)
    pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)

    return QImage(
        pix.samples,
        pix.width,
        pix.height,
        pix.stride,
        QImage.Format_RGB888 if pix.n == 3 else QImage.Format_ARGB32
    ).copy()


def get_page_text_dict(doc: fitz.Document, page_idx: int) -> dict:
    """
    Get text dictionary for a page.

    Args:
        doc: fitz.Document instance
        page_idx: Page index

    Returns:
        Dictionary with text information
    """
    page = doc[page_idx]
    return page.get_text("dict")


def get_page_raw_text(doc: fitz.Document, page_idx: int) -> dict:
    """
    Get raw character-level text information for a page.

    Args:
        doc: fitz.Document instance
        page_idx: Page index

    Returns:
        Dictionary with raw text information including character positions
    """
    page = doc[page_idx]
    return page.get_text("rawdict")


def search_page_text(doc: fitz.Document, page_idx: int,
                     query: str) -> list:
    """
    Search for text on a page.

    Args:
        doc: fitz.Document instance
        page_idx: Page index
        query: Search query string

    Returns:
        List of rectangles where text was found
    """
    page = doc[page_idx]
    return page.search_for(query)
