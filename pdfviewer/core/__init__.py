#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Core module - Domain layer for PDF processing.

This module provides pure data models and algorithms for PDF processing,
without any UI dependencies. It can be used in both UI and worker threads.
"""

from .document import PDFDocument, PageTextInfo
from .renderer import (
    render_page,
    render_thumbnail,
    render_page_to_image,
    get_page_text_dict,
    get_page_raw_text,
    search_page_text,
)
from .text_engine import TextEngine

__all__ = [
    'PDFDocument', 'PageTextInfo',
    'render_page', 'render_thumbnail', 'render_page_to_image',
    'get_page_text_dict', 'get_page_raw_text', 'search_page_text',
    'TextEngine',
]
