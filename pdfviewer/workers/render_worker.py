#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render Worker Thread - Handles asynchronous PDF page rendering.

This module provides a QThread-based worker for rendering PDF pages
in the background, supporting both full-page and clipped viewport rendering.
"""

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap

# PDF engine: PyMuPDF (compatible with both old and new versions)
try:
    import fitz  # PyMuPDF < 1.23
except ImportError:
    import pymupdf as fitz  # PyMuPDF >= 1.23


class RenderWorker(QThread):
    """
    P0/P1: Asynchronous rendering worker thread.
    Supports full-page and viewport-clipped rendering.
    """

    # Signals: page_idx, zoom_percent, dpi_scale, pixmap
    finished = pyqtSignal(int, int, float, object)
    # Signals: page_idx, error_msg
    error = pyqtSignal(int, str)

    def __init__(self, doc_path: str, page_idx: int, zoom: float,
                 dpi_scale: float, device_ratio: float,
                 clip_rect=None, viewport_size=None):
        """
        Initialize render worker.

        Args:
            doc_path: PDF file path
            page_idx: Page number to render
            zoom: Zoom factor
            dpi_scale: DPI scaling factor
            device_ratio: Device pixel ratio
            clip_rect: P1: Clipping region (x, y, w, h) for partial rendering,
                      None means full page
            viewport_size: P1: Viewport size (w, h) for clip calculation
        """
        super().__init__()
        self.doc_path = doc_path
        self.page_idx = page_idx
        self.zoom = zoom
        self.dpi_scale = dpi_scale
        self.device_ratio = device_ratio
        self.clip_rect = clip_rect
        self.viewport_size = viewport_size
        self._is_running = True
        self._is_clipped = False

    def run(self):
        """Render page in background thread."""
        try:
            # Open independent document instance per thread (thread-safe)
            doc = fitz.open(self.doc_path)
            page = doc[self.page_idx]

            # Create scale matrix
            mat = fitz.Matrix(self.zoom * self.dpi_scale, self.zoom * self.dpi_scale)

            # P1: Viewport clipping - only render visible region at high zoom
            if self.clip_rect and self.zoom > 2.0:
                # Calculate clipping region (PDF coordinates)
                x, y, w, h = self.clip_rect
                # Convert screen coordinates to PDF coordinates
                pdf_x = x / (self.zoom * self.dpi_scale)
                pdf_y = y / (self.zoom * self.dpi_scale)
                pdf_w = w / (self.zoom * self.dpi_scale)
                pdf_h = h / (self.zoom * self.dpi_scale)

                clip = fitz.Rect(pdf_x, pdf_y, pdf_x + pdf_w, pdf_y + pdf_h)
                pix = page.get_pixmap(matrix=mat, alpha=False,
                                     colorspace=fitz.csRGB, clip=clip)
                self._is_clipped = True
            else:
                # Normal full-page rendering
                pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)
                self._is_clipped = False

            # Convert to QImage
            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format_RGB888 if pix.n == 3 else QImage.Format_ARGB32
            ).copy()

            # Convert to QPixmap
            qpixmap = QPixmap.fromImage(img)
            qpixmap.setDevicePixelRatio(self.device_ratio)

            doc.close()

            if self._is_running:
                zoom_percent = int(self.zoom * 100)
                self.finished.emit(self.page_idx, zoom_percent, self.dpi_scale, qpixmap)

        except Exception as e:
            if self._is_running:
                self.error.emit(self.page_idx, str(e))

    def stop(self):
        """Stop rendering - safely wait for thread completion."""
        self._is_running = False
        # Wait up to 5 seconds
        if not self.wait(5000):
            # Force terminate if still running
            self.terminate()
            self.wait(1000)

    def is_clipped(self) -> bool:
        """Return True if this was a clipped render."""
        return self._is_clipped
