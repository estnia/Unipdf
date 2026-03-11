#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Annotation Service - Manages PDF annotations.

This service handles adding, deleting, and querying annotations
including highlights and underlines.
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from PyQt5.QtCore import QObject, pyqtSignal

# PDF engine: PyMuPDF (compatible with both old and new versions)
try:
    import fitz  # PyMuPDF < 1.23
except ImportError:
    import pymupdf as fitz  # PyMuPDF >= 1.23

from pdfviewer.core.document import PDFDocument


@dataclass
class AnnotationInfo:
    """Information about an annotation."""
    rect: fitz.Rect
    content: str
    annot_type: int  # 8 = Highlight, 9 = Underline
    page_idx: int


class AnnotationService(QObject):
    """
    Service for managing PDF annotations.

    Handles adding highlights, underlines, building annotation indexes,
    and querying annotations at positions.
    """

    annotations_changed = pyqtSignal()
    annotation_added = pyqtSignal(int, str)  # page_idx, annot_type
    annotation_deleted = pyqtSignal(int, str)  # page_idx, annot_type

    def __init__(self, parent=None):
        """Initialize annotation service."""
        super().__init__(parent)
        self._document: Optional[PDFDocument] = None
        self._hotspot_map: Dict[int, List[Dict]] = {}  # page_idx -> list of annot info

    def set_document(self, document: Optional[PDFDocument]):
        """Set the current document."""
        self._document = document
        self._hotspot_map.clear()
        if document:
            self.build_index()

    def build_index(self):
        """
        Build annotation hotspot index.
        Scans all pages for annotations and builds a lookup map.
        """
        self._hotspot_map.clear()

        if not self._document or not self._document.doc:
            return

        for page_idx in range(self._document.page_count):
            page = self._document.doc[page_idx]
            annots = list(page.annots())

            page_annots = []
            for annot in annots:
                # annot.type returns (type_num, type_name) or int depending on version
                annot_type = annot.type
                if isinstance(annot_type, tuple):
                    type_num = annot_type[0]
                else:
                    type_num = annot_type

                # Handle Highlight (8) and Underline (9) annotations
                if type_num in (8, 9):
                    rect = annot.rect
                    info = annot.info
                    content = info.get("content", "") if info else ""

                    # For underline, only show tooltip if has content
                    if type_num == 9 and not content:
                        continue

                    page_annots.append({
                        "rect": rect,
                        "content": content,
                        "type": type_num,
                    })

            if page_annots:
                self._hotspot_map[page_idx] = page_annots

    def get_annotations_for_page(self, page_idx: int) -> List[Dict]:
        """Get annotations for a specific page."""
        return self._hotspot_map.get(page_idx, [])

    def get_annotation_at_point(self, page_idx: int, pdf_point: Tuple[float, float]
                                ) -> Optional[Dict]:
        """
        Get annotation at a PDF point.

        Args:
            page_idx: Page index
            pdf_point: (x, y) in PDF coordinates

        Returns:
            Annotation dict or None
        """
        if page_idx not in self._hotspot_map:
            return None

        px, py = pdf_point
        for annot in self._hotspot_map[page_idx]:
            rect = annot["rect"]
            if rect.x0 <= px <= rect.x1 and rect.y0 <= py <= rect.y1:
                return annot

        return None

    def add_highlight(self, page_idx: int, char_infos: List[Dict]) -> int:
        """
        Add highlight annotations for selected characters.

        Args:
            page_idx: Page index
            char_infos: List of character info dicts with "bbox" keys

        Returns:
            Number of highlights added
        """
        if not self._document or not self._document.doc:
            return 0

        page = self._document.doc[page_idx]

        # Group characters by line
        line_groups = self._group_chars_by_line(char_infos)

        # Add highlight for each line
        count = 0
        for line_chars in line_groups:
            if not line_chars:
                continue

            # Calculate bounding box for the line
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
                count += 1

        if count > 0:
            self._document.mark_modified(True)
            self.build_index()
            self.annotations_changed.emit()
            self.annotation_added.emit(page_idx, "highlight")

        return count

    def add_underline(self, page_idx: int, char_infos: List[Dict],
                      content: str) -> int:
        """
        Add underline annotation for selected characters.

        Args:
            page_idx: Page index
            char_infos: List of character info dicts with "bbox" keys
            content: Annotation content/text

        Returns:
            Number of underlines added
        """
        if not self._document or not self._document.doc:
            return 0

        page = self._document.doc[page_idx]

        # Group characters by line
        line_groups = self._group_chars_by_line(char_infos)

        # Add underline for each line
        count = 0
        for line_chars in line_groups:
            if not line_chars:
                continue

            # Calculate bounding box
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
                underline.set_colors(stroke=(1, 0, 0))  # Red
                underline.set_info(content=content)
                underline.update()
                count += 1

        if count > 0:
            self._document.mark_modified(True)
            self.build_index()
            self.annotations_changed.emit()
            self.annotation_added.emit(page_idx, "underline")

        return count

    def _group_chars_by_line(self, char_infos: List[Dict],
                             tolerance: float = 5.0) -> List[List[Dict]]:
        """
        Group characters by line based on Y coordinate.

        Args:
            char_infos: List of character info dicts
            tolerance: Y coordinate tolerance for same line

        Returns:
            List of character groups (one per line)
        """
        if not char_infos:
            return []

        line_groups = []
        current_line = [char_infos[0]]
        current_y_center = sum(char_infos[0]["bbox"][1::2]) / 2

        for char_info in char_infos[1:]:
            bbox = char_info["bbox"]
            y_center = (bbox[1] + bbox[3]) / 2

            if abs(y_center - current_y_center) < tolerance:
                current_line.append(char_info)
            else:
                line_groups.append(current_line)
                current_line = [char_info]
                current_y_center = y_center

        line_groups.append(current_line)
        return line_groups

    def delete_annotation_at_point(self, page_idx: int,
                                   pdf_point: Tuple[float, float]) -> bool:
        """
        Delete annotation at a PDF point.

        Args:
            page_idx: Page index
            pdf_point: (x, y) in PDF coordinates

        Returns:
            True if annotation was deleted
        """
        if not self._document or not self._document.doc:
            return False

        page = self._document.doc[page_idx]
        px, py = pdf_point

        for annot in page.annots():
            annot_type = annot.type
            if isinstance(annot_type, tuple):
                type_num = annot_type[0]
            else:
                type_num = annot_type

            if type_num in (8, 9):  # Highlight or Underline
                rect = annot.rect
                if rect.x0 <= px <= rect.x1 and rect.y0 <= py <= rect.y1:
                    page.delete_annot(annot)
                    self._document.mark_modified(True)
                    self.build_index()
                    self.annotations_changed.emit()
                    self.annotation_deleted.emit(page_idx, "annot")
                    return True

        return False

    def get_all_annotations(self) -> List[AnnotationInfo]:
        """Get all annotations in the document."""
        result = []
        for page_idx, annots in self._hotspot_map.items():
            for annot in annots:
                result.append(AnnotationInfo(
                    rect=annot["rect"],
                    content=annot["content"],
                    annot_type=annot["type"],
                    page_idx=page_idx
                ))
        return result

    def clear(self):
        """Clear all annotation data."""
        self._hotspot_map.clear()
        self._document = None
