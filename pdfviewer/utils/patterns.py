#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TOC (Table of Contents) pattern definitions for automatic detection.

This module contains regular expression patterns for detecting document
structure in various types of documents including legal documents,
GB/T standards, and general documents.
"""

import re

# Legal document patterns (法律文档)
LEGAL_PATTERNS = {
    "L1": re.compile(r'^第[一二三四五六七八九十百千]+[编章]', re.UNICODE),
    "L2": re.compile(r'^第[一二三四五六七八九十百千]+[节条]', re.UNICODE)
}

# GB/T standard patterns (国标标准文档)
GBT_PATTERNS = {
    "L1": re.compile(r'^(\d+)\s+[\u4e00-\u9fa5]', re.UNICODE),  # 1-99 range
    "L2": re.compile(r'^(\d+\.\d+)\s+[\u4e00-\u9fa5]', re.UNICODE)  # 1.1, 2.1, etc.
}

# General document patterns (通用文档)
GENERAL_PATTERNS = {
    "L1": re.compile(r'^(?:第[一二三四五六七八九十百千]+[编章]|\d+\s+[\u4e00-\u9fa5])', re.UNICODE),
    "L2": re.compile(r'^(?:第[一二三四五六七八九十百千]+[节条]|\d+\.\d+)', re.UNICODE)
}

# Chapter title keywords for GB/T standard documents
# Used for merging chapter numbers with titles
CHAPTER_KEYWORDS = [
    '范围', '术语', '定义', '要求', '内容', '标示', '其他', '总则',
    '规定', '预包装', '食品', '配料', '生产', '保质期', '规格',
    '主要', '推荐', '豁免', '基本'
]


def get_patterns_for_doc_type(doc_type: str):
    """
    Get regex patterns for a specific document type.

    Args:
        doc_type: Document type - "legal", "gbt", or "general"

    Returns:
        Tuple of (l1_pattern, l2_pattern)
    """
    if doc_type == "legal":
        return LEGAL_PATTERNS["L1"], LEGAL_PATTERNS["L2"]
    elif doc_type == "gbt":
        return GBT_PATTERNS["L1"], GBT_PATTERNS["L2"]
    else:
        return GENERAL_PATTERNS["L1"], GENERAL_PATTERNS["L2"]


def detect_doc_type_from_text(sample_text: str) -> str:
    """
    Automatically detect document type from sample text.

    Args:
        sample_text: Text sample from the document

    Returns:
        Document type: "legal", "gbt", or "general"
    """
    # Check for legal document patterns
    if LEGAL_PATTERNS["L1"].search(sample_text):
        return "legal"

    # Check for GB/T standard patterns
    if GBT_PATTERNS["L1"].search(sample_text) or \
       GBT_PATTERNS["L2"].search(sample_text):
        return "gbt"

    return "general"
