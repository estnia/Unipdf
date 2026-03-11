#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thumbnail Service - Manages page thumbnail generation.

This service handles thumbnail generation and caching for document pages.
"""

from typing import Dict, Optional, List
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import QObject, pyqtSignal

# PDF engine: PyMuPDF (compatible with both old and new versions)
try:
    import fitz  # PyMuPDF < 1.23
except ImportError:
    import pymupdf as fitz  # PyMuPDF >= 1.23

from pdfviewer.core.document import PDFDocument


class ThumbnailService(QObject):
    """
    Service for managing page thumbnails.

    Generates and caches page thumbnails for navigation.
    """

    thumbnail_ready = pyqtSignal(int, object)  # page_idx, pixmap

    def __init__(self, parent=None, thumb_zoom: float = 0.15):
        """Initialize thumbnail service."""
        super().__init__(parent)
        self._document: Optional[PDFDocument] = None
        self._cache: Dict[int, QPixmap] = {}
        self._thumb_zoom = thumb_zoom

    def set_document(self, document: Optional[PDFDocument]):
        """Set the current document."""
        self._document = document
        self._cache.clear()

    def get_thumbnail(self, page_idx: int) -> Optional[QPixmap]:
        """
        Get thumbnail for a page.

        Args:
            page_idx: Page index

        Returns:
            QPixmap thumbnail or None if failed
        """
        # Check cache
        if page_idx in self._cache:
            return self._cache[page_idx]

        if not self._document or not self._document.doc:
            return None

        # Generate thumbnail
        pixmap = self._render_thumbnail(page_idx)
        if pixmap:
            self._cache[page_idx] = pixmap
            self.thumbnail_ready.emit(page_idx, pixmap)

        return pixmap

    def _render_thumbnail(self, page_idx: int) -> Optional[QPixmap]:
        """Render a single thumbnail."""
        try:
            page = self._document.doc[page_idx]
            mat = fitz.Matrix(self._thumb_zoom, self._thumb_zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)

            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format_RGB888 if pix.n == 3 else QImage.Format_ARGB32
            ).copy()

            return QPixmap.fromImage(img)
        except Exception as e:
            print(f"Thumbnail generation failed (page {page_idx + 1}): {e}")
            return None

    def get_all_thumbnails(self) -> List[Optional[QPixmap]]:
        """Get thumbnails for all pages."""
        if not self._document:
            return []

        result = []
        for i in range(self._document.page_count):
            result.append(self.get_thumbnail(i))
        return result

    def clear_cache(self):
        """Clear thumbnail cache."""
        self._cache.clear()

    def set_zoom(self, zoom: float):
        """Set thumbnail zoom level and clear cache."""
        self._thumb_zoom = zoom
        self.clear_cache()

    def get_zoom(self) -> float:
        """Get current thumbnail zoom level."""
        return self._thumb_zoom

    def is_cached(self, page_idx: int) -> bool:
        """Check if thumbnail is cached."""
        return page_idx in self._cache
