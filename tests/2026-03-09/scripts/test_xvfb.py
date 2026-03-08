#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Xvfb 虚拟显示测试脚本 - 方案2
用于在无显示服务器的环境中测试 PyQt5 PDF 查看器
"""

import sys
import os
import subprocess
import time
import signal


def setup_xvfb():
    """启动 Xvfb 虚拟显示服务器"""
    # 查找可用的显示号
    display_num = 99
    while os.path.exists(f"/tmp/.X{display_num}-lock"):
        display_num += 1

    xvfb_cmd = [
        "Xvfb",
        f":{display_num}",
        "-screen", "0", "1920x1080x24",
        "-ac",  # 禁用访问控制
        "+extension", "GLX",
        "+render",
        "-noreset",
        "-nolisten", "tcp"
    ]

    print(f"[*] 启动 Xvfb 虚拟显示 :{display_num}")
    xvfb_process = subprocess.Popen(
        xvfb_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # 等待 Xvfb 启动
    time.sleep(1)

    # 检查是否成功启动
    if xvfb_process.poll() is not None:
        stdout, stderr = xvfb_process.communicate()
        print(f"[!] Xvfb 启动失败:")
        print(stderr.decode())
        return None, None

    print(f"[+] Xvfb 已启动 (PID: {xvfb_process.pid})")
    return xvfb_process, display_num


def test_import():
    """测试必要的模块是否能正常导入"""
    print("\n[*] 测试模块导入...")

    try:
        from PyQt5.QtWidgets import QApplication
        print("[+] PyQt5 导入成功")
    except ImportError as e:
        print(f"[!] PyQt5 导入失败: {e}")
        return False

    # 尝试导入 PyMuPDF（兼容新旧版本）
    try:
        import fitz
        print(f"[+] PyMuPDF (fitz) 导入成功，版本: {fitz.__doc__.split()[0] if fitz.__doc__ else 'unknown'}")
    except ImportError:
        try:
            import pymupdf
            print(f"[+] PyMuPDF (pymupdf) 导入成功，版本: {pymupdf.__doc__.split()[1] if pymupdf.__doc__ else 'unknown'}")
        except ImportError as e:
            print(f"[!] PyMuPDF 导入失败: {e}")
            return False

    return True


def test_basic_functionality():
    """测试基本功能"""
    print("\n[*] 测试基本功能...")

    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt

    # 兼容新旧版本 PyMuPDF
    try:
        import fitz
    except ImportError:
        import pymupdf as fitz

    # 创建应用（使用 Xvfb）
    app = QApplication(sys.argv)

    # 测试 PyMuPDF 功能
    try:
        # 创建一个简单的内存 PDF
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((100, 100), "Test PDF for Xvfb")

        # 渲染页面
        pix = page.get_pixmap()
        print(f"[+] PDF 渲染成功: {pix.width}x{pix.height}")

        doc.close()
    except Exception as e:
        print(f"[!] PDF 渲染测试失败: {e}")
        return False

    # 测试 QWidget 创建
    try:
        from PyQt5.QtWidgets import QWidget
        widget = QWidget()
        widget.setWindowTitle("Xvfb Test")
        widget.resize(800, 600)
        print("[+] QWidget 创建成功")
    except Exception as e:
        print(f"[!] QWidget 创建失败: {e}")
        return False

    return True


def main():
    """主测试流程"""
    print("=" * 50)
    print("Unipdf Xvfb 虚拟显示测试")
    print("=" * 50)

    # 检查 Xvfb 是否已安装
    if not os.path.exists("/usr/bin/Xvfb"):
        print("[!] 错误: Xvfb 未安装")
        print("    请运行: sudo apt-get install xvfb")
        return 1

    # 启动 Xvfb
    xvfb_proc, display_num = setup_xvfb()
    if xvfb_proc is None:
        return 1

    # 设置 DISPLAY 环境变量
    os.environ["DISPLAY"] = f":{display_num}"
    print(f"[*] DISPLAY 设置为 :{display_num}")

    try:
        # 测试模块导入
        if not test_import():
            print("\n[!] 模块导入测试失败")
            return 1

        # 测试基本功能
        if not test_basic_functionality():
            print("\n[!] 基本功能测试失败")
            return 1

        print("\n" + "=" * 50)
        print("[+] 所有测试通过！Xvfb 方案工作正常")
        print("=" * 50)
        print("\n您现在可以运行:")
        print(f"  export DISPLAY=:{display_num}")
        print("  python3 main.py <pdf文件>")

        return 0

    except Exception as e:
        print(f"\n[!] 测试过程发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # 清理 Xvfb
        if xvfb_proc:
            print(f"\n[*] 关闭 Xvfb (PID: {xvfb_proc.pid})")
            xvfb_proc.terminate()
            xvfb_proc.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
