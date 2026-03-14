#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unipdf - 极简极速 PDF 查看器

重构版本 - 采用模块化架构

模块结构:
- core    : 核心领域层 (PDFDocument, 渲染, 文本引擎)
- services: 业务服务层 (渲染服务, 注释服务, 搜索服务, 缩略图服务)
- workers : 后台工作线程 (RenderWorker, AutoTocWorker)
- ui      : 界面层 (主窗口, 组件)
- utils   : 工具函数 (坐标转换, TOC模式)
"""

__version__ = "1.1.0"
__author__ = "Unipdf Team"

# Convenience imports
from pdfviewer.core import PDFDocument, TextEngine
from pdfviewer.services import (
    RenderService,
    AnnotationService,
    SearchService,
    ThumbnailService,
)
from pdfviewer.workers import RenderWorker, AutoTocWorker

__all__ = [
    '__version__',
    'PDFDocument',
    'TextEngine',
    'RenderService',
    'AnnotationService',
    'SearchService',
    'ThumbnailService',
    'RenderWorker',
    'AutoTocWorker',
]
