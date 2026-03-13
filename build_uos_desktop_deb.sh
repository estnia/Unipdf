#!/bin/bash
# 构建 UOS 桌面服务可用的 Debian 安装包

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_NAME="unipdf"
VERSION="1.0.0"
ARCH="amd64"
BUILD_DIR="${SCRIPT_DIR}/deb_build/${PACKAGE_NAME}_${VERSION}_${ARCH}"

echo "=== 构建 UOS 桌面服务 Debian 安装包 ==="
echo "包名: ${PACKAGE_NAME}"
echo "版本: ${VERSION}"
echo "架构: ${ARCH}"

# 清理并创建目录
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}/DEBIAN"
mkdir -p "${BUILD_DIR}/opt/${PACKAGE_NAME}"
mkdir -p "${BUILD_DIR}/usr/share/applications"
mkdir -p "${BUILD_DIR}/usr/share/icons/hicolor/256x256/apps"
mkdir -p "${BUILD_DIR}/usr/share/icons/hicolor/128x128/apps"
mkdir -p "${BUILD_DIR}/usr/share/icons/hicolor/64x64/apps"
mkdir -p "${BUILD_DIR}/usr/bin"
mkdir -p "${BUILD_DIR}/usr/share/mime/packages"

# 复制源代码到 /opt/unipdf/
echo "复制源代码..."
cp "${SCRIPT_DIR}/main.py" "${BUILD_DIR}/opt/${PACKAGE_NAME}/"
cp -r "${SCRIPT_DIR}/pdfviewer" "${BUILD_DIR}/opt/${PACKAGE_NAME}/"

# 复制 wheel 文件
echo "复制依赖包..."
mkdir -p "${BUILD_DIR}/opt/${PACKAGE_NAME}/wheels"
if ls "${SCRIPT_DIR}/wheels"/*.whl 1>/dev/null 2>&1; then
    cp "${SCRIPT_DIR}/wheels"/*.whl "${BUILD_DIR}/opt/${PACKAGE_NAME}/wheels/"
else
    cp "${SCRIPT_DIR}"/*.whl "${BUILD_DIR}/opt/${PACKAGE_NAME}/wheels/" 2>/dev/null || echo "警告: 未找到 wheel 文件"
fi

# 创建启动脚本
cat > "${BUILD_DIR}/usr/bin/unipdf" << 'LAUNCHER'
#!/bin/bash
# Unipdf 启动脚本

# 检查依赖是否安装
if ! python3 -c "import fitz; from PyQt5.QtWidgets import QApplication" 2>/dev/null; then
    echo "正在安装依赖..."
    sudo pip3 install --no-index /opt/unipdf/wheels/*.whl 2>/dev/null || {
        echo "错误: 依赖未安装，请先运行: sudo apt install unipdf"
        exit 1
    }
fi

# 启动 Unipdf
cd /opt/unipdf
python3 main.py "$@"
LAUNCHER
chmod 755 "${BUILD_DIR}/usr/bin/unipdf"

# 创建 .desktop 文件
cat > "${BUILD_DIR}/usr/share/applications/unipdf.desktop" << 'DESKTOP'
[Desktop Entry]
Name=Unipdf
Name[zh_CN]=Unipdf PDF查看器
Comment=Minimal, fast PDF viewer
Comment[zh_CN]=极简、极速的PDF查看器
Exec=/usr/bin/unipdf %f
Icon=unipdf
Type=Application
Categories=Office;Viewer;
MimeType=application/pdf;
Terminal=false
StartupNotify=true
Keywords=PDF;Viewer;Document;
Keywords[zh_CN]=PDF;查看器;文档;
DESKTOP
chmod 644 "${BUILD_DIR}/usr/share/applications/unipdf.desktop"

# 创建 MIME 类型关联
cat > "${BUILD_DIR}/usr/share/mime/packages/unipdf.xml" << 'MIME'
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
    <mime-type type="application/x-unipdf">
        <comment>Unipdf PDF Document</comment>
        <icon name="unipdf"/>
        <glob pattern="*.pdf"/>
    </mime-type>
</mime-info>
MIME
chmod 644 "${BUILD_DIR}/usr/share/mime/packages/unipdf.xml"

# 创建简单的 SVG 图标（使用 base64 编码的 PNG 占位符）
# 这里创建一个简单的文本图标，实际使用时可以替换为真实图标
cat > "${BUILD_DIR}/usr/share/icons/hicolor/256x256/apps/unipdf.png" << 'ICON'
iVBORw0KGgoAAAANSUhEUgAAAQAAAAEACAYAAABccqhmAAAACXBIWXMAAAsTAAALEwEAmpwYAAAF
0WlUWHRYTUw6Y29tLmFkb2JlLnhtcAAAAAAAPD94cGFja2V0IGJlZ2luPSLvu78iIGlkPSJXNU0w
TXBDZWhpSHpyZVN6TlRjemtjOWQiPz4gPHg6eG1wbWV0YSB4bWxuczp4PSJhZG9iZTpuczptZXRh
LyIgeDp4bXB0az0iQWRvYmUgWE1QIENvcmUgNS42LWMxNDAgNzkuMTYzNDk5LCAyMDEwLzEwLzEy
LTE3OjMyOjAwICAgICAgICAiPiA8cmRmOlJERiB4bWxuczpyZGY9Imh0dHA6Ly93d3cudzMub3Jn
LzE5OTkvMDIvMjItcmRmLXN5bnRheC1ucyMiPiA8cmRmOkRlc2NyaXB0aW9uIHJkZjphYm91dD0i
IiB4bWxuczp4bXBNTT0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL21tLyIgeG1sbnM6c3RS
ZWY9Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9zVHlwZS9SZXNvdXJjZVJlZiMiIHhtbG5z
OnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1wTU06T3JpZ2luYWxEb2N1bWVu
dElEPSJ4bXAuZGlkOjAxODAxMTc0MDcyMDY4MTE4OEM2REYyN0ExMDhBNDJFIiB4bXBNTTpEb2N1
bWVudElEPSJ4bXAuZGlkOjdCNTAyODcwMEY4NjExRTBBMzkyQzAyM0E1RDk3RDc3IiB4bXBNTTpJ
bnN0YW5jZUlEPSJ4bXAuaWlkOjdCNTAyODZGMEY4NjExRTBBMzkyQzAyM0E1RDk3RDc3IiB4bXA6
Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDUzUgTWFjaW50b3NoIj4gPHhtcE1NOkRlcml2
ZWRGcm9tIHN0UmVmOmluc3RhbmNlSUQ9InhtcC5paWQ6MDE4MDExNzQwNzIwNjgxMTg4QzZERjI3
QTEwOEE0MkUiIHN0UmVmOmRvY3VtZW50SUQ9InhtcC5kaWQ6MDE4MDExNzQwNzIwNjgxMTg4QzZE
RjI3QTEwOEE0MkUiLz4gPC9yZGY6RGVzY3JpcHRpb24+IDwvcmRmOlJERj4gPC94OnhtcG1ldGE+
IDw/eHBhY2tldCBlbmQ9InIiPz4B//79/Pv6+fj39vX08/Lx8O/u7ezr6uno5+bl5OPi4eDf3t3c
29rZ2NfW1dTT0tHQz87NzMvKycjHxsXEw8LBwL++vby7urm4t7a1tLOysbCvrq2sq6qpqKempaSj
op+fnZ6cm5qZmJeWlZSTkpGQj46NjIuKiYiHhoWEg4KBgH9+fXx7enl4d3Z1dHNycXBvbm1sa2pp
aGdmZWRjYmFgX15dXFtaWVhXVlVUU1JRUE9OTUxLSklIR0ZFRENCQUA/Pj08Ozo5ODc2NTQzMjEw
Ly4tLCsqKSgnJiUkIyIhIB8eHRwbGhkYFxYVFBMSERAPDg0MCwoJCAcGBQQDAgEAACwAAAAAAQAB
AAACAQwQAAA7
ICON

# 复制图标到其他尺寸
cp "${BUILD_DIR}/usr/share/icons/hicolor/256x256/apps/unipdf.png" \
   "${BUILD_DIR}/usr/share/icons/hicolor/128x128/apps/unipdf.png"
cp "${BUILD_DIR}/usr/share/icons/hicolor/256x256/apps/unipdf.png" \
   "${BUILD_DIR}/usr/share/icons/hicolor/64x64/apps/unipdf.png"

# 创建 control 文件
echo "创建控制文件..."
cat > "${BUILD_DIR}/DEBIAN/control" << CONTROL
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.7), python3-pip, libqt5widgets5, libqt5gui5, libqt5core5a
Maintainer: Unipdf <unipdf@local>
Description: Unipdf - Minimal PDF viewer
 A minimal, fast PDF viewer for UOS/Debian.
 Features: text selection, highlight annotation,
 underline annotation, full-text search, auto TOC.
 UOS桌面集成的PDF查看器，支持文本选择、
 高亮注释、下划线注释、全文搜索、智能目录。
CONTROL

# 创建 preinst 脚本
cat > "${BUILD_DIR}/DEBIAN/preinst" << 'PREINST'
#!/bin/bash
set -e

echo "准备安装 Unipdf..."

# 检查 Python 版本
if ! command -v python3 &> /dev/null; then
    echo "错误: Python3 未安装"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1-2)
echo "Python 版本: $PYTHON_VERSION"

exit 0
PREINST
chmod 755 "${BUILD_DIR}/DEBIAN/preinst"

# 创建 postinst 脚本
cat > "${BUILD_DIR}/DEBIAN/postinst" << 'POSTINST'
#!/bin/bash
# 不使用 set -e，允许容错

echo ""
echo "=== 安装 Unipdf ==="
echo ""

# 安装 Python 依赖
echo "正在安装 Python 依赖..."
WHEELS_DIR="/opt/unipdf/wheels"

if [ -d "$WHEELS_DIR" ]; then
    pip3 install --no-index "$WHEELS_DIR"/*.whl 2>/dev/null || {
        echo "注意: 部分依赖可能需要手动安装"
    }
fi

# 更新桌面数据库
echo "正在更新桌面菜单..."
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database /usr/share/applications/ 2>/dev/null || true
fi

# 更新 MIME 数据库
if command -v update-mime-database &> /dev/null; then
    update-mime-database /usr/share/mime/ 2>/dev/null || true
fi

# 更新图标缓存
if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache /usr/share/icons/hicolor/ 2>/dev/null || true
fi

echo ""
echo "=== 安装完成 ==="
echo ""
echo "启动方法:"
echo "  1. 从应用菜单启动 'Unipdf'"
echo "  2. 命令行: unipdf"
echo "  3. 双击 PDF 文件"
echo ""
echo "验证安装:"
python3 -c "import fitz; from PyQt5.QtWidgets import QApplication; print('依赖安装成功')" 2>/dev/null || echo "提示: 依赖可能需要重新安装"
echo ""

exit 0
POSTINST
chmod 755 "${BUILD_DIR}/DEBIAN/postinst"

# 创建 prerm 脚本
cat > "${BUILD_DIR}/DEBIAN/prerm" << 'PRERM'
#!/bin/bash
set -e

echo "正在卸载 Unipdf..."

# 清理桌面数据库
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database /usr/share/applications/ 2>/dev/null || true
fi

if command -v update-mime-database &> /dev/null; then
    update-mime-database /usr/share/mime/ 2>/dev/null || true
fi

echo "完成"

exit 0
PRERM
chmod 755 "${BUILD_DIR}/DEBIAN/prerm"

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
echo ""
echo "安装后从应用菜单启动 'Unipdf' 或使用命令: unipdf"
