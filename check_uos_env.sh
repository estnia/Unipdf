#!/bin/bash
# 检查 UOS 运行机环境

echo "=== UOS 环境检查 ==="
echo ""

echo "Python 版本:"
python3 --version
python3 -c "import sys; print(f'Python {sys.version}')"

echo ""
echo "平台信息:"
python3 -c "import platform; print(f'Platform: {platform.platform()}')"
python3 -c "import platform; print(f'Machine: {platform.machine()}')"
python3 -c "import platform; print(f'System: {platform.system()}')"

echo ""
echo "pip 版本:"
pip3 --version

echo ""
echo "支持的标签 (pip debug):"
pip3 debug --verbose 2>/dev/null | grep -A 50 "Compatible tags" || echo "pip debug 不支持"

echo ""
echo "当前 pip 支持的平台:"
python3 -c "import pip._internal; from pip._internal.models.target import Target; print(Target().platform_tags)" 2>/dev/null || \
python3 -c "import pip._vendor.packaging.tags; tags = list(pip._vendor.packaging.tags.sys_tags()); print('\\n'.join([str(t) for t in tags[:20]]))" 2>/dev/null || \
echo "无法获取平台标签"

echo ""
echo "可用的 wheel 文件:"
ls -la /usr/lib/unipdf-deps/wheels/ 2>/dev/null || echo "目录不存在"

echo ""
echo "尝试直接安装 PyMuPDF:"
pip3 install --no-index --find-links=/usr/lib/unipdf-deps/wheels/ PyMuPDF 2>&1 | head -20
