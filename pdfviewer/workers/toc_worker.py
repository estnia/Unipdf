#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TOC (Table of Contents) Worker Thread - Automatic TOC generation.

This module provides a QThread-based worker for automatically detecting
document structure and generating table of contents for various document
types including legal documents and GB/T standards.
"""

import re
from PyQt5.QtCore import QThread, pyqtSignal

# PDF engine: PyMuPDF (compatible with both old and new versions)
try:
    import fitz  # PyMuPDF < 1.23
except ImportError:
    import pymupdf as fitz  # PyMuPDF >= 1.23

from pdfviewer.utils.patterns import (
    LEGAL_PATTERNS, GBT_PATTERNS, GENERAL_PATTERNS,
    CHAPTER_KEYWORDS, get_patterns_for_doc_type, detect_doc_type_from_text
)


class AutoTocWorker(QThread):
    """
    Automatic table of contents generation worker thread.

    Analyzes document structure using font statistics and regex patterns
to detect chapter headings and build a hierarchical TOC.
    """

    # Signals: list of [level, title, page] entries
    finished = pyqtSignal(list)
    # Signals: current_page, total_pages
    progress = pyqtSignal(int, int)
    # Signals: error_message
    error = pyqtSignal(str)

    def __init__(self, doc_path: str, doc_type: str = "auto"):
        """
        Initialize TOC worker.

        Args:
            doc_path: PDF file path
            doc_type: Document type - "legal", "gbt", or "auto" for auto-detection
        """
        super().__init__()
        self.doc_path = doc_path
        self.doc_type = doc_type
        self._is_running = True

    def run(self):
        """Execute TOC analysis in background thread."""
        try:
            doc = fitz.open(self.doc_path)

            # Step 1: Character sampling - analyze font distribution in first 50 pages
            font_stats = self._analyze_font_stats(doc)
            base_size = self._determine_base_font(font_stats)

            # Step 2: Detect document type if auto
            if self.doc_type == "auto":
                self.doc_type = self._detect_doc_type(doc)

            # Step 3: Configure regex engine
            l1_pattern, l2_pattern = get_patterns_for_doc_type(self.doc_type)

            # Step 4: Scan pages to extract headings
            toc_candidates = []
            total_pages = min(len(doc), 50)  # Scan max 50 pages

            for page_idx in range(total_pages):
                if not self._is_running:
                    break

                self.progress.emit(page_idx + 1, total_pages)
                page = doc[page_idx]

                # Crop region: ignore 5% edges (exclude headers/page numbers)
                crop_rect = self._get_crop_rect(page.rect)

                # Get text lines (not blocks) so each heading is detected independently
                lines = self._get_text_lines(page, crop_rect)

                i = 0
                while i < len(lines):
                    line = lines[i]
                    next_line = lines[i + 1] if i + 1 < len(lines) else None
                    next_line_text = next_line["text"] if next_line else None

                    result = self._process_line(
                        line, page_idx, base_size,
                        l1_pattern, l2_pattern, next_line_text
                    )
                    if result:
                        toc_candidates.append(result)
                        # If next line was merged, skip it
                        text = line["text"].strip()
                        is_l1_digit = text.isdigit()
                        is_l2_digit_only = bool(re.match(r'^\d+\.\d+$', text))
                        if next_line_text and result["text"] != text:
                            if is_l1_digit or is_l2_digit_only:
                                i += 2
                                continue
                    i += 1

                # Memory optimization - clean up unreferenced objects
                if page_idx % 10 == 0:
                    fitz.TOOLS.store_shrink(100)  # 100% = clean all

            doc.close()

            # Step 5: Deduplication and hierarchy aggregation
            toc_list = self._build_toc_tree(toc_candidates)

            if self._is_running:
                self.finished.emit(toc_list)

        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        """Stop analysis."""
        self._is_running = False
        self.wait(100)

    def _analyze_font_stats(self, doc: fitz.Document) -> dict:
        """Analyze font size distribution in first 50 pages."""
        font_sizes = []
        sample_pages = min(len(doc), 50)

        for page_idx in range(sample_pages):
            page = doc[page_idx]
            blocks = page.get_text("dict")["blocks"]

            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            font_sizes.append(span["size"])

        # Count frequencies
        size_counts = {}
        for size in font_sizes:
            # Group font sizes to integer ranges
            rounded = round(size)
            size_counts[rounded] = size_counts.get(rounded, 0) + 1

        return size_counts

    def _determine_base_font(self, font_stats: dict) -> float:
        """Determine base font size from statistics."""
        if not font_stats:
            return 12.0

        # Find most frequent font size
        most_common = max(font_stats.items(), key=lambda x: x[1])
        return float(most_common[0])

    def _detect_doc_type(self, doc: fitz.Document) -> str:
        """Auto-detect document type from content."""
        sample_text = ""
        sample_pages = min(len(doc), 10)

        for page_idx in range(sample_pages):
            page = doc[page_idx]
            text = page.get_text()
            sample_text += text[:5000]  # First 5000 chars per page

        return detect_doc_type_from_text(sample_text)

    def _get_crop_rect(self, page_rect: fitz.Rect) -> fitz.Rect:
        """Get cropped page region (ignore 5% edges to avoid headers/page numbers)."""
        margin = 0.05  # 5% margin
        x0 = page_rect.x0 + page_rect.width * margin
        y0 = page_rect.y0 + page_rect.height * margin
        x1 = page_rect.x1 - page_rect.width * margin
        y1 = page_rect.y1 - page_rect.height * margin
        return fitz.Rect(x0, y0, x1, y1)

    def _get_text_lines(self, page: fitz.Page, clip_rect: fitz.Rect) -> list:
        """Extract text lines from page with coordinates."""
        lines = []
        blocks = page.get_text("dict", clip=clip_rect)["blocks"]

        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                # Collect all span texts in this line
                line_text = ""
                for span in line["spans"]:
                    line_text += span["text"]

                line_text = line_text.strip()
                if not line_text:
                    continue

                # Get line bbox
                bbox = line["bbox"]
                lines.append({
                    "text": line_text,
                    "bbox": bbox,
                    "font_size": line["spans"][0]["size"] if line["spans"] else 12.0
                })

        return lines

    def _process_line(self, line: dict, page_idx: int, base_size: float,
                      l1_pattern, l2_pattern, next_line_text: str = None) -> dict:
        """Process a single text line to extract heading candidate."""
        text = line["text"]
        x0, y0, x1, y1 = line["bbox"]

        # Clean text
        text = text.strip()
        if not text or len(text) > 200:
            return None

        # Try matching L2 (e.g., "2.1 Terms")
        l2_match = l2_pattern.match(text)
        if l2_match:
            # Filter out overly long matches
            if len(text) > 50:
                return None
            return {
                "page": page_idx,
                "text": text,
                "bbox": (x0, y0, x1, y1),
                "level": 2,
                "match_type": "L2"
            }

        # Special handling: L2 chapter number on separate line (e.g., "4.4")
        if re.match(r'^\d+\.\d+$', text) and next_line_text:
            next_text = next_line_text.strip()
            # Check if next line is chapter title
            if next_text and len(next_text) <= 20:
                if next_text[0] not in '。，、；：！？.' and '附录' not in next_text:
                    if any(next_text.startswith(kw) for kw in CHAPTER_KEYWORDS):
                        combined = text + " " + next_text
                        return {
                            "page": page_idx,
                            "text": combined,
                            "bbox": (x0, y0, x1, y1),
                            "level": 2,
                            "match_type": "L2"
                        }

        # Try matching L1 (e.g., "1 Scope", "10 General", "6 Appendix A")
        l1_match = l1_pattern.match(text)
        if l1_match:
            # Check for date keywords
            if any(keyword in text for keyword in ['年', '月', '日', '发布', '实施']):
                return None
            # Check if number too large (>100 might be page number or date)
            num = int(l1_match.group(1))
            if num > 100:
                return None
            return {
                "page": page_idx,
                "text": text,
                "bbox": (x0, y0, x1, y1),
                "level": 1,
                "match_type": "L1"
            }

        # Special handling: pure digit with next line being Chinese title
        if text.isdigit() and next_line_text:
            next_text = next_line_text.strip()
            if next_text and len(next_text) <= 20:
                if next_text[0] not in '。，、；：！？.':
                    extended_keywords = CHAPTER_KEYWORDS + ['附录']
                    if any(next_text.startswith(kw) for kw in extended_keywords):
                        combined = text + " " + next_text
                        return {
                            "page": page_idx,
                            "text": combined,
                            "bbox": (x0, y0, x1, y1),
                            "level": 1,
                            "match_type": "L1"
                        }

        return None

    def _process_block(self, block, page_idx: int, base_size: float,
                       l1_pattern, l2_pattern) -> dict:
        """Process a single text block to extract heading candidate."""
        x0, y0, x1, y1, text, block_no, block_type = block

        # Clean text
        text = text.strip()
        if not text or len(text) > 300:
            return None

        # Try matching
        l1_match = l1_pattern.match(text)
        l2_match = l2_pattern.match(text) if not l1_match else None

        if not l1_match and not l2_match:
            return None

        # Filter dates for L1
        if l1_match:
            if any(keyword in text for keyword in ['年', '月', '日', '发布', '实施']):
                return None
            num = int(l1_match.group(1))
            if num > 100:
                return None

        # Filter clause text ending with punctuation
        if text.endswith(('。', '.', '；', ';')) and not (l1_match or l2_match):
            return None

        return {
            "page": page_idx,
            "text": text,
            "bbox": (x0, y0, x1, y1),
            "level": 1 if l1_match else 2,
            "match_type": "L1" if l1_match else "L2"
        }

    def _build_toc_tree(self, candidates: list) -> list:
        """Build hierarchical tree structure in PyMuPDF TOC format."""
        # Deduplicate: (page, normalized_text) hash table
        seen = {}
        unique_candidates = []

        for c in candidates:
            key = (c["page"], self._normalize_text(c["text"]))
            if key not in seen:
                seen[key] = c
                unique_candidates.append(c)

        # Sort by page and Y coordinate
        unique_candidates.sort(key=lambda x: (x["page"], x["bbox"][1]))

        # Build nested structure
        toc_list = []
        active_l1 = None

        for c in unique_candidates:
            if c["level"] == 1:
                # L1 level - add directly
                toc_list.append([1, c["text"], c["page"] + 1])  # Page numbers start at 1
                active_l1 = c
            elif c["level"] == 2 and active_l1:
                # L2 level - under current L1
                toc_list.append([2, c["text"], c["page"] + 1])

        return toc_list

    def _normalize_text(self, text: str) -> str:
        """Normalize text for deduplication."""
        # Remove whitespace and lowercase
        return ''.join(text.split()).lower()
