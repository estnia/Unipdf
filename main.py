#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unipdf - 极简极速 PDF 查看器
适配 UOS V20 (Linux) 环境，类似 Windows SumatraPDF
核心技术栈: Python 3 + PyQt5 + PyMuPDF (fitz)

重构版本 - 采用模块化架构

项目结构:
- pdfviewer/core/    : 核心领域层 (PDFDocument, 渲染, 文本引擎)
- pdfviewer/services/: 业务服务层 (渲染服务, 注释服务, 搜索服务, 缩略图服务)
- pdfviewer/workers/ : 后台工作线程 (RenderWorker, AutoTocWorker)
- pdfviewer/ui/      : 界面层 (主窗口, 组件)
- pdfviewer/utils/   : 工具函数 (坐标转换, TOC模式)
"""

import sys
import os
from pathlib import Path

# Python 版本保护 - 确保在 UOS V20 (Python 3.7) 环境下运行
if sys.version_info < (3, 7):
    raise RuntimeError("Python 3.7+ required")
if sys.version_info >= (3, 8):
    import warnings
    warnings.warn("This application is optimized for Python 3.7", RuntimeWarning)

from PyQt5.QtWidgets import QApplication

# Import from new modular structure
from pdfviewer.ui.main_window import MainWindow


def main():
    """Application entry point."""
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("Unipdf")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("Unipdf")

    # Create main window
    window = MainWindow()
    window.show()

    # Open PDF from command line if provided
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        if os.path.exists(pdf_path) and pdf_path.lower().endswith('.pdf'):
            window.open_document(pdf_path)

    # Run application
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
