#!/bin/bash
# -*- coding: utf-8 -*-
#
# Unipdf Xvfb 启动脚本 - 方案2
# 使用虚拟显示运行 PyQt5 PDF 查看器
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Unipdf - Xvfb 虚拟显示启动脚本"
echo "=========================================="
echo ""

# 检查依赖
check_dependency() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}[!] 错误: $1 未安装${NC}"
        return 1
    fi
    echo -e "${GREEN}[+] $1 已安装${NC}"
    return 0
}

# 检查必要依赖
echo "[*] 检查依赖..."
DEPS_OK=true

if ! check_dependency "Xvfb"; then
    echo "    请安装: sudo apt-get install xvfb"
    DEPS_OK=false
fi

if ! check_dependency "python3"; then
    DEPS_OK=false
fi

if [ "$DEPS_OK" = false ]; then
    exit 1
fi

# 检查 Python 模块
echo ""
echo "[*] 检查 Python 模块..."

if ! python3 -c "import PyQt5" 2>/dev/null; then
    echo -e "${RED}[!] PyQt5 未安装${NC}"
    echo "    请安装: sudo apt-get install python3-pyqt5"
    exit 1
fi
echo -e "${GREEN}[+] PyQt5 已安装${NC}"

# 兼容新旧版本 PyMuPDF
if python3 -c "import fitz" 2>/dev/null || python3 -c "import pymupdf" 2>/dev/null; then
    echo -e "${GREEN}[+] PyMuPDF 已安装${NC}"
else
    echo -e "${YELLOW}[!] PyMuPDF 未安装${NC}"
    echo "    安装方法1: pip3 install PyMuPDF --break-system-packages"
    echo "    安装方法2: sudo apt-get install python3-pymupdf"
    exit 1
fi

# 查找可用的显示号
echo ""
echo "[*] 启动 Xvfb 虚拟显示..."

DISPLAY_NUM=99
while [ -f "/tmp/.X${DISPLAY_NUM}-lock" ]; do
    DISPLAY_NUM=$((DISPLAY_NUM + 1))
done

# 启动 Xvfb
Xvfb ":${DISPLAY_NUM}" \
    -screen 0 1920x1080x24 \
    -ac \
    +extension GLX \
    +render \
    -noreset \
    -nolisten tcp &

XVFB_PID=$!

# 等待 Xvfb 启动
sleep 1

# 检查 Xvfb 是否成功启动
if ! kill -0 $XVFB_PID 2>/dev/null; then
    echo -e "${RED}[!] Xvfb 启动失败${NC}"
    exit 1
fi

echo -e "${GREEN}[+] Xvfb 已启动 (显示号 :${DISPLAY_NUM}, PID: ${XVFB_PID})${NC}"

# 设置 DISPLAY 环境变量
export DISPLAY=":${DISPLAY_NUM}"

# 清理函数
cleanup() {
    echo ""
    echo "[*] 关闭 Xvfb..."
    if kill -0 $XVFB_PID 2>/dev/null; then
        kill $XVFB_PID 2>/dev/null || true
        wait $XVFB_PID 2>/dev/null || true
    fi
    echo -e "${GREEN}[+] Xvfb 已关闭${NC}"
}

# 设置退出时清理
trap cleanup EXIT INT TERM

# 运行主程序
echo ""
echo "[*] 启动 Unipdf..."
echo "    显示: ${DISPLAY}"
echo ""

python3 /home/feifei/Unipdf/main.py "$@"
