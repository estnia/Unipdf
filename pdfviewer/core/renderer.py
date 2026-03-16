#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rendering functions for PDF pages.

This module provides rendering functions that convert PDF pages
to pixmaps. These functions have minimal dependencies and can be used
in both UI and worker threads.

Architecture:
- pdfviewer.core.renderer_base: Pure Python rendering (PIL Image)
- pdfviewer.ui.qt_renderer: Qt conversion utilities
- pdfviewer.core.renderer: Backward-compatible Qt-based rendering (this file)

Note: This file retains Qt dependency for backward compatibility.
For pure Python rendering, use renderer_base.
"""

from typing import Optional, Tuple, Union
import os

# PDF engine: PyMuPDF (compatible with both old and new versions)
try:
    import fitz  # PyMuPDF < 1.23
except ImportError:
    import pymupdf as fitz  # PyMuPDF >= 1.23

# Qt imports for pixmap creation
from PyQt5.QtGui import QImage, QPixmap


def _get_doc_path(doc: Union[fitz.Document, str]) -> str:
    """Get document path from Document or string."""
    if isinstance(doc, str):
        return doc
    # Try to get path from Document
    if hasattr(doc, 'name') and doc.name:
        return doc.name
    raise ValueError("Cannot determine document path")


def render_page(doc: Union[fitz.Document, str], page_idx: int, zoom: float = 1.0,
                dpi_scale: float = 1.0, clip_rect: Optional[Tuple] = None) -> QPixmap:
    """
    Render a PDF page to a QPixmap.

    Args:
        doc: fitz.Document instance or document path string
        page_idx: Page index to render
        zoom: Zoom factor (1.0 = 100%)
        dpi_scale: DPI scaling factor
        clip_rect: Optional clipping rectangle (x, y, w, h) in screen coordinates

    Returns:
        QPixmap of the rendered page
    """
    # If doc is a path string, use the new renderer_base path
    if isinstance(doc, str) and os.path.exists(doc):
        try:
            from pdfviewer.core.renderer_base import render_page_to_pil
            from pdfviewer.ui.qt_renderer import pil_to_qpixmap
            pil_image = render_page_to_pil(doc, page_idx, zoom, dpi_scale, clip_rect)
            return pil_to_qpixmap(pil_image)
        except ImportError:
            # Fallback: open document and use legacy path
            doc = fitz.open(doc)
            try:
                return _render_page_legacy(doc, page_idx, zoom, dpi_scale, clip_rect)
            finally:
                doc.close()

    # Legacy path for fitz.Document
    return _render_page_legacy(doc, page_idx, zoom, dpi_scale, clip_rect)


def _render_page_legacy(doc: fitz.Document, page_idx: int, zoom: float = 1.0,
                        dpi_scale: float = 1.0,
                        clip_rect: Optional[Tuple] = None) -> QPixmap:
    """Legacy rendering using fitz.Document directly."""
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


def render_thumbnail(doc: Union[fitz.Document, str], page_idx: int,
                     max_size: int = 128) -> QPixmap:
    """
    Render a page thumbnail.

    Args:
        doc: fitz.Document instance or document path string
        page_idx: Page index to render
        max_size: Maximum dimension of the thumbnail

    Returns:
        QPixmap thumbnail
    """
    # If doc is a path string, use the new renderer_base path
    if isinstance(doc, str) and os.path.exists(doc):
        try:
            from pdfviewer.core.renderer_base import render_thumbnail_to_pil
            from pdfviewer.ui.qt_renderer import pil_to_qpixmap
            pil_image = render_thumbnail_to_pil(doc, page_idx, max_size)
            return pil_to_qpixmap(pil_image)
        except ImportError:
            doc = fitz.open(doc)
            try:
                return _render_thumbnail_legacy(doc, page_idx, max_size)
            finally:
                doc.close()

    return _render_thumbnail_legacy(doc, page_idx, max_size)


def _render_thumbnail_legacy(doc: fitz.Document, page_idx: int,
                             max_size: int = 128) -> QPixmap:
    """Legacy thumbnail rendering."""
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


def render_page_to_image(doc: Union[fitz.Document, str], page_idx: int,
                         zoom: float = 1.0, dpi_scale: float = 1.0) -> QImage:
    """
    Render a PDF page to a QImage.

    Args:
        doc: fitz.Document instance or document path string
        page_idx: Page index to render
        zoom: Zoom factor
        dpi_scale: DPI scaling factor

    Returns:
        QImage of the rendered page
    """
    # If doc is a path string, use the new renderer_base path
    if isinstance(doc, str) and os.path.exists(doc):
        try:
            from pdfviewer.core.renderer_base import render_page_to_pil
            from pdfviewer.ui.qt_renderer import pil_to_qimage
            pil_image = render_page_to_pil(doc, page_idx, zoom, dpi_scale)
            return pil_to_qimage(pil_image)
        except ImportError:
            doc = fitz.open(doc)
            try:
                return _render_page_to_image_legacy(doc, page_idx, zoom, dpi_scale)
            finally:
                doc.close()

    return _render_page_to_image_legacy(doc, page_idx, zoom, dpi_scale)


def _render_page_to_image_legacy(doc: fitz.Document, page_idx: int,
                                 zoom: float = 1.0, dpi_scale: float = 1.0) -> QImage:
    """Legacy QImage rendering."""
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


def get_page_text_dict(doc: Union[fitz.Document, str], page_idx: int) -> dict:
    """
    Get text dictionary for a page.

    Args:
        doc: fitz.Document instance or document path string
        page_idx: Page index

    Returns:
        Dictionary with text information
    """
    if isinstance(doc, str):
        from pdfviewer.core.renderer_base import get_page_text_dict as _get_page_text_dict
        return _get_page_text_dict(doc, page_idx)

    page = doc[page_idx]
    return page.get_text("dict")


def get_page_raw_text(doc: Union[fitz.Document, str], page_idx: int) -> dict:
    """
    Get raw character-level text information for a page.

    Args:
        doc: fitz.Document instance or document path string
        page_idx: Page index

    Returns:
        Dictionary with raw text information including character positions
    """
    if isinstance(doc, str):
        from pdfviewer.core.renderer_base import get_page_raw_text as _get_page_raw_text
        return _get_page_raw_text(doc, page_idx)

    page = doc[page_idx]
    return page.get_text("rawdict")


def search_page_text(doc: Union[fitz.Document, str], page_idx: int,
                     query: str) -> list:
    """
    Search for text on a page.

    Args:
        doc: fitz.Document instance or document path string
        page_idx: Page index
        query: Search query string

    Returns:
        List of rectangles where text was found
    """
    if isinstance(doc, str):
        from pdfviewer.core.renderer_base import search_page_text as _search_page_text
        return _search_page_text(doc, page_idx, query)

    page = doc[page_idx]
    return page.search_for(query)
