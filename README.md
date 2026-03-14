# Unipdf - 极速 PDF 查看器

适配 UOS V20 (Linux) 环境，功能丰富的 PDF 阅读器，支持文本选择、高亮注释、下划线注释、全文搜索、智能目录生成等功能。

## 特性亮点

- **极速渲染**: 异步渲染 + 多级缓存机制
- **精准选择**: 字符级文本选择精度
- **智能目录**: 基于字体和位置的目录自动生成
- **全文搜索**: 跨页面搜索 + 侧边栏结果展示
- **完整注释**: 高亮、下划线 + 悬停提示 + 右键删除
- **平滑缩放**: 视口中心锚点缩放，支持连续缩放
- **搜索历史**: 查找框支持上下键浏览历史记录
- **窗口记忆**: 自动保存和恢复窗口大小、位置
- **打印支持**: 完整打印功能，支持打印预览和页面范围选择
- **自动适应**: 支持整页适应和适应宽度模式（Ctrl+9 快速切换）

## 技术栈

- **语言**: Python 3.7+
- **GUI 框架**: PyQt5 5.15.9
- **PDF 引擎**: PyMuPDF 1.21.1 (兼容 `fitz` 和 `pymupdf` 导入方式)
- **操作系统**: Debian 10+ / UOS V20 / Ubuntu 20.04+
- **虚拟显示**: Xvfb (无头环境测试)

## 功能特性

### 已实现功能

✅ **基础架构**
- 模块化架构：core/, services/, ui/, workers/, utils/
- 单页显示模式，使用 QScrollArea + QLabel
- 内存渲染，无临时文件
- 延迟渲染机制，优化性能
- 异步渲染 Worker，避免界面卡顿

✅ **文件操作**
- 支持文件拖放打开
- 命令行参数打开文件
- 增量保存高亮注释
- 多标签页支持

✅ **导航与浏览**
- 目录侧边栏（QTreeWidget），支持点击跳转
- 智能目录自动生成（基于标题检测算法）
- 页面缩略图视图（快速预览和跳转）
- 注释列表侧边栏（显示所有注释，支持右键删除）
- 搜索结果侧边栏（深色主题，高亮匹配词）
- 翻页: PageUp/PageDown/↑/↓
- 首页/末页: Home/End 键
- 侧边栏显示/隐藏: F9 或 Ctrl+D 键
- 侧边栏显示/隐藏: F9 键

✅ **搜索功能**
- Ctrl+F 打开搜索框
- 实时搜索（输入时自动搜索，300ms防抖）
- 跨页面全文搜索
- 搜索结果高亮和导航（↑/↓按钮、Enter、F3）
- 搜索上下文显示（侧边栏展示，3行内容）
- **搜索历史**: 查找框内按上下键浏览历史关键字
- 匹配项计数显示 (N/M)

✅ **缩放功能**
- Ctrl + 鼠标滚轮缩放（视口中心锚点，平滑稳定）
- Ctrl + +/- 缩放快捷键
- Ctrl + 0 重置缩放
- 缩放范围: 10% - 500%
- 缩放时搜索结果覆盖层自动更新位置

✅ **文本选择与复制**
- 鼠标划选文本（字符级精度）
- QRubberBand 视觉反馈
- 自动复制到剪贴板
- 多行选择支持

✅ **高亮与注释**
- 右键菜单添加高亮（支持多行）
- 下划线注释（带 Tooltip 悬停提示）
- 注释删除（右键菜单）
- 增量保存不损坏原文件
- 注释列表显示所有注释
- 缩放后注释位置正确保持

✅ **视图功能**
- 窗口大小和位置自动记忆（重启后恢复）
- 适应宽度模式 / 整页适应模式（Ctrl+9 循环切换）
- 打开时自动适应（可开关）
- 侧边栏宽度自适应

## 安装

### 方案 1: Debian/Ubuntu 一键安装（推荐）

```bash
# 下载 release 页面的 .deb 包
wget https://github.com/estnia/Unipdf/releases/download/v1.1.0/unipdf_1.1.0_amd64.deb

# 一键安装依赖
sudo dpkg -i unipdf_1.1.0_amd64.deb

# 如有依赖问题，自动修复
sudo apt-get install -f

# 克隆代码运行
git clone https://github.com/estnia/Unipdf.git
cd Unipdf
python3 main.py
```

### 方案 2: pip 安装（需要网络）

```bash
# 安装系统依赖（Debian/UOS）
sudo apt-get update
sudo apt-get install -y python3-pyqt5 python3-pip

# 安装 Python 依赖
pip3 install pymupdf==1.21.1 pyqt5==5.15.9

# 运行
python3 main.py
```

### 方案 3: 无图形界面环境（Xvfb）

适用于服务器、CI/CD 环境或没有物理显示器的场景。

```bash
# 1. 安装系统依赖
sudo apt-get update
sudo apt-get install -y python3-pyqt5 python3-pymupdf xvfb

# 2. 使用 Xvfb 运行
xvfb-run -a python3 main.py /path/to/document.pdf
```

## 运行程序

```bash
# 直接运行
python3 main.py

# 打开指定 PDF 文件
python3 main.py /path/to/document.pdf
```

## 快捷键列表

| 快捷键 | 功能 |
|--------|------|
| `Ctrl + O` | 打开文件 |
| `Ctrl + W` | 关闭当前标签页 |
| `Ctrl + S` | 保存注释 |
| `Ctrl + Q` / `Alt + F4` | 退出程序 |
| `Ctrl + F` | 查找文本 |
| `F3` | 查找下一个 |
| `Shift + F3` | 查找上一个 |
| `Escape` | 隐藏搜索框 |
| `Ctrl + D` | 显示/隐藏侧边栏 |
| `Ctrl + 9` | 循环切换适应模式（整页/宽度）|
| `Ctrl + P` | 打印 |
| `PageUp` / `↑` | 上一页 |
| `PageDown` / `↓` | 下一页 |
| `Home` | 跳到第一页 |
| `End` | 跳到最后一页 |
| `Ctrl + +` | 放大 |
| `Ctrl + -` | 缩小 |
| `Ctrl + 0` | 重置缩放 |
| `Ctrl + 滚轮` | 缩放页面 |

**搜索框内快捷键：**
- `↑` / `↓` - 浏览搜索历史
- `Enter` - 查找下一个
- `Escape` - 关闭搜索框

## 项目结构

```
Unipdf/
├── main.py                    # 主程序入口
├── main_original.py           # 原始单文件版本（参考）
├── requirements.txt           # Python 依赖
├── README.md                  # 项目说明
├── CLAUDE.md                  # 开发规范
├── wheels/                    # 预编译 wheel 文件
│   ├── PyMuPDF-*.whl
│   ├── PyQt5-*.whl
│   └── PyQt5_sip-*.whl
├── pdfviewer/                 # 主包目录
│   ├── core/                  # 核心模块
│   │   ├── document.py        # PDF 文档管理
│   │   ├── renderer.py        # 渲染引擎
│   │   └── text_engine.py     # 文本处理
│   ├── services/              # 服务层
│   │   ├── annotation_service.py
│   │   ├── print_service.py   # 打印服务
│   │   ├── render_service.py
│   │   ├── search_service.py
│   │   └── thumbnail_service.py
│   ├── ui/                    # UI 层
│   │   ├── main_window.py     # 主窗口
│   │   ├── viewer_widget.py   # PDF 查看器组件
│   │   └── annotation_tooltip.py
│   ├── utils/                 # 工具模块
│   │   ├── geometry.py        # 坐标转换
│   │   └── patterns.py        # 正则模式
│   └── workers/               # 异步工作器
│       ├── render_worker.py
│       └── toc_worker.py
├── demo/                      # 示例 PDF 文件
├── docs/                      # 文档
└── test/                      # 测试
```

## 注意事项

1. **高分辨率 PDF**: 程序使用缩放矩阵渲染（DPI + devicePixelRatio），确保高 DPI 文档也能清晰显示
2. **大文件处理**: 采用延迟渲染机制 + 异步渲染线程，避免频繁操作时的卡顿
3. **增量保存**: 高亮注释使用 `doc.save(path, incremental=True)`，不修改原文件其他内容
4. **字符级选择**: 文本选择支持字符级精度，通过预计算字符位置实现快速 hit-test
5. **智能目录**: 支持法律条文、国家标准等文档的目录自动识别
6. **PyMuPDF 兼容**: 代码兼容新旧版本 PyMuPDF（`import fitz` 和 `import pymupdf`）
7. **缩放稳定性**: 缩放时使用视口中心作为锚点，配合防抖定时器，确保连续缩放时渲染正确
8. **DPI 自适应**: 正确处理高 DPI 显示器的缩放比例，确保适应宽度/整页适应模式精确填充视口
9. **窗口记忆**: 使用 QSettings 持久化窗口几何信息，跨会话保持用户布局偏好

## 开发计划

- [x] 搜索功能（全文搜索 + 侧边栏结果展示）
- [x] 智能目录自动生成
- [x] 页面缩略图视图
- [x] 注释列表侧边栏（支持删除）
- [x] 下划线注释 + Tooltip 提示
- [x] 视口中心锚点缩放
- [x] 模块化架构重构
- [x] 离线安装包（.deb）
- [x] 搜索历史功能
- [x] 窗口大小位置记忆
- [x] 打印支持
- [ ] 最近打开文件列表
- [ ] 全屏模式
- [ ] 连续滚动模式
- [ ] 夜间模式/护眼模式
- [ ] PDF 导出/转换

## 许可证

MIT License

## 作者

estnia

---

**版本**: v1.1.0
**更新日期**: 2026-03-14
