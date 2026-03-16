#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Async Search Worker - Background search thread.

Performs full-text search across PDF pages without blocking the UI.
Emits progress and results as they are found.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from PyQt5.QtCore import QThread, pyqtSignal

# PDF engine
try:
    import fitz
except ImportError:
    import pymupdf as fitz


@dataclass
class SearchMatch:
    """A single search match result."""
    page_idx: int
    char_start: int
    char_end: int
    context: str
    matched_text: str


class AsyncSearchWorker(QThread):
    """
    Asynchronous search worker for PDF documents.

    Signals:
        search_started: Emitted when search begins
        search_progress(current, total): Emitted for each page processed
        search_result(match): Emitted when a match is found
        search_completed(count): Emitted when search finishes
        search_error(error_msg): Emitted if an error occurs
        search_cancelled: Emitted if search was cancelled
    """

    search_started = pyqtSignal()
    search_progress = pyqtSignal(int, int)  # current_page, total_pages
    search_result = pyqtSignal(object)  # SearchMatch
    search_completed = pyqtSignal(int)  # total_matches
    search_error = pyqtSignal(str)
    search_cancelled = pyqtSignal()

    def __init__(self, doc_path: str, query: str, case_sensitive: bool = False,
                 parent=None):
        """
        Initialize search worker.

        Args:
            doc_path: Path to PDF document
            query: Search query string
            case_sensitive: Whether search is case-sensitive
            parent: Parent QObject
        """
        super().__init__(parent)
        self._doc_path = doc_path
        self._query = query
        self._case_sensitive = case_sensitive
        self._is_cancelled = False
        self._total_matches = 0

    def run(self):
        """Execute search in background thread."""
        try:
            self._is_cancelled = False
            self._total_matches = 0
            self.search_started.emit()

            doc = fitz.open(self._doc_path)
            try:
                total_pages = len(doc)

                for page_idx in range(total_pages):
                    if self._is_cancelled:
                        self.search_cancelled.emit()
                        return

                    # Emit progress
                    self.search_progress.emit(page_idx + 1, total_pages)

                    # Search this page
                    matches = self._search_page(doc, page_idx)
                    self._total_matches += len(matches)

                    # Emit each match
                    for match in matches:
                        if self._is_cancelled:
                            self.search_cancelled.emit()
                            return
                        self.search_result.emit(match)

                # Search completed
                self.search_completed.emit(self._total_matches)

            finally:
                doc.close()

        except Exception as e:
            self.search_error.emit(str(e))

    def _search_page(self, doc: fitz.Document, page_idx: int) -> List[SearchMatch]:
        """
        Search a single page for matches.

        Args:
            doc: fitz Document
            page_idx: Page index

        Returns:
            List of SearchMatch objects
        """
        matches = []
        page = doc[page_idx]
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
            return matches

        # Build page text
        page_text = "".join(c.get("c", "") for c in chars)

        # Find all matches
        query = self._query
        query_cmp = query if self._case_sensitive else query.lower()
        text_cmp = page_text if self._case_sensitive else page_text.lower()

        start = 0
        while True:
            idx = text_cmp.find(query_cmp, start)
            if idx == -1:
                break

            # Get context
            context = self._get_context(lines_info, idx, len(query), page_text)

            match = SearchMatch(
                page_idx=page_idx,
                char_start=idx,
                char_end=idx + len(query) - 1,
                context=context,
                matched_text=page_text[idx:idx + len(query)]
            )
            matches.append(match)

            start = idx + 1

        return matches

    def _get_context(self, lines_info: List[Dict], match_start: int,
                     match_len: int, full_text: str) -> str:
        """Get context around a match."""
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

                line_text = f"{before}[{matched}]{after}"

            context_parts.append(line_text)

        result = " ".join(context_parts)

        # Truncate if too long
        if len(result) > 100:
            result = result[:97] + "..."

        return result

    def cancel(self):
        """Cancel the ongoing search."""
        self._is_cancelled = True
        self.wait(100)  # Wait briefly for thread to notice

    def is_cancelled(self) -> bool:
        """Check if search was cancelled."""
        return self._is_cancelled
