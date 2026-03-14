#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Core document model - Pure data layer for PDF documents.

This module provides a wrapper around fitz.Document that encapsulates
document state without any UI dependencies.
"""

import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

# PDF engine: PyMuPDF (compatible with both old and new versions)
try:
    import fitz  # PyMuPDF < 1.23
except ImportError:
    import pymupdf as fitz  # PyMuPDF >= 1.23


@dataclass
class PageTextInfo:
    """Text information for a single page."""
    characters: List[Dict[str, Any]] = field(default_factory=list)
    words: List[Dict[str, Any]] = field(default_factory=list)


class PDFDocument:
    """
    Pure data model for a PDF document.

    This class wraps fitz.Document and maintains document state
    without any UI dependencies.
    """

    def __init__(self, file_path: Optional[str] = None):
        """Initialize document model."""
        self._doc: Optional[fitz.Document] = None
        self._file_path: Optional[str] = None
        self._metadata: Dict[str, Any] = {}
        self._current_page: int = 0
        self._zoom_factor: float = 1.0
        self._modified: bool = False

        # Text information cache
        self._page_text_info: Dict[int, PageTextInfo] = {}

        if file_path:
            self.open(file_path)

    def open(self, file_path: str) -> bool:
        """
        Open a PDF document.

        Args:
            file_path: Path to the PDF file

        Returns:
            True if successful, False otherwise
        """
        try:
            self.close()

            self._doc = fitz.open(file_path)
            self._file_path = file_path
            self._metadata = {
                'title': self._doc.metadata.get('title', ''),
                'author': self._doc.metadata.get('author', ''),
                'subject': self._doc.metadata.get('subject', ''),
                'creator': self._doc.metadata.get('creator', ''),
                'producer': self._doc.metadata.get('producer', ''),
                'format': self._doc.metadata.get('format', ''),
                'encryption': self._doc.metadata.get('encryption', None),
            }
            self._current_page = 0
            self._zoom_factor = 1.0
            self._modified = False
            self._page_text_info.clear()

            return True
        except Exception as e:
            print(f"Failed to open PDF: {e}")
            return False

    def close(self):
        """Close the document and release resources."""
        if self._doc:
            try:
                self._doc.close()
            except:
                pass
            self._doc = None

        self._file_path = None
        self._metadata = {}
        self._current_page = 0
        self._zoom_factor = 1.0
        self._modified = False
        self._page_text_info.clear()

    def save(self, file_path: Optional[str] = None) -> bool:
        """
        Save the document.

        Args:
            file_path: Optional path to save to (defaults to original path)

        Returns:
            True if successful, False otherwise
        """
        if not self._doc:
            return False

        path = file_path or self._file_path
        if not path:
            return False

        try:
            self._doc.save(path, incremental=True)
            self._modified = False
            return True
        except Exception as e:
            error_msg = str(e).lower()
            if "incremental" in error_msg or "encryption" in error_msg:
                try:
                    import shutil
                    temp_path = path + ".tmp"
                    self._doc.save(temp_path)
                    shutil.move(temp_path, path)
                    self._modified = False
                    return True
                except:
                    return False
            return False

    @property
    def doc(self) -> Optional[fitz.Document]:
        """Get the underlying fitz.Document."""
        return self._doc

    @property
    def file_path(self) -> Optional[str]:
        """Get the file path."""
        return self._file_path

    @property
    def file_name(self) -> str:
        """Get the file name."""
        if self._file_path:
            return os.path.basename(self._file_path)
        return "Untitled"

    @property
    def page_count(self) -> int:
        """Get the number of pages."""
        return len(self._doc) if self._doc else 0

    @property
    def metadata(self) -> Dict[str, Any]:
        """Get document metadata."""
        return self._metadata.copy()

    @property
    def current_page(self) -> int:
        """Get current page index."""
        return self._current_page

    @current_page.setter
    def current_page(self, value: int):
        """Set current page index."""
        if self._doc and 0 <= value < len(self._doc):
            self._current_page = value

    @property
    def zoom_factor(self) -> float:
        """Get current zoom factor."""
        return self._zoom_factor

    @zoom_factor.setter
    def zoom_factor(self, value: float):
        """Set zoom factor."""
        self._zoom_factor = max(0.1, min(5.0, value))

    @property
    def is_modified(self) -> bool:
        """Check if document has been modified."""
        return self._modified

    def mark_modified(self, modified: bool = True):
        """Mark document as modified."""
        self._modified = modified

    def get_page(self, page_idx: int) -> Optional[fitz.Page]:
        """
        Get a page by index.

        Args:
            page_idx: Page index (0-based)

        Returns:
            fitz.Page or None if invalid
        """
        if not self._doc or not (0 <= page_idx < len(self._doc)):
            return None
        return self._doc[page_idx]

    def get_page_size(self, page_idx: int) -> tuple:
        """
        Get page size in points.

        Args:
            page_idx: Page index (0-based)

        Returns:
            Tuple of (width, height) or (0, 0) if invalid
        """
        page = self.get_page(page_idx)
        if not page:
            return (0, 0)
        rect = page.rect
        return (rect.width, rect.height)

    def calculate_auto_fit_zoom(self, viewport_width: int, viewport_height: int,
                                fit_mode: str = "fit_page") -> float:
        """
        Calculate adaptive zoom factor to fit viewport.

        Args:
            viewport_width: Viewport width in pixels
            viewport_height: Viewport height in pixels
            fit_mode: Fit mode
                - "fit_page": Fit entire page (default)
                - "fit_width": Fit to width

        Returns:
            Calculated zoom factor
        """
        if not self._doc or self.page_count == 0:
            return 1.0

        # Get first page size (in points)
        page_width_pts, page_height_pts = self.get_page_size(0)
        if page_width_pts == 0 or page_height_pts == 0:
            return 1.0

        # Leave some margin for better visual effect
        # Reserve scrollbar width (20px) to prevent layout oscillation
        scrollbar_width = 20  # pixels
        if fit_mode == "fit_width":
            # For fit_width: use viewport width directly, no margin needed
            # but reserve scrollbar width to prevent horizontal scrollbar
            margin = scrollbar_width
            available_width = max(10, viewport_width - margin)
            available_height = max(10, viewport_height - margin)
        else:
            # For fit_page: larger margin for better visual
            margin = 40
            available_width = max(10, viewport_width - margin)
            available_height = max(10, viewport_height - margin)

        # Calculate zoom factor based on fit mode
        if fit_mode == "fit_page":
            # Fit entire page - use the smaller scale
            scale_w = available_width / page_width_pts
            scale_h = available_height / page_height_pts
            zoom = min(scale_w, scale_h)
        elif fit_mode == "fit_width":
            # Fit to width only
            zoom = available_width / page_width_pts
        else:
            zoom = 1.0

        # Limit zoom range [0.1, 5.0]
        return max(0.1, min(5.0, zoom))

    def load_page_text(self, page_idx: int) -> PageTextInfo:
        """
        Load text information for a page.

        Args:
            page_idx: Page index (0-based)

        Returns:
            PageTextInfo with characters and words
        """
        if page_idx in self._page_text_info:
            return self._page_text_info[page_idx]

        info = PageTextInfo()
        page = self.get_page(page_idx)
        if not page:
            return info

        try:
            # Use rawdict for character-level info
            text_dict = page.get_text("rawdict")
            char_idx = 0

            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        chars = span.get("chars", [])
                        origin = span.get("origin", [0, 0])

                        if chars:
                            for char_info in chars:
                                c = char_info.get("c", "")
                                bbox = char_info.get("bbox", [0, 0, 0, 0])
                                if c.strip() or c == " ":
                                    info.characters.append({
                                        "char": c,
                                        "bbox": bbox,
                                        "span_origin": origin,
                                        "index": char_idx,
                                    })
                                    char_idx += 1

            # Build word list
            info.words = self._build_words(info.characters)

        except Exception as e:
            print(f"Error loading page text: {e}")

        self._page_text_info[page_idx] = info
        return info

    def _build_words(self, characters: List[Dict]) -> List[Dict]:
        """
        Build word list from characters.

        Args:
            characters: List of character info dicts

        Returns:
            List of word info dicts
        """
        words = []
        if not characters:
            return words

        current_word_chars = []
        current_word_bbox = None

        for char_info in characters:
            char = char_info["char"]
            bbox = char_info["bbox"]

            if char.isspace():
                # End current word
                if current_word_chars:
                    word_text = "".join(c["char"] for c in current_word_chars)
                    words.append({
                        "text": word_text,
                        "bbox": current_word_bbox,
                        "char_indices": [c["index"] for c in current_word_chars],
                    })
                    current_word_chars = []
                    current_word_bbox = None
            else:
                # Add to current word
                current_word_chars.append(char_info)
                if current_word_bbox is None:
                    current_word_bbox = list(bbox)
                else:
                    current_word_bbox[0] = min(current_word_bbox[0], bbox[0])
                    current_word_bbox[1] = min(current_word_bbox[1], bbox[1])
                    current_word_bbox[2] = max(current_word_bbox[2], bbox[2])
                    current_word_bbox[3] = max(current_word_bbox[3], bbox[3])

        # Don't forget last word
        if current_word_chars:
            word_text = "".join(c["char"] for c in current_word_chars)
            words.append({
                "text": word_text,
                "bbox": current_word_bbox,
                "char_indices": [c["index"] for c in current_word_chars],
            })

        return words

    def clear_text_cache(self, page_idx: Optional[int] = None):
        """
        Clear text information cache.

        Args:
            page_idx: Specific page to clear, or None for all
        """
        if page_idx is None:
            self._page_text_info.clear()
        elif page_idx in self._page_text_info:
            del self._page_text_info[page_idx]

    def is_open(self) -> bool:
        """Check if a document is currently open."""
        return self._doc is not None

    def __len__(self) -> int:
        """Return page count."""
        return self.page_count

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
