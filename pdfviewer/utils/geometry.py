#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Geometry and coordinate transformation utilities.

This module provides functions for converting between PDF coordinates,
screen coordinates, and UI coordinates.
"""

from PyQt5.QtCore import QRectF


def compute_page_transform(page_label, zoom_factor: float):
    """
    Compute coordinate transformation parameters for a page.

    Args:
        page_label: The QLabel displaying the page
        zoom_factor: Current zoom factor

    Returns:
        Dictionary with transform parameters or None if invalid
    """
    if not page_label:
        return None

    # DPI scale (logical pixel scale)
    dpi_scale = page_label.logicalDpiX() / 96.0

    pixmap = page_label.pixmap()
    if not pixmap:
        return None

    # Account for device pixel ratio
    pixmap_logical_w = pixmap.width() / pixmap.devicePixelRatio()
    pixmap_logical_h = pixmap.height() / pixmap.devicePixelRatio()

    contents = page_label.contentsRect()

    # Calculate centering offset
    offset_x = (contents.width() - pixmap_logical_w) / 2.0
    offset_y = (contents.height() - pixmap_logical_h) / 2.0
    offset_x = max(0.0, offset_x)
    offset_y = max(0.0, offset_y)

    # Unified scale: zoom * dpi_scale
    scale = float(zoom_factor) * float(dpi_scale)

    return {
        "scale": scale,
        "offset_x": offset_x,
        "offset_y": offset_y,
        "contents": contents,
        "dpi_scale": dpi_scale
    }


def screen_to_pdf_point(screen_pos, page_label, zoom_factor: float) -> tuple:
    """
    Convert screen coordinates to PDF coordinates.

    PyMuPDF origin is at top-left, Y-axis points down.

    Args:
        screen_pos: QPoint in screen coordinates
        page_label: The QLabel displaying the page
        zoom_factor: Current zoom factor

    Returns:
        Tuple of (pdf_x, pdf_y)
    """
    t = compute_page_transform(page_label, zoom_factor)
    if not t:
        return (0.0, 0.0)

    sx = float(screen_pos.x())
    sy = float(screen_pos.y())

    contents = t["contents"]
    scale = t["scale"]
    ox = t["offset_x"]
    oy = t["offset_y"]

    pdf_x = (sx - contents.left() - ox) / scale
    pdf_y = (sy - contents.top() - oy) / scale

    return (pdf_x, pdf_y)


def pdf_to_screen_rect(pdf_rect: tuple, page_label, zoom_factor: float) -> QRectF:
    """
    Convert PDF rectangle to screen rectangle.

    Args:
        pdf_rect: Tuple of (x0, y0, x1, y1) in PDF coordinates
        page_label: The QLabel displaying the page
        zoom_factor: Current zoom factor

    Returns:
        QRectF in screen coordinates
    """
    t = compute_page_transform(page_label, zoom_factor)
    if not t:
        return QRectF()

    x0, y0, x1, y1 = pdf_rect
    scale = t["scale"]
    ox = t["offset_x"]
    oy = t["offset_y"]
    contents = t["contents"]

    ui_x0 = x0 * scale + contents.left() + ox
    ui_y0 = y0 * scale + contents.top() + oy
    ui_x1 = x1 * scale + contents.left() + ox
    ui_y1 = y1 * scale + contents.top() + oy

    return QRectF(ui_x0, ui_y0, ui_x1 - ui_x0, ui_y1 - ui_y0)


def update_words_ui_rect(words: list, page_label, zoom_factor: float):
    """
    Pre-compute UI rectangles for all words to accelerate hit-testing.

    Args:
        words: List of word dictionaries with "bbox" keys
        page_label: The QLabel displaying the page
        zoom_factor: Current zoom factor
    """
    t = compute_page_transform(page_label, zoom_factor)
    if not t:
        return

    scale = t["scale"]
    ox = t["offset_x"]
    oy = t["offset_y"]
    contents = t["contents"]

    for w in words:
        x0, y0, x1, y1 = w["bbox"]
        # PDF -> UI coordinate conversion
        ui_x0 = x0 * scale + contents.left() + ox
        ui_y0 = y0 * scale + contents.top() + oy
        ui_x1 = x1 * scale + contents.left() + ox
        ui_y1 = y1 * scale + contents.top() + oy
        w["ui_rect"] = QRectF(ui_x0, ui_y0, ui_x1 - ui_x0, ui_y1 - ui_y0)


def get_word_at_point(pdf_point: tuple, ui_point: tuple, words: list) -> int:
    """
    Get the word index at a given point.

    Args:
        pdf_point: (x, y) in PDF coordinates
        ui_point: (x, y) in UI coordinates, or None
        words: List of word dictionaries

    Returns:
        Word index or -1 if not found
    """
    eps = 0.5  # Tolerance in PDF units

    # Prefer UI rect check
    if ui_point is not None:
        ux, uy = ui_point
        for i, w in enumerate(words):
            r = w.get("ui_rect")
            if r is not None and r.contains(float(ux), float(uy)):
                return i

    # Fall back to PDF space
    px, py = pdf_point
    for i, w in enumerate(words):
        x0, y0, x1, y1 = w["bbox"]
        if (x0 - eps) <= px <= (x1 + eps) and (y0 - eps) <= py <= (y1 + eps):
            return i

    # Find nearest
    best_i = -1
    best_d2 = None
    for i, w in enumerate(words):
        x0, y0, x1, y1 = w["bbox"]
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        d2 = (cx - px) ** 2 + (cy - py) ** 2
        if best_d2 is None or d2 < best_d2:
            best_d2, best_i = d2, i

    return best_i if best_d2 is not None and best_d2 < 2500 else -1


def get_char_at_point(pdf_point: tuple, ui_point: tuple, text_chars: list) -> int:
    """
    Get the character index at a given point (character-level precision).

    Args:
        pdf_point: (x, y) in PDF coordinates
        ui_point: (x, y) in UI coordinates, or None
        text_chars: List of character info dictionaries

    Returns:
        Character index or -1 if not found
    """
    eps = 0.5
    px, py = pdf_point

    # Prefer UI rect check
    if ui_point is not None:
        ux, uy = ui_point
        for i, char_info in enumerate(text_chars):
            r = char_info.get("ui_rect")
            if r is not None and r.contains(float(ux), float(uy)):
                return i

    # Fall back to PDF space
    for i, char_info in enumerate(text_chars):
        x0, y0, x1, y1 = char_info["bbox"]
        if (x0 - eps) <= px <= (x1 + eps) and (y0 - eps) <= py <= (y1 + eps):
            return i

    # Find nearest character
    best_i = -1
    best_d = float('inf')
    for i, char_info in enumerate(text_chars):
        x0, y0, x1, y1 = char_info["bbox"]
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        d = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
        if d < best_d:
            best_d = d
            best_i = i

    return best_i if best_d < 20 else -1
