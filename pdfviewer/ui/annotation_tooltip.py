#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Annotation Tooltip - Lightweight tooltip for annotation content.

A simple QLabel-based tooltip widget for displaying annotation content
on hover.
"""

from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt


class AnnotationTooltip(QLabel):
    """
    Lightweight annotation tooltip component.

    - Uses Qt.ToolTip | Qt.FramelessWindowHint flags
    - Styled with QSS
    - UI layer independent of PDF rendering engine
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("""
            QLabel {
                background-color: #ffffcc;
                border: 1px solid #cccc99;
                border-radius: 4px;
                padding: 8px;
                color: #333333;
                font-size: 12px;
                max-width: 300px;
            }
        """)
        self.setWordWrap(True)
