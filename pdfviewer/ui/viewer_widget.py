#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Viewer Widget - PDF document viewer component.

This widget displays PDF pages and handles:
- Page rendering and display
- Text selection (mouse drag)
- Selection highlighting
- Context menu (copy, highlight, underline)
- Annotation hotspot detection and hover tooltips
"""

from typing import Optional, Tuple, List
import time
from PyQt5.QtWidgets import (
    QWidget, QLabel, QScrollArea, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QMenu, QAction, QMessageBox, QApplication, QShortcut
)
from PyQt5.QtCore import Qt, QRect, QRectF, QPoint, QSize, pyqtSignal
from PyQt5.QtGui import (
    QPixmap, QImage, QPainter, QColor, QMouseEvent,
    QContextMenuEvent, QCursor, QKeySequence
)

# PDF engine
try:
    import fitz
except ImportError:
    import pymupdf as fitz

from pdfviewer.core.document import PDFDocument
from pdfviewer.utils.geometry import compute_page_transform, pdf_to_screen_rect


class PageLabel(QLabel):
    """Custom QLabel for PDF page with mouse tracking."""

    def __init__(self, page_idx: int, parent=None):
        super().__init__(parent)
        self.page_idx = page_idx
        self.setMouseTracking(True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("QLabel { background-color: white; }")


class OverlayLabel(QLabel):
    """Overlay for displaying selections and highlights."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("QLabel { background-color: transparent; }")
        self._selections = []  # List of QRect
        self._highlights = []  # List of (QRect, color)
        self._underlines = []  # List of QRect
        self._search_results = []  # List of QRect for search results
        self._current_search_idx = -1  # Current highlighted search result

    def paintEvent(self, event):
        """Custom paint for selections and highlights."""
        super().paintEvent(event)

        painter = QPainter(self)

        # Draw selections (blue, semi-transparent)
        painter.setBrush(QColor(0, 120, 215, 80))
        painter.setPen(Qt.NoPen)
        for rect in self._selections:
            painter.drawRect(rect)

        # Draw highlights (yellow, semi-transparent)
        painter.setBrush(QColor(255, 255, 0, 100))
        for rect, _ in self._highlights:
            painter.drawRect(rect)

        # Draw underlines (red line at bottom of text)
        pen = painter.pen()
        pen.setColor(QColor(255, 0, 0, 200))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for rect in self._underlines:
            # Draw line at bottom of the rect (use rect.bottom() - 1 to stay within bounds)
            y = rect.bottom() - 2
            painter.drawLine(rect.left(), y, rect.right(), y)

        # Draw search results (orange, semi-transparent)
        for i, rect in enumerate(self._search_results):
            if i == self._current_search_idx:
                # Current result - darker orange with border
                painter.setBrush(QColor(255, 165, 0, 150))
                pen = painter.pen()
                pen.setColor(QColor(255, 140, 0))
                pen.setWidth(2)
                painter.setPen(pen)
            else:
                # Other results - lighter orange
                painter.setBrush(QColor(255, 200, 100, 80))
                painter.setPen(Qt.NoPen)
            painter.drawRect(rect)

    def clear_selections(self):
        """Clear all selections."""
        self._selections.clear()
        self.update()

    def add_selection(self, rect: QRect):
        """Add a selection rectangle."""
        self._selections.append(rect)
        self.update()

    def clear_highlights(self):
        """Clear all highlights."""
        self._highlights.clear()
        self.update()

    def add_highlight(self, rect: QRect, color: QColor = None):
        """Add a highlight rectangle."""
        if color is None:
            color = QColor(255, 255, 0, 100)
        self._highlights.append((rect, color))
        self.update()

    def clear_underlines(self):
        """Clear all underlines."""
        self._underlines.clear()
        self.update()

    def add_underline(self, rect: QRect):
        """Add an underline rectangle."""
        self._underlines.append(rect)
        self.update()

    def clear_search_results(self):
        """Clear all search results."""
        self._search_results.clear()
        self._current_search_idx = -1
        self.update()

    def set_search_results(self, rects: list, current_idx: int = -1):
        """Set search result rectangles."""
        self._search_results = rects
        self._current_search_idx = current_idx
        self.update()

    def set_current_search_idx(self, idx: int):
        """Set current highlighted search result index."""
        self._current_search_idx = idx
        self.update()


class AnnotationTooltip(QLabel):
    """
    轻量级注释浮窗组件
    - 设置 Qt.ToolTip | Qt.FramelessWindowHint 标志
    - 使用 QSS 渲染样式
    - UI 层独立于 PDF 渲染引擎
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("""
            QLabel {
                background-color: #ffffcc;
                border: 1px solid #cccc99;
                border-radius: 4px;
                padding: 8px;
                color: #333333;
                font-size: 12px;
                max-width: 300px;
            }
        """)
        self.setWordWrap(True)


class ViewerWidget(QWidget):
    """
    PDF document viewer widget.

    Displays PDF pages and handles user interactions like text selection,
    context menu, and annotation hover.
    """

    # Signals
    text_selected = pyqtSignal(str)  # Selected text
    page_clicked = pyqtSignal(int, QPoint)  # page_idx, position
    annotation_clicked = pyqtSignal(int, dict)  # page_idx, annot_info
    annotation_added = pyqtSignal()  # Annotation added/updated
    zoom_changed = pyqtSignal(float)  # Zoom factor changed
    document_loaded = pyqtSignal()  # Document finished loading

    def __init__(self, parent=None):
        super().__init__(parent)

        # Document reference
        self._doc: Optional[PDFDocument] = None
        self._file_path: Optional[str] = None

        # Page widgets
        self._page_labels: List[PageLabel] = []
        self._overlays: List[OverlayLabel] = []

        # Annotation data for hover tooltip (page_idx -> list of (rect, content, type))
        self._page_annotations: List[List[tuple]] = []

        # Text data
        self._page_text_chars: List[List[dict]] = []  # page_idx -> char list
        self._page_words: List[List[dict]] = []  # page_idx -> word list

        # Selection state
        self._selection_start_char: Optional[int] = None
        self._selection_end_char: Optional[int] = None
        self._is_selecting = False
        self._current_page_idx = 0

        # Annotation hover tooltip
        self._annot_tooltip: Optional[AnnotationTooltip] = None
        self._current_hover_annot: Optional[tuple] = None
        from PyQt5.QtCore import QTimer
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_annot_tooltip)

        # Zoom debounce timer
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.timeout.connect(self._apply_zoom_anchor)
        self._pending_zoom_anchor = None
        self._last_zoom_time = 0
        self._zoom_render_version = 0  # Track zoom changes to skip stale renders

        # UI setup
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #666666; }")

        # Pages container
        self.pages_container = QWidget()
        self.pages_container.setStyleSheet("QWidget { background-color: #555555; }")
        self.pages_layout = QVBoxLayout(self.pages_container)
        self.pages_layout.setSpacing(10)
        self.pages_layout.setContentsMargins(10, 10, 10, 10)
        self.pages_layout.setAlignment(Qt.AlignCenter)

        self.scroll_area.setWidget(self.pages_container)
        layout.addWidget(self.scroll_area)

        # Setup copy shortcut
        self._init_shortcuts()

        # Enable mouse tracking on container
        self.pages_container.setMouseTracking(True)
        self.pages_container.installEventFilter(self)

    def _init_shortcuts(self):
        """Initialize keyboard shortcuts."""
        # Copy shortcut (Ctrl+C) - use QShortcut for global window context
        self._copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self)
        self._copy_shortcut.setContext(Qt.WindowShortcut)
        self._copy_shortcut.activated.connect(self._copy_selection)

    def set_document(self, doc: Optional[PDFDocument]):
        """Set the current document."""
        self._doc = doc
        self._clear_all_pages()

        if doc and doc.is_open():
            self._load_pages()

            # Emit document_loaded after layout is ready
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(100, self.document_loaded.emit)

            # Apply pending zoom center after layout update
            pending_center = getattr(self, '_pending_zoom_center', None)
            if pending_center:
                # New format: (content_x, content_y, mouse_x, mouse_y, zoom_ratio)
                # Old format was: (mouse_ratio_x, mouse_ratio_y, mouse_x, mouse_y)
                if len(pending_center) == 5:
                    content_x, content_y, mouse_x, mouse_y, zoom_ratio = pending_center
                    # Use longer delay to ensure layout and scrollbars have updated
                    from PyQt5.QtCore import QTimer
                    QTimer.singleShot(50, lambda: self._apply_zoom_center(content_x, content_y, mouse_x, mouse_y, zoom_ratio))
                else:
                    # Backward compatibility with old format
                    mouse_ratio_x, mouse_ratio_y, mouse_x, mouse_y = pending_center
                    from PyQt5.QtCore import QTimer
                    QTimer.singleShot(50, lambda: self._apply_zoom_center_legacy(mouse_ratio_x, mouse_ratio_y, mouse_x, mouse_y))
                self._pending_zoom_center = None

    def _apply_zoom_center(self, content_x: int, content_y: int, mouse_x: int, mouse_y: int, zoom_ratio: float):
        """Apply zoom centering after layout update using absolute position.

        Args:
            content_x: Absolute x position of content under mouse before zoom
            content_y: Absolute y position of content under mouse before zoom
            mouse_x: Mouse x position relative to viewport
            mouse_y: Mouse y position relative to viewport
            zoom_ratio: new_zoom / old_zoom ratio
        """
        scrollbar_h = self.scroll_area.horizontalScrollBar()
        scrollbar_v = self.scroll_area.verticalScrollBar()

        # Check if scrollbars have valid ranges (layout is ready)
        # Retry if both scrollbars are at 0 (layout not ready yet)
        h_max = scrollbar_h.maximum()
        v_max = scrollbar_v.maximum()
        if h_max == 0 and v_max == 0:
            # Layout not ready, retry after a short delay
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(50, lambda: self._apply_zoom_center(content_x, content_y, mouse_x, mouse_y, zoom_ratio))
            return

        # Calculate new content absolute position after zoom
        # new_content_x = content_x * zoom_ratio
        new_content_x = content_x * zoom_ratio
        new_content_y = content_y * zoom_ratio

        # New scroll position = new content position - mouse offset in viewport
        # This keeps the content under the mouse at the same mouse position
        new_h = int(new_content_x - mouse_x)
        new_v = int(new_content_y - mouse_y)

        scrollbar_h.setValue(max(0, min(scrollbar_h.maximum(), new_h)))
        scrollbar_v.setValue(max(0, min(scrollbar_v.maximum(), new_v)))

    def _apply_zoom_center_legacy(self, mouse_ratio_x: float, mouse_ratio_y: float, mouse_x: int, mouse_y: int):
        """Legacy zoom centering using ratio (for backward compatibility)."""
        scrollbar_h = self.scroll_area.horizontalScrollBar()
        scrollbar_v = self.scroll_area.verticalScrollBar()

        # Get new content size
        content_w = self.pages_container.width()
        content_h = self.pages_container.height()

        if content_w == 0 or content_h == 0:
            return

        # Calculate where the mouse point should be after zoom
        new_content_mouse_x = mouse_ratio_x * content_w
        new_content_mouse_y = mouse_ratio_y * content_h

        # New scroll position = content position under mouse - mouse offset in viewport
        new_h = int(new_content_mouse_x - mouse_x)
        new_v = int(new_content_mouse_y - mouse_y)

        scrollbar_h.setValue(max(0, min(scrollbar_h.maximum(), new_h)))
        scrollbar_v.setValue(max(0, min(scrollbar_v.maximum(), new_v)))

    def _apply_scroll_ratios(self, ratio_x: float, ratio_y: float, mouse_ratio_x: float, mouse_ratio_y: float):
        """Apply scroll ratios after layout update, maintaining mouse-centered zoom."""
        scrollbar_h = self.scroll_area.horizontalScrollBar()
        scrollbar_v = self.scroll_area.verticalScrollBar()

        # Get new scrollbar ranges
        h_max = max(0, scrollbar_h.maximum())
        v_max = max(0, scrollbar_v.maximum())

        # Calculate new scroll values based on ratios
        # Adjust for mouse position to keep zoom centered on mouse
        viewport_w = self.scroll_area.viewport().width()
        viewport_h = self.scroll_area.viewport().height()

        new_h = int(ratio_x * h_max + mouse_ratio_x * (h_max - scrollbar_h.maximum()))
        new_v = int(ratio_y * v_max + mouse_ratio_y * (v_max - scrollbar_v.maximum()))

        scrollbar_h.setValue(max(0, min(h_max, new_h)))
        scrollbar_v.setValue(max(0, min(v_max, new_v)))

    def _apply_pending_scroll(self, h: int, v: int):
        """Apply pending scroll position after layout update."""
        self.scroll_area.horizontalScrollBar().setValue(h)
        self.scroll_area.verticalScrollBar().setValue(v)

    def _clear_all_pages(self):
        """Clear all pages."""
        # Remove all widgets
        while self.pages_layout.count():
            item = self.pages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._page_labels.clear()
        self._overlays.clear()
        self._page_text_chars.clear()
        self._page_words.clear()
        self._page_annotations.clear()

    def _reload_page(self, page_idx: int):
        """Reload a single page after annotation changes.

        This re-renders the page from PDF to show annotations properly.
        """
        if not self._doc or not self._doc.doc:
            return
        if page_idx < 0 or page_idx >= len(self._page_labels):
            return

        try:
            page = self._doc.doc[page_idx]
            page_label = self._page_labels[page_idx]
            overlay = self._overlays[page_idx]

            # Re-render the page with annotations
            zoom = self._doc.zoom_factor
            dpi_scale = self.logicalDpiX() / 96.0 if hasattr(self, 'logicalDpiX') else 1.0
            device_ratio = 1.0

            mat = fitz.Matrix(zoom * dpi_scale, zoom * dpi_scale)
            pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)

            img = QImage(
                pix.samples, pix.width, pix.height, pix.stride,
                QImage.Format_RGB888 if pix.n == 3 else QImage.Format_ARGB32
            ).copy()

            qpixmap = QPixmap.fromImage(img)
            qpixmap.setDevicePixelRatio(device_ratio)

            # Update page label
            page_label.setPixmap(qpixmap)
            page_label.setFixedSize(qpixmap.size())

            # Update overlay size
            overlay.resize(page_label.size())

            # Refresh annotations overlay (important after zoom/size changes)
            self._refresh_annotations_for_page(page_idx)

        except Exception as e:
            print(f"Failed to reload page {page_idx}: {e}")

    def _reload_page_with_zoom(self, page_idx: int, zoom: float):
        """Reload a single page with specified zoom factor."""
        if not self._doc or not self._doc.doc:
            return
        if page_idx < 0 or page_idx >= len(self._page_labels):
            return

        try:
            page = self._doc.doc[page_idx]
            page_label = self._page_labels[page_idx]
            overlay = self._overlays[page_idx]

            # Re-render the page with specified zoom
            dpi_scale = self.logicalDpiX() / 96.0 if hasattr(self, 'logicalDpiX') else 1.0
            device_ratio = 1.0

            mat = fitz.Matrix(zoom * dpi_scale, zoom * dpi_scale)
            pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)

            img = QImage(
                pix.samples, pix.width, pix.height, pix.stride,
                QImage.Format_RGB888 if pix.n == 3 else QImage.Format_ARGB32
            ).copy()

            qpixmap = QPixmap.fromImage(img)
            qpixmap.setDevicePixelRatio(device_ratio)

            # Update page label
            page_label.setPixmap(qpixmap)
            page_label.setFixedSize(qpixmap.size())

            # Update overlay size
            overlay.resize(page_label.size())

            # Reload text for this page
            self._load_page_text(page_idx)

            # Refresh annotations on this page
            self._refresh_annotations_for_page(page_idx)

        except Exception as e:
            print(f"Failed to reload page {page_idx}: {e}")

    def _refresh_annotations_for_page(self, page_idx: int):
        """Refresh annotations for a single page."""
        if page_idx < 0 or page_idx >= len(self._page_labels):
            return

        # Hide tooltip if the current hover annotation is on this page
        if self._current_hover_annot and self._current_hover_annot[0] == page_idx:
            self._hide_annot_tooltip()

        page = self._doc.doc[page_idx]
        page_label = self._page_labels[page_idx]
        overlay = self._overlays[page_idx]

        # Clear this page's annotations
        overlay.clear_highlights()
        overlay.clear_underlines()

        # Ensure overlay size matches
        if overlay.size() != page_label.size():
            overlay.resize(page_label.size())

        # Get transform
        t = self._compute_page_transform(page_label)
        if not t:
            return

        scale = t["scale"]
        ox = t["offset_x"]
        oy = t["offset_y"]
        contents = t["contents"]

        # Ensure _page_annotations list is long enough
        while len(self._page_annotations) <= page_idx:
            self._page_annotations.append([])

        # Clear this page's annotation data
        self._page_annotations[page_idx] = []

        for annot in page.annots():
            annot_type = annot.type
            if isinstance(annot_type, tuple):
                type_num = annot_type[0]
            else:
                type_num = annot_type

            rect = annot.rect
            annot_info = annot.info if hasattr(annot, "info") else {}
            content = annot_info.get("content", "") if annot_info else ""

            # Convert PDF rect to UI rect
            x0 = rect.x0 * scale + contents.left() + ox
            y0 = rect.y0 * scale + contents.top() + oy
            x1 = rect.x1 * scale + contents.left() + ox
            y1 = rect.y1 * scale + contents.top() + oy

            qrect = QRect(int(x0), int(y0), int(x1 - x0), int(y1 - y0))

            # Store for hover detection
            self._page_annotations[page_idx].append((qrect, content, type_num))

            if type_num == 8:  # Highlight
                overlay.add_highlight(qrect)
            elif type_num == 9:  # Underline
                overlay.add_underline(qrect)

    def _load_pages(self):
        """Load all pages of the document."""
        if not self._doc or not self._doc.doc:
            return

        zoom = self._doc.zoom_factor
        # Use logical DPI for consistent scaling across displays
        dpi_scale = self.logicalDpiX() / 96.0 if hasattr(self, 'logicalDpiX') else 1.0
        device_ratio = 1.0

        for page_idx in range(self._doc.page_count):
            page = self._doc.doc[page_idx]
            mat = fitz.Matrix(zoom * dpi_scale, zoom * dpi_scale)
            pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)

            img = QImage(
                pix.samples, pix.width, pix.height, pix.stride,
                QImage.Format_RGB888 if pix.n == 3 else QImage.Format_ARGB32
            ).copy()

            qpixmap = QPixmap.fromImage(img)
            qpixmap.setDevicePixelRatio(device_ratio)

            # Create page label
            page_label = PageLabel(page_idx)
            page_label.setPixmap(qpixmap)
            page_label.setFixedSize(qpixmap.size())
            page_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            page_label.setContentsMargins(0, 0, 0, 0)  # Ensure no margins

            # Create overlay
            overlay = OverlayLabel(page_label)
            overlay.resize(page_label.size())
            overlay.show()

            # Store references
            self._page_labels.append(page_label)
            self._overlays.append(overlay)

            # Add to layout
            self.pages_layout.addWidget(page_label)

            # Load text for this page
            self._load_page_text(page_idx)

        # Initialize annotations list after all pages are loaded
        self._page_annotations = [[] for _ in range(len(self._page_labels))]

        # Load annotations from PDF
        self._refresh_annotations()

        self.pages_layout.addStretch()

    def _load_page_text(self, page_idx: int):
        """Load text information for a page."""
        if not self._doc or not self._doc.doc:
            return

        page = self._doc.doc[page_idx]
        char_list = []
        word_list = []

        try:
            # Load character info
            text_dict = page.get_text("rawdict")
            char_idx = 0

            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "")
                        chars = span.get("chars", [])
                        origin = span.get("origin", [0, 0])

                        for char_info in chars:
                            c = char_info.get("c", "")
                            bbox = char_info.get("bbox", [0, 0, 0, 0])
                            if c.strip() or c == " ":
                                char_list.append({
                                    "char": c,
                                    "bbox": bbox,
                                    "page_idx": page_idx,
                                    "char_idx": char_idx,
                                })
                                char_idx += 1

            # Load word info
            words = page.get_text("words")
            for word in words:
                x0, y0, x1, y1, text = word[0:5]
                word_list.append({
                    "bbox": [x0, y0, x1, y1],
                    "text": text,
                    "page_idx": page_idx,
                })

        except Exception as e:
            print(f"加载页面文本失败 (page {page_idx}): {e}")

        # Store text data
        if len(self._page_text_chars) <= page_idx:
            self._page_text_chars.extend([[]] * (page_idx - len(self._page_text_chars) + 1))
        if len(self._page_words) <= page_idx:
            self._page_words.extend([[]] * (page_idx - len(self._page_words) + 1))

        self._page_text_chars[page_idx] = char_list
        self._page_words[page_idx] = word_list

        # Pre-compute UI rectangles
        self._update_text_ui_rects(page_idx)

    def _compute_page_transform(self, page_label):
        """
        Compute coordinate transformation parameters for a page.
        Matches the implementation in main_original.py.
        """
        if not page_label or not self._doc:
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
        scale = float(self._doc.zoom_factor) * float(dpi_scale)

        return {
            "scale": scale,
            "offset_x": offset_x,
            "offset_y": offset_y,
            "contents": contents,
            "dpi_scale": dpi_scale
        }

    def _update_text_ui_rects(self, page_idx: int):
        """Update UI rectangles for text on a page using the original transform method."""
        if page_idx >= len(self._page_labels) or not self._doc:
            return

        page_label = self._page_labels[page_idx]

        # Use the same transform computation as the original
        t = self._compute_page_transform(page_label)
        if not t:
            return

        scale = t["scale"]
        ox = t["offset_x"]
        oy = t["offset_y"]
        contents = t["contents"]

        # Update character UI rects - PyMuPDF origin is top-left, Y-axis points down
        # NO Y-flip needed
        if page_idx < len(self._page_text_chars):
            for char_info in self._page_text_chars[page_idx]:
                x0, y0, x1, y1 = char_info["bbox"]
                ui_x0 = x0 * scale + contents.left() + ox
                ui_y0 = y0 * scale + contents.top() + oy
                ui_x1 = x1 * scale + contents.left() + ox
                ui_y1 = y1 * scale + contents.top() + oy
                char_info["ui_rect"] = QRectF(ui_x0, ui_y0, ui_x1 - ui_x0, ui_y1 - ui_y0)

        # Update word UI rects
        if page_idx < len(self._page_words):
            for word_info in self._page_words[page_idx]:
                x0, y0, x1, y1 = word_info["bbox"]
                ui_x0 = x0 * scale + contents.left() + ox
                ui_y0 = y0 * scale + contents.top() + oy
                ui_x1 = x1 * scale + contents.left() + ox
                ui_y1 = y1 * scale + contents.top() + oy
                word_info["ui_rect"] = QRectF(ui_x0, ui_y0, ui_x1 - ui_x0, ui_y1 - ui_y0)

    def _get_page_at_pos(self, pos: QPoint, from_container: bool = False) -> Tuple[Optional[PageLabel], int, QPoint]:
        """
        Get the page label at a position.

        Args:
            pos: Position coordinates
            from_container: If True, pos is already in pages_container coordinates.
                           If False, pos is in ViewerWidget coordinates and will be converted.

        Returns: (page_label, page_idx, local_pos) or (None, -1, None)
        """
        # Convert pos to pages_container coordinates if needed
        if from_container:
            container_pos = pos
        else:
            container_pos = self.pages_container.mapFromParent(pos)

        for i, page_label in enumerate(self._page_labels):
            if page_label.geometry().contains(container_pos):
                local_pos = page_label.mapFromParent(container_pos)
                return page_label, i, local_pos
        return None, -1, QPoint()

    def _get_char_at_pos(self, page_idx: int, pos: QPoint) -> Optional[dict]:
        """Get character info at a position on a page."""
        if page_idx >= len(self._page_text_chars):
            return None

        # Try UI rect first
        for char_info in self._page_text_chars[page_idx]:
            ui_rect = char_info.get("ui_rect")
            if ui_rect and ui_rect.contains(float(pos.x()), float(pos.y())):
                return char_info

        return None

    def _get_selection_text(self, start_char: int, end_char: int, page_idx: int) -> str:
        """Get text between two character indices."""
        if page_idx >= len(self._page_text_chars):
            return ""

        chars = self._page_text_chars[page_idx]
        if not chars or start_char < 0 or end_char >= len(chars):
            return ""

        if start_char > end_char:
            start_char, end_char = end_char, start_char

        selected_chars = chars[start_char:end_char + 1]
        return "".join(c["char"] for c in selected_chars)

    def _draw_selection(self, start_char: int, end_char: int, page_idx: int):
        """Draw selection on a page."""
        if page_idx >= len(self._overlays):
            return

        overlay = self._overlays[page_idx]
        overlay.clear_selections()

        if page_idx >= len(self._page_text_chars):
            return

        chars = self._page_text_chars[page_idx]
        if not chars or start_char < 0 or end_char >= len(chars):
            return

        if start_char > end_char:
            start_char, end_char = end_char, start_char

        # Group selected characters by line
        line_groups = []
        current_line = []

        for i in range(start_char, end_char + 1):
            char_info = chars[i]
            bbox = char_info.get("ui_rect")
            if bbox:
                if not current_line:
                    current_line.append(char_info)
                else:
                    # Check if same line (y position similar)
                    prev_bbox = current_line[-1].get("ui_rect")
                    if prev_bbox and abs(bbox.y() - prev_bbox.y()) < 5:
                        current_line.append(char_info)
                    else:
                        line_groups.append(current_line)
                        current_line = [char_info]

        if current_line:
            line_groups.append(current_line)

        # Draw rectangle for each line
        for line_chars in line_groups:
            if not line_chars:
                continue

            x0_list = [c["ui_rect"].x() for c in line_chars if "ui_rect" in c]
            y0_list = [c["ui_rect"].y() for c in line_chars if "ui_rect" in c]
            x1_list = [c["ui_rect"].x() + c["ui_rect"].width() for c in line_chars if "ui_rect" in c]
            y1_list = [c["ui_rect"].y() + c["ui_rect"].height() for c in line_chars if "ui_rect" in c]

            if x0_list and y0_list:
                rect = QRect(
                    int(min(x0_list)),
                    int(min(y0_list)),
                    int(max(x1_list) - min(x0_list)),
                    int(max(y1_list) - min(y0_list))
                )
                overlay.add_selection(rect)

    def eventFilter(self, obj, event):
        """Event filter for mouse events on pages container."""
        if obj is self.pages_container:
            if event.type() == event.MouseButtonPress:
                self._on_mouse_press(event)
                return True
            elif event.type() == event.MouseMove:
                self._on_mouse_move(event)
                return True
            elif event.type() == event.MouseButtonRelease:
                self._on_mouse_release(event)
                return True
            elif event.type() == event.Wheel:
                return self._on_wheel_event(event)
        return super().eventFilter(obj, event)

    def _on_mouse_press(self, event: QMouseEvent):
        """Handle mouse press."""
        if event.button() == Qt.LeftButton:
            # Event from pages_container, pos is already in container coordinates
            page_label, page_idx, local_pos = self._get_page_at_pos(event.pos(), from_container=True)

            if page_label:
                self._current_page_idx = page_idx
                self._is_selecting = True

                # Get character at position
                char_info = self._get_char_at_pos(page_idx, local_pos)
                if char_info:
                    self._selection_start_char = char_info["char_idx"]
                    self._selection_end_char = char_info["char_idx"]
                else:
                    self._selection_start_char = None
                    self._selection_end_char = None

                # Clear previous selections
                for overlay in self._overlays:
                    overlay.clear_selections()

    def _on_mouse_move(self, event: QMouseEvent):
        """Handle mouse move."""
        if self._is_selecting and event.buttons() & Qt.LeftButton:
            # Event from pages_container, pos is already in container coordinates
            page_label, page_idx, local_pos = self._get_page_at_pos(event.pos(), from_container=True)

            if page_label and page_idx == self._current_page_idx:
                char_info = self._get_char_at_pos(page_idx, local_pos)
                if char_info and self._selection_start_char is not None:
                    self._selection_end_char = char_info["char_idx"]
                    self._draw_selection(
                        self._selection_start_char,
                        self._selection_end_char,
                        page_idx
                    )
        else:
            # Check for annotation hover (not selecting)
            # Event from pages_container, pos is already in container coordinates
            self._check_annotation_hover(event.pos(), from_container=True)

    def _on_mouse_release(self, event: QMouseEvent):
        """Handle mouse release."""
        if event.button() == Qt.LeftButton and self._is_selecting:
            self._is_selecting = False

            # Emit selected text
            if self._selection_start_char is not None and self._selection_end_char is not None:
                text = self._get_selection_text(
                    self._selection_start_char,
                    self._selection_end_char,
                    self._current_page_idx
                )
                if text:
                    self.text_selected.emit(f"已选择 {len(text)} 个字符")

    def _check_annotation_hover(self, pos, from_container=False):
        """Check if mouse is hovering over an annotation and show tooltip."""
        # Find which page the mouse is over
        page_label, page_idx, local_pos = self._get_page_at_pos(pos, from_container)

        if not page_label or page_idx >= len(self._page_annotations):
            self._hide_annot_tooltip()
            return

        # Check if mouse is over any annotation on this page
        # Only show tooltip for underline annotations (type 9), not highlights
        for rect, content, annot_type in self._page_annotations[page_idx]:
            if rect.contains(local_pos):
                # Only show tooltip for underline (type 9), not highlight (type 8)
                if annot_type == 9 and content:
                    annot_key = (page_idx, rect.x(), rect.y())
                    if self._current_hover_annot != annot_key:
                        self._current_hover_annot = annot_key
                        self._tooltip_timer.stop()
                        self._tooltip_timer.start(300)  # 300ms delay
                    return

        # Not hovering over underline, hide tooltip
        self._hide_annot_tooltip()

    def _show_annot_tooltip(self):
        """Show annotation tooltip popup."""
        if not self._current_hover_annot or not self._page_annotations:
            return

        page_idx = self._current_hover_annot[0]
        annot_x = self._current_hover_annot[1]
        annot_y = self._current_hover_annot[2]

        if page_idx >= len(self._page_annotations):
            return

        # Find the specific annotation matching the stored key
        # annot_key = (page_idx, rect.x(), rect.y())
        for rect, content, annot_type in self._page_annotations[page_idx]:
            if annot_type == 9 and rect.x() == annot_x and rect.y() == annot_y:
                if content:
                    # Create tooltip if not exists
                    if not self._annot_tooltip:
                        self._annot_tooltip = AnnotationTooltip(self)

                    self._annot_tooltip.setText(content)
                    self._annot_tooltip.adjustSize()

                    # Position near cursor
                    cursor_pos = QCursor.pos()
                    self._annot_tooltip.move(cursor_pos.x() + 15, cursor_pos.y() + 15)
                    self._annot_tooltip.show()
                return

    def _hide_annot_tooltip(self):
        """Hide annotation tooltip."""
        self._current_hover_annot = None
        self._tooltip_timer.stop()
        if self._annot_tooltip:
            self._annot_tooltip.hide()

    def contextMenuEvent(self, event):
        """Show context menu."""
        menu = QMenu(self)

        # Check if clicking on an annotation
        # contextMenuEvent pos is in ViewerWidget coordinates, need conversion
        page_label, page_idx, local_pos = self._get_page_at_pos(event.pos(), from_container=False)
        annot_to_delete = None

        if page_label and page_idx < len(self._page_annotations):
            for rect, content, annot_type in self._page_annotations[page_idx]:
                if rect.contains(local_pos):
                    # Store precise info: page_idx, annot_type, and rect coordinates
                    annot_to_delete = (page_idx, annot_type, rect.x(), rect.y(), rect.width(), rect.height())
                    break

        if annot_to_delete:
            # Show delete annotation option (unified menu)
            delete_action = QAction("删除注释", self)
            delete_action.triggered.connect(lambda: self._delete_annotation(annot_to_delete[0], annot_to_delete[1], annot_to_delete[2], annot_to_delete[3], annot_to_delete[4], annot_to_delete[5]))
            menu.addAction(delete_action)
            menu.addSeparator()

        # Copy action
        copy_action = QAction("复制", self)
        copy_action.triggered.connect(self._copy_selection)
        menu.addAction(copy_action)

        menu.addSeparator()

        # Highlight action
        highlight_action = QAction("添加高亮", self)
        highlight_action.triggered.connect(self._add_highlight)
        menu.addAction(highlight_action)

        # Underline action
        underline_action = QAction("添加下划线", self)
        underline_action.triggered.connect(self._add_underline)
        menu.addAction(underline_action)

        menu.exec_(event.globalPos())

    def _copy_selection(self):
        """Copy selected text to clipboard."""
        if self._selection_start_char is not None and self._selection_end_char is not None:
            text = self._get_selection_text(
                self._selection_start_char,
                self._selection_end_char,
                self._current_page_idx
            )
            if text:
                clipboard = QApplication.clipboard()
                clipboard.setText(text)
                # Emit signal for status bar feedback
                self.text_selected.emit(f"已复制 {len(text)} 个字符到剪贴板")
            else:
                self.text_selected.emit("无选中文本")

    def _add_highlight(self):
        """Add highlight annotation."""
        if not self._doc or not self._doc.doc:
            return

        if self._selection_start_char is None or self._selection_end_char is None:
            return

        try:
            page = self._doc.doc[self._current_page_idx]

            # Get selected characters
            chars = self._page_text_chars[self._current_page_idx]
            start = min(self._selection_start_char, self._selection_end_char)
            end = max(self._selection_start_char, self._selection_end_char)

            # Group by line
            line_groups = []
            current_line = []
            current_y = None

            for i in range(start, end + 1):
                if i >= len(chars):
                    break
                char_info = chars[i]
                bbox = char_info["bbox"]
                y_center = (bbox[1] + bbox[3]) / 2

                if current_y is None or abs(y_center - current_y) < 5:
                    current_line.append(char_info)
                    current_y = y_center
                else:
                    line_groups.append(current_line)
                    current_line = [char_info]
                    current_y = y_center

            if current_line:
                line_groups.append(current_line)

            # Add highlight for each line
            for line_chars in line_groups:
                x0_list = [c["bbox"][0] for c in line_chars]
                y0_list = [c["bbox"][1] for c in line_chars]
                x1_list = [c["bbox"][2] for c in line_chars]
                y1_list = [c["bbox"][3] for c in line_chars]

                pdf_rect = fitz.Rect(
                    min(x0_list), min(y0_list),
                    max(x1_list), max(y1_list)
                )

                highlight = page.add_highlight_annot(pdf_rect)
                if highlight:
                    highlight.update()

            self._doc.mark_modified(True)

            # Reload the page to show annotation properly
            self._reload_page(self._current_page_idx)

            # Emit signal to notify sidebar update
            self.annotation_added.emit()

        except Exception as e:
            QMessageBox.critical(self, "错误", f"添加高亮失败:\n{str(e)}")

    def _add_underline(self):
        """Add underline annotation."""
        from PyQt5.QtWidgets import QInputDialog, QLineEdit

        if not self._doc or not self._doc.doc:
            return

        if self._selection_start_char is None or self._selection_end_char is None:
            return

        # Get comment text
        text, ok = QInputDialog.getText(
            self, "添加下划线注释", "请输入注释内容:",
            QLineEdit.Normal, ""
        )

        if not ok:
            return

        try:
            page = self._doc.doc[self._current_page_idx]

            # Get selected characters
            chars = self._page_text_chars[self._current_page_idx]
            start = min(self._selection_start_char, self._selection_end_char)
            end = max(self._selection_start_char, self._selection_end_char)

            # Group by line
            line_groups = []
            current_line = []
            current_y = None

            for i in range(start, end + 1):
                if i >= len(chars):
                    break
                char_info = chars[i]
                bbox = char_info["bbox"]
                y_center = (bbox[1] + bbox[3]) / 2

                if current_y is None or abs(y_center - current_y) < 5:
                    current_line.append(char_info)
                    current_y = y_center
                else:
                    line_groups.append(current_line)
                    current_line = [char_info]
                    current_y = y_center

            if current_line:
                line_groups.append(current_line)

            # Add underline for each line
            for line_chars in line_groups:
                x0_list = [c["bbox"][0] for c in line_chars]
                y0_list = [c["bbox"][1] for c in line_chars]
                x1_list = [c["bbox"][2] for c in line_chars]
                y1_list = [c["bbox"][3] for c in line_chars]

                pdf_rect = fitz.Rect(
                    min(x0_list), min(y0_list),
                    max(x1_list), max(y1_list)
                )

                underline = page.add_underline_annot(pdf_rect)
                if underline:
                    underline.set_colors(stroke=(1, 0, 0))
                    underline.set_info(content=text)
                    underline.update()

            self._doc.mark_modified(True)

            # Reload the page to show annotation properly
            self._reload_page(self._current_page_idx)

            # Emit signal to notify sidebar update
            self.annotation_added.emit()

        except Exception as e:
            QMessageBox.critical(self, "错误", f"添加下划线失败:\n{str(e)}")

    def _delete_annotation(self, page_idx: int, annot_type: int, rect_x: int = None, rect_y: int = None, rect_w: int = None, rect_h: int = None):
        """Delete annotation at given page and type, using rect coordinates for precise matching."""
        if not self._doc or not self._doc.doc:
            return

        try:
            page = self._doc.doc[page_idx]

            # Find and delete the matching annotation using rect coordinates
            for annot in page.annots():
                atype = annot.type
                if isinstance(atype, tuple):
                    type_num = atype[0]
                else:
                    type_num = atype

                if type_num == annot_type:
                    # If rect coordinates provided, match precisely
                    if rect_x is not None and rect_y is not None:
                        annot_rect = annot.rect
                        # Convert PDF rect to UI coordinates for comparison
                        t = self._compute_page_transform(self._page_labels[page_idx]) if page_idx < len(self._page_labels) else None
                        if t:
                            scale = t["scale"]
                            ox = t["offset_x"]
                            oy = t["offset_y"]
                            contents = t["contents"]
                            ui_x0 = int(annot_rect.x0 * scale + contents.left() + ox)
                            ui_y0 = int(annot_rect.y0 * scale + contents.top() + oy)
                            # Check if coordinates match (with small tolerance)
                            if abs(ui_x0 - rect_x) <= 2 and abs(ui_y0 - rect_y) <= 2:
                                page.delete_annot(annot)
                                break
                        else:
                            # Fallback: delete first match if transform fails
                            page.delete_annot(annot)
                            break
                    else:
                        # No rect provided: delete first match (backward compatibility)
                        page.delete_annot(annot)
                        break

            self._doc.mark_modified(True)

            # Reload the page to reflect annotation deletion
            self._reload_page(page_idx)

            # Refresh annotations overlay to remove deleted highlight
            self._refresh_annotations_for_page(page_idx)

            # Emit signal to notify sidebar update
            self.annotation_added.emit()

        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除注释失败:\n{str(e)}")

    def _screen_to_pdf_point(self, page_label, screen_pos: QPoint) -> tuple:
        """Convert screen coordinates to PDF coordinates.

        PyMuPDF origin is at top-left, Y-axis points down.
        """
        t = self._compute_page_transform(page_label)
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

    def _refresh_annotations(self):
        """Refresh annotation display using the original transform method."""
        # Hide tooltip during refresh
        self._hide_annot_tooltip()

        # Clear existing highlights and underlines
        for overlay in self._overlays:
            overlay.clear_highlights()
            overlay.clear_underlines()

        # Clear annotation data
        self._page_annotations = [[] for _ in range(len(self._page_labels))]

        # Reload annotations
        if not self._doc or not self._doc.doc:
            return

        for page_idx in range(min(len(self._page_labels), self._doc.page_count)):
            page = self._doc.doc[page_idx]
            page_label = self._page_labels[page_idx]
            overlay = self._overlays[page_idx]

            # Ensure overlay size matches page_label
            if overlay.size() != page_label.size():
                overlay.resize(page_label.size())

            # Get transform for this page
            t = self._compute_page_transform(page_label)
            if not t:
                continue

            scale = t["scale"]
            ox = t["offset_x"]
            oy = t["offset_y"]
            contents = t["contents"]

            for annot in page.annots():
                annot_type = annot.type
                if isinstance(annot_type, tuple):
                    type_num = annot_type[0]
                else:
                    type_num = annot_type

                rect = annot.rect
                content = annot.info.get("content", "") if hasattr(annot, "info") else ""

                # Convert PDF rect to UI rect using the same transform as text selection
                # PyMuPDF origin is top-left, Y-axis points down - NO Y-flip needed
                x0 = rect.x0 * scale + contents.left() + ox
                y0 = rect.y0 * scale + contents.top() + oy
                x1 = rect.x1 * scale + contents.left() + ox
                y1 = rect.y1 * scale + contents.top() + oy

                qrect = QRect(int(x0), int(y0), int(x1 - x0), int(y1 - y0))

                # Store annotation data for hover tooltip
                self._page_annotations[page_idx].append((qrect, content, type_num))

                if type_num == 8:  # Highlight
                    overlay.add_highlight(qrect)
                elif type_num == 9:  # Underline
                    overlay.add_underline(qrect)

    def get_selected_text(self) -> str:
        """Get currently selected text."""
        if self._selection_start_char is not None and self._selection_end_char is not None:
            return self._get_selection_text(
                self._selection_start_char,
                self._selection_end_char,
                self._current_page_idx
            )
        return ""

    def clear_selection(self):
        """Clear current selection."""
        self._selection_start_char = None
        self._selection_end_char = None
        for overlay in self._overlays:
            overlay.clear_selections()

    def display_search_results(self, page_results: dict, current_result: tuple = None):
        """
        Display search results on pages.

        Args:
            page_results: Dict mapping page_idx to list of (x, y, w, h) rectangles
            current_result: Tuple (page_idx, rect_idx) for current highlighted result
        """
        # Clear previous results
        for overlay in self._overlays:
            overlay.clear_search_results()

        # Draw results on each page
        for page_idx, rects in page_results.items():
            if 0 <= page_idx < len(self._overlays):
                overlay = self._overlays[page_idx]
                qrects = []
                for i, (x, y, w, h) in enumerate(rects):
                    qrects.append(QRect(int(x), int(y), int(w), int(h)))
                current_idx = -1
                if current_result and current_result[0] == page_idx:
                    current_idx = current_result[1]
                overlay.set_search_results(qrects, current_idx)

    def clear_search_display(self):
        """Clear search result display."""
        for overlay in self._overlays:
            overlay.clear_search_results()

    def scroll_to_search_result(self, page_idx: int, rect: tuple = None):
        """
        Scroll to a search result, centering it in view.

        Args:
            page_idx: Page index
            rect: Optional (x, y, w, h) tuple to center on
        """
        if not (0 <= page_idx < len(self._page_labels)):
            return

        page_label = self._page_labels[page_idx]

        if rect:
            x, y, w, h = rect
            # Scroll to center the rectangle
            self.scroll_area.ensureVisible(
                int(x + w / 2), int(y + h / 2),
                int(self.scroll_area.viewport().width() / 2 - w / 2),
                int(self.scroll_area.viewport().height() / 2 - h / 2)
            )
        else:
            self.scroll_area.ensureWidgetVisible(page_label, 50, 50)

    def scroll_to_page(self, page_idx: int):
        """Scroll to make a page visible."""
        if 0 <= page_idx < len(self._page_labels):
            page_label = self._page_labels[page_idx]
            self.scroll_area.ensureWidgetVisible(page_label, 50, 50)

    def _on_wheel_event(self, event):
        """Handle wheel event for Ctrl+scroll zooming with mouse-centered anchor.

        Core formula: S_new = (S_old + P_mouse) * (k_new / k_old) - P_mouse
        Where:
        - S_old: current scroll position
        - P_mouse: mouse position in viewport
        - k_old/k_new: old/new zoom factors
        """
        if event.modifiers() & Qt.ControlModifier:
            if not self._doc:
                return True

            # Get zoom factor from wheel delta
            delta = event.angleDelta().y()
            if delta > 0:
                factor = 1.2
            elif delta < 0:
                factor = 1.0 / 1.2
            else:
                return True

            # Calculate new zoom
            old_zoom = self._doc.zoom_factor
            new_zoom = old_zoom * factor
            new_zoom = max(0.1, min(5.0, new_zoom))

            # Get current state
            viewport = self.scroll_area.viewport()
            scrollbar_h = self.scroll_area.horizontalScrollBar()
            scrollbar_v = self.scroll_area.verticalScrollBar()

            # Mouse position in viewport (anchor point)
            mouse_x = event.pos().x()
            mouse_y = event.pos().y()

            # Clamp to viewport bounds
            mouse_x = max(0, min(mouse_x, viewport.width()))
            mouse_y = max(0, min(mouse_y, viewport.height()))

            # Current scroll positions (as float for precision)
            scroll_x = float(scrollbar_h.value())
            scroll_y = float(scrollbar_v.value())

            # Calculate new scroll positions using the anchor formula
            # S_new = (S_old + P_mouse) * ratio - P_mouse
            zoom_ratio = new_zoom / old_zoom
            new_scroll_x = (scroll_x + mouse_x) * zoom_ratio - mouse_x
            new_scroll_y = (scroll_y + mouse_y) * zoom_ratio - mouse_y

            # Store target scroll positions for application after zoom
            self._pending_zoom_scroll = {
                'x': new_scroll_x,
                'y': new_scroll_y
            }

            # Apply zoom factor
            self._doc.zoom_factor = new_zoom

            # Reload pages - this updates page sizes and scrollbar ranges
            self._reload_all_pages()

            # Emit zoom changed signal
            self.zoom_changed.emit(new_zoom)

            return True
        return False

    def _apply_zoom_anchor(self):
        """Apply the calculated scroll position after zoom and page reload."""
        if not hasattr(self, '_pending_zoom_scroll') or self._pending_zoom_scroll is None:
            return

        anchor = self._pending_zoom_scroll
        self._pending_zoom_scroll = None

        scrollbar_h = self.scroll_area.horizontalScrollBar()
        scrollbar_v = self.scroll_area.verticalScrollBar()

        # Get current scroll bar ranges after pages have been resized
        h_max = scrollbar_h.maximum()
        v_max = scrollbar_v.maximum()

        # Get viewport size
        viewport = self.scroll_area.viewport()
        viewport_h = viewport.height()

        # Get pages container size
        container_h = self.pages_container.height()

        # Calculate target scroll positions
        target_x = anchor['x']
        target_y = anchor['y']

        # For zoom out (ratio < 1), the document shrinks
        # If document is smaller than viewport, center it
        if container_h < viewport_h:
            # Document fits in viewport, center it vertically
            target_y = -(viewport_h - container_h) / 2
        else:
            # Document larger than viewport, ensure target is within bounds
            target_y = max(0, min(v_max, target_y))

        # Horizontal: always clamp to bounds
        target_x = max(0, min(h_max, target_x))

        # Apply with rounding
        new_x = int(round(target_x))
        new_y = int(round(target_y))

        # Only set if different from current (avoid unnecessary updates)
        if abs(scrollbar_h.value() - new_x) > 1:
            scrollbar_h.setValue(new_x)
        if abs(scrollbar_v.value() - new_y) > 1:
            scrollbar_v.setValue(new_y)

    def _reload_all_pages(self):
        """Reload all pages with current zoom factor."""
        if not self._doc or not self._doc.doc:
            return

        # Increment render version to invalidate stale renders
        self._zoom_render_version += 1
        render_version = self._zoom_render_version

        # Capture current zoom factor to ensure consistency
        current_zoom = self._doc.zoom_factor

        # Update all page sizes first (lightweight)
        for page_idx in range(min(len(self._page_labels), self._doc.page_count)):
            page = self._doc.doc[page_idx]
            page_label = self._page_labels[page_idx]
            overlay = self._overlays[page_idx]

            # Calculate new size using captured zoom
            dpi_scale = self.logicalDpiX() / 96.0 if hasattr(self, 'logicalDpiX') else 1.0
            scale = current_zoom * dpi_scale
            new_width = int(page.rect.width * scale)
            new_height = int(page.rect.height * scale)

            # Update size
            page_label.setFixedSize(new_width, new_height)
            overlay.resize(new_width, new_height)

        # Force layout update
        self.pages_container.adjustSize()

        # Apply zoom anchor after layout
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self._apply_zoom_anchor)

        # Render visible pages with captured zoom
        visible_pages = self._get_visible_page_indices()
        for page_idx in visible_pages:
            if page_idx < len(self._page_labels) and page_idx < self._doc.page_count:
                self._reload_page_with_zoom(page_idx, current_zoom)

        # Refresh annotations
        self._refresh_annotations()

        # Schedule remaining pages with render version check
        QTimer.singleShot(50, lambda: self._reload_remaining_pages(current_zoom, render_version))

    def _get_visible_page_indices(self):
        """Get indices of pages currently visible in viewport."""
        visible_indices = []
        viewport = self.scroll_area.viewport()
        viewport_rect = viewport.rect()
        viewport_global = viewport.mapToGlobal(viewport_rect.topLeft())

        for i, page_label in enumerate(self._page_labels):
            page_rect = page_label.geometry()
            page_global_top = page_label.mapToGlobal(page_rect.topLeft())
            page_global_bottom = page_label.mapToGlobal(page_rect.bottomRight())

            # Check if page intersects with viewport
            if (page_global_top.y() < viewport_global.y() + viewport_rect.height() and
                page_global_bottom.y() > viewport_global.y()):
                visible_indices.append(i)

        return visible_indices

    def _reload_remaining_pages(self, expected_zoom: float, render_version: int):
        """Reload pages that are not currently visible."""
        if not self._doc or not self._doc.doc:
            return

        # Skip if a newer zoom render has been scheduled
        if render_version != self._zoom_render_version:
            return

        visible_pages = set(self._get_visible_page_indices())

        for page_idx in range(min(len(self._page_labels), self._doc.page_count)):
            if page_idx not in visible_pages:
                self._reload_page_with_zoom(page_idx, expected_zoom)

    def _zoom_changed(self, factor: float):
        """Handle zoom factor change."""
        if self._doc:
            new_zoom = self._doc.zoom_factor * factor
            # Limit zoom range
            new_zoom = max(0.1, min(5.0, new_zoom))
            self._doc.zoom_factor = new_zoom
            self._reload_all_pages()
            # Emit signal to notify main window
            self.zoom_changed.emit(new_zoom)

    def get_current_page(self) -> int:
        """Get the page with maximum visible area in viewport.

        Returns:
            Page index (0-based) of the page with largest visible area.
            Returns 0 if no document or no visible pages.
        """
        if not self._doc or not self._doc.doc:
            return 0

        if not self._page_labels:
            return 0

        viewport = self.scroll_area.viewport()
        viewport_rect = viewport.rect()
        viewport_height = viewport_rect.height()

        # Get scroll positions to convert to document coordinates
        scroll_y = self.scroll_area.verticalScrollBar().value()

        max_visible_area = 0
        current_page = 0

        for i, page_label in enumerate(self._page_labels):
            if i >= self._doc.page_count:
                break

            # Get page geometry (relative to pages_container)
            page_geo = page_label.geometry()
            page_top = page_geo.top()
            page_bottom = page_geo.bottom()
            page_height = page_geo.height()
            page_width = page_geo.width()

            # Calculate visible intersection in document coordinates
            # Viewport spans from scroll_y to scroll_y + viewport_height
            visible_top = max(page_top, scroll_y)
            visible_bottom = min(page_bottom, scroll_y + viewport_height)
            visible_height = max(0, visible_bottom - visible_top)

            # Calculate visible area
            visible_area = visible_height * page_width

            if visible_area > max_visible_area:
                max_visible_area = visible_area
                current_page = i

        return current_page

    def get_page_count(self) -> int:
        """Get total page count.

        Returns:
            Total number of pages in the document.
        """
        if not self._doc or not self._doc.doc:
            return 0
        return self._doc.page_count

    def auto_fit_to_window(self, fit_mode: str = "fit_page"):
        """Auto-adjust zoom to fit the window.

        Args:
            fit_mode: Fit mode
                - "fit_page": Fit entire page (default)
                - "fit_width": Fit to width
        """
        if not self._doc or not self._doc.doc:
            return

        # Get viewport size
        viewport = self.scroll_area.viewport()
        viewport_w = viewport.width()
        viewport_h = viewport.height()

        # Calculate DPI scale (same as in _reload_all_pages)
        dpi_scale = self.logicalDpiX() / 96.0 if hasattr(self, 'logicalDpiX') else 1.0

        # Calculate zoom factor (this is the base zoom, DPI scale will be applied during rendering)
        base_zoom = self._doc.calculate_auto_fit_zoom(
            viewport_w, viewport_h, fit_mode
        )

        # Adjust zoom to account for DPI scaling
        # _reload_all_pages multiplies zoom by dpi_scale, so we need to divide by it here
        new_zoom = base_zoom / dpi_scale if dpi_scale > 0 else base_zoom

        # Adjust alignment based on fit mode
        if fit_mode == "fit_width":
            self.scroll_area.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.pages_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.pages_layout.setContentsMargins(5, 10, 5, 10)
        else:
            self.scroll_area.setAlignment(Qt.AlignCenter)
            self.pages_layout.setAlignment(Qt.AlignCenter)
            self.pages_layout.setContentsMargins(10, 10, 10, 10)

        # Apply zoom
        self._doc.zoom_factor = new_zoom
        self._reload_all_pages()
        self.zoom_changed.emit(new_zoom)
