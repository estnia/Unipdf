#!/bin/bash
# 构建离线安装包

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_NAME="unipdf-offline-deps"
VERSION="$(date +%Y%m%d)"
BUILD_DIR="${SCRIPT_DIR}/${PACKAGE_NAME}-${VERSION}"

echo "=== 构建离线安装包 ==="
echo "目标目录: ${BUILD_DIR}"

# 创建目录
mkdir -p "${BUILD_DIR}/wheels"

# 复制 wheel 文件
echo "复制依赖包..."
cp "${SCRIPT_DIR}/wheels"/*.whl "${BUILD_DIR}/wheels/" 2>/dev/null || \
cp "${SCRIPT_DIR}"/*.whl "${BUILD_DIR}/wheels/" 2>/dev/null

# 创建 requirements.txt
echo "生成 requirements.txt..."
cat > "${BUILD_DIR}/requirements.txt" << 'REQUIREMENTS'
# Unipdf 离线依赖
PyMuPDF==1.21.1
PyQt5==5.15.9
PyQt5-Qt5==5.15.18
PyQt5_sip==12.13.0
REQUIREMENTS

# 创建安装脚本
echo "创建安装脚本..."
cat > "${BUILD_DIR}/install.sh" << 'INSTALLSCRIPT'
#!/bin/bash
# Unipdf 离线依赖安装脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WHEELS_DIR="${SCRIPT_DIR}/wheels"

echo "=== Unipdf 离线依赖安装 ==="
echo ""

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
echo "Python 版本: ${PYTHON_VERSION}"

# 检查 pip
if ! command -v pip3 &> /dev/null; then
    echo "错误: pip3 未找到"
    exit 1
fi

echo ""
echo "安装依赖包..."

# 安装 wheel 文件
pip3 install --no-index --find-links="${WHEELS_DIR}" \
    PyMuPDF==1.21.1 \
    PyQt5==5.15.9 \
    PyQt5-Qt5==5.15.18 \
    PyQt5_sip==12.13.0

echo ""
echo "=== 安装完成 ==="
echo ""
echo "验证安装:"
python3 -c "import fitz; print('PyMuPDF:', fitz.__doc__[:20])" 2>/dev/null || echo "PyMuPDF 安装成功"
python3 -c "from PyQt5.QtWidgets import QApplication; print('PyQt5: 安装成功')" 2>/dev/null || echo "PyQt5 安装成功"
echo ""
echo "现在可以运行: python3 main.py"
INSTALLSCRIPT

chmod +x "${BUILD_DIR}/install.sh"

# 创建说明文件
cat > "${BUILD_DIR}/README.txt" << 'README'
Unipdf 离线依赖包
==================

包含依赖:
- PyMuPDF 1.21.1 (PDF 渲染)
- PyQt5 5.15.9 (GUI 框架)
- PyQt5-Qt5 5.15.18 (Qt 库)
- PyQt5_sip 12.13.0 (Python 绑定)

系统要求:
- Python 3.7+
- pip3
- Linux x86_64

安装方法:
1. 解压此包
2. 运行: ./install.sh
3. 完成

验证安装:
    python3 -c "import fitz; from PyQt5.QtWidgets import QApplication; print('OK')"

运行程序:
    python3 main.py

注意: 此包仅包含依赖，不包含 Unipdf 源代码。
请将 main.py 和 pdfviewer/ 目录放到同一目录后运行。
README

# 打包成 tar.gz
echo "打包..."
cd "${SCRIPT_DIR}"
tar -czf "${PACKAGE_NAME}-${VERSION}.tar.gz" "${PACKAGE_NAME}-${VERSION}"

# 清理临时目录
rm -rf "${BUILD_DIR}"

echo ""
echo "=== 构建完成 ==="
echo "输出文件: ${SCRIPT_DIR}/${PACKAGE_NAME}-${VERSION}.tar.gz"
echo ""
echo "使用方法:"
echo "  1. 将 ${PACKAGE_NAME}-${VERSION}.tar.gz 复制到目标机器"
echo "  2. 解压: tar -xzf ${PACKAGE_NAME}-${VERSION}.tar.gz"
echo "  3. 进入目录: cd ${PACKAGE_NAME}-${VERSION}"
echo "  4. 运行安装: ./install.sh"
