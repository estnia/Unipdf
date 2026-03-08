#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
下划线注释功能测试脚本 - 截图验证
"""

import sys
import os
import subprocess
import time

def setup_xvfb():
    """启动 Xvfb"""
    display_num = 99
    while os.path.exists(f"/tmp/.X{display_num}-lock"):
        display_num += 1

    xvfb_cmd = [
        "Xvfb", f":{display_num}",
        "-screen", "0", "1920x1080x24",
        "-ac", "+extension", "GLX", "+render",
        "-noreset", "-nolisten", "tcp"
    ]

    print(f"[*] 启动 Xvfb :{display_num}")
    xvfb_proc = subprocess.Popen(xvfb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1)

    if xvfb_proc.poll() is not None:
        print("[!] Xvfb 启动失败")
        return None, None

    return xvfb_proc, display_num

def capture_screen(display, output_file):
    """使用 xwd 截图"""
    env = os.environ.copy()
    env["DISPLAY"] = f":{display}"

    # 使用 xwd 截图
    cmd = ["xwd", "-display", f":{display}", "-root", "-out", output_file]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"[+] 截图已保存: {output_file}")
        # 转换为 PNG 以便查看
        png_file = output_file.replace(".xwd", ".png")
        convert_cmd = ["convert", output_file, png_file]
        subprocess.run(convert_cmd, capture_output=True)
        if os.path.exists(png_file):
            print(f"[+] PNG 格式: {png_file}")
            return png_file
    else:
        print(f"[!] 截图失败: {result.stderr}")

    return None

def main():
    print("=" * 50)
    print("下划线注释功能测试 - 截图验证")
    print("=" * 50)

    # 检查测试文件
    pdf_file = "/home/feifei/Unipdf/test_underline_annot.pdf"
    if not os.path.exists(pdf_file):
        print(f"[!] 测试文件不存在: {pdf_file}")
        return 1

    # 启动 Xvfb
    xvfb_proc, display_num = setup_xvfb()
    if not xvfb_proc:
        return 1

    os.environ["DISPLAY"] = f":{display_num}"

    try:
        # 启动应用
        print("[*] 启动 Unipdf...")
        app_proc = subprocess.Popen(
            ["python3", "/home/feifei/Unipdf/main.py", pdf_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # 等待应用启动
        print("[*] 等待应用渲染...")
        time.sleep(5)

        # 截图 1: 初始状态（显示下划线注释）
        print("\n[*] 截取初始状态...")
        capture_screen(display_num, "/home/feifei/Unipdf/screenshot_1_initial.xwd")

        print("\n[+] 测试完成！")
        print(f"    应用 PID: {app_proc.pid}")
        print(f"    Xvfb 显示: :{display_num}")

        # 保持运行一段时间供查看
        print("\n[*] 保持运行 10 秒...")
        time.sleep(10)

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
        if xvfb_proc:
            xvfb_proc.terminate()
            xvfb_proc.wait(timeout=5)
            print("[*] Xvfb 已关闭")

if __name__ == "__main__":
    sys.exit(main())
