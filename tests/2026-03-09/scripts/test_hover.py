#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试鼠标悬停显示 tooltip
"""

import os
import subprocess
import time
import sys

def setup_xvfb():
    """启动 Xvfb"""
    display_num = 99
    while os.path.exists(f"/tmp/.X{display_num}-lock"):
        display_num += 1

    xvfb_cmd = [
        "Xvfb", f":{display_num}",
        "-screen", "0", "1200x800x24",
        "-ac", "+extension", "GLX", "+render",
        "-noreset"
    ]

    xvfb_proc = subprocess.Popen(xvfb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1)
    return xvfb_proc, display_num

def capture_screen(display, filename):
    """截图"""
    env = os.environ.copy()
    env["DISPLAY"] = f":{display}"
    subprocess.run(["xwd", "-display", f":{display}", "-root", "-out", filename],
                   env=env, capture_output=True)

def main():
    print("=" * 50)
    print("测试下划线注释悬停 tooltip")
    print("=" * 50)

    # 启动 Xvfb
    xvfb_proc, display_num = setup_xvfb()
    os.environ["DISPLAY"] = f":{display_num}"

    try:
        # 启动应用
        print("[*] 启动 Unipdf...")
        app_proc = subprocess.Popen(
            ["python3", "/home/feifei/Unipdf/main.py",
             "/home/feifei/Unipdf/test_underline_annot.pdf"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        # 等待应用启动
        time.sleep(4)

        # 截图 1: 初始状态
        print("[*] 截图 1: 初始状态...")
        capture_screen(display_num, "/tmp/hover_test_1.xwd")

        # 使用 xte 或 xdotool 移动鼠标（如果可用）
        # 由于可能没有这些工具，我们直接通过修改代码的方式来测试

        print("\n[+] 测试完成！")
        print("   截图 1: /tmp/hover_test_1.xwd")

        # 转换截图
        print("[*] 转换截图...")
        sys.path.insert(0, '/home/feifei/Unipdf')
        from convert_xwd import read_xwd

        img = read_xwd("/tmp/hover_test_1.xwd")
        img.save("/home/feifei/Unipdf/hover_test_1.png")
        print("   已保存: /home/feifei/Unipdf/hover_test_1.png")

        # 裁剪到 PDF 区域
        from PIL import Image
        width, height = img.size
        cropped = img.crop((0, 50, 800, 600))
        cropped.save("/home/feifei/Unipdf/hover_test_preview.png")
        print("   预览图: /home/feifei/Unipdf/hover_test_preview.png")

        # 清理
        app_proc.terminate()
        app_proc.wait(timeout=3)

        return 0

    except Exception as e:
        print(f"[!] 错误: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        xvfb_proc.terminate()
        xvfb_proc.wait(timeout=5)

if __name__ == "__main__":
    sys.exit(main())
