# Unipdf - 极速 PDF 查看器

适配 UOS V20 (Linux) 环境，功能丰富的 PDF 阅读器，支持文本选择、高亮注释、下划线注释、全文搜索、智能目录生成等功能。

## 特性亮点

- **极速渲染**: 异步渲染 + 多级缓存机制
- **精准选择**: 字符级文本选择精度
- **智能目录**: 基于字体和位置的目录自动生成
- **全文搜索**: 跨页面搜索 + 上下文显示
- **完整注释**: 高亮、下划线 + 悬停提示

## 技术栈

- **语言**: Python 3.7+
- **GUI 框架**: PyQt5
- **PDF 引擎**: PyMuPDF (兼容 `fitz` 和 `pymupdf` 导入方式)
- **操作系统**: Debian 10 / UOS V20 / 其他 Linux 发行版
- **虚拟显示**: Xvfb (无头环境测试)

## 功能特性

### 已实现功能

✅ **基础架构**
- 单页显示模式，使用 QScrollArea + QLabel
- 内存渲染，无临时文件
- 延迟渲染机制，优化性能

✅ **文件操作**
- 支持文件拖放打开
- 命令行参数打开文件
- 增量保存高亮注释

✅ **导航与浏览**
- 目录侧边栏（QTreeWidget），支持点击跳转
- 智能目录自动生成（基于标题检测算法）
- 页面缩略图视图（快速预览和跳转）
- 注释列表侧边栏（显示所有注释）
- 翻页: PageUp/PageDown
- 首页/末页: Home/End 键
- 侧边栏显示/隐藏: F9 键

✅ **搜索功能**
- Ctrl+F 打开搜索框
- 实时搜索（输入时自动搜索）
- 跨页面全文搜索
- 搜索结果高亮和导航（↑/↓按钮或 Enter 键）
- 搜索上下文显示（前后各一行）

✅ **缩放功能**
- Ctrl + 鼠标滚轮缩放
- Ctrl + +/- 缩放快捷键
- Ctrl + 0 重置缩放
- 缩放范围: 10% - 500%

✅ **文本选择与复制**
- 鼠标划选文本（字符级精度）
- QRubberBand 视觉反馈
- 自动复制到剪贴板

✅ **高亮与注释**
- 右键菜单添加高亮（支持多行）
- 下划线注释（带 Tooltip 悬停提示）
- 增量保存不损坏原文件
- 注释列表显示所有注释

✅ **其他功能**
- 文件拖放打开
- 命令行参数打开文件
- 导出当前页为图片

## 安装依赖

### 方案 1：有图形界面环境

```bash
# 安装系统依赖（Debian/UOS）
sudo apt-get update
sudo apt-get install -y python3-pyqt5 python3-pip

# 安装 Python 依赖
pip3 install -r requirements.txt
```

### 方案 2：无图形界面环境（使用 Xvfb 虚拟显示）

适用于服务器、CI/CD 环境或没有物理显示器的场景。

```bash
# 1. 安装系统依赖
sudo apt-get update
sudo apt-get install -y python3-pyqt5 python3-pymupdf xvfb

# 2. 使用 Xvfb 运行（已提供脚本）
./run_with_xvfb.sh /path/to/document.pdf

# 或手动启动 Xvfb
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &
export DISPLAY=:99
python3 main.py /path/to/document.pdf
```

#### Xvfb 方案文件说明

| 文件 | 说明 |
|------|------|
| `run_with_xvfb.sh` | 一键启动脚本，自动管理 Xvfb 生命周期 |
| `tests/2026-03-09/scripts/test_xvfb.py` | Xvfb 环境测试脚本，验证依赖和功能 |

#### 测试 Xvfb 环境

```bash
# 运行测试脚本验证环境
python3 tests/2026-03-09/scripts/test_xvfb.py
```

预期输出：
```
==================================================
Unipdf Xvfb 虚拟显示测试
==================================================
[*] 启动 Xvfb 虚拟显示 :99
[+] Xvfb 已启动 (PID: xxxxx)
[*] DISPLAY 设置为 :99

[*] 测试模块导入...
[+] PyQt5 导入成功
[+] PyMuPDF (fitz) 导入成功

[*] 测试基本功能...
[+] PDF 渲染成功
[+] QWidget 创建成功

==================================================
[+] 所有测试通过！Xvfb 方案工作正常
==================================================
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
| `Ctrl + W` | 关闭文件 |
| `Ctrl + S` | 保存注释 |
| `Ctrl + Q` | 退出程序 |
| `Ctrl + F` | 查找文本 |
| `Escape` | 隐藏搜索框 |
| `F9` | 显示/隐藏侧边栏 |
| `PageUp` | 上一页 |
| `PageDown` | 下一页 |
| `Home` | 跳到第一页 |
| `End` | 跳到最后一页 |
| `Ctrl + +` | 放大 |
| `Ctrl + -` | 缩小 |
| `Ctrl + 0` | 重置缩放 |
| `Ctrl + 滚轮` | 缩放页面 |

## 项目结构

```
Unipdf/
├── main.py              # 主程序入口
├── requirements.txt     # Python 依赖
├── README.md            # 项目说明
├── run_with_xvfb.sh     # Xvfb 一键启动脚本（方案2）
└── tests/               # 测试目录
    └── 2026-03-09/      # 测试日期
        ├── scripts/     # 测试脚本
        │   ├── test_xvfb.py        # Xvfb 环境测试
        │   ├── test_screenshot.py  # 截图测试
        │   ├── test_hover.py       # 悬停功能测试
        │   ├── test_report.py      # 测试报告生成
        │   └── convert_xwd.py      # XWD 图片转换
        ├── fixtures/    # 测试数据
        │   ├── test_document.pdf          # 基础测试 PDF
        │   └── test_underline_annot.pdf   # 下划线注释测试 PDF
        └── screenshots/ # 测试截图
            ├── screenshot_test.png
            ├── screenshot_preview.png
            └── hover_test_preview.png
```

## 注意事项

1. **高分辨率 PDF**: 程序使用缩放矩阵渲染（DPI + devicePixelRatio），确保高 DPI 文档也能清晰显示
2. **大文件处理**: 采用延迟渲染机制 + 异步渲染线程，避免频繁操作时的卡顿
3. **增量保存**: 高亮注释使用 `doc.save(path, incremental=True)`，不修改原文件其他内容
4. **字符级选择**: 文本选择支持字符级精度，通过预计算字符位置实现快速 hit-test
5. **智能目录**: 支持法律条文、国家标准等文档的目录自动识别
6. **PyMuPDF 兼容**: 代码兼容新旧版本 PyMuPDF（`import fitz` 和 `import pymupdf`）

## 开发计划

- [x] 搜索功能（全文搜索 + 上下文显示）
- [x] 智能目录自动生成
- [x] 页面缩略图视图
- [x] 注释列表侧边栏
- [x] 下划线注释 + Tooltip 提示
- [ ] 最近打开文件列表
- [ ] 全屏模式
- [ ] 连续滚动模式
- [ ] 夜间模式/护眼模式
