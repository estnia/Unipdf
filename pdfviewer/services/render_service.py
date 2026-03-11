#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render Service - Manages rendering operations.

This service coordinates rendering workers and manages the render queue,
L2 cache, and high-DPI rendering.
"""

from typing import Dict, Optional, Callable
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QPixmap

from pdfviewer.workers.render_worker import RenderWorker


class RenderService(QObject):
    """
    Service for managing PDF page rendering.

    Coordinates RenderWorker instances and manages rendering queues
    and caches.
    """

    page_rendered = pyqtSignal(int, int, float, object)  # page_idx, zoom, dpi, pixmap
    render_error = pyqtSignal(int, str)  # page_idx, error_msg

    def __init__(self, parent=None):
        """Initialize render service."""
        super().__init__(parent)
        self._active_workers: Dict[int, RenderWorker] = {}
        self._l2_cache: Dict[int, Dict[int, QPixmap]] = {}  # zoom_percent -> {page_idx -> pixmap}
        self._base_pixmaps: Dict[int, QPixmap] = {}
        self._doc_path: Optional[str] = None

    def set_document(self, doc_path: str):
        """Set the document path for rendering."""
        self.cancel_all()
        self._doc_path = doc_path
        self._l2_cache.clear()
        self._base_pixmaps.clear()

    def clear_document(self):
        """Clear document and cancel all renders."""
        self.cancel_all()
        self._doc_path = None
        self._l2_cache.clear()
        self._base_pixmaps.clear()

    def render_page(self, page_idx: int, zoom: float, dpi_scale: float,
                    device_ratio: float, clip_rect=None, viewport_size=None):
        """
        Queue a page for rendering.

        Args:
            page_idx: Page index to render
            zoom: Zoom factor
            dpi_scale: DPI scaling factor
            device_ratio: Device pixel ratio
            clip_rect: Optional clipping rectangle
            viewport_size: Optional viewport size
        """
        if not self._doc_path:
            return

        # Cancel any existing worker for this page
        self.cancel_page(page_idx)

        # Check L2 cache
        zoom_percent = int(zoom * 100)
        if zoom_percent in self._l2_cache:
            if page_idx in self._l2_cache[zoom_percent]:
                pixmap = self._l2_cache[zoom_percent][page_idx]
                self.page_rendered.emit(page_idx, zoom_percent, dpi_scale, pixmap)
                return

        # Create and start worker
        worker = RenderWorker(
            self._doc_path, page_idx, zoom, dpi_scale, device_ratio,
            clip_rect, viewport_size
        )
        worker.finished.connect(self._on_render_finished)
        worker.error.connect(self._on_render_error)

        self._active_workers[page_idx] = worker
        worker.start()

    def _on_render_finished(self, page_idx: int, zoom_percent: int,
                            dpi_scale: float, pixmap: QPixmap):
        """Handle render completion."""
        if page_idx in self._active_workers:
            del self._active_workers[page_idx]

        self._add_to_cache(page_idx, zoom_percent, pixmap)
        self._base_pixmaps[page_idx] = pixmap
        self.page_rendered.emit(page_idx, zoom_percent, dpi_scale, pixmap)

    def _on_render_error(self, page_idx: int, error_msg: str):
        """Handle render error."""
        if page_idx in self._active_workers:
            del self._active_workers[page_idx]
        self.render_error.emit(page_idx, error_msg)

    def _add_to_cache(self, page_idx: int, zoom_percent: int, pixmap: QPixmap):
        """Add rendered pixmap to L2 cache."""
        if zoom_percent not in self._l2_cache:
            self._l2_cache[zoom_percent] = {}
        self._l2_cache[zoom_percent][page_idx] = pixmap.copy()

    def get_cached_pixmap(self, page_idx: int, zoom_percent: int) -> Optional[QPixmap]:
        """Get cached pixmap if available."""
        if zoom_percent in self._l2_cache:
            return self._l2_cache[zoom_percent].get(page_idx)
        return None

    def has_cached(self, page_idx: int, zoom_percent: int) -> bool:
        """Check if page is cached at given zoom."""
        if zoom_percent in self._l2_cache:
            return page_idx in self._l2_cache[zoom_percent]
        return False

    def cancel_page(self, page_idx: int):
        """Cancel rendering for a specific page."""
        if page_idx in self._active_workers:
            worker = self._active_workers[page_idx]
            worker.stop()
            del self._active_workers[page_idx]

    def cancel_all(self):
        """Cancel all active rendering workers."""
        for worker in list(self._active_workers.values()):
            worker.stop()
        self._active_workers.clear()

    def clear_cache(self, zoom_percent: Optional[int] = None):
        """
        Clear render cache.

        Args:
            zoom_percent: Specific zoom level to clear, or None for all
        """
        if zoom_percent is None:
            self._l2_cache.clear()
        elif zoom_percent in self._l2_cache:
            del self._l2_cache[zoom_percent]

    def get_base_pixmap(self, page_idx: int) -> Optional[QPixmap]:
        """Get base pixmap for a page."""
        return self._base_pixmaps.get(page_idx)

    def set_base_pixmap(self, page_idx: int, pixmap: QPixmap):
        """Set base pixmap for a page."""
        self._base_pixmaps[page_idx] = pixmap
