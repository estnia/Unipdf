#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TOC生成器通用测试脚本

用法:
    python test_toc.py <pdf_path> [doc_type]

    doc_type 可选值（自动检测）:
    - gbt    : GB/ISO标准文档（如 GB7718）
    - legal  : 法律法规文档（如食品安全法）

示例:
    python test_toc.py demo/GB7718.pdf gbt
    python test_toc.py demo/食品安全法.pdf legal
"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PyQt5.QtCore import QCoreApplication
from pdfviewer.workers import TocWorkerFactory, list_toc_worker_types


def print_progress(current: int, total: int):
    percent = (current / total) * 100 if total > 0 else 0
    bar_length = 30
    filled = int(bar_length * current / total) if total > 0 else 0
    bar = '█' * filled + '░' * (bar_length - filled)
    print(f"\r进度: [{bar}] {current}/{total} ({percent:.1f}%)", end='', flush=True)


def print_toc_result(toc_list: list, doc_type: str):
    print("\n\n" + "=" * 60)
    type_names = {'gbt': 'GB/ISO标准文档', 'legal': '法律法规文档'}
    print(f"{type_names.get(doc_type, doc_type)} 目录生成结果")
    print("=" * 60)

    if not toc_list:
        print("未识别到目录条目")
        return

    print(f"共识别到 {len(toc_list)} 个目录条目\n")

    for i, entry in enumerate(toc_list, 1):
        level, title, page = entry
        indent = "  " * (level - 1)
        print(f"{i:3d}. {indent}[L{level}] {title}  →  第 {page} 页")


def print_statistics(toc_list: list):
    if not toc_list:
        return

    levels = {}
    for entry in toc_list:
        level = entry[0]
        levels[level] = levels.get(level, 0) + 1

    print("\n" + "-" * 60)
    print("统计信息:")
    for level in sorted(levels.keys()):
        print(f"  - 层级 {level}: {levels[level]} 个")
    print(f"  - 总计: {len(toc_list)} 个条目")


def detect_doc_type(pdf_path: str) -> str:
    """根据文件名自动检测文档类型"""
    basename = os.path.basename(pdf_path).lower()

    # 法律法规关键词
    legal_keywords = ['法', '条例', '办法', '规定', '规章', '令']
    if any(kw in basename for kw in legal_keywords):
        return 'legal'

    # GB/ISO标准关键词
    if re.match(r'^(gb|iso|iec)', basename):
        return 'gbt'

    return 'gbt'  # 默认


def test_toc(pdf_path: str, doc_type: str = None, app=None):
    import re

    if not os.path.exists(pdf_path):
        print(f"错误: 文件不存在: {pdf_path}")
        return 1

    if not pdf_path.lower().endswith('.pdf'):
        print(f"错误: 不是PDF文件: {pdf_path}")
        return 1

    # 自动检测类型
    if doc_type is None:
        doc_type = detect_doc_type(pdf_path)
        print(f"自动检测文档类型: {doc_type}")

    # 检查类型是否可用
    if not TocWorkerFactory.is_available(doc_type):
        available = [t[0] for t in list_toc_worker_types()]
        print(f"错误: 未知的文档类型 '{doc_type}'")
        print(f"可用类型: {', '.join(available)}")
        return 1

    print(f"测试文件: {pdf_path}")
    print(f"文件大小: {os.path.getsize(pdf_path) / 1024:.1f} KB")
    print(f"文档类型: {doc_type}")
    print("\n开始生成目录...")
    print("-" * 60)

    # 只在需要时创建 QCoreApplication
    need_app = app is None
    if need_app:
        app = QCoreApplication(sys.argv)

    worker = TocWorkerFactory.create(doc_type, pdf_path)

    if worker is None:
        print("错误: 无法创建 Worker")
        return 1

    result = {"toc": None, "error": None}

    def on_finished(toc_list):
        result["toc"] = toc_list
        if need_app:
            app.quit()

    def on_error(error_msg):
        result["error"] = error_msg
        if need_app:
            app.quit()

    worker.progress.connect(print_progress)
    worker.finished.connect(on_finished)
    worker.error.connect(on_error)

    worker.start()
    if need_app:
        app.exec_()
    else:
        # 等待worker完成
        import time
        while worker.isRunning():
            app.processEvents()
            time.sleep(0.01)
    worker.wait()
    print()  # 确保进度条后有换行

    if result["error"]:
        print(f"\n错误: {result['error']}")
        return 1

    if result["toc"] is not None:
        print_toc_result(result["toc"], doc_type)
        print_statistics(result["toc"])

    print("\n" + "=" * 60)
    print("测试完成（未保存修改）")
    print("=" * 60)

    return 0


def main():
    if len(sys.argv) < 2:
        # 显示帮助
        print(__doc__)
        print("\n已注册的文档类型:")
        for doc_type, doc_name in list_toc_worker_types():
            print(f"  - {doc_type:10s} : {doc_name}")
        print()

        # 创建全局 QCoreApplication
        app = QCoreApplication(sys.argv)

        # 测试默认文件
        test_files = [
            ("demo/GB 7718-2011预包装食品标签通则.pdf", "gbt"),
            ("demo/33中华人民共和国食品安全法实施条例.pdf", "legal"),
            ("demo/市场监督管理行政处罚案件违法所得认定办法（总局令第118号）.pdf", "legal"),
        ]

        for pdf_path, doc_type in test_files:
            if os.path.exists(pdf_path):
                print(f"\n{'='*60}")
                print(f"测试: {os.path.basename(pdf_path)}")
                print(f"类型: {doc_type}")
                print('='*60)
                test_toc(pdf_path, doc_type, app)
            else:
                print(f"跳过: {pdf_path} 不存在")
        return 0

    pdf_path = sys.argv[1]
    doc_type = sys.argv[2] if len(sys.argv) > 2 else None
    return test_toc(pdf_path, doc_type)


if __name__ == "__main__":
    sys.exit(main())
