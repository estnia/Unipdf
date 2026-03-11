#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Text parsing and selection engine.

This module provides functions for parsing text from PDF pages,
handling text selection, and working with character/word positions.
"""

from typing import List, Dict, Any, Optional, Tuple

# PDF engine: PyMuPDF (compatible with both old and new versions)
try:
    import fitz  # PyMuPDF < 1.23
except ImportError:
    import pymupdf as fitz  # PyMuPDF >= 1.23


class TextEngine:
    """
    Text parsing and selection engine.

    Handles loading, parsing, and querying text from PDF pages
    at both character and word levels.
    """

    def __init__(self):
        """Initialize the text engine."""
        self._page_cache: Dict[int, Dict[str, Any]] = {}

    def load_page(self, doc: fitz.Document, page_idx: int) -> Dict[str, Any]:
        """
        Load and parse text from a page.

        Args:
            doc: fitz.Document instance
            page_idx: Page index

        Returns:
            Dictionary with 'characters', 'words', and 'lines' lists
        """
        if page_idx in self._page_cache:
            return self._page_cache[page_idx]

        page = doc[page_idx]
        result = {
            'characters': [],
            'words': [],
            'lines': [],
            'blocks': []
        }

        try:
            # Get raw character data
            text_dict = page.get_text("rawdict")
            char_idx = 0

            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:  # Skip non-text blocks
                    continue

                block_info = {
                    'bbox': block.get("bbox", [0, 0, 0, 0]),
                    'lines': []
                }

                for line in block.get("lines", []):
                    line_info = {
                        'bbox': line.get("bbox", [0, 0, 0, 0]),
                        'spans': []
                    }

                    for span in line.get("spans", []):
                        span_info = {
                            'text': span.get("text", ""),
                            'bbox': span.get("bbox", [0, 0, 0, 0]),
                            'origin': span.get("origin", [0, 0]),
                            'font': span.get("font", ""),
                            'size': span.get("size", 12.0),
                            'flags': span.get("flags", 0),
                            'chars': []
                        }

                        chars = span.get("chars", [])
                        for char_info in chars:
                            c = char_info.get("c", "")
                            bbox = char_info.get("bbox", [0, 0, 0, 0])
                            if c.strip() or c == " ":
                                char_data = {
                                    "char": c,
                                    "bbox": bbox,
                                    "index": char_idx,
                                    "span_origin": span.get("origin", [0, 0]),
                                }
                                result['characters'].append(char_data)
                                span_info['chars'].append(char_data)
                                char_idx += 1

                        line_info['spans'].append(span_info)
                        block_info['lines'].append(line_info)

                    result['lines'].append(line_info)

                result['blocks'].append(block_info)

            # Build word list
            result['words'] = self._build_words(result['characters'])

        except Exception as e:
            print(f"Error loading page text: {e}")

        self._page_cache[page_idx] = result
        return result

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

    def get_text_between(self, start_idx: int, end_idx: int,
                         page_data: Dict[str, Any]) -> str:
        """
        Get text between two character indices.

        Args:
            start_idx: Starting character index
            end_idx: Ending character index
            page_data: Page data from load_page()

        Returns:
            Selected text string
        """
        chars = page_data.get('characters', [])
        if not chars or start_idx < 0 or end_idx >= len(chars):
            return ""

        # Ensure start <= end
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx

        selected_chars = chars[start_idx:end_idx + 1]
        return "".join(c["char"] for c in selected_chars)

    def get_word_at_point(self, point: Tuple[float, float],
                          page_data: Dict[str, Any],
                          tolerance: float = 0.5) -> Optional[Dict]:
        """
        Get the word at a given PDF point.

        Args:
            point: (x, y) in PDF coordinates
            page_data: Page data from load_page()
            tolerance: Hit tolerance in PDF units

        Returns:
            Word dict or None if not found
        """
        px, py = point
        words = page_data.get('words', [])

        for word in words:
            x0, y0, x1, y1 = word["bbox"]
            if (x0 - tolerance) <= px <= (x1 + tolerance) and \
               (y0 - tolerance) <= py <= (y1 + tolerance):
                return word

        # Find nearest if not directly hit
        best_word = None
        best_dist = float('inf')
        for word in words:
            x0, y0, x1, y1 = word["bbox"]
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            dist = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_word = word

        return best_word if best_dist < 20 else None

    def get_char_at_point(self, point: Tuple[float, float],
                          page_data: Dict[str, Any],
                          tolerance: float = 0.5) -> Optional[Dict]:
        """
        Get the character at a given PDF point.

        Args:
            point: (x, y) in PDF coordinates
            page_data: Page data from load_page()
            tolerance: Hit tolerance in PDF units

        Returns:
            Character dict or None if not found
        """
        px, py = point
        chars = page_data.get('characters', [])

        for char_info in chars:
            x0, y0, x1, y1 = char_info["bbox"]
            if (x0 - tolerance) <= px <= (x1 + tolerance) and \
               (y0 - tolerance) <= py <= (y1 + tolerance):
                return char_info

        # Find nearest
        best_char = None
        best_dist = float('inf')
        for char_info in chars:
            x0, y0, x1, y1 = char_info["bbox"]
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            dist = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_char = char_info

        return best_char if best_dist < 20 else None

    def get_line_at_point(self, point: Tuple[float, float],
                          page_data: Dict[str, Any]) -> Optional[Dict]:
        """
        Get the text line at a given PDF point.

        Args:
            point: (x, y) in PDF coordinates
            page_data: Page data from load_page()

        Returns:
            Line dict or None if not found
        """
        px, py = point
        lines = page_data.get('lines', [])

        for line in lines:
            x0, y0, x1, y1 = line["bbox"]
            if y0 <= py <= y1:
                return line

        return None

    def clear_cache(self, page_idx: Optional[int] = None):
        """
        Clear the text cache.

        Args:
            page_idx: Specific page to clear, or None for all
        """
        if page_idx is None:
            self._page_cache.clear()
        elif page_idx in self._page_cache:
            del self._page_cache[page_idx]

    def search_text(self, query: str, page_data: Dict[str, Any]) -> List[Dict]:
        """
        Search for text on a page.

        Args:
            query: Search query string
            page_data: Page data from load_page()

        Returns:
            List of match dicts with 'start_idx', 'end_idx', 'text', 'bbox'
        """
        matches = []
        query_lower = query.lower()
        chars = page_data.get('characters', [])

        if not chars or not query:
            return matches

        # Build full text
        full_text = "".join(c["char"] for c in chars)
        text_lower = full_text.lower()

        # Find all occurrences
        start = 0
        while True:
            idx = text_lower.find(query_lower, start)
            if idx == -1:
                break

            end_idx = idx + len(query) - 1

            # Calculate bbox
            start_char = chars[idx]
            end_char = chars[min(end_idx, len(chars) - 1)]

            bbox = [
                start_char["bbox"][0],
                min(start_char["bbox"][1], end_char["bbox"][1]),
                end_char["bbox"][2],
                max(start_char["bbox"][3], end_char["bbox"][3]),
            ]

            matches.append({
                'start_idx': idx,
                'end_idx': end_idx,
                'text': full_text[idx:end_idx + 1],
                'bbox': bbox,
            })

            start = idx + 1

        return matches
