#!/bin/bash
# -*- coding: utf-8 -*-
# PDF Viewer 离线依赖下载脚本
# 用于在联网机器（UOS/Debian）上下载所有依赖，然后打包到离线环境安装

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Unipdf 离线依赖下载脚本${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 创建依赖目录
DEPS_DIR="offline_deps"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PACKAGE_NAME="unipdf_deps_${TIMESTAMP}"
mkdir -p "${DEPS_DIR}/${PACKAGE_NAME}"

echo -e "${YELLOW}[1/6] 检查 Python 环境...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 python3${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
echo "Python 版本: ${PYTHON_VERSION}"

# 检查 pip
echo -e "${YELLOW}[2/6] 检查并安装 pip...${NC}"
if ! command -v pip3 &> /dev/null; then
    echo "pip3 未安装，尝试安装..."
    sudo apt-get update
    sudo apt-get install -y python3-pip
fi
pip3 --version

# 升级 pip 工具
echo -e "${YELLOW}[3/6] 升级 pip 工具...${NC}"
pip3 install --upgrade pip setuptools wheel

# 下载 Python 依赖
echo -e "${YELLOW}[4/6] 下载 Python wheel 依赖包...${NC}"
pip3 download \
    --only-binary=:all: \
    --python-version 37 \
    --platform manylinux2014_x86_64 \
    --dest "${DEPS_DIR}/${PACKAGE_NAME}/python_wheels" \
    -r requirements.txt 2>/dev/null || {
    echo -e "${YELLOW}警告: 特定平台下载失败，尝试通用下载...${NC}"
    pip3 download \
        --dest "${DEPS_DIR}/${PACKAGE_NAME}/python_wheels" \
        -r requirements.txt
}

# 尝试为多个 Python 版本下载（兼容性考虑）
echo -e "${YELLOW}       尝试为 Python 3.9 下载（兼容性备选）...${NC}"
pip3 download \
    --only-binary=:all: \
    --python-version 39 \
    --platform manylinux2014_x86_64 \
    --dest "${DEPS_DIR}/${PACKAGE_NAME}/python_wheels_py39" \
    -r requirements.txt 2>/dev/null || echo -e "${YELLOW}       Python 3.9 wheel 下载失败（可忽略）${NC}"

# 统计下载的 wheel 文件
echo ""
echo -e "${GREEN}已下载的 Python 包:${NC}"
find "${DEPS_DIR}/${PACKAGE_NAME}" -name "*.whl" -exec basename {} \; | sort

# 获取系统依赖信息
echo ""
echo -e "${YELLOW}[5/6] 收集系统依赖信息...${NC}"

# 创建系统依赖列表
cat > "${DEPS_DIR}/${PACKAGE_NAME}/system_deps.txt" << 'EOF'
# UOS/Debian 系统依赖列表
# 在目标机器上运行以下命令安装:

# 基础 Python 环境
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv

# PyQt5 系统依赖
sudo apt-get install -y python3-pyqt5
sudo apt-get install -y libqt5gui5 libqt5widgets5 libqt5core5a

# PyMuPDF 系统依赖
sudo apt-get install -y libfreetype6 libharfbuzz0b libjpeg62-turbo
sudo apt-get install -y libopenjp2-7 libpng16-16 libtiff5

# X11 显示支持（如需要）
sudo apt-get install -y libx11-6 libxcb1 libxext6
EOF

echo -e "${GREEN}系统依赖列表已保存到: ${DEPS_DIR}/${PACKAGE_NAME}/system_deps.txt${NC}"

# 创建离线安装脚本
echo -e "${YELLOW}[6/6] 创建离线安装脚本...${NC}"

cat > "${DEPS_DIR}/${PACKAGE_NAME}/install_offline.sh" << 'EOF'
#!/bin/bash
# 离线安装脚本
# 在目标离线机器上运行此脚本

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Unipdf 离线安装${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 python3${NC}"
    echo "请先安装 Python 3: sudo apt-get install python3"
    exit 1
fi

echo -e "${YELLOW}[1/3] 安装系统依赖...${NC}"
if [ -f "system_deps.txt" ]; then
    echo "请手动运行 system_deps.txt 中的命令安装系统依赖"
    echo "或运行: sudo bash -c '\$(cat system_deps.txt | grep "^sudo")'"
fi

echo -e "${YELLOW}[2/3] 创建虚拟环境（推荐）...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}虚拟环境已创建${NC}"
fi
source venv/bin/activate

echo -e "${YELLOW}[3/3] 安装 Python 依赖...${NC}"
# 优先使用当前目录的 wheels
if [ -d "python_wheels" ]; then
    pip install --no-index --find-links=./python_wheels -r ../requirements.txt
elif [ -d "python_wheels_py39" ]; then
    pip install --no-index --find-links=./python_wheels_py39 -r ../requirements.txt
else
    echo -e "${RED}错误: 未找到 wheel 文件目录${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  安装完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "使用方法:"
echo "  source venv/bin/activate"
echo "  python3 main.py"
echo ""
EOF

chmod +x "${DEPS_DIR}/${PACKAGE_NAME}/install_offline.sh"

# 复制 requirements.txt
cp requirements.txt "${DEPS_DIR}/${PACKAGE_NAME}/"

# 打包
echo ""
echo -e "${YELLOW}打包依赖...${NC}"
cd "${DEPS_DIR}"
tar -czf "${PACKAGE_NAME}.tar.gz" "${PACKAGE_NAME}"
cd ..

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  离线依赖包创建完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "包位置: ${YELLOW}${DEPS_DIR}/${PACKAGE_NAME}.tar.gz${NC}"
echo ""
echo -e "包含内容:"
find "${DEPS_DIR}/${PACKAGE_NAME}" -type f | while read f; do
    size=$(du -h "$f" | cut -f1)
    echo "  - $(basename $f) (${size})"
done

echo ""
echo -e "${YELLOW}使用说明:${NC}"
echo "1. 将 ${PACKAGE_NAME}.tar.gz 复制到离线机器"
echo "2. 解压: tar -xzf ${PACKAGE_NAME}.tar.gz"
echo "3. 进入目录: cd ${PACKAGE_NAME}"
echo "4. 运行安装: bash install_offline.sh"
echo ""
echo -e "${GREEN}完成！${NC}"
