#!/bin/bash
# 构建 Debian 安装包

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_NAME="unipdf-deps"
VERSION="1.0.0"
ARCH="amd64"
BUILD_DIR="${SCRIPT_DIR}/deb_build/${PACKAGE_NAME}_${VERSION}_${ARCH}"

echo "=== 构建 Debian 安装包 ==="
echo "包名: ${PACKAGE_NAME}"
echo "版本: ${VERSION}"
echo "架构: ${ARCH}"

# 清理并创建目录
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}/DEBIAN"
mkdir -p "${BUILD_DIR}/usr/lib/unipdf-deps/wheels"
mkdir -p "${BUILD_DIR}/usr/share/doc/unipdf-deps"

# 复制 wheel 文件
echo "复制依赖包..."
if ls "${SCRIPT_DIR}/wheels"/*.whl 1>/dev/null 2>&1; then
    cp "${SCRIPT_DIR}/wheels"/*.whl "${BUILD_DIR}/usr/lib/unipdf-deps/wheels/"
else
    cp "${SCRIPT_DIR}"/*.whl "${BUILD_DIR}/usr/lib/unipdf-deps/wheels/"
fi

# 创建 control 文件
echo "创建控制文件..."
cat > "${BUILD_DIR}/DEBIAN/control" << CONTROL
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.7), python3-pip
Maintainer: Unipdf <unipdf@local>
Description: Unipdf PDF viewer dependencies
 Includes PyMuPDF, PyQt5 and related packages
 for offline installation.
CONTROL

# 创建 preinst 脚本（安装前检查）
cat > "${BUILD_DIR}/DEBIAN/preinst" << PREINST
#!/bin/bash
set -e

echo "准备安装 Unipdf 依赖..."

# 检查 Python 版本
if ! command -v python3 &> /dev/null; then
    echo "错误: Python3 未安装"
    exit 1
fi

PYTHON_VERSION=\$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1-2)
echo "Python 版本: \$PYTHON_VERSION"

exit 0
PREINST
chmod 755 "${BUILD_DIR}/DEBIAN/preinst"

# 创建 postinst 脚本（安装后执行）
cat > "${BUILD_DIR}/DEBIAN/postinst" << 'POSTINST'
#!/bin/bash
# 不使用 set -e，允许部分安装失败

echo ""
echo "=== 安装 Unipdf Python 依赖 ==="
echo ""

WHEELS_DIR="/usr/lib/unipdf-deps/wheels"

# 安装 wheel 包 - 直接安装所有 wheel 文件
echo "正在安装依赖包..."
echo "这可能需要几分钟时间..."

# 方法1: 直接安装所有 wheel 文件
pip3 install --no-index --find-links="${WHEELS_DIR}" ${WHEELS_DIR}/*.whl || {
    echo "警告: 部分 wheel 安装失败，尝试备用方案..."

    # 方法2: 逐个安装
    for whl in ${WHEELS_DIR}/*.whl; do
        echo "安装: $whl"
        pip3 install --no-index "$whl" 2>/dev/null || echo "  跳过或失败: $(basename $whl)"
    done
}

echo ""
echo "=== 依赖安装完成 ==="
echo ""
echo "验证安装:"
python3 -c "import fitz; print('PyMuPDF: OK')" 2>/dev/null || echo "PyMuPDF: 未安装"
python3 -c "from PyQt5.QtWidgets import QApplication; print('PyQt5: OK')" 2>/dev/null || echo "PyQt5: 未安装"
echo ""
echo "现在可以运行: python3 main.py"
echo ""

exit 0
POSTINST
chmod 755 "${BUILD_DIR}/DEBIAN/postinst"

# 创建 prerm 脚本（卸载前）
cat > "${BUILD_DIR}/DEBIAN/prerm" << PRERM
#!/bin/bash
set -e

echo "卸载 Unipdf 依赖..."

# 可选：卸载安装的包
# pip3 uninstall -y PyMuPDF PyQt5 PyQt5-Qt5 PyQt5_sip 2>/dev/null || true

echo "完成"

exit 0
PRERM
chmod 755 "${BUILD_DIR}/DEBIAN/prerm"

# 创建文档
cat > "${BUILD_DIR}/usr/share/doc/unipdf-deps/README" << README
Unipdf 依赖包
=============

此包包含 Unipdf PDF 查看器所需的 Python 依赖：
- PyMuPDF 1.21.1
- PyQt5 5.15.9
- PyQt5-Qt5 5.15.18
- PyQt5_sip 12.13.0

安装后自动配置系统环境。

使用方法:
1. 安装此 deb 包: sudo dpkg -i unipdf-deps_*.deb
2. 将 main.py 和 pdfviewer/ 复制到工作目录
3. 运行: python3 main.py

卸载:
  sudo apt remove unipdf-deps

注意: 卸载不会自动删除已安装的 Python 包。
README

chmod 644 "${BUILD_DIR}/usr/share/doc/unipdf-deps/README"

# 构建 deb 包
echo ""
echo "构建 deb 包..."
cd "${SCRIPT_DIR}/deb_build"
dpkg-deb --build "${PACKAGE_NAME}_${VERSION}_${ARCH}"

# 移动结果到主目录
mv "${PACKAGE_NAME}_${VERSION}_${ARCH}.deb" "${SCRIPT_DIR}/"

# 清理
cd "${SCRIPT_DIR}"
rm -rf "deb_build"

echo ""
echo "=== 构建完成 ==="
echo "输出: ${SCRIPT_DIR}/${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
echo ""
echo "安装方法:"
echo "  sudo dpkg -i ${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
echo ""
echo "如果提示依赖问题，运行:"
echo "  sudo apt-get install -f"
