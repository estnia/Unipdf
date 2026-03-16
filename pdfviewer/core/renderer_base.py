#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base Renderer - Pure Python PDF rendering functions.

This module provides rendering functions that do not depend on Qt.
It returns PIL.Image objects which can be converted to Qt pixmaps
by the UI layer.

This separation allows the core layer to be tested without Qt dependencies.
"""

from typing import Optional, Tuple, Dict, Any
from io import BytesIO

# PDF engine: PyMuPDF (compatible with both old and new versions)
try:
    import fitz  # PyMuPDF < 1.23
except ImportError:
    import pymupdf as fitz  # PyMuPDF >= 1.23

# PIL for image handling
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def render_page_to_pil(doc_path: str, page_idx: int, zoom: float = 1.0,
                       dpi_scale: float = 1.0,
                       clip_rect: Optional[Tuple[float, float, float, float]] = None) -> "Image.Image":
    """
    Render a PDF page to a PIL Image.

    Args:
        doc_path: Path to the PDF file
        page_idx: Page index to render
        zoom: Zoom factor (1.0 = 100%)
        dpi_scale: DPI scaling factor
        clip_rect: Optional clipping rectangle (x, y, w, h) in screen coordinates

    Returns:
        PIL Image of the rendered page (RGB mode)

    Raises:
        ImportError: If PIL is not installed
        RuntimeError: If rendering fails
    """
    if not HAS_PIL:
        raise ImportError("PIL (Pillow) is required for rendering. "
                          "Install with: pip install Pillow")

    doc = fitz.open(doc_path)
    try:
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

        # Convert fitz pixmap to PIL Image
        # fitz pixmap samples are in RGB format
        img = Image.frombytes(
            "RGB",
            (pix.width, pix.height),
            pix.samples
        )
        return img
    finally:
        doc.close()


def render_thumbnail_to_pil(doc_path: str, page_idx: int,
                            max_size: int = 128) -> "Image.Image":
    """
    Render a page thumbnail to PIL Image.

    Args:
        doc_path: Path to the PDF file
        page_idx: Page index to render
        max_size: Maximum dimension of the thumbnail

    Returns:
        PIL Image thumbnail (RGB mode)

    Raises:
        ImportError: If PIL is not installed
    """
    if not HAS_PIL:
        raise ImportError("PIL (Pillow) is required for rendering.")

    doc = fitz.open(doc_path)
    try:
        page = doc[page_idx]
        rect = page.rect

        # Calculate scale to fit within max_size
        scale = min(max_size / rect.width, max_size / rect.height)
        mat = fitz.Matrix(scale, scale)

        pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)

        img = Image.frombytes(
            "RGB",
            (pix.width, pix.height),
            pix.samples
        )
        return img
    finally:
        doc.close()


def render_page_to_bytes(doc_path: str, page_idx: int, zoom: float = 1.0,
                         dpi_scale: float = 1.0,
                         format: str = "png") -> bytes:
    """
    Render a PDF page to image bytes.

    Args:
        doc_path: Path to the PDF file
        page_idx: Page index to render
        zoom: Zoom factor
        dpi_scale: DPI scaling factor
        format: Image format ("png", "jpeg", "bmp", etc.)

    Returns:
        Image data as bytes
    """
    img = render_page_to_pil(doc_path, page_idx, zoom, dpi_scale)
    buffer = BytesIO()
    img.save(buffer, format=format.upper())
    return buffer.getvalue()


def get_page_info(doc_path: str, page_idx: int) -> Dict[str, Any]:
    """
    Get information about a page.

    Args:
        doc_path: Path to the PDF file
        page_idx: Page index

    Returns:
        Dictionary with page information:
        - width: Page width in points
        - height: Page height in points
        - rotation: Page rotation
        - number: Page number (1-based)
    """
    doc = fitz.open(doc_path)
    try:
        page = doc[page_idx]
        rect = page.rect
        return {
            "width": rect.width,
            "height": rect.height,
            "rotation": page.rotation,
            "number": page_idx + 1,
            "index": page_idx
        }
    finally:
        doc.close()


def get_document_info(doc_path: str) -> Dict[str, Any]:
    """
    Get information about a PDF document.

    Args:
        doc_path: Path to the PDF file

    Returns:
        Dictionary with document information:
        - page_count: Number of pages
        - metadata: Document metadata dict
        - title: Document title
        - author: Document author
    """
    doc = fitz.open(doc_path)
    try:
        metadata = doc.metadata
        return {
            "page_count": len(doc),
            "metadata": metadata,
            "title": metadata.get("title", ""),
            "author": metadata.get("author", ""),
            "subject": metadata.get("subject", ""),
            "creator": metadata.get("creator", ""),
            "producer": metadata.get("producer", "")
        }
    finally:
        doc.close()


# Text extraction functions (no Qt dependency)

def get_page_text_dict(doc_path: str, page_idx: int) -> dict:
    """
    Get text dictionary for a page.

    Args:
        doc_path: Path to the PDF file
        page_idx: Page index

    Returns:
        Dictionary with text information
    """
    doc = fitz.open(doc_path)
    try:
        page = doc[page_idx]
        return page.get_text("dict")
    finally:
        doc.close()


def get_page_raw_text(doc_path: str, page_idx: int) -> dict:
    """
    Get raw character-level text information for a page.

    Args:
        doc_path: Path to the PDF file
        page_idx: Page index

    Returns:
        Dictionary with raw text information including character positions
    """
    doc = fitz.open(doc_path)
    try:
        page = doc[page_idx]
        return page.get_text("rawdict")
    finally:
        doc.close()


def search_page_text(doc_path: str, page_idx: int, query: str) -> list:
    """
    Search for text on a page.

    Args:
        doc_path: Path to the PDF file
        page_idx: Page index
        query: Search query string

    Returns:
        List of rectangles where text was found
    """
    doc = fitz.open(doc_path)
    try:
        page = doc[page_idx]
        return page.search_for(query)
    finally:
        doc.close()


def extract_page_text(doc_path: str, page_idx: int) -> str:
    """
    Extract plain text from a page.

    Args:
        doc_path: Path to the PDF file
        page_idx: Page index

    Returns:
        Plain text content of the page
    """
    doc = fitz.open(doc_path)
    try:
        page = doc[page_idx]
        return page.get_text()
    finally:
        doc.close()
