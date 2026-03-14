#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workers module - Background worker threads.

This module provides QThread-based workers for performing
long-running tasks without blocking the UI.

自动目录生成器扩展机制:

1. 创建新文件（如 my_toc_worker.py）
2. 继承 BaseTocWorker 并实现 _parse_heading 方法
3. 使用 @register_toc_worker 装饰器注册
4. 通过 TocWorkerFactory.create() 创建实例

示例:
    from pdfviewer.workers import BaseTocWorker, register_toc_worker

    @register_toc_worker
    class MyTocWorker(BaseTocWorker):
        DOC_TYPE = "mytype"
        DOC_TYPE_NAME = "我的文档类型"

        def _parse_heading(self, text, line, page_min_x, body_font, font_name):
            # 实现识别逻辑
            pass
"""

# 基础类和工厂（必须先导入，供子类继承）
from .base_toc_worker import (
    BaseTocWorker,
    TocWorkerFactory,
    register_toc_worker,
    get_toc_worker_class,
    list_toc_worker_types,
)

# 渲染 worker
from .render_worker import RenderWorker

# 自动导入并注册所有 TOC worker
# 导入顺序很重要，后导入的会覆盖先导入的同名 DOC_TYPE
from .gbt_toc_worker import GbtTocWorker, AutoTocWorker
from .legal_toc_worker import LegalTocWorker

__all__ = [
    # 渲染
    'RenderWorker',
    # TOC 工厂和基础类
    'BaseTocWorker',
    'TocWorkerFactory',
    'register_toc_worker',
    'get_toc_worker_class',
    'list_toc_worker_types',
    # 具体实现（向后兼容）
    'GbtTocWorker',
    'LegalTocWorker',
    'AutoTocWorker',  # 别名，向后兼容
]
