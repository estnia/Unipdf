# 离线安装依赖说明

## 概述

本项目需要以下依赖：
- **PyMuPDF==1.21.1** - PDF渲染引擎
- **PyQt5==5.15.9** - GUI框架

## 系统要求

- UOS V20 / Debian 10 或更高版本
- Python 3.7+
- 系统已安装 PyQt5 基础库

## 快速开始

### 在联网机器上下载依赖

```bash
# 方法1: 完整版（推荐）
bash download_offline_deps.sh

# 方法2: 仅下载 wheel 文件
bash download_wheels.sh
```

### 复制到离线机器

```bash
# 完整版
scp offline_deps/unipdf_deps_*.tar.gz user@offline-machine:/path/to/

# 仅 wheels
scp -r offline_wheels/ user@offline-machine:/path/to/unipdf/
```

### 在离线机器上安装

```bash
# 方法1: 完整版
tar -xzf unipdf_deps_*.tar.gz
cd unipdf_deps_*/
bash install_offline.sh

# 方法2: 仅 wheels
pip3 install --no-index --find-links=offline_wheels/ -r requirements.txt
```

## 系统依赖安装

在目标 UOS/Debian 机器上，需要预先安装以下系统包：

```bash
# 基础环境
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv

# PyQt5 系统库
sudo apt-get install -y python3-pyqt5

# 可选：X11 支持（如果使用图形界面）
sudo apt-get install -y libx11-6 libxcb1 libxext6
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `download_offline_deps.sh` | 完整离线包创建脚本 |
| `download_wheels.sh` | 简化版，仅下载 wheel 文件 |
| `offline_deps/` | 完整版输出目录 |
| `offline_wheels/` | 简化版输出目录 |

## 常见问题

### 1. PyQt5 安装失败

确保系统已安装 PyQt5：
```bash
sudo apt-get install python3-pyqt5
```

### 2. 版本不兼容

如需其他 Python 版本，修改脚本中的 `--python-version` 参数：
```bash
# 例如 Python 3.9
--python-version 39
```

### 3. 平台不匹配

如需其他平台，修改 `--platform` 参数：
```bash
# ARM64
--platform manylinux2014_aarch64
```

## 手动下载单个包

如需手动下载特定版本的包：

```bash
# PyMuPDF
pip download PyMuPDF==1.21.1 -d ./offline_wheels/

# PyQt5
pip download PyQt5==5.15.9 -d ./offline_wheels/
```
