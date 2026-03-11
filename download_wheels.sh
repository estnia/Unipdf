#!/bin/bash
# -*- coding: utf-8 -*-
# 简化版离线依赖下载脚本
# 仅下载 Python wheel 文件，不包含系统依赖

set -e

DEPS_DIR="offline_wheels"
mkdir -p "${DEPS_DIR}"

echo "========================================"
echo "  下载离线 Wheel 文件"
echo "========================================"
echo ""

# 升级 pip
pip3 install --upgrade pip wheel

# 下载依赖
echo "正在下载依赖..."
pip3 download -d "${DEPS_DIR}" -r requirements.txt

echo ""
echo "========================================"
echo "  下载完成！"
echo "========================================"
echo ""
echo "Wheel 文件位置: ${DEPS_DIR}/"
echo ""
ls -lh "${DEPS_DIR}/"
echo ""
echo "在离线机器上安装方法:"
echo "  pip install --no-index --find-links=${DEPS_DIR}/ -r requirements.txt"
