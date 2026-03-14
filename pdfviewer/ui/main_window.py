#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main Window - Complete PDF Viewer main window.

This is the full implementation migrated from main_original.py,
using the new modular architecture.
"""

import sys
import os
import html
from pathlib import Path

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QFileDialog, QMessageBox,
    QApplication, QLabel, QScrollArea, QTreeWidget,
    QTreeWidgetItem, QListWidget, QListWidgetItem,
    QLineEdit, QPushButton, QToolButton, QFrame,
    QStackedWidget, QSizePolicy, QShortcut, QMenu,
    QProgressDialog, QInputDialog, QActionGroup
)
from PyQt5.QtCore import Qt, QSize, QPoint, QTimer, pyqtSignal, QSettings
from PyQt5.QtGui import (
    QDragEnterEvent, QDropEvent, QKeySequence,
    QCursor, QIcon
)

# PDF engine
try:
    import fitz
except ImportError:
    import pymupdf as fitz

# Import from new modules
from pdfviewer.core.document import PDFDocument
from pdfviewer.services.render_service import RenderService
from pdfviewer.services.annotation_service import AnnotationService
from pdfviewer.services.search_service import SearchService
from pdfviewer.services.thumbnail_service import ThumbnailService
from pdfviewer.services.print_service import PrintService
from pdfviewer.workers.toc_worker import AutoTocWorker
from pdfviewer.ui.annotation_tooltip import AnnotationTooltip


class MainWindow(QMainWindow):
    """主窗口类 - PDF 查看器核心功能"""

    def __init__(self):
        super().__init__()

        # 基础配置
        self.setWindowTitle("Unipdf - 极简 PDF 查看器")
        self.setGeometry(100, 100, 1200, 800)

        # 多标签页支持
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)

        # 当前活动文档引用
        self.current_doc = None

        # 侧边栏相关
        self._sidebar_visible = False
        self._sidebar_width = 250

        # 搜索功能相关
        self.search_results = []
        self.current_search_index = -1
        self.search_widget = None
        self.search_input = None
        self.search_counter = None
        self._search_history = []  # 查找历史缓存
        self._search_history_index = -1  # 当前历史索引
        self._restoring_history = False  # 标记是否正在从历史恢复

        # 缓存和渲染
        self._l2_cache = {}
        self._base_pixmaps = {}
        self._active_workers = {}
        self._zoom_timer = QTimer()
        self._zoom_timer.setSingleShot(True)
        self._target_zoom = 1.0

        # Auto-fit configuration
        self._auto_fit_on_open = True  # 打开时自动适应
        self._auto_fit_mode = "fit_page"  # 默认适应模式: fit_page, fit_width

        # 初始化界面
        self._init_ui()

        # 启用拖放
        self.setAcceptDrops(True)

        # 剪贴板
        self.clipboard = QApplication.clipboard()

        # Page label update timer (debounce) - must be before _add_welcome_tab
        self._page_label_timer = QTimer()
        self._page_label_timer.setSingleShot(True)
        self._page_label_timer.timeout.connect(self._update_page_label)

        # 显示欢迎页
        self._add_welcome_tab()

        # 注释提示
        self._annot_tooltip = None
        self._tooltip_timer = QTimer()
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_annot_tooltip)
        self._current_hover_annot = None

        # TOC worker
        self._toc_worker = None

        # Print service
        self._print_service = PrintService(self)

        # 恢复窗口几何信息
        self._restore_window_geometry()

    def _init_ui(self):
        """初始化用户界面 - 左右分割布局"""
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 分割器
        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter, 1)

        # 左侧: 侧边栏容器
        self.sidebar_container = QWidget()
        self.sidebar_container.setMaximumWidth(300)
        self.sidebar_container.setMinimumWidth(200)
        sidebar_layout = QVBoxLayout(self.sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # 侧边栏工具栏
        self._init_sidebar_toolbar(sidebar_layout)

        # 侧边栏内容区域
        self.sidebar_stack = QStackedWidget()
        sidebar_layout.addWidget(self.sidebar_stack)

        # 1. 目录视图
        self.toc_widget = QTreeWidget()
        self.toc_widget.setHeaderLabel("目录")
        self.toc_widget.itemClicked.connect(self._on_toc_clicked)
        self.sidebar_stack.addWidget(self.toc_widget)

        # 2. 注释视图
        self.annot_widget = QListWidget()
        self.annot_widget.itemClicked.connect(self._on_annot_clicked)
        self.annot_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.annot_widget.customContextMenuRequested.connect(self._show_annot_context_menu)
        self.sidebar_stack.addWidget(self.annot_widget)

        # 3. 缩略图视图
        self.thumbnail_widget = QListWidget()
        self.thumbnail_widget.setViewMode(QListWidget.IconMode)
        self.thumbnail_widget.setIconSize(QSize(120, 160))
        self.thumbnail_widget.setResizeMode(QListWidget.Adjust)
        self.thumbnail_widget.setSpacing(10)
        self.thumbnail_widget.itemClicked.connect(self._on_thumbnail_clicked)
        self.sidebar_stack.addWidget(self.thumbnail_widget)

        # 4. 搜索结果视图
        self.search_results_widget = QListWidget()
        # 使用 currentRowChanged 替代 itemClicked，因为自定义 widget 会拦截点击事件
        self.search_results_widget.currentRowChanged.connect(self._on_search_result_row_changed)
        # 设置项间距为半行（约10像素）
        self.search_results_widget.setSpacing(5)
        # 设置样式：未选中项白字深色背景，选中项蓝底白字
        self.search_results_widget.setStyleSheet("""
            QListWidget {
                background-color: #2d2d2d;
                border: none;
            }
            QListWidget::item {
                background-color: #3d3d3d;
                color: #fff;
                border-bottom: 1px solid #555;
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
                color: #fff;
            }
        """)
        self.sidebar_stack.addWidget(self.search_results_widget)

        self.splitter.addWidget(self.sidebar_container)

        # 右侧: 标签页区域
        self.splitter.addWidget(self.tab_widget)
        self.splitter.setSizes([250, 950])

        # 菜单栏
        self._init_menu_bar()

        # 搜索框（初始隐藏）
        self._init_search_widget(main_layout)

        # 快捷键
        self._init_shortcuts()

        # 侧边栏初始隐藏
        self.sidebar_container.setVisible(False)
        self._sidebar_visible = False

        # 初始化状态栏页码显示
        self._page_label = QLabel("第 0 页 / 共 0 页")
        self._page_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._page_label.setMinimumWidth(150)
        self.statusBar().addPermanentWidget(self._page_label)

    def _init_sidebar_toolbar(self, sidebar_layout):
        """初始化侧边栏工具栏"""
        toolbar = QFrame()
        toolbar.setFrameShape(QFrame.StyledPanel)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(5, 5, 5, 5)
        toolbar_layout.setSpacing(5)

        # 目录按钮
        btn_toc = QToolButton()
        btn_toc.setText("目录")
        btn_toc.setCheckable(True)
        btn_toc.setChecked(True)
        btn_toc.clicked.connect(lambda: self._switch_sidebar_view(0))
        toolbar_layout.addWidget(btn_toc)
        self._btn_toc = btn_toc

        # 注释按钮
        btn_annot = QToolButton()
        btn_annot.setText("注释")
        btn_annot.setCheckable(True)
        btn_annot.clicked.connect(lambda: self._switch_sidebar_view(1))
        toolbar_layout.addWidget(btn_annot)
        self._btn_annot = btn_annot

        # 缩略图按钮
        btn_thumb = QToolButton()
        btn_thumb.setText("缩略图")
        btn_thumb.setCheckable(True)
        btn_thumb.clicked.connect(lambda: self._switch_sidebar_view(2))
        toolbar_layout.addWidget(btn_thumb)
        self._btn_thumb = btn_thumb

        # 搜索按钮
        btn_search = QToolButton()
        btn_search.setText("搜索")
        btn_search.setCheckable(True)
        btn_search.clicked.connect(lambda: self._switch_sidebar_view(3))
        toolbar_layout.addWidget(btn_search)
        self._btn_search = btn_search

        toolbar_layout.addStretch()
        sidebar_layout.addWidget(toolbar)

    def _switch_sidebar_view(self, index: int):
        """切换侧边栏视图"""
        self.sidebar_stack.setCurrentIndex(index)

        # 更新按钮状态
        self._btn_toc.setChecked(index == 0)
        self._btn_annot.setChecked(index == 1)
        self._btn_thumb.setChecked(index == 2)
        self._btn_search.setChecked(index == 3)

        # 显示侧边栏
        if not self._sidebar_visible:
            self.sidebar_container.setVisible(True)
            self._sidebar_visible = True
            # 侧边栏显示后，延迟重新应用适应模式
            QTimer.singleShot(100, self._reapply_auto_fit_if_needed)

    def _toggle_sidebar_with_toc(self):
        """切换侧边栏显示/隐藏（显示目录）"""
        if self._sidebar_visible:
            # 直接关闭侧边栏
            self.sidebar_container.setVisible(False)
            self._sidebar_visible = False
            # 侧边栏关闭后，延迟重新应用适应模式
            QTimer.singleShot(100, self._reapply_auto_fit_if_needed)
        else:
            self._switch_sidebar_view(0)

    def _reapply_auto_fit_if_needed(self):
        """如果当前是适应宽度模式，重新应用以适应新的视口大小"""
        if self.current_doc and hasattr(self.current_doc, 'auto_fit_to_window'):
            if self._auto_fit_mode in ("fit_width", "fit_page"):
                self.current_doc.auto_fit_to_window(self._auto_fit_mode)

    def _init_search_widget(self, main_layout):
        """初始化搜索框"""
        self.search_widget = QWidget()
        self.search_widget.setVisible(False)
        search_layout = QHBoxLayout(self.search_widget)
        search_layout.setContentsMargins(10, 5, 10, 5)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("查找文本...")
        self.search_input.setMinimumWidth(200)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._search_find_next)
        # 安装事件过滤器处理上键
        self.search_input.installEventFilter(self)

        # Debounce timer for real-time search
        self.search_timer = None

        self.search_counter = QLabel("0/0")
        self.search_counter.setMinimumWidth(50)

        btn_prev = QPushButton("↑")
        btn_prev.setToolTip("上一个匹配")
        btn_prev.setMaximumWidth(30)
        btn_prev.clicked.connect(self._search_prev)

        btn_next = QPushButton("↓")
        btn_next.setToolTip("下一个匹配")
        btn_next.setMaximumWidth(30)
        btn_next.clicked.connect(self._search_next)

        btn_close = QPushButton("×")
        btn_close.setToolTip("关闭搜索")
        btn_close.setMaximumWidth(30)
        btn_close.clicked.connect(self._hide_search_widget)

        search_layout.addWidget(QLabel("查找:"))
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_counter)
        search_layout.addWidget(btn_prev)
        search_layout.addWidget(btn_next)
        search_layout.addWidget(btn_close)
        search_layout.addStretch()

        main_layout.addWidget(self.search_widget)

    def _init_menu_bar(self):
        """初始化菜单栏"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")

        open_action = file_menu.addAction("打开(&O)...")
        open_action.setShortcut("Ctrl+O")
        open_action.setShortcutContext(Qt.ApplicationShortcut)
        open_action.triggered.connect(self.open_document)

        file_menu.addSeparator()

        save_action = file_menu.addAction("保存(&S)")
        save_action.setShortcut("Ctrl+S")
        save_action.setShortcutContext(Qt.ApplicationShortcut)
        save_action.triggered.connect(self.save_document)

        close_action = file_menu.addAction("关闭(&C)")
        close_action.setShortcut("Ctrl+W")
        close_action.setShortcutContext(Qt.ApplicationShortcut)
        close_action.triggered.connect(self.close_current_tab)

        file_menu.addSeparator()

        print_action = file_menu.addAction("打印(&P)...")
        print_action.setShortcut("Ctrl+P")
        print_action.setShortcutContext(Qt.ApplicationShortcut)
        print_action.triggered.connect(self.print_document)

        file_menu.addSeparator()

        exit_action = file_menu.addAction("退出(&X)")
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setShortcutContext(Qt.ApplicationShortcut)
        exit_action.triggered.connect(self.close)

        # 视图菜单
        view_menu = menubar.addMenu("视图(&V)")

        sidebar_action = view_menu.addAction("侧边栏(&S)")
        sidebar_action.setShortcut("Ctrl+D")
        sidebar_action.setShortcutContext(Qt.ApplicationShortcut)
        sidebar_action.triggered.connect(self._toggle_sidebar_with_toc)

        view_menu.addSeparator()

        zoom_in_action = view_menu.addAction("放大(&I)")
        zoom_in_action.setShortcut("Ctrl++")
        zoom_in_action.setShortcutContext(Qt.ApplicationShortcut)
        zoom_in_action.triggered.connect(self.zoom_in)

        zoom_out_action = view_menu.addAction("缩小(&O)")
        zoom_out_action.setShortcut("Ctrl+-")
        zoom_out_action.setShortcutContext(Qt.ApplicationShortcut)
        zoom_out_action.triggered.connect(self.zoom_out)

        zoom_reset_action = view_menu.addAction("重置缩放(&R)")
        zoom_reset_action.setShortcut("Ctrl+0")
        zoom_reset_action.setShortcutContext(Qt.ApplicationShortcut)
        zoom_reset_action.triggered.connect(self.zoom_reset)

        view_menu.addSeparator()

        # 自动适应菜单
        self._auto_fit_action = view_menu.addAction("打开时自动适应")
        self._auto_fit_action.setCheckable(True)
        self._auto_fit_action.setChecked(self._auto_fit_on_open)
        self._auto_fit_action.triggered.connect(self._toggle_auto_fit_on_open)

        # 适应模式子菜单
        fit_mode_menu = view_menu.addMenu("适应模式")

        # 使用 QActionGroup 管理互斥选项
        self._fit_mode_group = QActionGroup(self)
        self._fit_mode_group.setExclusive(True)

        self._fit_page_action = fit_mode_menu.addAction("整页适应")
        self._fit_page_action.setCheckable(True)
        self._fit_page_action.setChecked(self._auto_fit_mode == "fit_page")
        self._fit_mode_group.addAction(self._fit_page_action)
        self._fit_page_action.triggered.connect(lambda: self._set_and_apply_auto_fit_mode("fit_page"))

        self._fit_width_action = fit_mode_menu.addAction("适应宽度")
        self._fit_width_action.setCheckable(True)
        self._fit_width_action.setChecked(self._auto_fit_mode == "fit_width")
        self._fit_mode_group.addAction(self._fit_width_action)
        self._fit_width_action.triggered.connect(lambda: self._set_and_apply_auto_fit_mode("fit_width"))

        view_menu.addSeparator()

        # 循环切换适应模式 (Ctrl+9)
        cycle_fit_action = view_menu.addAction("循环切换适应模式(&C)")
        cycle_fit_action.setShortcut("Ctrl+9")
        cycle_fit_action.setShortcutContext(Qt.ApplicationShortcut)
        cycle_fit_action.triggered.connect(self._cycle_auto_fit_mode)

        # 工具菜单
        tools_menu = menubar.addMenu("工具(&T)")

        find_action = tools_menu.addAction("查找(&F)...")
        find_action.setShortcut("Ctrl+F")
        find_action.setShortcutContext(Qt.ApplicationShortcut)
        find_action.triggered.connect(self._show_search_widget)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")

        about_action = help_menu.addAction("关于(&A)...")
        about_action.triggered.connect(self._show_about_dialog)

    def _show_about_dialog(self):
        """显示关于对话框"""
        from pdfviewer import __version__

        QMessageBox.about(
            self,
            "关于 Unipdf",
            f"""<h2>Unipdf</h2>
<p><b>版本:</b> {__version__}</p>
<p><b>描述:</b> 极简极速 PDF 查看器</p>
<p>基于 PyQt5 和 PyMuPDF 构建</p>
<p>采用模块化架构重构版本</p>
<hr>
<p>© 2024 Unipdf Team</p>"""
        )

    def _init_shortcuts(self):
        """初始化额外的快捷键（不与菜单重复的）"""
        # Escape 键关闭搜索框（菜单中没有的快捷键）
        self.shortcut_esc = QShortcut(QKeySequence("Escape"), self)
        self.shortcut_esc.activated.connect(self._hide_search_widget)

        # F3 查找下一个
        self.shortcut_find_next = QShortcut(QKeySequence("F3"), self)
        self.shortcut_find_next.activated.connect(self._search_next)

        # Shift+F3 查找上一个
        self.shortcut_find_prev = QShortcut(QKeySequence("Shift+F3"), self)
        self.shortcut_find_prev.activated.connect(self._search_prev)

    def eventFilter(self, obj, event):
        """事件过滤器：处理查找输入框的上键事件（栈模式，不循环）"""
        if obj == self.search_input and event.type() == event.KeyPress:
            if event.key() == Qt.Key_Up:
                # 上键：显示上一个查找关键字（向栈底移动）
                if self._search_history and self._search_history_index > 0:
                    self._search_history_index -= 1
                    self._restoring_history = True
                    self.search_input.setText(self._search_history[self._search_history_index])
                    self._restoring_history = False
                    self.search_input.selectAll()
                # 已到最旧或没有历史，不循环，停在原地
                return True
            elif event.key() == Qt.Key_Down:
                # 下键：显示下一个查找关键字（向栈顶移动）
                if self._search_history and self._search_history_index < len(self._search_history) - 1:
                    self._search_history_index += 1
                    self._restoring_history = True
                    self.search_input.setText(self._search_history[self._search_history_index])
                    self._restoring_history = False
                    self.search_input.selectAll()
                # 已到最新或没有历史，不循环，停在原地
                return True
        return super().eventFilter(obj, event)

    def _save_window_geometry(self):
        """保存窗口几何信息到 QSettings."""
        from PyQt5.QtCore import QSettings
        settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "Unipdf", "Unipdf")
        geometry = self.saveGeometry()
        state = self.saveState()

        print(f"[DEBUG] 保存前 - geometry bytes: {len(geometry) if geometry else 0}")
        print(f"[DEBUG] 保存前 - state bytes: {len(state) if state else 0}")

        settings.setValue("window/geometry", geometry)
        settings.setValue("window/state", state)
        settings.sync()  # 强制立即写入磁盘

        # 验证是否保存成功
        test_geo = settings.value("window/geometry")
        print(f"[DEBUG] 验证 - geometry 已保存: {test_geo is not None}")
        print(f"[DEBUG] 窗口配置已保存到: {settings.fileName()}")

    def _restore_window_geometry(self):
        """从 QSettings 恢复窗口几何信息."""
        from PyQt5.QtCore import QSettings
        settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "Unipdf", "Unipdf")
        geometry = settings.value("window/geometry")
        state = settings.value("window/state")

        print(f"[DEBUG] 尝试从 {settings.fileName()} 恢复窗口配置")
        print(f"[DEBUG] geometry: {geometry is not None}, state: {state is not None}")

        # 处理不同类型（PyQt5 可能返回 QByteArray 或 str）
        if geometry is not None:
            if isinstance(geometry, str):
                geometry = geometry.encode('utf-8')
            self.restoreGeometry(geometry)
            print("[DEBUG] 已恢复窗口几何")

        if state is not None:
            if isinstance(state, str):
                state = state.encode('utf-8')
            self.restoreState(state)
            print("[DEBUG] 已恢复窗口状态")

        # 如果没有保存的几何信息，使用默认大小
        if geometry is None:
            print("[DEBUG] 未找到保存的配置，使用默认值")
            self.resize(1200, 800)
            self.move(100, 100)

    def _add_welcome_tab(self):
        """添加欢迎页标签"""
        welcome = QWidget()
        layout = QVBoxLayout(welcome)
        layout.setAlignment(Qt.AlignCenter)

        label = QLabel("<h1>Unipdf</h1><p>极简、极速的 PDF 查看器</p>"
                      "<p>拖拽 PDF 文件到窗口或按 Ctrl+O 打开文件</p>")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        self.tab_widget.addTab(welcome, "欢迎")
        self.current_doc = None

    # ==================== 文档操作 ====================

    def open_document(self, file_path: str = None):
        """打开 PDF 文档"""
        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "打开 PDF 文件",
                "",
                "PDF 文件 (*.pdf);;所有文件 (*.*)"
            )

        if not file_path or not os.path.exists(file_path):
            return False

        try:
            # 移除欢迎页
            if self.tab_widget.count() == 1 and self.current_doc is None:
                widget = self.tab_widget.widget(0)
                if isinstance(widget, QWidget) and not hasattr(widget, '_doc'):
                    self.tab_widget.removeTab(0)

            # 创建新标签页
            doc_widget = self._create_document_tab(file_path)
            if not doc_widget:
                return False

            filename = os.path.basename(file_path)
            idx = self.tab_widget.addTab(doc_widget, filename)
            self.tab_widget.setTabToolTip(idx, file_path)
            self.tab_widget.setCurrentIndex(idx)

            # current_doc 已在 _create_document_tab 中设置
            # _on_tab_changed 会被 setCurrentIndex 触发，无需重复设置

            # 生成目录
            self._generate_toc(file_path)

            self._update_sidebar_for_current_tab()

            return True

        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开文件失败:\n{str(e)}")
            return False

    def _create_document_tab(self, file_path: str):
        """创建文档标签页"""
        try:
            # 创建 PDFDocument
            from pdfviewer.core.document import PDFDocument
            doc = PDFDocument(file_path)
            if not doc.is_open():
                return None

            # 创建 ViewerWidget
            from pdfviewer.ui.viewer_widget import ViewerWidget
            viewer = ViewerWidget()
            viewer.set_document(doc)

            # 连接信号
            viewer.text_selected.connect(self._on_text_selected)
            viewer.annotation_added.connect(self._on_annotation_added)
            viewer.zoom_changed.connect(self._on_zoom_changed)
            viewer.document_loaded.connect(self._update_page_label)

            # 应用自动适应（延迟执行，等待布局完成）
            if self._auto_fit_on_open:
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(200, lambda v=viewer: self._apply_auto_fit_to_viewer(v))

            # 连接滚动信号以更新页码（使用防抖）
            viewer.scroll_area.verticalScrollBar().valueChanged.connect(
                lambda value: self._page_label_timer.start(150)
            )

            # 保存引用
            viewer.doc = doc
            viewer.file_path = file_path

            # 先设置 current_doc
            self.current_doc = viewer

            return viewer

        except Exception as e:
            print(f"创建文档标签页失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _update_page_label(self):
        """更新状态栏页码显示"""
        if self._page_label is None:
            return

        viewer = self.current_doc

        if viewer and hasattr(viewer, 'get_current_page') and hasattr(viewer, 'get_page_count'):
            current_page = viewer.get_current_page()
            total_pages = viewer.get_page_count()
            self._page_label.setText(f"第 {current_page + 1} 页 / 共 {total_pages} 页")
        else:
            self._page_label.setText("第 0 页 / 共 0 页")

    def _on_text_selected(self, text: str):
        """处理文本选择/复制"""
        self.statusBar().showMessage(text, 2000)

    def _on_annotation_added(self):
        """处理注释添加/更新"""
        # 更新侧边栏注释列表
        self._update_sidebar_for_current_tab()

    def _on_zoom_changed(self, zoom_factor: float):
        """处理缩放变化"""
        self.statusBar().showMessage(f"缩放: {int(zoom_factor * 100)}%", 2000)
        # 延迟更新页码（等待缩放动画完成）
        self._page_label_timer.start(300)
        # 延迟重新计算搜索结果位置，等待页面渲染完成
        if self.search_results:
            from PyQt5.QtCore import QTimer
            # 使用更长的延迟确保页面完全渲染（包括异步渲染）
            QTimer.singleShot(300, self._display_search_results_on_pages)

    def _generate_toc(self, file_path: str):
        """生成自动目录"""
        if self._toc_worker and self._toc_worker.isRunning():
            self._toc_worker.stop()

        self._toc_worker = AutoTocWorker(file_path)
        self._toc_worker.finished.connect(self._on_toc_finished)
        self._toc_worker.start()

    def _on_toc_finished(self, toc_list):
        """目录生成完成"""
        self.toc_widget.clear()

        if not toc_list:
            item = QTreeWidgetItem(self.toc_widget)
            item.setText(0, "(无目录)")
            item.setData(0, Qt.UserRole, -1)
            return

        stack = []
        for level, title, page_num in toc_list:
            page_index = page_num - 1
            item = QTreeWidgetItem()
            item.setText(0, title)
            item.setToolTip(0, title)
            item.setData(0, Qt.UserRole, page_index)

            if level == 1:
                self.toc_widget.addTopLevelItem(item)
                stack = [item]
            else:
                while len(stack) >= level:
                    stack.pop()
                if stack:
                    stack[-1].addChild(item)
                else:
                    self.toc_widget.addTopLevelItem(item)
                stack.append(item)

        self.toc_widget.expandAll()

    def save_document(self):
        """保存当前文档"""
        if not self.current_doc or not hasattr(self.current_doc, '_doc'):
            return False

        try:
            doc = self.current_doc._doc
            file_path = self.current_doc.file_path

            if doc.save():
                self.statusBar().showMessage("文档已保存", 3000)
                return True
            else:
                QMessageBox.critical(self, "错误", "保存失败")
                return False
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败:\n{str(e)}")
            return False

    def print_document(self):
        """打印当前文档"""
        if not self.current_doc or not hasattr(self.current_doc, '_doc'):
            QMessageBox.information(self, "提示", "请先打开一个PDF文档")
            return False

        try:
            # Get the fitz document
            doc = self.current_doc._doc.doc
            if not doc:
                QMessageBox.critical(self, "错误", "无法访问文档")
                return False

            # Get current page index
            current_page = 0
            if hasattr(self.current_doc, 'get_current_page'):
                current_page = self.current_doc.get_current_page()

            # Use print service to print the document
            from pdfviewer.services.print_service import PrintRange
            success = self._print_service.print_document(
                doc,
                page_range=PrintRange.ALL_PAGES,
                current_page=current_page,
                show_dialog=True
            )

            if success:
                self.statusBar().showMessage("打印任务已发送", 3000)
            return success

        except Exception as e:
            QMessageBox.critical(self, "错误", f"打印失败:\n{str(e)}")
            return False

    def close_current_tab(self, idx: int = None):
        """关闭当前或指定标签页"""
        if idx is None:
            idx = self.tab_widget.currentIndex()

        if idx < 0 or idx >= self.tab_widget.count():
            return

        widget = self.tab_widget.widget(idx)

        # Check if document has unsaved changes
        if hasattr(widget, '_doc') and widget._doc and widget._doc.is_modified:
            filename = os.path.basename(widget.file_path) if hasattr(widget, 'file_path') else "未命名"
            reply = QMessageBox.question(
                self,
                "未保存的更改",
                f"文件 '{filename}' 有未保存的更改，是否保存？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )

            if reply == QMessageBox.Save:
                if not self.save_document():
                    return  # Save failed, don't close
            elif reply == QMessageBox.Cancel:
                return  # User cancelled, don't close
            # If Discard, continue to close without saving

        # 关闭文档
        if hasattr(widget, '_doc') and widget._doc:
            widget._doc.close()

        self.tab_widget.removeTab(idx)

        if self.tab_widget.count() == 0:
            self._add_welcome_tab()
            self.current_doc = None

    # ==================== 标签页管理 ====================

    def _on_tab_changed(self, index: int):
        """切换标签页"""
        if index < 0:
            return

        widget = self.tab_widget.widget(index)
        if hasattr(widget, '_doc') and widget._doc:
            self.current_doc = widget
            self._update_sidebar_for_current_tab()
            self._update_window_title()
            self._page_label_timer.start(0)  # 立即更新页码
        else:
            self.current_doc = None
            self.toc_widget.clear()
            self.annot_widget.clear()
            self.thumbnail_widget.clear()
            self.setWindowTitle("Unipdf - 极简 PDF 查看器")
            self._page_label_timer.start(0)

    def _on_tab_close_requested(self, index: int):
        """关闭标签页请求"""
        self.close_current_tab(index)

    def _update_sidebar_for_current_tab(self):
        """根据当前标签页更新侧边栏"""
        if not self.current_doc or not hasattr(self.current_doc, '_doc'):
            return

        doc = self.current_doc._doc.doc
        if not doc:
            return

        # 更新注释列表
        self.annot_widget.clear()
        annots = self._get_annotations_from_doc(doc)

        for annot in annots:
            if annot["type_num"] in (8, 9):
                content = annot["content"]
                page = annot["page"]
                annot_type = annot["type"]
                if content:
                    text = f"第{page+1}页 [{annot_type}] {content[:40]}"
                    if len(content) > 40:
                        text += "..."
                else:
                    text = f"第{page+1}页 [{annot_type}] (无内容)"
                item = QListWidgetItem(text)
                # Store complete annotation data for precise deletion
                item.setData(Qt.UserRole, {
                    "page": page,
                    "type_num": annot["type_num"],
                    "rect": annot["rect"]
                })
                self.annot_widget.addItem(item)

        if self.annot_widget.count() == 0:
            item = QListWidgetItem("(文档中无注释)")
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.annot_widget.addItem(item)

        # 更新缩略图
        self._load_thumbnails()

        # 清除搜索结果
        self.search_results = []
        self.current_search_index = -1
        self.search_results_widget.clear()

    def _get_annotations_from_doc(self, doc) -> list:
        """从文档获取注释列表"""
        annots = []
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_annots = list(page.annots())

            for annot in page_annots:
                annot_type_raw = annot.type
                if isinstance(annot_type_raw, tuple):
                    annot_type = annot_type_raw[1] if len(annot_type_raw) > 1 else "未知"
                    type_num = annot_type_raw[0]
                else:
                    type_map = {8: "高亮", 9: "下划线"}
                    annot_type = type_map.get(annot_type_raw, f"类型{annot_type_raw}")
                    type_num = annot_type_raw

                info = annot.info
                content = info.get("content", "") if info else ""

                annots.append({
                    "page": page_idx,
                    "type": annot_type,
                    "type_num": type_num,
                    "content": content,
                    "rect": annot.rect
                })

        return annots

    def _update_window_title(self):
        """更新窗口标题"""
        if self.current_doc and hasattr(self.current_doc, 'file_path'):
            filename = os.path.basename(self.current_doc.file_path)
            if self.current_doc._doc and self.current_doc._doc.is_modified:
                self.setWindowTitle(f"Unipdf - {filename} *")
            else:
                self.setWindowTitle(f"Unipdf - {filename}")
        else:
            self.setWindowTitle("Unipdf - 极简 PDF 查看器")

    # ==================== 侧边栏操作 ====================

    def _on_toc_clicked(self, item: QTreeWidgetItem):
        """目录点击"""
        page_idx = item.data(0, Qt.UserRole)
        if page_idx >= 0 and self.current_doc:
            self.current_doc.scroll_to_page(page_idx)

    def _on_annot_clicked(self, item: QListWidgetItem):
        """注释点击"""
        annot_data = item.data(Qt.UserRole)
        if not annot_data:
            return
        page_idx = annot_data.get("page")
        if page_idx is not None and page_idx >= 0 and self.current_doc:
            self.current_doc.scroll_to_page(page_idx)

    def _show_annot_context_menu(self, pos):
        """显示注释上下文菜单"""
        item = self.annot_widget.itemAt(pos)
        if not item:
            return

        annot_data = item.data(Qt.UserRole)
        if not annot_data:
            return

        page_idx = annot_data.get("page")
        annot_type = annot_data.get("type_num")
        annot_rect = annot_data.get("rect")

        if page_idx is None or annot_type is None:
            return

        menu = QMenu(self)
        delete_action = menu.addAction("删除注释")
        jump_action = menu.addAction("跳转到注释")

        action = menu.exec_(self.annot_widget.mapToGlobal(pos))
        if action == delete_action:
            self._delete_annotation_by_rect(page_idx, annot_type, annot_rect)
        elif action == jump_action:
            self.current_doc.scroll_to_page(page_idx)

    def _delete_annotation_by_rect(self, page_idx: int, annot_type: int, annot_rect):
        """删除指定页面的指定类型注释，使用 rect 精确匹配"""
        if not self.current_doc or not hasattr(self.current_doc, '_doc'):
            return

        try:
            doc = self.current_doc._doc.doc
            if not doc or page_idx >= len(doc):
                return

            page = doc[page_idx]

            # Find and delete the matching annotation using rect
            deleted = False
            for annot in page.annots():
                atype = annot.type
                if isinstance(atype, tuple):
                    type_num = atype[0]
                else:
                    type_num = atype

                if type_num == annot_type:
                    # Match by rect coordinates (with small tolerance)
                    rect = annot.rect
                    if (abs(rect.x0 - annot_rect.x0) < 0.01 and
                        abs(rect.y0 - annot_rect.y0) < 0.01 and
                        abs(rect.x1 - annot_rect.x1) < 0.01 and
                        abs(rect.y1 - annot_rect.y1) < 0.01):
                        page.delete_annot(annot)
                        deleted = True
                        break

            if deleted:
                self.current_doc._doc.mark_modified(True)

                # Reload the page to reflect annotation deletion
                self.current_doc._reload_page(page_idx)

                # Update sidebar
                self._update_sidebar_for_current_tab()

        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除注释失败:\n{str(e)}")

    def _load_thumbnails(self):
        """加载缩略图"""
        self.thumbnail_widget.clear()

        if not self.current_doc or not hasattr(self.current_doc, '_doc'):
            return

        doc = self.current_doc._doc.doc
        if not doc:
            return

        thumb_zoom = 0.15

        for i in range(len(doc)):
            try:
                page = doc[i]
                mat = fitz.Matrix(thumb_zoom, thumb_zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)

                from PyQt5.QtGui import QImage, QPixmap
                img = QImage(
                    pix.samples, pix.width, pix.height, pix.stride,
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

    def _on_thumbnail_clicked(self, item: QListWidgetItem):
        """缩略图点击"""
        page_index = item.data(Qt.UserRole)
        if self.current_doc and page_index is not None:
            self.current_doc.scroll_to_page(page_index)

    # ==================== 搜索功能 ====================

    def _show_search_widget(self):
        """显示搜索框"""
        self.search_widget.setVisible(True)
        self.search_input.setFocus()
        self.search_input.selectAll()
        self._switch_sidebar_view(3)

    def _hide_search_widget(self):
        """隐藏搜索框"""
        self.search_widget.setVisible(False)
        # Clear search display on pages
        if self.current_doc and hasattr(self.current_doc, 'clear_search_display'):
            self.current_doc.clear_search_display()
        # 切换侧边栏回到目录视图
        self._switch_sidebar_view(0)
        # 清除搜索输入框
        self.search_input.clear()
        # 清空搜索结果列表
        self.search_results = []
        self.current_search_index = -1

    def _perform_search(self):
        """执行搜索"""
        query = self.search_input.text().strip()

        # 清除旧结果
        self._clear_search_results()

        if not query or not self.current_doc or not hasattr(self.current_doc, '_doc'):
            return

        # 添加到历史（如果不同于最后一个）
        if not self._search_history or self._search_history[-1] != query:
            self._search_history.append(query)
        self._search_history_index = len(self._search_history)  # 设置索引到末尾之后

        self.search_results = []
        self.current_search_index = -1

        doc = self.current_doc._doc.doc
        if not doc:
            return

        # Store search result rectangles per page
        self._search_result_rects = {}  # page_idx -> list of (x, y, w, h)

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            # Use search_for to get rectangles of matches
            rects = page.search_for(query)
            if rects:
                # Store rectangles for display
                page_rects = []
                for rect in rects:
                    page_rects.append((rect.x0, rect.y0, rect.width, rect.height))
                self._search_result_rects[page_idx] = page_rects

                # Process each match with correct context
                for match_idx, rect in enumerate(rects):
                    # Get context text for this specific match
                    try:
                        # Get text at this rect
                        matched_text = page.get_textbox(rect)

                        # Get a larger area around the match for context
                        # Expand the rect by ~50 points in each direction
                        context_rect = fitz.Rect(
                            max(0, rect.x0 - 50),
                            max(0, rect.y0 - 50),
                            rect.x1 + 50,
                            rect.y1 + 50
                        )
                        context_text = page.get_textbox(context_rect)

                        # Clean up context
                        context = context_text.strip()
                        if len(context) > 100:
                            # Find the match position in context and center it
                            match_pos = context.lower().find(matched_text.lower())
                            if match_pos >= 0:
                                start = max(0, match_pos - 30)
                                end = min(len(context), match_pos + len(matched_text) + 30)
                                context = context[start:end]
                    except:
                        context = query

                    self.search_results.append({
                        "page_idx": page_idx,
                        "rect": rect,
                        "context": context,
                        "matched_text": matched_text if 'matched_text' in dir() else query,
                        "match_idx": match_idx  # Track which match this is on the page
                    })

        self._update_search_results_ui()

        # Display search results on pages
        self._display_search_results_on_pages()

        if self.search_results:
            self.current_search_index = 0
            self._navigate_to_search_result(0)

    def _clear_search_results(self):
        """清除搜索结果"""
        self.search_results = []
        self.current_search_index = -1
        self._search_result_rects = {}
        self.search_counter.setText("0/0")
        self.search_results_widget.clear()
        item = QListWidgetItem("(无搜索结果)")
        item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
        self.search_results_widget.addItem(item)

        # Clear display on pages
        if self.current_doc and hasattr(self.current_doc, 'clear_search_display'):
            self.current_doc.clear_search_display()

    def _display_search_results_on_pages(self):
        """在页面上显示搜索结果高亮"""
        if not hasattr(self.current_doc, 'display_search_results'):
            return

        # Build a flat list of all result rects in order, matching self.search_results
        self._search_result_rects_flat = []  # List of (page_idx, rect_idx_in_page, rect)

        # Convert rects to screen coordinates
        page_results = {}

        # Process in the same order as self.search_results
        for result_idx, result in enumerate(self.search_results):
            page_idx = result["page_idx"]
            rect = result["rect"]

            # Convert PDF coordinates to screen coordinates
            from pdfviewer.utils.geometry import pdf_to_screen_rect
            page_label = self.current_doc._page_labels[page_idx] if page_idx < len(self.current_doc._page_labels) else None
            if page_label:
                screen_rect = pdf_to_screen_rect(
                    [rect.x0, rect.y0, rect.x1, rect.y1],
                    page_label,
                    self.current_doc._doc.zoom_factor
                )

                # Add to page_results
                if page_idx not in page_results:
                    page_results[page_idx] = []
                page_results[page_idx].append((screen_rect.x(), screen_rect.y(), screen_rect.width(), screen_rect.height()))

                # Find rect_idx_in_page for this result
                rect_idx_in_page = len(page_results[page_idx]) - 1
                self._search_result_rects_flat.append((page_idx, rect_idx_in_page, (rect.x0, rect.y0, rect.width, rect.height)))

        self.current_doc.display_search_results(page_results)

    def _update_search_results_ui(self):
        """更新搜索结果 UI"""
        self.search_results_widget.clear()

        if not self.search_results:
            self.search_counter.setText("0/0")
            item = QListWidgetItem("(无搜索结果)")
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.search_results_widget.addItem(item)
            return

        total = len(self.search_results)
        self.search_counter.setText(f"{self.current_search_index + 1}/{total}")

        # Get current search query for highlighting
        query = self.search_input.text().strip()

        for i, result in enumerate(self.search_results):
            page_num = result['page_idx'] + 1
            match_idx = result.get('match_idx', 0) + 1
            # 增加上下文长度以显示3行（约200字符）
            context = result['context'][:200]

            # Highlight the search query in context
            if query:
                highlighted_text = self._highlight_text(context, query, page_num, match_idx)
            else:
                highlighted_text = html.escape(context)

            # Create list item
            item = QListWidgetItem()
            item.setData(Qt.UserRole, i)

            # 设置项高度以容纳3行文字（约60像素）
            item.setSizeHint(QSize(self.search_results_widget.width() - 20, 60))

            # Create custom widget with QLabel for HTML rendering
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(5, 4, 5, 4)
            layout.setSpacing(5)

            # Label for page number and match index (plain text)
            header_label = QLabel(f"第{page_num}页-{match_idx}: ")
            header_label.setStyleSheet("color: #fff; font-weight: bold;")
            header_label.setAlignment(Qt.AlignTop)
            layout.addWidget(header_label)

            # Label for context with HTML highlighting
            context_label = QLabel()
            context_label.setTextFormat(Qt.RichText)
            context_label.setText(highlighted_text)
            context_label.setStyleSheet("color: #fff;")
            context_label.setWordWrap(True)  # 自动换行
            layout.addWidget(context_label, 1)  # Stretch factor

            self.search_results_widget.addItem(item)
            self.search_results_widget.setItemWidget(item, widget)

            # Store tooltip
            if query and query.lower() in context.lower():
                item.setToolTip(f"匹配: '{query}'\n上下文: {context}")

    def _highlight_text(self, text: str, query: str, page_num: int, match_idx: int) -> str:
        """Highlight search query in text using HTML formatting."""
        if not query or not text:
            return html.escape(text)

        # Escape HTML special characters
        escaped_text = html.escape(text)

        # Find the query position (case insensitive)
        lower_text = text.lower()
        lower_query = query.lower()
        pos = lower_text.find(lower_query)

        if pos < 0:
            return escaped_text

        # Build highlighted text with HTML
        before = escaped_text[:pos]
        match = escaped_text[pos:pos + len(query)]
        after = escaped_text[pos + len(query):]

        # Truncate if too long
        if len(before) > 30:
            before = "..." + before[-30:]
        if len(after) > 30:
            after = after[:30] + "..."

        # Orange background with high contrast, wrap in white color span for dark background
        highlighted = f'<span style="color: #fff;">{before}<span style="background-color: #FF8C00; color: #fff; padding: 1px 3px; border-radius: 2px; font-weight: bold;">{match}</span>{after}</span>'

        return highlighted

    def _on_search_result_row_changed(self, row: int):
        """搜索结果行改变时触发"""
        if row < 0 or row >= self.search_results_widget.count():
            return
        item = self.search_results_widget.item(row)
        if item:
            idx = item.data(Qt.UserRole)
            if idx is not None:
                self._navigate_to_search_result(idx)

    def _on_search_result_clicked(self, item: QListWidgetItem):
        """搜索结果点击（保留作为备用）"""
        idx = item.data(Qt.UserRole)
        if idx is not None:
            self._navigate_to_search_result(idx)

    def _navigate_to_search_result(self, idx: int):
        """导航到搜索结果"""
        if not self.search_results or idx < 0 or idx >= len(self.search_results):
            return

        self.current_search_index = idx
        result = self.search_results[idx]

        self.search_counter.setText(f"{idx + 1}/{len(self.search_results)}")

        # 同步选中侧边栏中的对应项
        self.search_results_widget.setCurrentRow(idx)

        # 滚动到页面并居中显示搜索结果
        if self.current_doc:
            page_idx = result["page_idx"]
            rect = result.get("rect")

            # Update current highlight on page
            self._update_search_highlight(idx)

            # Scroll to result with centering
            if rect:
                from pdfviewer.utils.geometry import pdf_to_screen_rect
                if page_idx < len(self.current_doc._page_labels):
                    page_label = self.current_doc._page_labels[page_idx]
                    screen_rect = pdf_to_screen_rect(
                        [rect.x0, rect.y0, rect.x1, rect.y1],
                        page_label,
                        self.current_doc._doc.zoom_factor
                    )
                    # Convert to absolute position in scroll area
                    # page_label.pos() gives position in pages_container
                    abs_x = screen_rect.x() + page_label.pos().x()
                    abs_y = screen_rect.y() + page_label.pos().y()
                    self.current_doc.scroll_to_search_result(page_idx, (
                        abs_x, abs_y,
                        screen_rect.width(), screen_rect.height()
                    ))
            else:
                self.current_doc.scroll_to_page(page_idx)

    def _update_search_highlight(self, current_idx: int):
        """更新页面上搜索结果的当前高亮"""
        if not hasattr(self.current_doc, '_overlays'):
            return

        # Clear all current search highlights first
        for overlay in self.current_doc._overlays:
            overlay.set_current_search_idx(-1)

        # Get the flat list of search results
        flat_results = getattr(self, '_search_result_rects_flat', [])
        if not flat_results or current_idx < 0 or current_idx >= len(flat_results):
            return

        # Get the current result info
        page_idx, rect_idx_in_page, _ = flat_results[current_idx]

        # Update the overlay for this page
        if page_idx < len(self.current_doc._overlays):
            overlay = self.current_doc._overlays[page_idx]
            overlay.set_current_search_idx(rect_idx_in_page)

    def _search_prev(self):
        """上一个搜索结果"""
        if not self.search_results:
            return
        idx = self.current_search_index - 1
        if idx < 0:
            idx = len(self.search_results) - 1
        self._navigate_to_search_result(idx)

    def _search_next(self):
        """下一个搜索结果"""
        if not self.search_results:
            return
        idx = self.current_search_index + 1
        if idx >= len(self.search_results):
            idx = 0
        self._navigate_to_search_result(idx)

    def _search_find_next(self):
        """查找下一个（Enter 键）"""
        # 如果已有搜索结果，跳到下一个；否则执行搜索
        if self.search_results:
            self._search_next()
        else:
            self._perform_search()

    def _on_search_text_changed(self, text: str):
        """搜索文本改变时触发实时搜索"""
        # 如果正在从历史恢复，不触发搜索
        if self._restoring_history:
            return

        # 清除之前的定时器
        if self.search_timer:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, lambda: None)  # Just to check if we can use QTimer

        # 使用单次定时器实现防抖（300ms延迟）
        from PyQt5.QtCore import QTimer
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._perform_search)
        self.search_timer.start(300)

    # ==================== 缩放功能 ====================

    def zoom_in(self):
        """放大"""
        if self.current_doc and hasattr(self.current_doc, '_doc'):
            self.current_doc._doc.zoom_factor *= 1.2
            self.current_doc.set_document(self.current_doc._doc)
            self.statusBar().showMessage(f"缩放: {int(self.current_doc._doc.zoom_factor * 100)}%", 2000)

    def zoom_out(self):
        """缩小"""
        if self.current_doc and hasattr(self.current_doc, '_doc'):
            self.current_doc._doc.zoom_factor /= 1.2
            self.current_doc.set_document(self.current_doc._doc)
            self.statusBar().showMessage(f"缩放: {int(self.current_doc._doc.zoom_factor * 100)}%", 2000)

    def zoom_reset(self):
        """重置缩放"""
        if self.current_doc and hasattr(self.current_doc, '_doc'):
            # 获取当前页
            current_page = self.current_doc.get_current_page()
            self.current_doc._doc.zoom_factor = 1.0
            self.current_doc.set_document(self.current_doc._doc)
            self.statusBar().showMessage("缩放: 100%", 2000)
            # 重置后跳转回当前页（延迟执行，等待布局完成）
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(150, lambda: self.current_doc.scroll_to_page(current_page))

    def _toggle_auto_fit_on_open(self, checked: bool):
        """Toggle auto-fit on open setting."""
        self._auto_fit_on_open = checked

    def _set_auto_fit_mode(self, mode: str):
        """Set auto-fit mode.

        Args:
            mode: "fit_page", "fit_width", or "fit_height"
        """
        self._auto_fit_mode = mode
        # Update menu check states
        self._fit_page_action.setChecked(mode == "fit_page")
        self._fit_width_action.setChecked(mode == "fit_width")

    def _set_and_apply_auto_fit_mode(self, mode: str):
        """Set auto-fit mode and apply to current document immediately.

        Args:
            mode: "fit_page" or "fit_width"
        """
        self._set_auto_fit_mode(mode)

        # Apply immediately to current document
        if self.current_doc and hasattr(self.current_doc, 'auto_fit_to_window'):
            self.current_doc.auto_fit_to_window(mode)
            mode_names = {
                "fit_page": "整页适应",
                "fit_width": "适应宽度"
            }
            mode_name = mode_names.get(mode, "整页适应")
            zoom_percent = int(self.current_doc._doc.zoom_factor * 100)
            self.statusBar().showMessage(f"已应用 {mode_name}: {zoom_percent}%", 2000)

    def _cycle_auto_fit_mode(self):
        """Cycle through fit modes: fit_page -> fit_width -> fit_page."""
        # Define cycle order
        modes = ["fit_page", "fit_width"]
        # Get current index and move to next
        try:
            current_idx = modes.index(self._auto_fit_mode)
        except ValueError:
            current_idx = 0
        next_idx = (current_idx + 1) % len(modes)
        next_mode = modes[next_idx]
        # Apply the next mode
        self._set_and_apply_auto_fit_mode(next_mode)

    def auto_fit_now(self):
        """Apply auto-fit to current document immediately."""
        if self.current_doc and hasattr(self.current_doc, 'auto_fit_to_window'):
            self.current_doc.auto_fit_to_window(self._auto_fit_mode)
            mode_names = {
                "fit_page": "整页适应",
                "fit_width": "适应宽度"
            }
            mode_name = mode_names.get(self._auto_fit_mode, "整页适应")
            zoom_percent = int(self.current_doc._doc.zoom_factor * 100)
            self.statusBar().showMessage(f"已应用 {mode_name}: {zoom_percent}%", 2000)

    def _apply_auto_fit_to_viewer(self, viewer):
        """Apply auto-fit to a specific viewer (used when opening documents)."""
        if viewer and hasattr(viewer, 'auto_fit_to_window'):
            viewer.auto_fit_to_window(self._auto_fit_mode)

    # ==================== 事件处理 ====================

    def dragEnterEvent(self, event: QDragEnterEvent):
        """拖拽进入"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                if url.toLocalFile().lower().endswith('.pdf'):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        """放置文件"""
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith('.pdf'):
                self.open_document(file_path)

    def _show_annot_tooltip(self):
        """显示注释提示"""
        pass

    def closeEvent(self, event):
        """关闭窗口"""
        # Check for unsaved documents
        unsaved_tabs = []
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if hasattr(widget, '_doc') and widget._doc and widget._doc.is_modified:
                filename = os.path.basename(widget.file_path) if hasattr(widget, 'file_path') else f"未命名{i+1}"
                unsaved_tabs.append((i, filename, widget))

        if unsaved_tabs:
            # Show dialog for unsaved documents
            if len(unsaved_tabs) == 1:
                # Single unsaved document
                idx, filename, widget = unsaved_tabs[0]
                reply = QMessageBox.question(
                    self,
                    "未保存的更改",
                    f"文件 '{filename}' 有未保存的更改，是否保存？",
                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                    QMessageBox.Save
                )

                if reply == QMessageBox.Save:
                    self.tab_widget.setCurrentIndex(idx)
                    self.current_doc = widget
                    if not self.save_document():
                        event.ignore()  # Save failed, don't close
                        return
                elif reply == QMessageBox.Cancel:
                    event.ignore()  # User cancelled, don't close
                    return
                # If Discard, continue to close without saving
            else:
                # Multiple unsaved documents
                filenames = "\n".join([f"  - {name}" for _, name, _ in unsaved_tabs])
                reply = QMessageBox.question(
                    self,
                    "未保存的更改",
                    f"以下文件有未保存的更改：\n{filenames}\n\n是否全部保存？",
                    QMessageBox.SaveAll | QMessageBox.Discard | QMessageBox.Cancel,
                    QMessageBox.SaveAll
                )

                if reply == QMessageBox.SaveAll:
                    for idx, _, widget in unsaved_tabs:
                        self.tab_widget.setCurrentIndex(idx)
                        self.current_doc = widget
                        if not self.save_document():
                            event.ignore()  # Save failed, don't close
                            return
                elif reply == QMessageBox.Cancel:
                    event.ignore()  # User cancelled, don't close
                    return
                # If Discard, continue to close without saving

        # 关闭所有文档
        while self.tab_widget.count() > 0:
            widget = self.tab_widget.widget(0)
            if hasattr(widget, '_doc') and widget._doc:
                widget._doc.close()
            self.tab_widget.removeTab(0)

        if self._toc_worker and self._toc_worker.isRunning():
            self._toc_worker.stop()

        # 保存窗口几何信息
        self._save_window_geometry()

        event.accept()
