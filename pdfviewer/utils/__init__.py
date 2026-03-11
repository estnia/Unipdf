#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utils module - Utility functions and patterns.

This module provides utility functions for coordinate transformations,
pattern definitions for TOC detection, and other helper functions.
"""

from .patterns import (
    LEGAL_PATTERNS,
    GBT_PATTERNS,
    GENERAL_PATTERNS,
    CHAPTER_KEYWORDS,
    get_patterns_for_doc_type,
    detect_doc_type_from_text,
)
from .geometry import (
    compute_page_transform,
    screen_to_pdf_point,
    pdf_to_screen_rect,
    update_words_ui_rect,
    get_word_at_point,
    get_char_at_point,
)

__all__ = [
    'LEGAL_PATTERNS', 'GBT_PATTERNS', 'GENERAL_PATTERNS', 'CHAPTER_KEYWORDS',
    'get_patterns_for_doc_type', 'detect_doc_type_from_text',
    'compute_page_transform', 'screen_to_pdf_point', 'pdf_to_screen_rect',
    'update_words_ui_rect', 'get_word_at_point', 'get_char_at_point',
]
