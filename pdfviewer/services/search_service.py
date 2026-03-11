#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Search Service - Full-text search across PDF documents.

This service provides full-text search functionality with result navigation
and context extraction.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from PyQt5.QtCore import QObject, pyqtSignal

# PDF engine: PyMuPDF (compatible with both old and new versions)
try:
    import fitz  # PyMuPDF < 1.23
except ImportError:
    import pymupdf as fitz  # PyMuPDF >= 1.23

from pdfviewer.core.document import PDFDocument


@dataclass
class SearchMatch:
    """A single search match result."""
    page_idx: int
    char_start: int
    char_end: int
    context: str
    matched_text: str


class SearchService(QObject):
    """
    Service for full-text search in PDF documents.

    Provides search functionality with context extraction and
    result navigation.
    """

    search_completed = pyqtSignal(int)  # Number of results found
    result_selected = pyqtSignal(int, int, int)  # page_idx, char_start, char_end
    search_cleared = pyqtSignal()

    def __init__(self, parent=None):
        """Initialize search service."""
        super().__init__(parent)
        self._document: Optional[PDFDocument] = None
        self._results: List[SearchMatch] = []
        self._current_index: int = -1
        self._last_query: str = ""

    def set_document(self, document: Optional[PDFDocument]):
        """Set the current document."""
        self._document = document
        self.clear_results()

    def search(self, query: str, case_sensitive: bool = False) -> int:
        """
        Perform search across all pages.

        Args:
            query: Search query string
            case_sensitive: Whether search is case-sensitive

        Returns:
            Number of matches found
        """
        self.clear_results()

        if not self._document or not self._document.doc:
            return 0

        if not query:
            return 0

        self._last_query = query

        # Search all pages
        for page_idx in range(self._document.page_count):
            page = self._document.doc[page_idx]
            text_dict = page.get_text("rawdict")

            # Collect characters and lines
            lines_info = []
            chars = []
            char_idx = 0

            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    line_chars = []
                    line_text = ""
                    line_start_idx = char_idx

                    for span in line.get("spans", []):
                        for char_info in span.get("chars", []):
                            c = char_info.get("c", "")
                            chars.append(char_info)
                            line_chars.append(char_info)
                            line_text += c
                            char_idx += 1

                    if line_text:
                        lines_info.append({
                            "text": line_text,
                            "start_idx": line_start_idx,
                            "end_idx": char_idx - 1,
                            "chars": line_chars
                        })

            if not chars:
                continue

            # Build page text
            page_text = "".join(c.get("c", "") for c in chars)

            # Find all matches
            query_cmp = query if case_sensitive else query.lower()
            text_cmp = page_text if case_sensitive else page_text.lower()

            start = 0
            while True:
                idx = text_cmp.find(query_cmp, start)
                if idx == -1:
                    break

                # Get context
                context = self._get_context(lines_info, idx, len(query), page_text)

                self._results.append(SearchMatch(
                    page_idx=page_idx,
                    char_start=idx,
                    char_end=idx + len(query) - 1,
                    context=context,
                    matched_text=page_text[idx:idx + len(query)]
                ))

                start = idx + 1

        self.search_completed.emit(len(self._results))
        return len(self._results)

    def _get_context(self, lines_info: List[Dict], match_start: int,
                     match_len: int, full_text: str) -> str:
        """
        Get context around a match (one line before and after).

        Args:
            lines_info: List of line information
            match_start: Start index of match
            match_len: Length of match
            full_text: Full page text

        Returns:
            Context string with match highlighted
        """
        match_end = match_start + match_len - 1

        # Find match line
        match_line_idx = -1
        for i, line_info in enumerate(lines_info):
            if line_info["start_idx"] <= match_start <= line_info["end_idx"]:
                match_line_idx = i
                break

        if match_line_idx == -1:
            # Simple truncation fallback
            context_start = max(0, match_start - 30)
            context_end = min(len(full_text), match_start + match_len + 30)
            return full_text[context_start:context_end]

        # Get surrounding lines (up to 3 lines)
        context_parts = []
        start_line = max(0, match_line_idx - 1)
        end_line = min(len(lines_info) - 1, match_line_idx + 1)

        for i in range(start_line, end_line + 1):
            line_text = lines_info[i]["text"]

            # Highlight match on match line
            if i == match_line_idx:
                line_start = lines_info[i]["start_idx"]
                relative_start = match_start - line_start
                relative_end = min(relative_start + match_len, len(line_text))

                before = line_text[:relative_start]
                matched = line_text[relative_start:relative_end]
                after = line_text[relative_end:]

                # Use markers for highlighting
                line_text = f"{before}[{matched}]{after}"

            context_parts.append(line_text)

        result = " ".join(context_parts)

        # Truncate if too long
        if len(result) > 100:
            result = result[:97] + "..."

        return result

    def get_results(self) -> List[SearchMatch]:
        """Get all search results."""
        return self._results.copy()

    def get_current_result(self) -> Optional[SearchMatch]:
        """Get the currently selected result."""
        if 0 <= self._current_index < len(self._results):
            return self._results[self._current_index]
        return None

    def navigate_to(self, idx: int) -> Optional[SearchMatch]:
        """
        Navigate to a specific result.

        Args:
            idx: Result index

        Returns:
            The SearchMatch or None if invalid
        """
        if not self._results or idx < 0 or idx >= len(self._results):
            return None

        self._current_index = idx
        result = self._results[idx]
        self.result_selected.emit(result.page_idx, result.char_start, result.char_end)
        return result

    def navigate_next(self) -> Optional[SearchMatch]:
        """Navigate to next result."""
        if not self._results:
            return None

        next_idx = self._current_index + 1
        if next_idx >= len(self._results):
            next_idx = 0  # Wrap around

        return self.navigate_to(next_idx)

    def navigate_prev(self) -> Optional[SearchMatch]:
        """Navigate to previous result."""
        if not self._results:
            return None

        prev_idx = self._current_index - 1
        if prev_idx < 0:
            prev_idx = len(self._results) - 1  # Wrap around

        return self.navigate_to(prev_idx)

    def clear_results(self):
        """Clear all search results."""
        self._results.clear()
        self._current_index = -1
        self.search_cleared.emit()

    def get_result_count(self) -> int:
        """Get total number of results."""
        return len(self._results)

    def get_current_index(self) -> int:
        """Get current result index."""
        return self._current_index

    def is_search_active(self) -> bool:
        """Check if there's an active search."""
        return len(self._results) > 0

    def get_last_query(self) -> str:
        """Get the last search query."""
        return self._last_query
