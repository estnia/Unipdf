#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Print Service - Handles PDF printing functionality.

This service provides printing capabilities for PDF documents using
PyMuPDF for page rendering and Qt's QPrinter/QPrintDialog for printing.
"""

from typing import Optional, List
from enum import Enum

from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QPainter, QImage
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog

# PDF engine
try:
    import fitz
except ImportError:
    import pymupdf as fitz


class PrintRange(Enum):
    """Print range options."""
    CURRENT_PAGE = "current"
    ALL_PAGES = "all"
    PAGE_RANGE = "range"


class PrintService:
    """
    Service for printing PDF documents.

    Uses PyMuPDF to render pages and Qt's printing framework
to send pages to the printer.
    """

    def __init__(self, parent=None):
        """Initialize print service."""
        self._parent = parent
        self._printer = QPrinter()
        self._setup_printer()

    def _setup_printer(self):
        """Configure default printer settings."""
        # Default to high resolution for quality PDF printing
        self._printer.setResolution(300)
        # Default to color if available
        self._printer.setColorMode(QPrinter.Color)
        # Default to A4
        self._printer.setPageSize(QPrinter.A4)

    def print_document(
        self,
        doc: fitz.Document,
        page_range: PrintRange = PrintRange.ALL_PAGES,
        start_page: int = 0,
        end_page: int = 0,
        current_page: int = 0,
        show_dialog: bool = True
    ) -> bool:
        """
        Print a PDF document.

        Args:
            doc: The fitz.Document to print
            page_range: Which pages to print (current, all, or range)
            start_page: Start page for range (0-based, inclusive)
            end_page: End page for range (0-based, inclusive)
            current_page: Current page index (for CURRENT_PAGE mode)
            show_dialog: Whether to show print dialog

        Returns:
            True if printing succeeded, False otherwise
        """
        if not doc or len(doc) == 0:
            return False

        # Determine pages to print
        pages = self._get_pages_to_print(
            len(doc),
            page_range,
            start_page,
            end_page,
            current_page
        )

        if not pages:
            return False

        # Show print dialog
        if show_dialog:
            dialog = QPrintDialog(self._printer, self._parent)
            dialog.setMinMax(1, len(doc))

            # Set initial page range in dialog
            if page_range == PrintRange.CURRENT_PAGE:
                dialog.setPrintRange(QPrintDialog.CurrentPage)
            elif page_range == PrintRange.PAGE_RANGE:
                dialog.setFromTo(start_page + 1, end_page + 1)

            if dialog.exec_() != QPrintDialog.Accepted:
                return False

        # Perform printing
        return self._do_print(doc, pages)

    def print_current_page(self, doc: fitz.Document, current_page: int) -> bool:
        """
        Print only the current page.

        Args:
            doc: The fitz.Document to print
            current_page: Current page index (0-based)

        Returns:
            True if printing succeeded, False otherwise
        """
        return self.print_document(
            doc,
            page_range=PrintRange.CURRENT_PAGE,
            current_page=current_page
        )

    def print_all_pages(self, doc: fitz.Document) -> bool:
        """
        Print all pages of the document.

        Args:
            doc: The fitz.Document to print

        Returns:
            True if printing succeeded, False otherwise
        """
        return self.print_document(
            doc,
            page_range=PrintRange.ALL_PAGES
        )

    def print_page_range(
        self,
        doc: fitz.Document,
        start_page: int,
        end_page: int
    ) -> bool:
        """
        Print a specific page range.

        Args:
            doc: The fitz.Document to print
            start_page: Start page index (0-based, inclusive)
            end_page: End page index (0-based, inclusive)

        Returns:
            True if printing succeeded, False otherwise
        """
        return self.print_document(
            doc,
            page_range=PrintRange.PAGE_RANGE,
            start_page=start_page,
            end_page=end_page
        )

    def preview_document(
        self,
        doc: fitz.Document
    ) -> bool:
        """
        Show print preview dialog.

        Args:
            doc: The fitz.Document to preview

        Returns:
            True if preview was shown, False otherwise
        """
        if not doc or len(doc) == 0:
            return False

        dialog = QPrintPreviewDialog(self._printer, self._parent)

        def _on_paint_requested(printer):
            self._do_print(doc, list(range(len(doc))), printer)

        dialog.paintRequested.connect(_on_paint_requested)
        dialog.exec_()
        return True

    def _get_pages_to_print(
        self,
        total_pages: int,
        page_range: PrintRange,
        start_page: int,
        end_page: int,
        current_page: int
    ) -> List[int]:
        """Get list of page indices to print."""
        if page_range == PrintRange.CURRENT_PAGE:
            if 0 <= current_page < total_pages:
                return [current_page]
            return []

        elif page_range == PrintRange.ALL_PAGES:
            return list(range(total_pages))

        elif page_range == PrintRange.PAGE_RANGE:
            start = max(0, min(start_page, total_pages - 1))
            end = max(start, min(end_page, total_pages - 1))
            return list(range(start, end + 1))

        return []

    def _do_print(
        self,
        doc: fitz.Document,
        pages: List[int],
        printer: Optional[QPrinter] = None
    ) -> bool:
        """
        Perform the actual printing.

        Args:
            doc: The fitz.Document to print
            pages: List of page indices to print
            printer: Optional QPrinter instance (uses internal if None)

        Returns:
            True if printing succeeded, False otherwise
        """
        if not pages:
            return False

        printer = printer or self._printer

        # Start painting to printer
        painter = QPainter()
        if not painter.begin(printer):
            return False

        try:
            # Calculate scaling factor for printer DPI
            printer_dpi = printer.resolution()
            pdf_dpi = 72.0  # PDF uses 72 DPI
            scale_factor = printer_dpi / pdf_dpi

            for i, page_idx in enumerate(pages):
                if i > 0:
                    # New page for subsequent pages
                    if not printer.newPage():
                        break

                # Get page from document
                page = doc[page_idx]

                # Get page rectangle (in points)
                page_rect = page.rect
                page_width = page_rect.width
                page_height = page_rect.height

                # Get printer page rectangle (in pixels)
                printer_rect = printer.pageRect()
                printer_width = printer_rect.width()
                printer_height = printer_rect.height()

                # Calculate scale to fit page to printer area
                # while maintaining aspect ratio
                scale_x = printer_width / (page_width * scale_factor)
                scale_y = printer_height / (page_height * scale_factor)
                scale = min(scale_x, scale_y)

                # Calculate final dimensions
                final_scale = scale_factor * scale
                final_width = page_width * final_scale
                final_height = page_height * final_scale

                # Center on page
                x_offset = (printer_width - final_width) / 2
                y_offset = (printer_height - final_height) / 2

                # Render page at high resolution
                # Use a matrix to scale to the desired resolution
                mat = fitz.Matrix(
                    final_scale * 2,  # Higher resolution for quality
                    final_scale * 2
                )
                pix = page.get_pixmap(matrix=mat)

                # Convert fitz pixmap to QImage
                if pix.n == 4:  # RGBA
                    img = QImage(
                        pix.samples,
                        pix.width,
                        pix.height,
                        pix.stride,
                        QImage.Format_ARGB32
                    )
                else:  # RGB
                    img = QImage(
                        pix.samples,
                        pix.width,
                        pix.height,
                        pix.stride,
                        QImage.Format_RGB888
                    )

                # Draw image to printer
                target_rect = QRectF(
                    x_offset,
                    y_offset,
                    final_width,
                    final_height
                )
                painter.drawImage(target_rect, img)

            return True

        except Exception as e:
            print(f"Print error: {e}")
            return False

        finally:
            painter.end()

    def get_printer(self) -> QPrinter:
        """Get the internal QPrinter instance."""
        return self._printer

    def set_printer(self, printer: QPrinter):
        """Set a custom QPrinter instance."""
        self._printer = printer
