#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unipdf - 极简极速 PDF 查看器
适配 UOS V20 (Linux) 环境，类似 Windows SumatraPDF
核心技术栈: Python 3 + PyQt5 + PyMuPDF (fitz)
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

# PyQt5 导入
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QScrollArea, QLabel,
    QAction, QFileDialog, QMessageBox, QRubberBand, QMenu,
    QStackedWidget, QListWidget, QListWidgetItem, QToolButton, QFrame,
    QSizePolicy, QLineEdit, QPushButton, QShortcut, QProgressDialog
)
from PyQt5.QtCore import Qt, QRect, QSize, QPoint, QTimer, QMimeData, QThread, pyqtSignal
from PyQt5.QtGui import (
    QImage, QPixmap, QKeyEvent, QDragEnterEvent, QDropEvent, QClipboard,
    QPainter, QColor, QFont, QCursor, QFontMetrics, QIcon, QKeySequence,
    QMouseEvent
)

# PDF 引擎: PyMuPDF (兼容新旧版本)
try:
    import fitz  # PyMuPDF < 1.23
except ImportError:
    import pymupdf as fitz  # PyMuPDF >= 1.23
import hashlib
import time
import re
from datetime import datetime


class RenderWorker(QThread):
    """P0/P1: 异步渲染工作线程 - 支持全页和视口裁剪渲染"""
    finished = pyqtSignal(int, int, float, QPixmap)  # page_idx, zoom_percent, dpi_scale, pixmap
    error = pyqtSignal(int, str)  # page_idx, error_msg

    def __init__(self, doc_path, page_idx, zoom, dpi_scale, device_ratio,
                 clip_rect=None, viewport_size=None):
        """
        Args:
            doc_path: PDF 文件路径
            page_idx: 页码
            zoom: 缩放因子
            dpi_scale: DPI 缩放
            device_ratio: 设备像素比
            clip_rect: P1: 裁剪区域 (x, y, w, h) 用于局部渲染，None 表示全页
            viewport_size: P1: 视口大小 (w, h) 用于计算裁剪
        """
        super().__init__()
        self.doc_path = doc_path
        self.page_idx = page_idx
        self.zoom = zoom
        self.dpi_scale = dpi_scale
        self.device_ratio = device_ratio
        self.clip_rect = clip_rect  # P1: 裁剪区域
        self.viewport_size = viewport_size  # P1: 视口大小
        self._is_running = True
        self._is_clipped = False  # 标记是否为裁剪渲染

    def run(self):
        """在后台线程中渲染页面"""
        try:
            # 每个线程打开独立的文档实例（线程安全）
            doc = fitz.open(self.doc_path)
            page = doc[self.page_idx]

            # 创建缩放矩阵
            mat = fitz.Matrix(self.zoom * self.dpi_scale, self.zoom * self.dpi_scale)

            # P1: 视口裁剪渲染 - 高倍率下只渲染可见区域
            if self.clip_rect and self.zoom > 2.0:
                # 计算裁剪区域（PDF 坐标）
                x, y, w, h = self.clip_rect
                # 将屏幕坐标转换为 PDF 坐标（考虑 DPI 缩放）
                pdf_x = x / (self.zoom * self.dpi_scale)
                pdf_y = y / (self.zoom * self.dpi_scale)
                pdf_w = w / (self.zoom * self.dpi_scale)
                pdf_h = h / (self.zoom * self.dpi_scale)

                clip = fitz.Rect(pdf_x, pdf_y, pdf_x + pdf_w, pdf_y + pdf_h)
                pix = page.get_pixmap(matrix=mat, alpha=False,
                                     colorspace=fitz.csRGB, clip=clip)
                # 标记这是裁剪渲染
                self._is_clipped = True
            else:
                # 正常全页渲染
                pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)
                self._is_clipped = False

            # 转换为 QImage
            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format_RGB888 if pix.n == 3 else QImage.Format_ARGB32
            ).copy()

            # 转换为 QPixmap
            qpixmap = QPixmap.fromImage(img)
            qpixmap.setDevicePixelRatio(self.device_ratio)

            doc.close()

            if self._is_running:
                zoom_percent = int(self.zoom * 100)
                self.finished.emit(self.page_idx, zoom_percent, self.dpi_scale, qpixmap)

        except Exception as e:
            if self._is_running:
                self.error.emit(self.page_idx, str(e))

    def stop(self):
        """停止渲染"""
        self._is_running = False
        self.wait(100)  # 等待100ms


# 自动目录生成 - 正则表达式配置
LEGAL_PATTERNS = {
    "L1": re.compile(r'^第[一二三四五六七八九十百千]+[编章]', re.UNICODE),
    "L2": re.compile(r'^第[一二三四五六七八九十百千]+[节条]', re.UNICODE)
}

GBT_PATTERNS = {
    "L1": re.compile(r'^(\d+)\s+[\u4e00-\u9fa5]', re.UNICODE),  # 1 范围
    "L2": re.compile(r'^(\d+\.\d+)(\s+[\u4e00-\u9fa5])', re.UNICODE)  # 1.1 术语
}

GENERAL_PATTERNS = {
    "L1": re.compile(r'^(?:第[一二三四五六七八九十百千]+[编章]|\d+\s+[\u4e00-\u9fa5])', re.UNICODE),
    "L2": re.compile(r'^(?:第[一二三四五六七八九十百千]+[节条]|\d+\.\d+)', re.UNICODE)
}


class AutoTocWorker(QThread):
    """自动目录生成工作线程"""
    finished = pyqtSignal(list)  # 返回 TOC 列表 [[lvl, title, page], ...]
    progress = pyqtSignal(int, int)  # 当前页, 总页数
    error = pyqtSignal(str)

    def __init__(self, doc_path: str, doc_type: str = "auto"):
        """
        Args:
            doc_path: PDF 文件路径
            doc_type: 文档类型 - "legal"(法律), "gbt"(国标), "auto"(自动检测)
        """
        super().__init__()
        self.doc_path = doc_path
        self.doc_type = doc_type
        self._is_running = True

    def run(self):
        """后台执行目录分析"""
        try:
            doc = fitz.open(self.doc_path)

            # Step 1: 特征采样 - 统计前50页字体分布
            font_stats = self._analyze_font_stats(doc)
            base_size = self._determine_base_font(font_stats)

            # Step 2: 检测文档类型（如果设置为 auto）
            if self.doc_type == "auto":
                self.doc_type = self._detect_doc_type(doc)

            # Step 3: 配置正则引擎
            l1_pattern, l2_pattern = self._get_regex_patterns(self.doc_type)

            # Step 4: 逐页扫描提取标题
            toc_candidates = []
            total_pages = min(len(doc), 50)  # 最多扫描50页

            for page_idx in range(total_pages):
                if not self._is_running:
                    break

                self.progress.emit(page_idx + 1, total_pages)
                page = doc[page_idx]

                # 区域裁剪：忽略边缘10%（排除页眉页码）
                crop_rect = self._get_crop_rect(page.rect)

                # 获取文本块
                blocks = page.get_text("blocks", clip=crop_rect)

                for block in blocks:
                    result = self._process_block(
                        block, page_idx, base_size,
                        l1_pattern, l2_pattern
                    )
                    if result:
                        toc_candidates.append(result)

                # 内存优化
                if page_idx % 10 == 0:
                    fitz.TOOLS.store_shrink()

            doc.close()

            # Step 5: 去重与层级聚合
            toc_list = self._build_toc_tree(toc_candidates)

            if self._is_running:
                self.finished.emit(toc_list)

        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        """停止分析"""
        self._is_running = False
        self.wait(100)

    def _analyze_font_stats(self, doc: fitz.Document) -> dict:
        """统计前50页字体大小分布"""
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

        # 统计频次
        size_counts = {}
        for size in font_sizes:
            # 将字体大小分组到整数区间
            rounded = round(size)
            size_counts[rounded] = size_counts.get(rounded, 0) + 1

        return size_counts

    def _determine_base_font(self, font_stats: dict) -> float:
        """根据统计确定正文字号"""
        if not font_stats:
            return 12.0

        # 找出出现频次最高的字体大小
        most_common = max(font_stats.items(), key=lambda x: x[1])
        return float(most_common[0])

    def _detect_doc_type(self, doc: fitz.Document) -> str:
        """自动检测文档类型"""
        sample_text = ""
        sample_pages = min(len(doc), 10)

        for page_idx in range(sample_pages):
            page = doc[page_idx]
            text = page.get_text()
            sample_text += text[:5000]  # 每个页面取前5000字符

        # 检测法律文档特征
        if LEGAL_PATTERNS["L1"].search(sample_text):
            return "legal"

        # 检测 GB/T 标准特征
        if GBT_PATTERNS["L1"].search(sample_text) or \
           GBT_PATTERNS["L2"].search(sample_text):
            return "gbt"

        return "general"

    def _get_regex_patterns(self, doc_type: str):
        """获取对应文档类型的正则模式"""
        if doc_type == "legal":
            return LEGAL_PATTERNS["L1"], LEGAL_PATTERNS["L2"]
        elif doc_type == "gbt":
            return GBT_PATTERNS["L1"], GBT_PATTERNS["L2"]
        else:
            return GENERAL_PATTERNS["L1"], GENERAL_PATTERNS["L2"]

    def _get_crop_rect(self, page_rect: fitz.Rect) -> fitz.Rect:
        """获取裁剪后的页面区域（忽略边缘10%）"""
        margin = 0.1  # 10% 边距
        x0 = page_rect.x0 + page_rect.width * margin
        y0 = page_rect.y0 + page_rect.height * margin
        x1 = page_rect.x1 - page_rect.width * margin
        y1 = page_rect.y1 - page_rect.height * margin
        return fitz.Rect(x0, y0, x1, y1)

    def _process_block(self, block, page_idx: int, base_size: float,
                       l1_pattern, l2_pattern) -> dict:
        """处理单个文本块，提取标题候选"""
        x0, y0, x1, y1, text, block_no, block_type = block

        # 清理文本
        text = text.strip()
        if not text or len(text) > 200:  # 标题不会太长
            return None

        # 独立行判定：标题不应以句号结尾
        if text.endswith(('。', '.', '；', ';')):
            return None

        # 正则匹配
        l1_match = l1_pattern.match(text)
        l2_match = l2_pattern.match(text) if not l1_match else None

        if not l1_match and not l2_match:
            return None

        result = {
            "page": page_idx,
            "text": text,
            "bbox": (x0, y0, x1, y1),
            "level": 1 if l1_match else 2,
            "match_type": "L1" if l1_match else "L2"
        }

        return result

    def _build_toc_tree(self, candidates: list) -> list:
        """构建层级树结构，转换为 PyMuPDF TOC 格式"""
        # 去重：(page, normalized_text) 散列表
        seen = {}
        unique_candidates = []

        for c in candidates:
            key = (c["page"], self._normalize_text(c["text"]))
            if key not in seen:
                seen[key] = c
                unique_candidates.append(c)

        # 按页码和 Y 坐标排序
        unique_candidates.sort(key=lambda x: (x["page"], x["bbox"][1]))

        # 构建嵌套结构
        toc_list = []
        active_l1 = None

        for c in unique_candidates:
            if c["level"] == 1:
                # L1 级别直接添加
                toc_list.append([1, c["text"], c["page"] + 1])  # 页码从1开始
                active_l1 = c
            elif c["level"] == 2 and active_l1:
                # L2 级别归入当前 L1
                toc_list.append([2, c["text"], c["page"] + 1])

        return toc_list

    def _normalize_text(self, text: str) -> str:
        """规范化文本用于去重"""
        # 移除空白字符并转为小写
        return ''.join(text.split()).lower()


class PDFViewer(QMainWindow):
    """主窗口类 - 实现 PDF 查看器的核心功能"""

    def __init__(self):
        super().__init__()

        # ==================== 基础配置 ====================
        self.setWindowTitle("Unipdf - 极简 PDF 查看器")
        self.setGeometry(100, 100, 1200, 800)

        # 当前文档状态
        self.doc = None  # fitz.Document 对象
        self.current_page = 0  # 当前页码（从 0 开始）
        self.zoom_factor = 1.0  # 缩放因子
        self.total_pages = 0  # 总页数
        self.file_path = None  # 当前打开的文件路径

        # 文本选择相关
        self.selection_start_char = None  # 选择起始字符索引
        self.selection_end_char = None  # 选择结束字符索引
        self.selection_start_word = None  # 选择起始 word 索引
        self.selection_end_word = None  # 选择结束 word 索引
        self.current_selected_text = ""  # 当前选中的文本
        self.page_text_chars = []  # 当前页面字符位置信息
        self.page_words = []  # 当前页面 words 列表（用于 hit-test）
        self.is_selecting = False  # 是否正在选择
        self.is_ctrl_pressed = False  # Ctrl 是否按下
        self.rubber_band = None  # 橡皮筋选择框
        self.current_page_label = None  # 当前正在操作的页面标签

        # 多页面显示
        self.page_labels = []  # 存储所有页面标签
        self.page_overlays = []  # 存储所有文本选择覆盖层
        self.is_ctrl_pressed = False  # 是否按住 Ctrl 键
        self._selection_overlay = None  # 文本选择覆盖层

        # 渲染延迟定时器（用于优化性能，避免频繁渲染）
        self.render_timer = QTimer()
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self._do_render)

        # 搜索功能相关
        self.search_results = []  # 搜索结果列表
        self.current_search_index = -1  # 当前高亮的搜索结果索引
        self.search_widget = None  # 搜索框部件
        self.search_input = None  # 搜索输入框
        self.search_counter = None  # 匹配计数显示

        # ==================== P0/P2: 平滑缩放优化与多级缓存 ====================
        # L1 缓存: 当前显示缩放级别的页面图像 {page_idx: QPixmap}
        self._render_cache = {}
        # P2: L2 缓存 - 其他缩放级别的图像，最多保留 3 个缩放级别
        # 结构: {zoom_percent: {page_idx: QPixmap}}
        self._l2_cache = {}
        self._max_l2_zoom_levels = 3  # 最多保留的缩放级别数
        # 当前显示的基础图像（用于即时拉伸）
        self._base_pixmaps = {}
        # 正在进行的渲染任务 {page_idx: RenderWorker}
        self._active_workers = {}
        # 防抖定时器（缩放停止后才渲染高清）
        self._zoom_timer = QTimer()
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.timeout.connect(self._do_hd_render)
        # 目标缩放值（用于即时显示）
        self._target_zoom = 1.0

        # ==================== 初始化界面 ====================
        self._init_ui()

        # 启用拖放功能
        self.setAcceptDrops(True)

        # 剪贴板
        self.clipboard = QApplication.clipboard()

        # 侧边栏状态 - REQ-01: 默认隐藏
        self._sidebar_visible = False
        self._sidebar_width = 250

        # ==================== 下划线注释功能 ====================
        # 注释热区索引 {page_idx: [{"rect": fitz.Rect, "content": str}, ...]}
        self._annot_hotspot_map = {}
        # 当前悬停的注释
        self._current_hover_annot = None
        # 文档是否已修改（未保存）
        self._document_modified = False
        # 浮窗延时定时器
        self._tooltip_timer = QTimer()
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_annot_tooltip)
        # 自定义浮窗
        self._annot_tooltip = None

    def _init_ui(self):
        """初始化用户界面 - 左右分割布局"""

        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局 - 垂直布局，包含分割器和搜索框
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ==================== 分割器 ====================
        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter, 1)  # stretch=1 占据所有可用空间

        # ==================== 左侧: 侧边栏容器 ====================
        self.sidebar_container = QWidget()
        self.sidebar_container.setMaximumWidth(300)
        self.sidebar_container.setMinimumWidth(200)
        sidebar_layout = QVBoxLayout(self.sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # 侧边栏切换按钮区域
        self._init_sidebar_toolbar(sidebar_layout)

        # 侧边栏内容区域（使用堆叠部件切换不同视图）
        self.sidebar_stack = QStackedWidget()
        sidebar_layout.addWidget(self.sidebar_stack)

        # 1. 目录（书签）视图
        self.toc_widget = QTreeWidget()
        self.toc_widget.setHeaderLabel("目录")
        self.toc_widget.itemClicked.connect(self._on_toc_clicked)
        self.sidebar_stack.addWidget(self.toc_widget)  # 索引 0

        # 2. 注释视图
        self.annot_widget = QListWidget()
        self.annot_widget.itemClicked.connect(self._on_annot_clicked)
        # 启用右键菜单
        self.annot_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.annot_widget.customContextMenuRequested.connect(self._show_annot_context_menu)
        self.sidebar_stack.addWidget(self.annot_widget)  # 索引 1

        # 3. 页面缩略图视图
        self.thumbnail_widget = QListWidget()
        self.thumbnail_widget.setViewMode(QListWidget.IconMode)
        self.thumbnail_widget.setIconSize(QSize(120, 160))
        self.thumbnail_widget.setResizeMode(QListWidget.Adjust)
        self.thumbnail_widget.setSpacing(10)
        self.thumbnail_widget.itemClicked.connect(self._on_thumbnail_clicked)
        self.sidebar_stack.addWidget(self.thumbnail_widget)  # 索引 2

        # 4. 搜索结果视图
        self.search_results_widget = QListWidget()
        self.search_results_widget.itemClicked.connect(self._on_search_result_clicked)
        self.sidebar_stack.addWidget(self.search_results_widget)  # 索引 3

        self.splitter.addWidget(self.sidebar_container)

        # ==================== 右侧: 页面展示区域 ====================
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)  # 启用自动调整
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #666666; }")

        # 创建容器部件容纳所有页面（垂直布局）
        self.pages_container = QWidget()
        self.pages_container.setStyleSheet("QWidget { background-color: #555555; }")
        self.pages_layout = QVBoxLayout(self.pages_container)
        self.pages_layout.setSpacing(10)  # 页间间距 10 像素
        self.pages_layout.setContentsMargins(10, 10, 10, 10)  # 边距
        self.pages_layout.setAlignment(Qt.AlignCenter)  # 居中对齐

        self.scroll_area.setWidget(self.pages_container)

        # 页面标签列表 - 每个页面一个 QLabel
        self.page_labels = []  # 存储所有页面标签
        self.page_overlays = []  # 存储所有覆盖层

        self.splitter.addWidget(self.scroll_area)

        # 设置分割比例（侧边栏:页面 = 1:4）
        self.splitter.setSizes([250, 950])

        # 记录侧边栏宽度用于显示/隐藏
        self._sidebar_width = 250

        # ==================== 菜单栏 ====================
        self._init_menu_bar()

        # ==================== 鼠标事件 ====================
        self.pages_container.setMouseTracking(True)
        # 安装事件过滤器以捕获鼠标事件
        self.pages_container.installEventFilter(self)
        # 给 scroll_area 也安装事件过滤器，拦截 Ctrl+滚轮
        self.scroll_area.installEventFilter(self)
        # 注意：现在需要动态识别当前操作的页面

        # 右键菜单 - 通过 eventFilter 处理，不使用 customContextMenuRequested 避免重复触发
        self.pages_container.setContextMenuPolicy(Qt.NoContextMenu)

        # ==================== 底部搜索框（初始隐藏）====================
        self.search_widget = QWidget()
        self.search_widget.setVisible(False)
        search_layout = QHBoxLayout(self.search_widget)
        search_layout.setContentsMargins(10, 5, 10, 5)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("查找文本...")
        self.search_input.setMinimumWidth(200)
        # REQ-06: Enter 键执行查找下一个（而不是重新搜索）
        self.search_input.returnPressed.connect(self._search_find_next)
        self.search_input.textChanged.connect(self._on_search_text_changed)

        self.search_counter = QLabel("0/0")
        self.search_counter.setMinimumWidth(50)

        self.btn_search_prev = QPushButton("↑")
        self.btn_search_prev.setToolTip("上一个匹配")
        self.btn_search_prev.setMaximumWidth(30)
        self.btn_search_prev.clicked.connect(self._search_prev)

        self.btn_search_next = QPushButton("↓")
        self.btn_search_next.setToolTip("下一个匹配")
        self.btn_search_next.setMaximumWidth(30)
        self.btn_search_next.clicked.connect(self._search_next)

        self.btn_search_close = QPushButton("×")
        self.btn_search_close.setToolTip("关闭搜索")
        self.btn_search_close.setMaximumWidth(30)
        self.btn_search_close.clicked.connect(self._hide_search_widget)

        search_layout.addWidget(QLabel("查找:"))
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_counter)
        search_layout.addWidget(self.btn_search_prev)
        search_layout.addWidget(self.btn_search_next)
        search_layout.addWidget(self.btn_search_close)
        search_layout.addStretch()

        # 将搜索框添加到主布局（splitter 下方）
        main_layout.addWidget(self.search_widget)

        # 设置全局快捷键（无论焦点在哪里都能生效）
        self.shortcut_find = QShortcut(QKeySequence("Ctrl+F"), self)
        self.shortcut_find.activated.connect(self._show_search_widget)

        self.shortcut_esc = QShortcut(QKeySequence("Escape"), self)
        self.shortcut_esc.activated.connect(self._hide_search_widget)

        # REQ-05: Ctrl+D 快捷切换侧边栏
        self.shortcut_sidebar = QShortcut(QKeySequence("Ctrl+D"), self)
        self.shortcut_sidebar.activated.connect(self._toggle_sidebar_with_toc)

        # REQ-01: 侧边栏初始隐藏
        self.sidebar_container.setVisible(False)
        self._sidebar_visible = False

    def _init_menu_bar(self):
        """初始化菜单栏"""

        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")

        # 打开文件
        open_action = QAction("打开(&O)...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_file_dialog)
        file_menu.addAction(open_action)

        # 关闭文件
        close_action = QAction("关闭(&C)", self)
        close_action.setShortcut("Ctrl+W")
        close_action.triggered.connect(self._close_document)
        file_menu.addAction(close_action)

        file_menu.addSeparator()

        # 保存（增量保存高亮）
        save_action = QAction("保存(&S)", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_document)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        # 退出
        exit_action = QAction("退出(&Q)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 查看菜单
        view_menu = menubar.addMenu("查看(&V)")

        # 放大（仅通过 Ctrl+滚轮触发，不设置键盘快捷键）
        zoom_in_action = QAction("放大(&I)", self)
        zoom_in_action.triggered.connect(lambda: self._zoom(1.1))
        view_menu.addAction(zoom_in_action)

        # 缩小（仅通过 Ctrl+滚轮触发，不设置键盘快捷键）
        zoom_out_action = QAction("缩小(&O)", self)
        zoom_out_action.triggered.connect(lambda: self._zoom(0.9))
        view_menu.addAction(zoom_out_action)

        # 重置缩放
        zoom_reset_action = QAction("重置缩放(&R)", self)
        zoom_reset_action.setShortcut("Ctrl+0")
        zoom_reset_action.triggered.connect(self._zoom_reset)
        view_menu.addAction(zoom_reset_action)

        view_menu.addSeparator()

        # 上一页
        prev_page_action = QAction("上一页(&P)", self)
        prev_page_action.setShortcut("PageUp")
        prev_page_action.triggered.connect(self._prev_page)
        view_menu.addAction(prev_page_action)

        # 下一页
        next_page_action = QAction("下一页(&N)", self)
        next_page_action.setShortcut("PageDown")
        next_page_action.triggered.connect(self._next_page)
        view_menu.addAction(next_page_action)

        view_menu.addSeparator()

        # 侧边栏显示/隐藏 - REQ-01: 初始未勾选（因为默认隐藏）
        self.sidebar_toggle_action = QAction("侧边栏(&S)", self)
        self.sidebar_toggle_action.setShortcut("F9")
        self.sidebar_toggle_action.setCheckable(True)
        self.sidebar_toggle_action.setChecked(False)  # 初始隐藏
        self.sidebar_toggle_action.triggered.connect(self._toggle_sidebar)
        view_menu.addAction(self.sidebar_toggle_action)

        # REQ-03: 编辑菜单 - 添加查找功能
        edit_menu = menubar.addMenu("编辑(&E)")

        # 查找
        find_action = QAction("查找(&F)...", self)
        # 快捷键由全局 QShortcut 处理，避免重复定义
        find_action.triggered.connect(self._show_search_widget)
        edit_menu.addAction(find_action)

        # 工具菜单
        tools_menu = menubar.addMenu("工具(&T)")

        # 自动生成目录
        auto_toc_action = QAction("自动生成目录(&A)...", self)
        auto_toc_action.triggered.connect(self._show_auto_toc_dialog)
        tools_menu.addAction(auto_toc_action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")

        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # ==================== 文件操作 ====================

    def _open_file_dialog(self):
        """打开文件对话框选择 PDF"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开 PDF 文件", "",
            "PDF 文件 (*.pdf);;所有文件 (*.*)"
        )
        if file_path:
            self.open_document(file_path)

    def open_document(self, file_path: str):
        """
        打开指定的 PDF 文档

        Args:
            file_path: PDF 文件的完整路径
        """
        # 检查是否有未保存的更改
        if self._document_modified and self.file_path:
            reply = QMessageBox.question(
                self, "未保存的更改",
                f"文件 \"{os.path.basename(self.file_path)}\" 有未保存的更改。\n是否保存？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )
            if reply == QMessageBox.Save:
                if not self._save_document_safely():
                    return  # 保存失败，取消打开
            elif reply == QMessageBox.Cancel:
                return  # 取消打开
            # Discard: 继续打开新文档

        # 清除缓存强制刷新
        self._l2_cache.clear()
        self._base_pixmaps.clear()

        try:
            # 关闭现有文档
            self._close_document()

            # 打开新文档
            self.doc = fitz.open(file_path)
            self.file_path = file_path
            self.total_pages = len(self.doc)
            self.current_page = 0
            self.zoom_factor = 1.0
            self._document_modified = False  # 重置修改标记

            # 更新窗口标题
            self.setWindowTitle(f"Unipdf - {os.path.basename(file_path)}")

            # 加载目录
            self._load_toc()

            # 构建注释热区索引
            self._build_annot_index()

            # 加载注释侧边栏
            self._load_annotations()

            # 渲染第一页
            self.render_page(self.current_page, self.zoom_factor)

            # 加载缩略图
            self._load_thumbnails()

        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开 PDF 文件:\n{str(e)}")

    def _close_document(self):
        """关闭当前文档，释放资源"""
        if self.doc:
            self.doc.close()
            self.doc = None

        self.file_path = None
        self.total_pages = 0
        self.current_page = 0
        self.zoom_factor = 1.0
        self.toc_widget.clear()
        self.thumbnail_widget.clear()

        # 清除所有页面
        self._clear_all_pages()

        # 清除文本选择
        self._clear_text_selection()

        self.setWindowTitle("Unipdf - 极简 PDF 查看器")

    def _mark_document_modified(self, modified: bool = True):
        """标记文档修改状态并更新标题栏"""
        self._document_modified = modified
        if self.file_path:
            filename = os.path.basename(self.file_path)
            if modified:
                self.setWindowTitle(f"Unipdf - {filename} *")
            else:
                self.setWindowTitle(f"Unipdf - {filename}")

    def _save_document_safely(self):
        """
        安全保存文档（自动处理增量/完整保存）
        - 首先尝试增量保存（保持原文件结构）
        - 如果失败（加密、权限等问题），保存到临时文件后替换原文件
        """
        if not self.doc or not self.file_path:
            return False

        try:
            # 首先尝试增量保存
            self.doc.save(self.file_path, incremental=True)
            self._mark_document_modified(False)
            return True
        except Exception as e:
            error_msg = str(e).lower()
            # 增量保存失败，尝试完整保存到临时文件后替换
            if "incremental" in error_msg or "encryption" in error_msg:
                try:
                    import shutil
                    # 保存到临时文件（与原文件同目录以确保在同一文件系统）
                    temp_path = self.file_path + ".tmp"
                    self.doc.save(temp_path)
                    # 替换原文件
                    shutil.move(temp_path, self.file_path)
                    self._mark_document_modified(False)
                    return True
                except Exception:
                    return False
            return False

    def _save_document(self):
        """保存文档（菜单触发）"""
        if self._save_document_safely():
            self.statusBar().showMessage("已保存", 2000)
        else:
            QMessageBox.critical(self, "错误", "保存失败")

    # ==================== 目录加载与跳转 ====================

    def _load_toc(self):
        """加载 PDF 目录（书签/大纲）到侧边栏 - REQ-02: 单行省略+悬停提示"""
        self.toc_widget.clear()

        # 设置目录树样式：单行显示，超出部分省略号
        self.toc_widget.setStyleSheet("""
            QTreeWidget::item {
                padding: 4px 2px;
            }
            QTreeWidget::item:selected {
                background-color: #0078d7;
                color: white;
            }
        """)

        if not self.doc:
            return

        toc = self.doc.get_toc()  # 获取目录列表 [level, title, page]

        if not toc:
            item = QTreeWidgetItem(self.toc_widget)
            item.setText(0, "(无目录)")
            item.setData(0, Qt.UserRole, -1)
            return

        # 构建目录树
        stack = []  # 用于处理层级关系

        for level, title, page_num in toc:
            # 注意: get_toc 返回的 page_num 是从 1 开始的
            page_index = page_num - 1

            item = QTreeWidgetItem()
            # REQ-02: 设置单行显示文本（QTreeWidget 默认会处理省略号）
            item.setText(0, title)
            # REQ-02: 设置悬停提示显示完整标题
            item.setToolTip(0, title)
            item.setData(0, Qt.UserRole, page_index)  # 存储页码（从 0 开始）

            if level == 1:
                # 顶级目录项
                self.toc_widget.addTopLevelItem(item)
                stack = [item]
            else:
                # 子目录项 - 找到正确的父节点
                while len(stack) >= level:
                    stack.pop()

                if stack:
                    stack[-1].addChild(item)
                else:
                    self.toc_widget.addTopLevelItem(item)

                stack.append(item)

        # 展开所有项
        self.toc_widget.expandAll()

    def _on_toc_clicked(self, item: QTreeWidgetItem):
        """目录点击事件 - 跳转到对应页面"""
        page_index = item.data(0, Qt.UserRole)
        if page_index >= 0 and page_index < self.total_pages:
            self._scroll_to_page(page_index)

    # ==================== 页面渲染（核心功能） ====================

    def render_page(self, index: int, zoom: float = 1.0):
        """
        渲染指定页面的 PDF 内容

        Args:
            index: 页码索引（从 0 开始）
            zoom: 缩放因子，1.0 表示 100%

        注意:
            - 使用延迟渲染机制，避免频繁操作时的性能问题
            - 通过设置矩阵（Matrix）实现高质量缩放
        """
        if not self.doc or index < 0 or index >= self.total_pages:
            return

        # 保存当前要渲染的参数
        self._pending_index = index
        self._pending_zoom = zoom

        # 延迟渲染（如果用户在 100ms 内有新的操作，则取消本次渲染）
        self.render_timer.stop()
        self.render_timer.start(100)

    def _do_render(self):
        """P0/P2: 执行实际渲染操作 - 使用多级缓存"""
        if not self.doc:
            return

        # 取消任何正在进行的异步渲染
        self._cancel_active_workers()

        try:
            zoom = self.zoom_factor
            zoom_percent = int(zoom * 100)

            # 获取 DPI 缩放因子（与坐标转换保持一致）
            screen = QApplication.primaryScreen()
            if screen:
                dpi_scale = screen.logicalDotsPerInchX() / 96.0
            else:
                dpi_scale = 1.0

            # 清空现有页面和基础图像缓存
            self._clear_all_pages()
            self._base_pixmaps.clear()

            # P2: 检查 L2 缓存
            l2_cache = self._l2_cache.get(zoom_percent, {})

            # 渲染所有页面
            for page_idx in range(self.total_pages):
                # P2: 优先使用 L2 缓存
                if page_idx in l2_cache:
                    qpixmap = l2_cache[page_idx]
                    self._base_pixmaps[page_idx] = qpixmap
                else:
                    page = self.doc[page_idx]

                    # 创建缩放矩阵（包含 DPI scale，与坐标转换一致）
                    mat = fitz.Matrix(zoom * dpi_scale, zoom * dpi_scale)

                    # P2: 使用 colorspace=fitz.csRGB 优化渲染速度
                    pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)

                    # 转换为 QImage
                    img = QImage(
                        pix.samples,
                        pix.width,
                        pix.height,
                        pix.stride,
                        QImage.Format_RGB888 if pix.n == 3 else QImage.Format_ARGB32
                    ).copy()

                    # 转换为 QPixmap
                    qpixmap = QPixmap.fromImage(img)

                    # 设置 device pixel ratio，使 Qt 正确显示
                    device_ratio = screen.devicePixelRatio() if screen else 1.0
                    qpixmap.setDevicePixelRatio(device_ratio)

                    # P0: 保存为基础图像（用于缩放预览）
                    self._base_pixmaps[page_idx] = qpixmap

                    # P2: 存储到 L2 缓存
                    self._add_to_l2_cache(page_idx, zoom_percent, qpixmap)

                # 获取最终使用的 pixmap
                qpixmap = self._base_pixmaps[page_idx]

                # 创建页面标签
                page_label = QLabel()
                page_label.setPixmap(qpixmap)
                page_label.setAlignment(Qt.AlignCenter)
                page_label.setStyleSheet("QLabel { background-color: white; }")
                # 使用逻辑尺寸设置固定大小
                page_label.setFixedSize(qpixmap.size())

                # 创建文本选择覆盖层
                overlay = QLabel(page_label)
                overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
                overlay.setStyleSheet("QLabel { background-color: transparent; }")
                overlay.resize(page_label.size())
                overlay.hide()

                # 存储页面信息
                page_label.page_index = page_idx  # 存储页码
                self.page_labels.append(page_label)
                self.page_overlays.append(overlay)

                # 安装事件过滤器以支持悬停检测
                page_label.setMouseTracking(True)
                page_label.installEventFilter(self)

                # 添加到布局
                self.pages_layout.addWidget(page_label)

            # 添加弹性空间
            self.pages_layout.addStretch()

            # 更新状态栏
            self.statusBar().showMessage(f"共 {self.total_pages} 页 | 缩放: {zoom * 100:.0f}%")

            # 清除文本选择
            self._clear_text_selection()

        except Exception as e:
            print(f"渲染页面失败: {e}")

    def _clear_all_pages(self):
        """清除所有页面标签"""
        # 清空布局中的所有部件
        while self.pages_layout.count():
            item = self.pages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.page_labels.clear()
        self.page_overlays.clear()

    def _get_page_at_pos(self, pos: QPoint) -> tuple:
        """获取指定位置对应的页面标签和页码"""
        for i, page_label in enumerate(self.page_labels):
            # 获取页面标签在容器中的全局位置
            label_pos = page_label.mapFrom(self.pages_container, pos)
            if page_label.rect().contains(label_pos):
                return page_label, i, label_pos
        return None, -1, None

    # ==================== 翻页功能 ====================

    def _prev_page(self):
        """翻到上一页"""
        if self.current_page > 0:
            self.current_page -= 1
            self.render_page(self.current_page, self.zoom_factor)

    def _next_page(self):
        """翻到下一页"""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.render_page(self.current_page, self.zoom_factor)

    # ==================== 缩放功能 ====================

    def _zoom(self, factor: float):
        """
        P0: 按比例缩放页面 - 即时拉伸 + 异步高清渲染

        Args:
            factor: 缩放倍数，例如 1.1 表示放大 10%，0.9 表示缩小 10%
        """
        if not self.doc:
            return

        new_zoom = self.zoom_factor * factor

        # 限制缩放范围（10% - 500%）
        new_zoom = max(0.1, min(5.0, new_zoom))

        if abs(new_zoom - self._target_zoom) < 0.01:
            return  # 缩放变化太小，忽略

        self._target_zoom = new_zoom

        # P0: 即时视觉反馈 - 使用 QPainter 拉伸当前图像
        self._apply_zoom_preview(factor)

        # P0: 防抖处理 - 停止之前的定时器
        self._zoom_timer.stop()
        # 150ms 后执行高清渲染
        self._zoom_timer.start(150)

    def _apply_zoom_preview(self, factor: float):
        """P0: 即时缩放预览 - 使用 QPainter 拉伸当前显示的图像"""
        if not self.page_labels:
            return

        for i, page_label in enumerate(self.page_labels):
            # 获取当前显示的大小
            current_size = page_label.size()

            # 计算新的大小
            new_width = int(current_size.width() * factor)
            new_height = int(current_size.height() * factor)

            # 获取基础图像（原始渲染的图像）
            if i in self._base_pixmaps:
                base_pixmap = self._base_pixmaps[i]

                # 创建缩放后的图像
                scaled = base_pixmap.scaled(
                    new_width, new_height,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation  # 平滑变换，减少锯齿
                )

                # 更新 QLabel 显示
                page_label.setPixmap(scaled)
                page_label.setFixedSize(scaled.size())

                # 同步更新覆盖层大小
                if i < len(self.page_overlays):
                    self.page_overlays[i].resize(page_label.size())

        # 更新状态栏显示目标缩放比例
        self.statusBar().showMessage(f"共 {self.total_pages} 页 | 缩放: {self._target_zoom * 100:.0f}% (渲染中...)")

    def _do_hd_render(self):
        """P0: 防抖后执行高清异步渲染"""
        if not self.doc or abs(self._target_zoom - self.zoom_factor) < 0.01:
            return

        # 更新实际缩放值
        old_zoom = self.zoom_factor
        self.zoom_factor = self._target_zoom

        # 清除 UI 矩形缓存（zoom 改变后需要重新计算）
        if hasattr(self, 'page_words') and self.page_words:
            for w in self.page_words:
                if "ui_rect" in w:
                    del w["ui_rect"]

        # P0: 启动异步渲染所有页面
        self._start_async_render()

    def _start_async_render(self):
        """P0/P1/P2: 启动异步渲染任务 - 支持视口裁剪和多级缓存"""
        # 取消正在进行的渲染任务
        self._cancel_active_workers()

        if not self.file_path:
            return

        # 获取显示参数
        screen = QApplication.primaryScreen()
        dpi_scale = screen.logicalDotsPerInchX() / 96.0 if screen else 1.0
        device_ratio = screen.devicePixelRatio() if screen else 1.0

        # P1: 获取视口信息用于裁剪渲染
        viewport_rect = self.scroll_area.viewport().geometry()
        scroll_x = self.scroll_area.horizontalScrollBar().value()
        scroll_y = self.scroll_area.verticalScrollBar().value()

        # P2: 检查 L2 缓存是否有所需缩放级别
        zoom_percent = int(self.zoom_factor * 100)
        cached_pages = self._l2_cache.get(zoom_percent, {})

        # 为每个页面启动渲染任务
        for page_idx in range(self.total_pages):
            # P2: 检查缓存
            if page_idx in cached_pages:
                # 使用 L2 缓存，直接更新显示
                pixmap = cached_pages[page_idx]
                if page_idx < len(self.page_labels):
                    page_label = self.page_labels[page_idx]
                    page_label.setPixmap(pixmap)
                    page_label.setFixedSize(pixmap.size())
                    self._base_pixmaps[page_idx] = pixmap
                    if page_idx < len(self.page_overlays):
                        self.page_overlays[page_idx].resize(page_label.size())
                continue

            # P1: 计算该页面在视口中的可见区域
            clip_rect = None
            if page_idx < len(self.page_labels) and self.zoom_factor > 2.0:
                page_label = self.page_labels[page_idx]
                page_pos = page_label.pos()
                page_size = page_label.size()

                # 计算页面相对于视口的位置
                page_x = page_pos.x() - scroll_x
                page_y = page_pos.y() - scroll_y

                # 检查页面是否在视口内
                if (page_x < viewport_rect.width() and
                    page_x + page_size.width() > 0 and
                    page_y < viewport_rect.height() and
                    page_y + page_size.height() > 0):

                    # 计算可见区域的交集
                    visible_x = max(0, -page_x)
                    visible_y = max(0, -page_y)
                    visible_w = min(page_size.width(), viewport_rect.width() - page_x) - visible_x
                    visible_h = min(page_size.height(), viewport_rect.height() - page_y) - visible_y

                    if visible_w > 0 and visible_h > 0:
                        # 添加边距避免边缘模糊
                        margin = 100
                        clip_rect = (
                            max(0, visible_x - margin),
                            max(0, visible_y - margin),
                            min(page_size.width(), visible_w + 2 * margin),
                            min(page_size.height(), visible_h + 2 * margin)
                        )

            worker = RenderWorker(
                self.file_path,
                page_idx,
                self.zoom_factor,
                dpi_scale,
                device_ratio,
                clip_rect=clip_rect,
                viewport_size=(viewport_rect.width(), viewport_rect.height())
            )
            worker.finished.connect(self._on_render_finished)
            worker.error.connect(self._on_render_error)
            self._active_workers[page_idx] = worker
            worker.start()

    def _cancel_active_workers(self):
        """P0: 取消所有正在进行的渲染任务"""
        for worker in self._active_workers.values():
            worker.stop()
        self._active_workers.clear()

    def _on_render_finished(self, page_idx: int, zoom_percent: int, dpi_scale: float, pixmap: QPixmap):
        """P0/P1/P2: 异步渲染完成回调 - 支持裁剪渲染合成和多级缓存"""
        # 从活动任务中移除
        is_clipped = False
        clip_rect = None
        if page_idx in self._active_workers:
            worker = self._active_workers.pop(page_idx, None)
            if worker:
                is_clipped = getattr(worker, '_is_clipped', False)
                clip_rect = worker.clip_rect

        # 检查缩放级别是否仍然匹配
        current_zoom_percent = int(self.zoom_factor * 100)
        if zoom_percent != current_zoom_percent:
            return  # 缩放已改变，丢弃此结果

        # 更新页面显示
        if page_idx < len(self.page_labels):
            page_label = self.page_labels[page_idx]

            if is_clipped and clip_rect and page_idx in self._base_pixmaps:
                # P1: 裁剪渲染 - 将新图像合成到基础图像上
                base_pixmap = self._base_pixmaps[page_idx]

                # 创建画家进行合成
                painter = QPainter(base_pixmap)
                painter.drawPixmap(int(clip_rect[0]), int(clip_rect[1]), pixmap)
                painter.end()

                # 更新显示
                page_label.setPixmap(base_pixmap)
                # P2: 存储到 L2 缓存
                self._add_to_l2_cache(page_idx, current_zoom_percent, base_pixmap)
            else:
                # 全页渲染 - 直接更新
                page_label.setPixmap(pixmap)
                page_label.setFixedSize(pixmap.size())
                self._base_pixmaps[page_idx] = pixmap
                # P2: 存储到 L2 缓存
                self._add_to_l2_cache(page_idx, current_zoom_percent, pixmap)

            # 同步更新覆盖层
            if page_idx < len(self.page_overlays):
                self.page_overlays[page_idx].resize(page_label.size())

        # 更新状态栏
        if not self._active_workers:
            self.statusBar().showMessage(f"共 {self.total_pages} 页 | 缩放: {self.zoom_factor * 100:.0f}%")

    def _add_to_l2_cache(self, page_idx: int, zoom_percent: int, pixmap: QPixmap):
        """P2: 添加渲染结果到 L2 缓存"""
        # 确保该缩放级别的缓存存在
        if zoom_percent not in self._l2_cache:
            # 清理旧缓存（如果超过最大缩放级别数）
            if len(self._l2_cache) >= self._max_l2_zoom_levels:
                # 删除最早的缩放级别
                oldest_zoom = min(self._l2_cache.keys())
                del self._l2_cache[oldest_zoom]
            self._l2_cache[zoom_percent] = {}

        # 存储到缓存（深拷贝）
        self._l2_cache[zoom_percent][page_idx] = pixmap.copy()

    def _get_from_l2_cache(self, page_idx: int, zoom_percent: int) -> QPixmap:
        """P2: 从 L2 缓存获取渲染结果"""
        if zoom_percent in self._l2_cache and page_idx in self._l2_cache[zoom_percent]:
            return self._l2_cache[zoom_percent][page_idx]
        return None

    def _on_render_error(self, page_idx: int, error_msg: str):
        """P0: 异步渲染错误回调"""
        print(f"页面 {page_idx + 1} 渲染失败: {error_msg}")
        if page_idx in self._active_workers:
            del self._active_workers[page_idx]

    def _zoom_reset(self):
        """P0: 重置缩放为 100% - 使用异步渲染"""
        if not self.doc:
            return

        self._target_zoom = 1.0
        self.zoom_factor = 1.0

        # 清除 UI 矩形缓存
        if hasattr(self, 'page_words') and self.page_words:
            for w in self.page_words:
                if "ui_rect" in w:
                    del w["ui_rect"]

        # 启动异步渲染
        self._start_async_render()

    # ==================== 鼠标滚轮事件（缩放） ====================

    def wheelEvent(self, event):
        """
        鼠标滚轮事件

        Ctrl + 滚轮: 缩放页面（阻止页面滚动）
        普通滚轮: 翻页或滚动
        """
        if not self.doc:
            event.ignore()
            return

        # 检查是否按住 Ctrl 键
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()

            if delta > 0:
                # 向上滚动 + Ctrl = 放大
                self._zoom(1.1)
            elif delta < 0:
                # 向下滚动 + Ctrl = 缩小
                self._zoom(0.9)

            # 关键：接受事件，阻止传递给 QScrollArea
            event.accept()
            return

        # 普通滚轮 - 让 QScrollArea 处理
        super().wheelEvent(event)

    def eventFilter(self, obj, event):
        """事件过滤器 - 处理 pages_container 和 scroll_area 的事件"""
        # 双击主页面隐藏搜索框
        if event.type() == event.MouseButtonDblClick:
            # 检查是否点击在主页面区域
            if obj in [self.pages_container, self.scroll_area] or \
               (hasattr(obj, 'parent') and obj.parent() == self.pages_container):
                self._hide_search_widget()
                # 不拦截事件，让其他处理继续

        # 处理滚轮事件：Ctrl+滚轮时阻止滚动并执行缩放
        if event.type() == event.Wheel:
            if event.modifiers() & Qt.ControlModifier:
                # Ctrl+滚轮：直接处理缩放
                delta = event.angleDelta().y()
                if delta > 0:
                    self._zoom(1.1)
                elif delta < 0:
                    self._zoom(0.9)
                event.accept()
                return True  # 拦截事件，阻止 scroll_area 滚动

        # 处理 pages_container 或其子控件（page_labels）的鼠标事件
        is_page_label = hasattr(obj, 'page_index')
        if (obj == self.pages_container or is_page_label) and self.doc:
            if event.type() == event.MouseButtonPress:
                if event.button() == Qt.RightButton:
                    # 处理右键点击
                    pos = event.pos()
                    if is_page_label:
                        # 转换坐标到 pages_container
                        global_pos = obj.mapToGlobal(pos)
                        pos = self.pages_container.mapFromGlobal(global_pos)
                    self._show_context_menu(pos)
                else:
                    # 处理左键点击 - 确保坐标在 pages_container 坐标系
                    if is_page_label:
                        pos = event.pos()
                        global_pos = obj.mapToGlobal(pos)
                        new_pos = self.pages_container.mapFromGlobal(global_pos)
                        # 创建新的事件对象（使用转换后的坐标）
                        new_event = QMouseEvent(
                            event.type(), new_pos, event.button(),
                            event.buttons(), event.modifiers()
                        )
                        self._on_mouse_press(new_event)
                    else:
                        self._on_mouse_press(event)
                return True
            elif event.type() == event.MouseMove:
                # 处理鼠标移动 - 确保坐标在 pages_container 坐标系
                if is_page_label:
                    pos = event.pos()
                    global_pos = obj.mapToGlobal(pos)
                    new_pos = self.pages_container.mapFromGlobal(global_pos)
                    new_event = QMouseEvent(
                        event.type(), new_pos, event.button(),
                        event.buttons(), event.modifiers()
                    )
                    self._on_mouse_move(new_event)
                else:
                    self._on_mouse_move(event)
                return True
            elif event.type() == event.MouseButtonRelease:
                # 处理鼠标释放 - 确保坐标在 pages_container 坐标系
                if is_page_label:
                    pos = event.pos()
                    global_pos = obj.mapToGlobal(pos)
                    new_pos = self.pages_container.mapFromGlobal(global_pos)
                    new_event = QMouseEvent(
                        event.type(), new_pos, event.button(),
                        event.buttons(), event.modifiers()
                    )
                    self._on_mouse_release(new_event)
                else:
                    self._on_mouse_release(event)
                return True

        return super().eventFilter(obj, event)

    # ==================== 键盘快捷键 ====================

    def keyPressEvent(self, event: QKeyEvent):
        """
        键盘事件处理

        快捷键映射:
        - PageUp: 上一页
        - PageDown: 下一页
        - Ctrl + 0: 重置缩放
        - Ctrl + O: 打开文件
        - Ctrl + W: 关闭文件
        - Ctrl + S: 保存
        - Ctrl + Q: 退出
        - Ctrl + F: 查找
        - F9: 显示/隐藏侧边栏
        - Home: 跳到第一页
        - End: 跳到最后一页
        - Escape: 隐藏搜索框
        """
        # ESC: 隐藏搜索框
        if event.key() == Qt.Key_Escape:
            if self.search_widget and self.search_widget.isVisible():
                self._hide_search_widget()
                event.accept()
                return

        if not self.doc:
            super().keyPressEvent(event)
            return

        key = event.key()
        modifiers = event.modifiers()

        # F9 - 切换侧边栏显示/隐藏
        if key == Qt.Key_F9:
            self._toggle_sidebar()
            event.accept()
            return

        # 无修饰键的快捷键
        if modifiers == Qt.NoModifier:
            if key == Qt.Key_PageUp:
                self._prev_page()
                event.accept()
                return

            elif key == Qt.Key_PageDown:
                self._next_page()
                event.accept()
                return

            elif key == Qt.Key_Home:
                self.current_page = 0
                self.render_page(self.current_page, self.zoom_factor)
                event.accept()
                return

            elif key == Qt.Key_End:
                if self.total_pages > 0:
                    self.current_page = self.total_pages - 1
                    self.render_page(self.current_page, self.zoom_factor)
                event.accept()
                return

        # Ctrl 修饰键的快捷键
        elif modifiers & Qt.ControlModifier:
            if key == Qt.Key_Plus or key == Qt.Key_Equal:
                self._zoom(1.1)
                event.accept()
                return

            elif key == Qt.Key_Minus:
                self._zoom(0.9)
                event.accept()
                return

            elif key == Qt.Key_F:
                self._show_search_widget()
                event.accept()
                return

        # 未处理的按键交给父类
        super().keyPressEvent(event)

    # ==================== 文本选择与复制（编辑器风格）====================

    def _compute_page_transform(self, page_label):
        """集中计算坐标变换参数（正确处理 DPI 和 devicePixelRatio）"""
        if not page_label or not self.doc:
            return None

        # DPI 缩放（逻辑像素 scale）
        dpi_scale = page_label.logicalDpiX() / 96.0

        pixmap = page_label.pixmap()
        if not pixmap:
            return None

        # 由于设置了 setDevicePixelRatio，pixmap.size() 返回的是逻辑尺寸
        # 但 pixmap.width() 返回的是设备像素，所以需要转换
        pixmap_logical_w = pixmap.width() / pixmap.devicePixelRatio()
        pixmap_logical_h = pixmap.height() / pixmap.devicePixelRatio()

        contents = page_label.contentsRect()

        # 计算居中对齐偏移（基于逻辑像素）
        offset_x = (contents.width() - pixmap_logical_w) / 2.0
        offset_y = (contents.height() - pixmap_logical_h) / 2.0
        offset_x = max(0.0, offset_x)
        offset_y = max(0.0, offset_y)

        # 统一的 scale：zoom * dpi_scale
        # 这与渲染时使用的 mat = fitz.Matrix(zoom * dpi_scale, zoom * dpi_scale) 一致
        scale = float(self.zoom_factor) * float(dpi_scale)

        return {
            "scale": scale,
            "offset_x": offset_x,
            "offset_y": offset_y,
            "contents": contents,
            "dpi_scale": dpi_scale
        }

    def _update_words_ui_rect(self, page_label):
        """预计算所有 word 的 UI 矩形，加速 hit-test"""
        if not self.page_words or not page_label:
            return

        t = self._compute_page_transform(page_label)
        if not t:
            return

        scale = t["scale"]
        ox = t["offset_x"]
        oy = t["offset_y"]
        contents = t["contents"]

        for w in self.page_words:
            x0, y0, x1, y1 = w["bbox"]
            # PDF -> UI 坐标转换（PyMuPDF 原点在左上角，Y轴向下，不需要翻转）
            ui_x0 = x0 * scale + contents.left() + ox
            ui_y0 = y0 * scale + contents.top() + oy
            ui_x1 = x1 * scale + contents.left() + ox
            ui_y1 = y1 * scale + contents.top() + oy
            # 使用 QRectF 保持浮点精度
            from PyQt5.QtCore import QRectF
            w["ui_rect"] = QRectF(ui_x0, ui_y0, ui_x1 - ui_x0, ui_y1 - ui_y0)

    def _load_page_text_chars(self, page_idx: int = None):
        """加载指定页面的字符位置信息 - 字符级精度"""
        self.page_text_chars = []  # 字符级信息列表
        self.page_words = []  # 词级别信息（备用）
        if not self.doc:
            return

        if page_idx is None:
            page_idx = self.current_page

        try:
            page = self.doc[page_idx]

            # 使用 rawdict 获取最细粒度的字符信息
            text_dict = page.get_text("rawdict")
            char_idx = 0  # 全局字符索引

            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:  # 跳过非文本块
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "")
                        chars = span.get("chars", [])
                        origin = span.get("origin", [0, 0])

                        # 如果 rawdict 提供了字符级 bbox，使用它
                        if chars:
                            for char_info in chars:
                                c = char_info.get("c", "")
                                bbox = char_info.get("bbox", [0, 0, 0, 0])
                                if c.strip() or c == " ":  # 包括空格
                                    self.page_text_chars.append({
                                        "char": c,
                                        "bbox": bbox,
                                        "span_origin": origin,
                                        "char_idx": char_idx,
                                        "span_text": text
                                    })
                                    char_idx += 1
                        else:
                            # 如果没有字符级信息，按字符分割 span
                            bbox = span.get("bbox", [0, 0, 0, 0])
                            x0, y0, x1, y1 = bbox
                            char_width = (x1 - x0) / max(1, len(text))

                            for i, c in enumerate(text):
                                if c.strip() or c == " ":
                                    char_bbox = [
                                        x0 + i * char_width,
                                        y0,
                                        x0 + (i + 1) * char_width,
                                        y1
                                    ]
                                    self.page_text_chars.append({
                                        "char": c,
                                        "bbox": char_bbox,
                                        "span_origin": origin,
                                        "char_idx": char_idx,
                                        "span_text": text
                                    })
                                    char_idx += 1

            # 同时加载词级别信息（用于双击选择等场景）
            words = page.get_text("words")
            for word in words:
                x0, y0, x1, y1, text = word[0:5]
                self.page_words.append({
                    "bbox": [x0, y0, x1, y1],
                    "text": text,
                    "rect": fitz.Rect(x0, y0, x1, y1)
                })

            # 预计算字符的 UI 矩形
            if hasattr(self, 'current_page_label') and self.current_page_label:
                self._update_chars_ui_rect(self.current_page_label)
                self._update_words_ui_rect(self.current_page_label)

        except Exception as e:
            print(f"加载页面文本失败: {e}")

    def _update_chars_ui_rect(self, page_label):
        """预计算所有字符的 UI 矩形"""
        if not self.page_text_chars or not page_label:
            return

        t = self._compute_page_transform(page_label)
        if not t:
            return

        scale = t["scale"]
        ox = t["offset_x"]
        oy = t["offset_y"]
        contents = t["contents"]

        from PyQt5.QtCore import QRectF
        for char_info in self.page_text_chars:
            x0, y0, x1, y1 = char_info["bbox"]
            ui_x0 = x0 * scale + contents.left() + ox
            ui_y0 = y0 * scale + contents.top() + oy
            ui_x1 = x1 * scale + contents.left() + ox
            ui_y1 = y1 * scale + contents.top() + oy
            char_info["ui_rect"] = QRectF(ui_x0, ui_y0, ui_x1 - ui_x0, ui_y1 - ui_y0)

    def _screen_to_pdf_point(self, page_label, screen_pos: QPoint) -> tuple:
        """UI 坐标 -> PDF 坐标（PyMuPDF 原点在左上角，Y轴向下，不需要翻转）"""
        t = self._compute_page_transform(page_label)
        if not t:
            return (0.0, 0.0)

        sx = float(screen_pos.x())
        sy = float(screen_pos.y())

        contents = t["contents"]
        scale = t["scale"]
        ox = t["offset_x"]
        oy = t["offset_y"]

        pdf_x = (sx - contents.left() - ox) / scale
        pdf_y = (sy - contents.top() - oy) / scale

        return (pdf_x, pdf_y)

    def _get_word_at_point(self, pdf_point: tuple, ui_point: tuple = None) -> int:
        """获取点处的 word 索引，优先使用 UI 矩形"""
        if not self.page_words:
            return -1

        eps = 0.5  # PDF 单位容差

        # 优先使用 UI 矩形（更精确、更快）
        if ui_point is not None:
            ux, uy = ui_point
            for i, w in enumerate(self.page_words):
                r = w.get("ui_rect")
                # QRectF.contains 接受 float 坐标
                if r is not None and r.contains(float(ux), float(uy)):
                    return i

        # 回退到 PDF 空间
        px, py = pdf_point
        for i, w in enumerate(self.page_words):
            x0, y0, x1, y1 = w["bbox"]
            if (x0 - eps) <= px <= (x1 + eps) and (y0 - eps) <= py <= (y1 + eps):
                return i

        # 回退：找最近的
        best_i = -1
        best_d2 = None
        for i, w in enumerate(self.page_words):
            x0, y0, x1, y1 = w["bbox"]
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            d2 = (cx - px) ** 2 + (cy - py) ** 2
            if best_d2 is None or d2 < best_d2:
                best_d2, best_i = d2, i

        return best_i if best_d2 is not None and best_d2 < 2500 else -1

    def _get_char_at_point(self, pdf_point: tuple, ui_point: tuple = None) -> int:
        """获取坐标处的字符索引 - 字符级精度"""
        if not self.page_text_chars:
            return -1

        # 优先使用 UI 矩形（更精确）
        if ui_point is not None:
            ux, uy = ui_point
            for i, char_info in enumerate(self.page_text_chars):
                r = char_info.get("ui_rect")
                if r is not None and r.contains(float(ux), float(uy)):
                    return i

        # 回退到 PDF 空间检测
        px, py = pdf_point
        eps = 0.5  # 容差

        for i, char_info in enumerate(self.page_text_chars):
            x0, y0, x1, y1 = char_info["bbox"]
            if (x0 - eps) <= px <= (x1 + eps) and (y0 - eps) <= py <= (y1 + eps):
                return i

        # 找最近的字符
        best_i = -1
        best_d = float('inf')
        for i, char_info in enumerate(self.page_text_chars):
            x0, y0, x1, y1 = char_info["bbox"]
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            d = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
            if d < best_d:
                best_d = d
                best_i = i

        return best_i if best_d < 20 else -1

    def _get_selected_text(self, start_idx: int, end_idx: int) -> str:
        """获取从 start_idx 到 end_idx 的选中文本 - 字符级精度"""
        # 边界检查
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx

        # 使用字符级信息
        if not self.page_text_chars:
            return ""

        # 确保索引在有效范围内
        start_idx = max(0, start_idx)
        end_idx = min(end_idx, len(self.page_text_chars) - 1)

        if start_idx > end_idx:
            return ""

        # 直接拼接字符
        chars = []
        for i in range(start_idx, end_idx + 1):
            char_info = self.page_text_chars[i]
            chars.append(char_info["char"])

        return "".join(chars)

    def _update_text_selection(self):
        """更新文本选择显示"""
        if not self.current_page_label:
            return

        # 获取当前页面的覆盖层
        overlay = None
        if self.current_page < len(self.page_overlays):
            overlay = self.page_overlays[self.current_page]

        if overlay is None:
            return

        # 清除之前的选择
        overlay.clear()

        if self.selection_start_char is None or self.selection_end_char is None:
            return

        start_idx = min(self.selection_start_char, self.selection_end_char)
        end_idx = max(self.selection_start_char, self.selection_end_char)

        # 获取选中的文本
        self.current_selected_text = self._get_selected_text(start_idx, end_idx)

        # 绘制选择高亮
        self._draw_selection_highlight(start_idx, end_idx, overlay)

    def _draw_selection_highlight(self, start_idx: int, end_idx: int, overlay: QLabel):
        """绘制文本选择高亮 - 字符级精度，合并同一行连续字符"""
        if not self.current_page_label:
            return

        # 使用字符级信息
        chars_list = self.page_text_chars
        if not chars_list or not self.doc:
            return

        # 边界保护
        start_idx = max(0, min(start_idx, len(chars_list) - 1))
        end_idx = max(0, min(end_idx, len(chars_list) - 1))

        page_label = self.current_page_label

        # 创建透明 pixmap
        overlay_pixmap = QPixmap(page_label.size())
        overlay_pixmap.fill(Qt.transparent)

        painter = QPainter(overlay_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        # 设置选择背景色
        highlight_color = QColor(0, 120, 215, 128)
        painter.setBrush(highlight_color)
        painter.setPen(Qt.NoPen)

        from PyQt5.QtCore import QRectF

        # 收集所有字符的 ui_rect
        char_rects = []
        for i in range(start_idx, end_idx + 1):
            if i >= len(chars_list):
                break
            char_info = chars_list[i]
            ui_rect = char_info.get("ui_rect")
            if ui_rect is None:
                # 实时计算
                t = self._compute_page_transform(page_label)
                if not t:
                    continue
                scale = t["scale"]
                offset_x = t["offset_x"]
                offset_y = t["offset_y"]
                contents = t["contents"]
                x0, y0, x1, y1 = char_info["bbox"]
                ui_x = x0 * scale + offset_x + contents.left()
                ui_y = y0 * scale + offset_y + contents.top()
                ui_w = (x1 - x0) * scale
                ui_h = (y1 - y0) * scale
                ui_rect = QRectF(ui_x, ui_y, ui_w, ui_h)
            char_rects.append((i, ui_rect))

        if not char_rects:
            painter.end()
            overlay.setPixmap(overlay_pixmap)
            overlay.show()
            return

        # 按行分组并合并连续字符
        # 使用Y坐标容差来判断是否同一行
        line_groups = []
        current_line = [char_rects[0]]
        current_y_center = char_rects[0][1].y() + char_rects[0][1].height() / 2

        for idx, rect in char_rects[1:]:
            y_center = rect.y() + rect.height() / 2
            # 如果Y坐标相近（同一行），加入当前组
            if abs(y_center - current_y_center) < 5:  # 5像素容差
                current_line.append((idx, rect))
            else:
                # 新行开始
                line_groups.append(current_line)
                current_line = [(idx, rect)]
                current_y_center = y_center
        line_groups.append(current_line)

        # 对每一行，合并连续字符的矩形
        for line_chars in line_groups:
            if not line_chars:
                continue

            # 按X坐标排序
            line_chars.sort(key=lambda x: x[1].x())

            # 合并连续字符
            merged_rects = []
            current_start_idx = line_chars[0][0]
            current_rect = QRectF(line_chars[0][1])

            for i in range(1, len(line_chars)):
                char_idx, char_rect = line_chars[i]
                prev_idx = line_chars[i-1][0]

                # 检查是否连续（索引连续且X坐标接近）
                is_continuous = (char_idx == prev_idx + 1) and \
                               (abs(char_rect.x() - (current_rect.x() + current_rect.width())) < 10)

                if is_continuous:
                    # 扩展当前矩形
                    current_rect = current_rect.united(char_rect)
                else:
                    # 保存当前矩形，开始新的
                    merged_rects.append(current_rect)
                    current_rect = QRectF(char_rect)

            merged_rects.append(current_rect)

            # 绘制合并后的矩形
            for rect in merged_rects:
                painter.drawRect(rect)

        painter.end()

        # 显示覆盖层
        overlay.setPixmap(overlay_pixmap)
        overlay.show()

    def _clear_text_selection(self):
        """清除文本选择"""
        # 清除所有覆盖层
        for overlay in self.page_overlays:
            overlay.clear()
            overlay.hide()
        self.selection_start_char = None
        self.selection_end_char = None
        self.selection_start_word = None
        self.selection_end_word = None
        self.current_selected_text = ""
        self.current_page_label = None

    def _on_mouse_press(self, event):
        """鼠标按下 - 开始文本选择"""
        if not self.doc or event.button() != Qt.LeftButton:
            return

        # 获取点击位置相对于 pages_container
        pos = event.pos()

        # 识别当前操作的页面
        page_label, page_idx, local_pos = self._get_page_at_pos(pos)
        if page_label is None:
            return

        self.current_page_label = page_label
        self.current_page = page_idx

        # 检查是否按住 Ctrl 键
        self.is_ctrl_pressed = (event.modifiers() & Qt.ControlModifier) != 0

        # 加载页面文本信息
        self._load_page_text_chars(page_idx)

        if not self.page_text_chars:
            # 没有文本可选择的页面，使用区域选择模式
            self._start_region_selection(local_pos)
            return

        # 文本选择模式 - 字符级精度选择
        self.is_selecting = True
        pdf_point = self._screen_to_pdf_point(page_label, local_pos)
        # 优先使用字符级 hit-test
        char_idx = self._get_char_at_point(pdf_point, (local_pos.x(), local_pos.y()))
        if char_idx < 0:
            # 如果字符级没命中，尝试词级别
            char_idx = self._get_word_at_point(pdf_point, (local_pos.x(), local_pos.y()))

        self.selection_start_char = char_idx
        self.selection_end_char = char_idx
        self._update_text_selection()

    def _start_region_selection(self, pos: QPoint):
        """开始区域选择模式（用于扫描图片页面）"""
        self.selection_start = pos

        if self.rubber_band is None:
            self.rubber_band = QRubberBand(QRubberBand.Rectangle, self.current_page_label)

        self.rubber_band.setGeometry(QRect(pos, QSize()))
        self.rubber_band.show()

    def _on_mouse_move(self, event):
        """鼠标移动 - 更新选择区域或检测注释悬停"""
        if not self.doc:
            return

        # 获取事件源和坐标
        sender = self.sender()
        pos = event.pos()

        # 如果事件源是 page_label，将坐标转换为相对于 pages_container
        if sender and hasattr(sender, 'page_index'):
            # 事件来自 page_label，需要转换坐标
            global_pos = sender.mapToGlobal(pos)
            pos = self.pages_container.mapFromGlobal(global_pos)

        if self.is_selecting and self.page_text_chars and self.current_page_label:
            # 文本选择模式 - 字符级精度
            local_pos = self.current_page_label.mapFrom(self.pages_container, pos)
            pdf_point = self._screen_to_pdf_point(self.current_page_label, local_pos)
            char_idx = self._get_char_at_point(pdf_point, (local_pos.x(), local_pos.y()))
            if char_idx >= 0:
                self.selection_end_char = char_idx
                self._update_text_selection()
        elif self.rubber_band and self.rubber_band.isVisible():
            # 区域选择模式
            if hasattr(self, 'selection_start') and self.current_page_label:
                local_pos = self.current_page_label.mapFrom(self.pages_container, pos)
                rect = QRect(self.selection_start, local_pos).normalized()
                self.rubber_band.setGeometry(rect)
        else:
            # 非选择模式，检测注释悬停
            # 若 is_selecting == True，则屏蔽 Hover-Engine
            if not self.is_selecting:
                self._check_annot_hover(pos)

    def _on_mouse_release(self, event):
        """鼠标释放 - 完成选择，按住 Ctrl 时自动复制文本"""
        if not self.doc or event.button() != Qt.LeftButton:
            return

        if self.is_selecting and self.page_text_chars:
            # 文本选择模式
            self.is_selecting = False

            # 如果按住 Ctrl，自动复制选中的文本
            if (event.modifiers() & Qt.ControlModifier) and self.current_selected_text:
                self._copy_to_clipboard(self.current_selected_text)

            self.is_ctrl_pressed = False

        elif self.rubber_band and self.rubber_band.isVisible():
            # 区域选择模式 - 隐藏选择框
            self.rubber_band.hide()

    def _copy_to_clipboard(self, text: str):
        """复制文本到剪贴板（带 X11 兼容性处理）"""
        try:
            # 使用 QClipboard.Clipboard 模式，避免 Selection 模式的问题
            self.clipboard.setText(text, QClipboard.Clipboard)
            self.statusBar().showMessage(f"已复制 {len(text)} 个字符", 2000)
        except Exception as e:
            print(f"复制到剪贴板失败: {e}")
            # 备用方案：使用系统命令
            try:
                import subprocess
                proc = subprocess.Popen(['xclip', '-selection', 'clipboard'],
                                        stdin=subprocess.PIPE)
                proc.communicate(text.encode('utf-8'))
                self.statusBar().showMessage(f"已复制 {len(text)} 个字符", 2000)
            except:
                pass

    def _is_scanned_page(self) -> bool:
        """检测当前页面是否为扫描图片（无文本）"""
        if not self.doc:
            return False

        try:
            page = self.doc[self.current_page]
            text = page.get_text("text").strip()
            return len(text) == 0
        except:
            return False

    def _save_page_as_image(self):
        """保存当前页面为图片"""
        if not self.doc or not self.file_path:
            return

        try:
            page = self.doc[self.current_page]

            # 生成文件名：修改日期_时间_hash.png
            file_mtime = os.path.getmtime(self.file_path)
            dt = datetime.fromtimestamp(file_mtime)
            date_str = dt.strftime("%Y%m%d")
            time_str = dt.strftime("%H%M%S")

            # 使用当前时间和页面号生成 hash
            hash_input = f"{file_mtime}_{self.current_page}_{time.time()}"
            hash_str = hashlib.md5(hash_input.encode()).hexdigest()[:8]

            default_name = f"{date_str}_{time_str}_{hash_str}.png"

            # 显示保存对话框
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "保存页面为图片",
                default_name,
                "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;所有文件 (*.*)"
            )

            if file_path:
                # 渲染页面为图片（较高分辨率）
                mat = fitz.Matrix(2.0, 2.0)  # 2x 缩放以获得更高质量
                pix = page.get_pixmap(matrix=mat, alpha=False)

                # 保存图片
                pix.save(file_path)
                self.statusBar().showMessage(f"已保存: {file_path}", 3000)

        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存图片失败:\n{str(e)}")

    def _show_context_menu(self, pos):
        """显示右键菜单"""
        if not self.doc:
            return

        menu = QMenu(self)

        # 首先检查是否点击了注释（优先显示删除注释选项）
        clicked_annot = self._get_annotation_at_pos(pos)
        if clicked_annot:
            delete_action = menu.addAction("删除注释(&D)")
            delete_action.triggered.connect(lambda: self._delete_annot_at_pos(pos))
            menu.addSeparator()

        # 判断是否为扫描页面（无文本）
        is_scanned = self._is_scanned_page()

        if is_scanned:
            # 扫描图片页面：显示保存图片选项
            save_image_action = menu.addAction("保存页面为图片(&S)")
            save_image_action.triggered.connect(self._save_page_as_image)
        else:
            # 文本页面：显示高亮选项
            highlight_action = menu.addAction("高亮选区(&H)")
            highlight_action.triggered.connect(self._add_highlight)

            # 下划线注释选项
            underline_action = menu.addAction("下划线注释(&U)...")
            underline_action.triggered.connect(self._add_underline_annot)

            # 如果没有文本选区，禁用高亮和下划线
            if not self.current_selected_text:
                highlight_action.setEnabled(False)
                underline_action.setEnabled(False)

            menu.addSeparator()

            # 复制选项
            if self.current_selected_text:
                copy_action = menu.addAction("复制(&C)")
                copy_action.setShortcut("Ctrl+C")
                copy_action.triggered.connect(self._copy_current_selection)
            else:
                no_copy_action = menu.addAction("复制(&C)")
                no_copy_action.setEnabled(False)

        menu.exec_(self.pages_container.mapToGlobal(pos))

    def _get_annotation_at_pos(self, pos):
        """检查指定位置是否有注释"""
        if not self.doc or not self._annot_hotspot_map:
            return None

        page_label, page_idx, local_pos = self._get_page_at_pos(pos)
        if page_label is None or page_idx < 0:
            return None

        # 计算 PDF 坐标
        screen = QApplication.primaryScreen()
        dpi_scale = screen.logicalDotsPerInchX() / 96.0 if screen else 1.0
        scale = self.zoom_factor * dpi_scale

        pdf_x = local_pos.x() / scale
        pdf_y = local_pos.y() / scale

        # 检查是否在注释区域内
        if page_idx in self._annot_hotspot_map:
            for annot_info in self._annot_hotspot_map[page_idx]:
                rect = annot_info["rect"]
                if rect.x0 <= pdf_x <= rect.x1 and rect.y0 <= pdf_y <= rect.y1:
                    return annot_info

        return None

    def _delete_annot_at_pos(self, pos):
        """删除指定位置的注释"""
        page_label, page_idx, local_pos = self._get_page_at_pos(pos)
        if page_label is None or page_idx < 0:
            return

        try:
            page = self.doc[page_idx]
            annots = list(page.annots())

            # 计算 PDF 坐标
            screen = QApplication.primaryScreen()
            dpi_scale = screen.logicalDotsPerInchX() / 96.0 if screen else 1.0
            scale = self.zoom_factor * dpi_scale

            pdf_x = local_pos.x() / scale
            pdf_y = local_pos.y() / scale

            # 查找并删除匹配的注释
            for annot in annots:
                rect = annot.rect
                if rect.x0 <= pdf_x <= rect.x1 and rect.y0 <= pdf_y <= rect.y1:
                    page.delete_annot(annot)
                    self._mark_document_modified(True)
                    # 刷新显示
                    self._l2_cache.clear()
                    self._base_pixmaps.clear()
                    self.render_timer.stop()
                    self._do_render()
                    self._load_thumbnails()
                    self._load_annotations()
                    self._build_annot_index()
                    self.statusBar().showMessage("已删除注释（未保存）", 3000)
                    return

        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除注释失败:\n{str(e)}")

    def _copy_current_selection(self):
        """复制当前选区的文本到剪贴板"""
        if self.current_selected_text:
            self._copy_to_clipboard(self.current_selected_text)

    def _add_highlight(self):
        """为当前选区添加高亮注释 - 按行分别高亮"""
        if not self.doc or not self.current_selected_text:
            return

        try:
            page = self.doc[self.current_page]

            # 获取选中的字符范围
            start_idx = min(self.selection_start_char, self.selection_end_char)
            end_idx = max(self.selection_start_char, self.selection_end_char)

            # 边界检查
            start_idx = max(0, start_idx)
            end_idx = min(end_idx, len(self.page_text_chars) - 1)

            if start_idx > end_idx or not self.page_text_chars:
                return

            # 按行分组字符
            line_groups = []
            current_line = [self.page_text_chars[start_idx]]
            current_y_center = sum(self.page_text_chars[start_idx]["bbox"][1::2]) / 2

            for i in range(start_idx + 1, end_idx + 1):
                char_info = self.page_text_chars[i]
                bbox = char_info["bbox"]
                y_center = (bbox[1] + bbox[3]) / 2

                # 如果Y坐标相近（同一行），加入当前组
                if abs(y_center - current_y_center) < 5:  # 5点容差
                    current_line.append(char_info)
                else:
                    # 新行开始
                    line_groups.append(current_line)
                    current_line = [char_info]
                    current_y_center = y_center
            line_groups.append(current_line)

            # 为每行添加高亮
            highlight_count = 0
            for line_chars in line_groups:
                if not line_chars:
                    continue

                # 计算该行的包围盒
                x0_list = [c["bbox"][0] for c in line_chars]
                y0_list = [c["bbox"][1] for c in line_chars]
                x1_list = [c["bbox"][2] for c in line_chars]
                y1_list = [c["bbox"][3] for c in line_chars]

                pdf_rect = fitz.Rect(
                    min(x0_list), min(y0_list),
                    max(x1_list), max(y1_list)
                )

                # 添加高亮注释
                highlight = page.add_highlight_annot(pdf_rect)
                if highlight:
                    # 应用注释更改
                    highlight.update()
                    highlight_count += 1

            if highlight_count > 0:
                # 标记文档已修改
                self._mark_document_modified(True)
                # 清除缓存强制重新渲染
                self._l2_cache.clear()
                self._base_pixmaps.clear()
                # 立即重新渲染以显示高亮（跳过延迟）
                self.render_timer.stop()
                self._do_render()
                # 刷新缩略图以同步显示注释
                self._load_thumbnails()
                # 刷新注释侧边栏
                self._load_annotations()
                self.statusBar().showMessage(f"已添加 {highlight_count} 处高亮（未保存）", 3000)

        except Exception as e:
            QMessageBox.critical(self, "错误", f"添加高亮失败:\n{str(e)}")

    def _add_underline_annot(self):
        """
        为当前选区添加下划线注释
        - 复用逐字选择产生的字符数据
        - 调用 page.add_underline_annot() 创建物理批注
        - 弹出对话框输入注释内容
        - 调用 annot.set_info(content=user_text) 存储注释文本
        - 增量保存到 PDF
        """
        if not self.doc or not self.current_selected_text:
            return

        # 弹出输入对话框获取注释内容
        from PyQt5.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            self, "添加下划线注释", "请输入注释内容:",
            QLineEdit.Normal, ""
        )

        if not ok:
            return  # 用户取消

        try:
            page = self.doc[self.current_page]

            # 获取选中的字符范围
            start_idx = min(self.selection_start_char, self.selection_end_char)
            end_idx = max(self.selection_start_char, self.selection_end_char)

            # 边界检查
            start_idx = max(0, start_idx)
            end_idx = min(end_idx, len(self.page_text_chars) - 1)

            if start_idx > end_idx or not self.page_text_chars:
                return

            # 按行分组字符（复用高亮功能的逻辑）
            line_groups = []
            current_line = [self.page_text_chars[start_idx]]
            current_y_center = sum(self.page_text_chars[start_idx]["bbox"][1::2]) / 2

            for i in range(start_idx + 1, end_idx + 1):
                char_info = self.page_text_chars[i]
                bbox = char_info["bbox"]
                y_center = (bbox[1] + bbox[3]) / 2

                # 如果Y坐标相近（同一行），加入当前组
                if abs(y_center - current_y_center) < 5:  # 5点容差
                    current_line.append(char_info)
                else:
                    # 新行开始
                    line_groups.append(current_line)
                    current_line = [char_info]
                    current_y_center = y_center
            line_groups.append(current_line)

            # 为每行添加下划线注释
            annot_count = 0
            for line_chars in line_groups:
                if not line_chars:
                    continue

                # 计算该行的包围盒
                x0_list = [c["bbox"][0] for c in line_chars]
                y0_list = [c["bbox"][1] for c in line_chars]
                x1_list = [c["bbox"][2] for c in line_chars]
                y1_list = [c["bbox"][3] for c in line_chars]

                pdf_rect = fitz.Rect(
                    min(x0_list), min(y0_list),
                    max(x1_list), max(y1_list)
                )

                # 添加下划线注释
                underline = page.add_underline_annot(pdf_rect)
                if underline:
                    # 设置下划线颜色为红色 (RGB: 1, 0, 0)
                    underline.set_colors(stroke=(1, 0, 0))
                    # 设置注释内容（PDF 标准 Contents 属性）
                    underline.set_info(content=text)
                    # 应用注释更改
                    underline.update()
                    annot_count += 1

            if annot_count > 0:
                # 标记文档已修改
                self._mark_document_modified(True)

                # 清除缓存强制重新渲染
                self._l2_cache.clear()
                self._base_pixmaps.clear()
                # 立即重新渲染以显示下划线（跳过延迟）
                self.render_timer.stop()
                self._do_render()
                # 刷新缩略图以同步显示注释
                self._load_thumbnails()
                # 刷新注释侧边栏
                self._load_annotations()
                self.statusBar().showMessage(f"已添加 {annot_count} 处下划线注释（未保存）", 3000)

                # 更新热区索引
                self._build_annot_index()

        except Exception as e:
            QMessageBox.critical(self, "错误", f"添加下划线注释失败:\n{str(e)}")

    def _build_annot_index(self):
        """
        构建注释热区索引
        - 扫描所有页面的 annots()
        - 提取 type == 8 (Highlight) 和 type == 9 (Underline) 的 rect 和 content
        - 建立 HotspotMap = {page_index: [{"rect", "content", "type"}, ...]}
        """
        if not self.doc:
            return

        self._annot_hotspot_map = {}

        for page_idx in range(self.total_pages):
            page = self.doc[page_idx]
            annots = list(page.annots())

            page_annots = []
            for annot in annots:
                # annot.type 返回 (type_num, type_name) 或整数（取决于 PyMuPDF 版本）
                annot_type = annot.type
                if isinstance(annot_type, tuple):
                    type_num = annot_type[0]
                else:
                    type_num = annot_type

                # 处理高亮 (8) 和下划线 (9) 注释
                if type_num in (8, 9):  # Highlight 或 Underline
                    rect = annot.rect
                    info = annot.info
                    content = info.get("content", "") if info else ""

                    # 对于下划线，需要有内容才显示悬停提示
                    # 对于高亮，即使没有内容也可以右键删除
                    if type_num == 9 and not content:
                        continue

                    page_annots.append({
                        "rect": rect,
                        "content": content,
                        "type": type_num  # 8=高亮, 9=下划线
                    })

            if page_annots:
                self._annot_hotspot_map[page_idx] = page_annots

    def _check_annot_hover(self, pos):
        """
        高性能注释悬停检测
        - 将鼠标像素坐标转换为 PDF 点坐标
        - 先判断鼠标是否在当前页的 Annots 总包围盒内
        - 再匹配具体的条目
        """
        if not self.doc or not self._annot_hotspot_map:
            self._hide_annot_tooltip()
            return

        # 获取当前页面
        page_label, page_idx, local_pos = self._get_page_at_pos(pos)
        if page_label is None or page_idx < 0 or page_idx not in self._annot_hotspot_map:
            self._hide_annot_tooltip()
            return

        # 计算鼠标在 PDF 坐标系中的位置
        page_annots = self._annot_hotspot_map[page_idx]

        # 获取该页的标签和变换信息
        if page_idx >= len(self.page_labels):
            return

        page_label = self.page_labels[page_idx]
        local_pos = page_label.mapFrom(self.pages_container, pos)

        # 像素坐标 -> PDF 坐标（考虑缩放和 DPI）
        screen = QApplication.primaryScreen()
        dpi_scale = screen.logicalDotsPerInchX() / 96.0 if screen else 1.0
        scale = self.zoom_factor * dpi_scale

        pdf_x = local_pos.x() / scale
        pdf_y = local_pos.y() / scale

        # 检测碰撞
        for annot in page_annots:
            rect = annot["rect"]
            # 快速包围盒检测
            if rect.x0 <= pdf_x <= rect.x1 and rect.y0 <= pdf_y <= rect.y1:
                # 命中注释，启动延时显示
                if self._current_hover_annot != annot:
                    self._current_hover_annot = annot
                    self._tooltip_timer.stop()
                    self._tooltip_timer.start(300)  # 300ms 延迟
                return

        # 未命中，隐藏浮窗
        self._hide_annot_tooltip()

    def _show_annot_tooltip(self):
        """显示注释浮窗"""
        if not self._current_hover_annot:
            return

        # 创建浮窗（如果不存在）
        if not self._annot_tooltip:
            self._annot_tooltip = AnnotationTooltip(self)

        content = self._current_hover_annot.get("content", "")
        if not content:
            return

        self._annot_tooltip.setText(content)
        self._annot_tooltip.adjustSize()

        # 计算显示位置（鼠标附近）
        cursor_pos = QCursor.pos()
        self._annot_tooltip.move(cursor_pos.x() + 15, cursor_pos.y() + 15)
        self._annot_tooltip.show()

    def _hide_annot_tooltip(self):
        """隐藏注释浮窗"""
        self._current_hover_annot = None
        self._tooltip_timer.stop()
        if self._annot_tooltip:
            self._annot_tooltip.hide()

    # ==================== 拖放支持 ====================

    def dragEnterEvent(self, event: QDragEnterEvent):
        """拖拽进入事件 - 接受 PDF 文件"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            # 检查是否是 PDF 文件
            for url in urls:
                if url.toLocalFile().lower().endswith('.pdf'):
                    event.acceptProposedAction()
                    return

        event.ignore()

    def dragMoveEvent(self, event):
        """拖拽移动事件"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        """放置事件 - 打开拖入的 PDF 文件"""
        urls = event.mimeData().urls()

        if urls:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith('.pdf'):
                self.open_document(file_path)
                event.acceptProposedAction()
            else:
                event.ignore()
        else:
            event.ignore()

    # ==================== 关于对话框 ====================

    def _show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于 Unipdf",
            """<h2>Unipdf 1.0</h2>
            <p>极简、极速的 PDF 查看器</p>
            <p>适配 UOS V20 (Linux) 环境</p>
            <p>技术栈: Python 3 + PyQt5 + PyMuPDF</p>
            <p>风格: 类似 Windows SumatraPDF</p>
            """
        )

    # ==================== 自动目录生成 ====================

    def _show_auto_toc_dialog(self):
        """显示自动目录生成对话框"""
        if not self.doc:
            QMessageBox.warning(self, "提示", "请先打开 PDF 文件")
            return

        # 创建对话框选择文档类型
        from PyQt5.QtWidgets import QDialog, QComboBox, QVBoxLayout, QLabel, QHBoxLayout

        dialog = QDialog(self)
        dialog.setWindowTitle("自动生成目录")
        dialog.setMinimumWidth(300)

        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("选择文档类型："))

        doc_type_combo = QComboBox()
        doc_type_combo.addItem("自动检测", "auto")
        doc_type_combo.addItem("法律法规", "legal")
        doc_type_combo.addItem("国家标准 (GB/T)", "gbt")
        layout.addWidget(doc_type_combo)

        layout.addWidget(QLabel("此功能将分析文档结构并自动生成可折叠目录。"))
        layout.addWidget(QLabel("分析过程在后台进行，不会阻塞界面。"))

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("开始分析")
        cancel_btn = QPushButton("取消")

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        if dialog.exec_() == QDialog.Accepted:
            doc_type = doc_type_combo.currentData()
            self._start_auto_toc_generation(doc_type)

    def _start_auto_toc_generation(self, doc_type: str):
        """启动自动目录生成"""
        if not self.file_path:
            return

        # 显示进度对话框
        self._toc_progress_dialog = QProgressDialog(
            "正在分析文档结构...", "取消", 0, 50, self
        )
        self._toc_progress_dialog.setWindowTitle("生成目录")
        self._toc_progress_dialog.setWindowModality(Qt.WindowModal)

        # 创建工作线程
        self._toc_worker = AutoTocWorker(self.file_path, doc_type)
        self._toc_worker.progress.connect(self._on_toc_progress)
        self._toc_worker.finished.connect(self._on_toc_finished)
        self._toc_worker.error.connect(self._on_toc_error)

        self._toc_progress_dialog.canceled.connect(self._toc_worker.stop)

        self._toc_worker.start()

    def _on_toc_progress(self, current: int, total: int):
        """目录生成进度更新"""
        if hasattr(self, '_toc_progress_dialog'):
            self._toc_progress_dialog.setMaximum(total)
            self._toc_progress_dialog.setValue(current)
            self._toc_progress_dialog.setLabelText(
                f"正在分析文档结构... ({current}/{total})"
            )

    def _on_toc_finished(self, toc_list: list):
        """目录生成完成"""
        if hasattr(self, '_toc_progress_dialog'):
            self._toc_progress_dialog.close()

        if not toc_list:
            QMessageBox.information(self, "完成", "未检测到有效的章节结构")
            return

        # 应用到文档
        try:
            self.doc.set_toc(toc_list)

            # 标记文档已修改
            self._mark_document_modified(True)

            # 刷新目录显示
            self._load_toc()

            # 展开侧边栏并切换到目录视图
            if not self._sidebar_visible:
                self._toggle_sidebar()
            self._switch_sidebar_view(0)

            QMessageBox.information(
                self, "完成",
                f"成功生成目录，共 {len(toc_list)} 个条目（未保存）"
            )

        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存目录失败:\n{str(e)}")

    def _on_toc_error(self, error_msg: str):
        """目录生成错误"""
        if hasattr(self, '_toc_progress_dialog'):
            self._toc_progress_dialog.close()
        QMessageBox.critical(self, "错误", f"目录生成失败:\n{error_msg}")

    # ==================== 侧边栏功能 ====================

    def _init_sidebar_toolbar(self, parent_layout):
        """初始化侧边栏顶部的视图切换工具栏"""
        toolbar = QFrame()
        toolbar.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        toolbar.setMaximumHeight(40)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(5, 2, 5, 2)
        toolbar_layout.setSpacing(5)

        # 目录按钮
        self.btn_toc = QToolButton()
        self.btn_toc.setText("目录")
        self.btn_toc.setCheckable(True)
        self.btn_toc.setChecked(True)
        self.btn_toc.setToolTip("显示目录")
        self.btn_toc.clicked.connect(lambda: self._switch_sidebar_view(0))
        toolbar_layout.addWidget(self.btn_toc)

        # 注释按钮
        self.btn_annot = QToolButton()
        self.btn_annot.setText("注释")
        self.btn_annot.setCheckable(True)
        self.btn_annot.setToolTip("显示注释列表")
        self.btn_annot.clicked.connect(lambda: self._switch_sidebar_view(1))
        toolbar_layout.addWidget(self.btn_annot)

        # 缩略图按钮
        self.btn_thumbnail = QToolButton()
        self.btn_thumbnail.setText("页面")
        self.btn_thumbnail.setCheckable(True)
        self.btn_thumbnail.setToolTip("显示页面缩略图")
        self.btn_thumbnail.clicked.connect(lambda: self._switch_sidebar_view(2))
        toolbar_layout.addWidget(self.btn_thumbnail)

        toolbar_layout.addStretch()
        parent_layout.addWidget(toolbar)

    def _switch_sidebar_view(self, index):
        """切换侧边栏视图"""
        self.sidebar_stack.setCurrentIndex(index)

        # 更新按钮状态
        self.btn_toc.setChecked(index == 0)
        self.btn_annot.setChecked(index == 1)
        self.btn_thumbnail.setChecked(index == 2)

        # 确保侧边栏是可见的
        if not self._sidebar_visible:
            self._toggle_sidebar()

        # 如果切换到缩略图视图且未加载过，则加载缩略图
        if index == 2 and self.doc and self.thumbnail_widget.count() == 0:
            self._load_thumbnails()

    def _toggle_sidebar(self):
        """显示/隐藏侧边栏，快捷键 F9"""
        if self._sidebar_visible:
            # 隐藏侧边栏
            self._sidebar_width = self.sidebar_container.width()
            self.sidebar_container.setVisible(False)
            self._sidebar_visible = False
            self.sidebar_toggle_action.setChecked(False)  # 同步菜单状态
        else:
            # 显示侧边栏
            self.sidebar_container.setVisible(True)
            self._sidebar_visible = True
            self.sidebar_toggle_action.setChecked(True)  # 同步菜单状态
            # 恢复原来的宽度
            sizes = self.splitter.sizes()
            if sizes[0] == 0:
                self.splitter.setSizes([self._sidebar_width, sizes[1] - self._sidebar_width])

    def _toggle_sidebar_with_toc(self):
        """REQ-05: Ctrl+D 快捷切换侧边栏
        - 若侧边栏关闭，显示侧边栏并自动激活目录选项卡
        - 若侧边栏开启，隐藏侧边栏
        """
        if self._sidebar_visible:
            # 侧边栏已开启，隐藏它
            self._toggle_sidebar()
        else:
            # 侧边栏已关闭，显示并切换到目录
            self._switch_sidebar_view(0)  # 0 = 目录选项卡

    def _load_annotations(self):
        """加载所有页面的注释列表"""
        self.annot_widget.clear()

        if not self.doc:
            return

        try:
            total_annots = 0
            for page_idx in range(self.total_pages):
                page = self.doc[page_idx]
                annots = list(page.annots())

                for annot in annots:
                    # 处理注释类型（兼容不同 PyMuPDF 版本）
                    annot_type_raw = annot.type
                    if isinstance(annot_type_raw, tuple):
                        annot_type = annot_type_raw[1] if len(annot_type_raw) > 1 else "未知"
                    else:
                        # 根据类型数字映射名称
                        type_map = {8: "高亮", 9: "下划线", 10: "删除线", 11: "波浪线",
                                    0: "文本", 12: "盖章", 14: "墨水", 15: "弹出", 16: "文件附件"}
                        annot_type = type_map.get(annot_type_raw, f"类型{annot_type_raw}")

                    info = annot.info
                    content = info.get("content", "") if info else ""

                    # 格式化显示文本
                    if content:
                        display_text = f"第{page_idx+1}页 [{annot_type}] {content[:40]}"
                        if len(content) > 40:
                            display_text += "..."
                    else:
                        display_text = f"第{page_idx+1}页 [{annot_type}] (无内容)"

                    item = QListWidgetItem(display_text)
                    item.setData(Qt.UserRole, page_idx)
                    item.setData(Qt.UserRole + 1, annot.rect)
                    self.annot_widget.addItem(item)
                    total_annots += 1

            if total_annots == 0:
                item = QListWidgetItem("(文档中无注释)")
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                self.annot_widget.addItem(item)

        except Exception as e:
            print(f"加载注释失败: {e}")

    def _on_annot_clicked(self, item: QListWidgetItem):
        """REQ-04: 注释点击事件 - 跳转到对应页面及坐标"""
        page_index = item.data(Qt.UserRole)
        rect = item.data(Qt.UserRole + 1)  # 获取注释的矩形区域
        if page_index is not None and 0 <= page_index < self.total_pages:
            # 使用统一的跳转方法，保持当前缩放
            self._scroll_to_page(page_index, rect=rect, keep_zoom=True)

    def _show_annot_context_menu(self, pos):
        """注释列表右键菜单"""
        item = self.annot_widget.itemAt(pos)
        if not item:
            return

        # 检查是否是有效注释项（不是"无注释"提示）
        page_index = item.data(Qt.UserRole)
        if page_index is None:
            return

        menu = QMenu(self)
        delete_action = menu.addAction("删除注释(&D)")
        delete_action.triggered.connect(lambda: self._delete_annotation(item))

        menu.exec_(self.annot_widget.mapToGlobal(pos))

    def _delete_annotation(self, item):
        """删除指定注释"""
        if not self.doc:
            return

        page_index = item.data(Qt.UserRole)
        rect = item.data(Qt.UserRole + 1)

        if page_index is None or page_index < 0 or page_index >= self.total_pages:
            return

        try:
            page = self.doc[page_index]
            annots = list(page.annots())

            # 查找匹配的注释（根据页面和矩形区域）
            for annot in annots:
                if annot.rect == rect:
                    # 删除注释
                    page.delete_annot(annot)
                    # 标记文档已修改
                    self._mark_document_modified(True)
                    # 刷新显示
                    self._l2_cache.clear()
                    self._base_pixmaps.clear()
                    self.render_timer.stop()
                    self._do_render()
                    self._load_thumbnails()
                    self._load_annotations()
                    self._build_annot_index()
                    self.statusBar().showMessage("已删除注释（未保存）", 3000)
                    return

        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除注释失败:\n{str(e)}")

    def _load_thumbnails(self):
        """加载页面缩略图"""
        self.thumbnail_widget.clear()

        if not self.doc:
            return

        # 使用较小的缩放比例生成缩略图
        thumb_zoom = 0.15  # 缩略图缩放比例

        for i in range(self.total_pages):
            try:
                page = self.doc[i]
                mat = fitz.Matrix(thumb_zoom, thumb_zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)

                # 使用 .copy() 创建深拷贝，防止 pix 被释放后产生 use-after-free
                img = QImage(
                    pix.samples,
                    pix.width,
                    pix.height,
                    pix.stride,
                    QImage.Format_RGB888 if pix.n == 3 else QImage.Format_ARGB32
                ).copy()

                pixmap = QPixmap.fromImage(img)
                item = QListWidgetItem(f"第 {i + 1} 页")
                item.setIcon(QIcon(pixmap))
                item.setData(Qt.UserRole, i)
                item.setTextAlignment(Qt.AlignCenter)
                self.thumbnail_widget.addItem(item)

            except Exception as e:
                print(f"生成缩略图失败 (第 {i + 1} 页): {e}")

    def _scroll_to_page(self, page_index: int, rect: fitz.Rect = None, keep_zoom: bool = True, center: bool = True):
        """REQ-04: 滚动到指定页面及坐标位置，支持垂直居中

        Args:
            page_index: 页码索引（从 0 开始）
            rect: PDF 页面中的矩形区域（fitz.Rect），可选
            keep_zoom: 是否保持当前缩放倍率（默认 True）
            center: 是否将目标区域垂直居中（默认 True）
        """
        if not (0 <= page_index < len(self.page_labels)):
            return

        page_label = self.page_labels[page_index]

        # 滚动到页面位置
        if rect is not None:
            # 如果有指定坐标区域，计算在 QLabel 中的对应位置
            # 使用当前缩放因子（不强制重置）
            zoom = self.zoom_factor if keep_zoom else 1.0

            # 获取 DPI 缩放因子
            screen = QApplication.primaryScreen()
            dpi_scale = screen.logicalDotsPerInchX() / 96.0 if screen else 1.0

            # 计算 QLabel 中的坐标（考虑缩放）
            scale = zoom * dpi_scale

            # 获取 page_label 在 pages_container 中的位置偏移
            label_pos = page_label.pos()
            x = int(rect.x0 * scale) + label_pos.x()
            y = int(rect.y0 * scale) + label_pos.y()
            w = int((rect.x1 - rect.x0) * scale)
            h = int((rect.y1 - rect.y0) * scale)

            if center:
                # 垂直居中：计算滚动位置使目标区域位于视口中央
                viewport_height = self.scroll_area.viewport().height()
                target_center_y = y + h // 2
                scroll_y = max(0, target_center_y - viewport_height // 2)

                # 水平滚动到可见区域即可
                viewport_width = self.scroll_area.viewport().width()
                container_width = self.pages_container.width()
                if container_width > viewport_width:
                    target_center_x = x + w // 2
                    scroll_x = max(0, min(target_center_x - viewport_width // 2, container_width - viewport_width))
                else:
                    scroll_x = 0

                # 设置滚动位置
                self.scroll_area.horizontalScrollBar().setValue(scroll_x)
                self.scroll_area.verticalScrollBar().setValue(scroll_y)
            else:
                # 滚动到该区域（带边距）
                margin = 50
                self.scroll_area.ensureVisible(x + margin, y + margin, margin, margin)
        else:
            # 无特定坐标，只滚动到页面
            if center and page_label:
                # 垂直居中显示整个页面
                viewport_height = self.scroll_area.viewport().height()
                label_pos = page_label.pos()
                page_height = page_label.height()
                scroll_y = max(0, label_pos.y() + page_height // 2 - viewport_height // 2)
                self.scroll_area.verticalScrollBar().setValue(scroll_y)
            else:
                self.scroll_area.ensureWidgetVisible(page_label, 50, 50)

        self.current_page = page_index

    def _on_thumbnail_clicked(self, item: QListWidgetItem):
        """缩略图点击事件"""
        page_index = item.data(Qt.UserRole)
        if page_index is not None and 0 <= page_index < self.total_pages:
            self._scroll_to_page(page_index)

    # ==================== 搜索功能 ====================

    def _show_search_widget(self):
        """显示搜索框并切换到搜索视图"""
        if self.search_widget is None:
            return

        self.search_widget.setVisible(True)
        self.search_input.setFocus()
        self.search_input.selectAll()

        # 切换到搜索结果侧边栏
        self._switch_sidebar_view(3)

    def _hide_search_widget(self):
        """隐藏搜索框并清除搜索高亮"""
        if self.search_widget is None or not self.search_widget.isVisible():
            return

        self.search_widget.setVisible(False)
        # 清除搜索结果高亮
        self._clear_text_selection()

    def _perform_search(self):
        """REQ-06/07: 执行搜索，遍历所有页面查找匹配文本"""
        query = self.search_input.text().strip()
        if not query or not self.doc:
            return

        self.search_results = []
        self.current_search_index = -1

        # 遍历所有页面
        for page_idx in range(self.total_pages):
            page = self.doc[page_idx]
            text_dict = page.get_text("rawdict")

            # 收集该页所有字符和行信息
            lines_info = []  # 存储每行的文本和字符范围
            chars = []
            char_idx = 0

            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    line_chars = []
                    line_text = ""
                    line_start_idx = char_idx

                    for span in line.get("spans", []):
                        for char_info in span.get("chars", []):
                            c = char_info.get("c", "")
                            chars.append(char_info)
                            line_chars.append(char_info)
                            line_text += c
                            char_idx += 1

                    if line_text:
                        lines_info.append({
                            "text": line_text,
                            "start_idx": line_start_idx,
                            "end_idx": char_idx - 1,
                            "chars": line_chars
                        })

            if not chars:
                continue

            # 构建页面文本
            page_text = "".join(c.get("c", "") for c in chars)

            # 查找所有匹配（不区分大小写）
            query_lower = query.lower()
            page_text_lower = page_text.lower()

            start = 0
            while True:
                idx = page_text_lower.find(query_lower, start)
                if idx == -1:
                    break

                # REQ-07: 获取上下文（前后各一行，共3行）
                context_lines = self._get_search_context(lines_info, idx, len(query), page_text)

                # 保存匹配信息
                # char_end 应该是包含的索引（因为 _draw_selection_highlight 使用 range(start_idx, end_idx + 1)）
                self.search_results.append({
                    "page_idx": page_idx,
                    "char_start": idx,
                    "char_end": idx + len(query) - 1,  # 改为包含边界
                    "context": context_lines,
                    "matched_text": page_text[idx:idx + len(query)]
                })

                start = idx + 1

        # 更新UI
        self._update_search_results_ui()

        # 如果有结果，自动跳转到第一个
        if self.search_results:
            self.current_search_index = 0
            self._navigate_to_search_result(0)

    def _get_search_context(self, lines_info, match_start, match_len, full_text):
        """REQ-07: 获取搜索匹配的上下文（前后各一行，共3行）"""
        match_end = match_start + match_len - 1
        query = full_text[match_start:match_start + match_len]

        # 找到匹配所在的行
        match_line_idx = -1
        for i, line_info in enumerate(lines_info):
            if line_info["start_idx"] <= match_start <= line_info["end_idx"]:
                match_line_idx = i
                break

        if match_line_idx == -1:
            # 未找到所在行，返回简单截断的上下文
            context_start = max(0, match_start - 30)
            context_end = min(len(full_text), match_start + match_len + 30)
            return full_text[context_start:context_end]

        # 获取前后各一行（共3行）
        context_parts = []
        start_line = max(0, match_line_idx - 1)
        end_line = min(len(lines_info) - 1, match_line_idx + 1)

        for i in range(start_line, end_line + 1):
            line_text = lines_info[i]["text"]

            # 如果是匹配所在行，高亮关键词
            if i == match_line_idx:
                # 计算关键词在行内的位置
                line_start = lines_info[i]["start_idx"]
                relative_start = match_start - line_start
                relative_end = min(relative_start + match_len, len(line_text))

                # 分割行文本，在中间插入高亮标记
                before = line_text[:relative_start]
                matched = line_text[relative_start:relative_end]
                after = line_text[relative_end:]

                # 使用 ► ◄ 标记高亮（Qt 列表项支持富文本）
                line_text = f"{before}►{matched}◄{after}"

            context_parts.append(line_text)

        # 合并多行，行之间用空格分隔
        result = " ".join(context_parts)

        # 如果太长，截断并添加省略号
        if len(result) > 100:
            result = result[:97] + "..."

        return result

    def _update_search_results_ui(self):
        """更新搜索结果侧边栏显示"""
        self.search_results_widget.clear()

        if not self.search_results:
            self.search_counter.setText("0/0")
            item = QListWidgetItem("(无搜索结果)")
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.search_results_widget.addItem(item)
            return

        total = len(self.search_results)
        self.search_counter.setText(f"{self.current_search_index + 1}/{total}")

        for i, result in enumerate(self.search_results):
            page_idx = result["page_idx"]
            context = result["context"]
            matched = result["matched_text"]

            # 格式化显示文本
            display_text = f"第 {page_idx + 1} 页: {context}"

            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, i)  # 存储索引
            item.setToolTip(f"匹配文本: {matched}")

            # 当前选中项高亮
            if i == self.current_search_index:
                item.setBackground(QColor(0, 120, 215, 60))

            self.search_results_widget.addItem(item)

    def _on_search_result_clicked(self, item):
        """点击搜索结果跳转到对应位置"""
        idx = item.data(Qt.UserRole)
        if idx is None:
            return

        self.current_search_index = idx
        self._navigate_to_search_result(idx)

    def _navigate_to_search_result(self, idx):
        """REQ-04: 导航到指定索引的搜索结果，保持当前缩放"""
        if not self.search_results or idx < 0 or idx >= len(self.search_results):
            return

        result = self.search_results[idx]
        page_idx = result["page_idx"]
        char_start = result["char_start"]
        char_end = result["char_end"]

        # 更新计数显示
        self.search_counter.setText(f"{idx + 1}/{len(self.search_results)}")

        # 确保页面已渲染（连续滚动模式需要）
        self._ensure_page_visible(page_idx)

        # 加载该页文本字符信息
        self._load_page_text_chars(page_idx)

        # 设置选择范围
        self.selection_start_char = char_start
        self.selection_end_char = char_end

        # 找到对应的 page_label
        if page_idx < len(self.page_labels):
            self.current_page_label = self.page_labels[page_idx]
            # 更新当前页码，确保覆盖层能正确获取
            self.current_page = page_idx
            self._update_text_selection()

            # REQ-04: 计算搜索结果的矩形区域用于精确定位
            rect = None
            if self.page_text_chars and char_start < len(self.page_text_chars):
                start_char = self.page_text_chars[char_start]
                bbox = start_char.get("bbox", [0, 0, 0, 0])
                rect = fitz.Rect(bbox)

            # REQ-04: 使用统一的跳转方法，保持当前缩放
            self._scroll_to_page(page_idx, rect=rect, keep_zoom=True)

            # 更新侧边栏高亮
            self._update_search_results_ui()

    def _ensure_page_visible(self, page_idx):
        """确保指定页面在视图中可见（用于连续滚动模式）"""
        if page_idx < 0 or page_idx >= self.total_pages:
            return

        # 如果页面标签列表为空或长度不够，需要渲染
        if not self.page_labels or len(self.page_labels) <= page_idx:
            self.current_page = page_idx
            self.render_page(0, self.zoom_factor)

    def _search_prev(self):
        """跳转到上一个搜索结果"""
        if not self.search_results:
            return

        self.current_search_index -= 1
        if self.current_search_index < 0:
            self.current_search_index = len(self.search_results) - 1

        self._navigate_to_search_result(self.current_search_index)

    def _search_next(self):
        """跳转到下一个搜索结果"""
        if not self.search_results:
            return

        self.current_search_index += 1
        if self.current_search_index >= len(self.search_results):
            self.current_search_index = 0

        self._navigate_to_search_result(self.current_search_index)

    def _search_find_next(self):
        """REQ-06: 搜索框 Enter 键 - 查找下一个匹配项

        - 如果没有搜索结果，执行新搜索
        - 如果有结果，跳转到下一个（循环）
        - 保持焦点在搜索框内
        """
        query = self.search_input.text().strip()
        if not query or not self.doc:
            return

        # 如果没有搜索结果或搜索词已改变，执行新搜索
        if not self.search_results:
            self._perform_search()
        else:
            # 有结果，跳到下一个（循环）
            self.current_search_index += 1
            if self.current_search_index >= len(self.search_results):
                self.current_search_index = 0

            self._navigate_to_search_result(self.current_search_index)

        # 保持焦点在搜索框内
        self.search_input.setFocus()

    def _on_search_text_changed(self, text):
        """搜索文本变化时自动搜索（可选：延迟搜索）"""
        if len(text) >= 1:  # 至少1个字符开始搜索
            self._perform_search()
        else:
            # 清空搜索结果
            self.search_results = []
            self.current_search_index = -1
            self._update_search_results_ui()
            self._clear_text_selection()

    # ==================== 程序退出清理 ====================

    def closeEvent(self, event):
        """窗口关闭事件 - 检查未保存的修改"""
        if self._document_modified:
            reply = QMessageBox.question(
                self,
                "未保存的更改",
                f"文件 \"{os.path.basename(self.file_path)}\" 有未保存的更改。\n是否保存？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )

            if reply == QMessageBox.Save:
                if self._save_document_safely():
                    self.statusBar().showMessage("已保存", 2000)
                else:
                    QMessageBox.critical(self, "错误", "保存失败")
                    event.ignore()
                    return
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return
            # Discard: 不保存直接关闭

        self._close_document()
        event.accept()


class AnnotationTooltip(QLabel):
    """
    轻量级注释浮窗组件
    - 设置 Qt.ToolTip | Qt.FramelessWindowHint 标志
    - 使用 QSS 渲染样式
    - UI 层独立于 PDF 渲染引擎
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


def main():
    """程序入口"""
    # 创建应用
    app = QApplication(sys.argv)
    app.setApplicationName("Unipdf")
    app.setApplicationVersion("1.0")

    # 创建主窗口
    viewer = PDFViewer()
    viewer.show()

    # 如果命令行参数中有 PDF 文件路径，直接打开
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        if os.path.exists(pdf_path) and pdf_path.lower().endswith('.pdf'):
            viewer.open_document(pdf_path)

    # 运行应用
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
