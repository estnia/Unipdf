#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TOC Worker 基础类

定义目录生成器的通用接口，支持通过继承和注册机制扩展新类型。

使用方法:
    1. 继承 BaseTocWorker 实现具体的识别逻辑
    2. 使用 register_toc_worker() 注册新的文档类型
    3. 使用 TocWorkerFactory.create() 创建对应类型的 worker

示例:
    from pdfviewer.workers.base_toc_worker import BaseTocWorker, register_toc_worker

    class MyTocWorker(BaseTocWorker):
        DOC_TYPE = "mytype"
        DOC_TYPE_NAME = "我的文档类型"

        def _parse_heading(self, text, line, page_min_x, body_font=0, font_name=""):
            # 实现识别逻辑
            pass

    register_toc_worker(MyTocWorker)
"""

import re
from typing import Optional, List, Dict, Any, Type
from PyQt5.QtCore import QThread, pyqtSignal

# PDF engine: PyMuPDF
try:
    import fitz
except ImportError:
    import pymupdf as fitz

# Memory manager
from pdfviewer.services.memory_manager import MemoryManager


class BaseTocWorker(QThread):
    """
    TOC生成器基础类。

    子类必须定义:
        DOC_TYPE: str - 文档类型标识符（如 "gbt", "legal"）
        DOC_TYPE_NAME: str - 文档类型显示名称（如 "GB/ISO标准", "法律法规"）

    子类必须实现:
        _parse_heading() - 解析标题的核心逻辑
    """

    # 子类必须重写
    DOC_TYPE: str = ""
    DOC_TYPE_NAME: str = ""

    # 通用正则（子类可用）
    RE_YEAR = re.compile(r'^(19|20)\d{2}$')

    # 信号
    finished = pyqtSignal(list)  # 返回 [(level, title, page), ...]
    progress = pyqtSignal(int, int)  # (current, total)
    error = pyqtSignal(str)

    def __init__(self, doc_path: str):
        super().__init__()
        self.doc_path = doc_path
        self._is_running = True
        # Memory manager for automatic cleanup
        self._memory_manager = MemoryManager(threshold_mb=600, critical_mb=1200)

    def run(self):
        """主流程，子类一般不需要重写"""
        try:
            headings = self._extract_toc()

            if not self._is_running:
                return

            if headings:
                headings = self._post_process(headings)
                toc_list = self._build_toc_list(headings)
                self.finished.emit(toc_list)
            else:
                self.finished.emit([])

        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._is_running = False
        self.wait(100)

    def _extract_toc(self) -> List[Dict[str, Any]]:
        """提取目录条目（通用实现，子类可重写）"""
        doc = fitz.open(self.doc_path)
        all_lines = []
        pages_data = []

        total_pages = min(len(doc), self._get_max_pages())

        for page_idx in range(total_pages):
            if not self._is_running:
                break
            self.progress.emit(page_idx + 1, total_pages)

            page = doc[page_idx]
            lines = self._extract_lines(page)
            all_lines.extend(lines)
            pages_data.append((page_idx, page.rect.width, page.rect.height, lines))

            if page_idx % 10 == 0:
                self._memory_manager.check_and_cleanup()

        doc.close()

        if not all_lines:
            return []

        body_font = self._calc_body_font(all_lines)
        min_x = min([line["x"] for line in all_lines]) if all_lines else 0
        headings = []

        for page_idx, page_width, page_height, lines in pages_data:
            if not self._is_running:
                break

            lines.sort(key=lambda x: x["y"])
            page_min_x = min([line["x"] for line in lines]) if lines else min_x

            for i, line in enumerate(lines):
                text = line["text"].strip()
                if not text:
                    continue

                if self._is_header_footer(text, line["y"], page_height, line["size"], body_font):
                    continue

                heading_info = self._parse_heading(text, line, page_min_x, body_font, line.get("font", ""))

                if heading_info:
                    heading_info["page"] = page_idx + 1
                    heading_info["line_idx"] = i
                    headings.append(heading_info)

        return headings

    def _extract_lines(self, page: fitz.Page) -> List[Dict[str, Any]]:
        """提取页面文本行（通用实现）"""
        lines = []
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if block["type"] != 0:
                continue

            for line in block["lines"]:
                text = ""
                size = 0
                x0 = None
                y0 = None
                is_bold = False
                flags = 0
                font_name = ""

                for span in line["spans"]:
                    text += span["text"]
                    size = max(size, span["size"])
                    flags |= span.get("flags", 0)

                    span_font = span.get("font", "").lower()
                    if "bold" in span_font or "black" in span_font or "heavy" in span_font:
                        is_bold = True
                    if "heiti" in span_font or "simhei" in span_font:
                        is_bold = True
                        font_name = span.get("font", "")

                    if x0 is None:
                        x0 = span["bbox"][0]
                        y0 = span["bbox"][1]

                text = text.strip()
                if not text:
                    continue

                is_bold = is_bold or (flags & 16) != 0

                lines.append({
                    "text": text,
                    "size": size,
                    "x": x0 if x0 is not None else 0,
                    "y": y0 if y0 is not None else 0,
                    "is_bold": is_bold,
                    "flags": flags,
                    "font": font_name
                })

        return lines

    def _calc_body_font(self, all_lines: List[Dict]) -> float:
        """计算正文字体大小（默认使用中位数）"""
        from statistics import median
        return median([line["size"] for line in all_lines]) if all_lines else 12

    def _get_max_pages(self) -> int:
        """返回要扫描的最大页数（子类可重写）"""
        return 100

    def _is_header_footer(self, text: str, y: float, page_height: float,
                          font_size: float, body_font: float) -> bool:
        """判断是否为页眉页脚（通用实现，子类可重写）"""
        # 纯数字页码
        if text.isdigit():
            if y < page_height * 0.12 or y > page_height * 0.88:
                return True
            if font_size < body_font * 0.85:
                return True
        # 极端位置
        if y < page_height * 0.05 or y > page_height * 0.95:
            return True
        return False

    def _parse_heading(self, text: str, line: Dict, page_min_x: float,
                       body_font: float, font_name: str) -> Optional[Dict]:
        """
        解析标题的核心逻辑，子类必须实现。

        返回字典格式:
            {
                "text": str,      # 标题文本
                "level": int,     # 层级（1=最高级）
                "size": float,    # 字体大小
                "x": float,       # X坐标
                "y": float,       # Y坐标
                # 可选字段:
                "is_bold": bool,
                "main_num": int,  # 主编号（用于排序/验证）
                "sub_num": int,   # 子编号
                "is_appendix": bool,
            }
        或返回 None 表示不是标题
        """
        raise NotImplementedError("子类必须实现 _parse_heading 方法")

    def _post_process(self, headings: List[Dict]) -> List[Dict]:
        """后处理（排序、去重、层级验证等，子类可重写）"""
        headings = self._sort_and_dedup(headings)
        headings = self._validate_sequence(headings)
        return headings

    def _validate_sequence(self, headings: List[Dict]) -> List[Dict]:
        """
        验证编号顺序，识别可能遗漏的章节。
        子类可重写以实现特定验证逻辑。
        """
        return headings

    def _sort_and_dedup(self, headings: List[Dict]) -> List[Dict]:
        """按页码和Y坐标排序并去重"""
        headings.sort(key=lambda x: (x["page"], x["y"]))
        seen = set()
        unique = []
        for h in headings:
            key = (h["page"], h["text"].strip())
            if key not in seen:
                seen.add(key)
                unique.append(h)
        return unique

    def _build_toc_list(self, headings: List[Dict]) -> List[List]:
        """构建TOC列表格式 [[level, title, page], ...]"""
        return [[h["level"], h["text"], h["page"]] for h in headings]


# ============ 注册/工厂机制 ============

# 全局注册表: {doc_type: WorkerClass}
_TOC_WORKER_REGISTRY: Dict[str, Type[BaseTocWorker]] = {}


def register_toc_worker(worker_class: Type[BaseTocWorker]):
    """
    注册TOC生成器类。

    示例:
        @register_toc_worker
        class MyTocWorker(BaseTocWorker):
            DOC_TYPE = "mytype"
            DOC_TYPE_NAME = "我的文档类型"
    """
    if not issubclass(worker_class, BaseTocWorker):
        raise TypeError(f"Worker class must inherit from BaseTocWorker")
    if not worker_class.DOC_TYPE:
        raise ValueError(f"Worker class must define DOC_TYPE")

    _TOC_WORKER_REGISTRY[worker_class.DOC_TYPE] = worker_class
    return worker_class


def get_toc_worker_class(doc_type: str) -> Optional[Type[BaseTocWorker]]:
    """获取指定类型的Worker类"""
    return _TOC_WORKER_REGISTRY.get(doc_type)


def list_toc_worker_types() -> List[tuple]:
    """
    列出所有已注册的文档类型。

    返回: [(doc_type, doc_type_name), ...]
    """
    return [(cls.DOC_TYPE, cls.DOC_TYPE_NAME)
            for cls in _TOC_WORKER_REGISTRY.values()]


class TocWorkerFactory:
    """
    TOC Worker 工厂类。

    使用示例:
        worker = TocWorkerFactory.create("gbt", "/path/to/doc.pdf")
        worker.finished.connect(on_finished)
        worker.start()
    """

    @staticmethod
    def create(doc_type: str, doc_path: str) -> Optional[BaseTocWorker]:
        """
        创建指定类型的Worker实例。

        Args:
            doc_type: 文档类型标识符（如 "gbt", "legal"）
            doc_path: PDF文件路径

        Returns:
            Worker实例，或None（如果类型未注册）
        """
        worker_class = get_toc_worker_class(doc_type)
        if worker_class:
            return worker_class(doc_path)
        return None

    @staticmethod
    def list_types() -> List[tuple]:
        """列出所有可用的文档类型"""
        return list_toc_worker_types()

    @staticmethod
    def is_available(doc_type: str) -> bool:
        """检查指定类型是否可用"""
        return doc_type in _TOC_WORKER_REGISTRY
