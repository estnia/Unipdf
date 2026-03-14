#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TOC Worker - GB/ISO/行业标准文档

利用标准文档的严格结构规律，实现接近 100% 的准确率。
"""

import re
from typing import Optional, List, Dict, Any

from .base_toc_worker import BaseTocWorker, register_toc_worker


# GB/ISO标准文档专用正则
RE_L1 = re.compile(r'^([1-9]\d*)(?!\.\d)\s+(\S.*)$')  # "1 范围"
RE_L2 = re.compile(r'^([1-9]\d*\.\d+)\s+(\S.*)$')     # "2.1 术语"
RE_APPENDIX = re.compile(r'^((?:附录|附 录|Annex|Appendix)\s*[A-Z])\s*(\S.*)?$', re.IGNORECASE)
RE_APPENDIX_LETTER = re.compile(r'^([A-Z])\.$')  # "A.", "B.", "C." 用于2025版附录小节
RE_FIG_TABLE = re.compile(r'^(图|表|Figure|Table)\s*\d', re.IGNORECASE)
RE_STD_REF = re.compile(r'^(GB|ISO|IEC|GB/T|GB/Z)\s*\d', re.IGNORECASE)


@register_toc_worker
class GbtTocWorker(BaseTocWorker):
    """GB/ISO标准文档目录生成器"""

    DOC_TYPE = "gbt"
    DOC_TYPE_NAME = "GB/ISO标准"

    def _get_max_pages(self) -> int:
        return 100

    def _is_header_footer(self, text: str, y: float, page_height: float,
                          font_size: float, body_font: float) -> bool:
        # 标准引用
        if RE_STD_REF.match(text):
            return True
        # 纯数字页码
        if text.isdigit():
            if y < page_height * 0.12 or y > page_height * 0.88:
                return True
            if font_size < body_font * 0.85:
                return True
        # 极端位置
        if y < page_height * 0.05 or y > page_height * 0.95:
            return True
        return False

    def _extract_toc(self) -> List[Dict[str, Any]]:
        """重写以支持跨行标题合并"""
        try:
            import fitz
        except ImportError:
            import pymupdf as fitz

        doc = fitz.open(self.doc_path)
        all_lines = []
        pages_data = []

        total_pages = min(len(doc), self._get_max_pages())

        for page_idx in range(total_pages):
            if not self._is_running:
                break
            self.progress.emit(page_idx + 1, total_pages)

            page = doc[page_idx]
            lines = self._extract_lines(page)
            all_lines.extend(lines)
            pages_data.append((page_idx, page.rect.width, page.rect.height, lines))

            if page_idx % 10 == 0:
                fitz.TOOLS.store_shrink(100)

        doc.close()

        if not all_lines:
            return []

        body_font = self._calc_body_font(all_lines)
        min_x = min([line["x"] for line in all_lines]) if all_lines else 0
        headings = []

        for page_idx, page_width, page_height, lines in pages_data:
            if not self._is_running:
                break

            lines.sort(key=lambda x: x["y"])
            page_min_x = min([line["x"] for line in lines]) if lines else min_x

            i = 0
            while i < len(lines):
                line = lines[i]
                text = line["text"].strip()
                if not text:
                    i += 1
                    continue

                if self._is_header_footer(text, line["y"], page_height, line["size"], body_font):
                    i += 1
                    continue

                heading_info = self._parse_heading(text, line, page_min_x, body_font, line.get("font", ""))

                # 跨行附录标题（附 录 X + 下一行标题）
                if heading_info and heading_info.get("is_appendix"):
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        next_text = next_line["text"].strip()
                        # 下一行应该是附录标题（非数字开头，不以L1/L2格式开头，不是附录标记）
                        if (next_text and
                            not next_text[0].isdigit() and
                            not RE_L1.match(next_text) and
                            not RE_L2.match(next_text) and
                            not RE_APPENDIX.match(next_text) and
                            len(next_text) < 60):
                            heading_info["text"] = f"{text} {next_text}"
                            heading_info["size"] = max(line["size"], next_line["size"])
                            i += 1

                # 跨行L1标题（数字 + 下一行文本）
                if not heading_info and self._is_l1_number_line(text, line, page_min_x):
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        next_text = next_line["text"].strip()

                        # 2025版：下一行可以不加粗，但需要是标题格式（短文本，不以数字开头）
                        is_next_valid = (
                            not next_text[0].isdigit() and
                            not RE_L2.match(next_text) and
                            len(next_text) < 50 and  # 标题不应该太长
                            next_line["x"] <= page_min_x + 20
                        )

                        if is_next_valid:
                            heading_info = {
                                "text": f"{text} {next_text}",
                                "level": 1,
                                "size": max(line["size"], next_line["size"]),
                                "x": line["x"],
                                "y": line["y"],
                                "is_appendix": False,
                                "is_bold": True,
                                "main_num": int(text)
                            }
                            i += 1

                # 跨行L2标题（数字.数字 + 下一行文本）
                if not heading_info and self._is_l2_number_line(text, line, page_min_x):
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        next_text = next_line["text"].strip()

                        if (next_line.get("is_bold", False) and
                            not next_text[0].isdigit() and
                            next_line["x"] <= page_min_x + 40):

                            parts = text.split(".")
                            heading_info = {
                                "text": f"{text} {next_text}",
                                "level": 2,
                                "size": max(line["size"], next_line["size"]),
                                "x": line["x"],
                                "y": line["y"],
                                "is_appendix": False,
                                "is_bold": True,
                                "main_num": int(parts[0]),
                                "sub_num": int(parts[1])
                            }
                            i += 1

                # GB7718-2025 特殊格式："X." + "Y 标题"（如 "2." + "1 预包装食品"）
                if not heading_info and self._is_l2_prefix_line(text, line, page_min_x):
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        next_text = next_line["text"].strip()

                        # 下一行应该是 "数字 标题" 格式（2025版：下一行可以不加粗）
                        next_match = re.match(r'^([1-9]\d*)\s+(\S.*)$', next_text)
                        if (next_match and
                            next_line["x"] <= page_min_x + 40):

                            sub_num = int(next_match.group(1))
                            title = next_match.group(2)
                            main_num = int(text.rstrip('.'))

                            heading_info = {
                                "text": f"{main_num}.{sub_num} {title}",
                                "level": 2,
                                "size": max(line["size"], next_line["size"]),
                                "x": line["x"],
                                "y": line["y"],
                                "is_appendix": False,
                                "is_bold": True,
                                "main_num": main_num,
                                "sub_num": sub_num
                            }
                            i += 1

                if heading_info:
                    heading_info["page"] = page_idx + 1
                    heading_info["line_idx"] = i
                    headings.append(heading_info)

                i += 1

        return headings

    def _is_l1_number_line(self, text: str, line: Dict, page_min_x: float) -> bool:
        """检查是否是L1章节号行（纯数字，缩进最前）"""
        if not re.match(r'^[1-9]\d?$', text):
            return False
        if line["x"] > page_min_x + 20:
            return False
        return True

    def _is_l2_number_line(self, text: str, line: Dict, page_min_x: float) -> bool:
        """检查是否是L2章节号行（数字.数字，如 4.4）"""
        if not re.match(r'^[1-9]\d*\.[1-9]\d*$', text):
            return False
        is_heiti = "heiti" in line.get("font", "").lower() or "simhei" in line.get("font", "").lower()
        if not (line.get("is_bold", False) or is_heiti):
            return False
        if line["x"] > page_min_x + 20:
            return False
        return True

    def _is_l2_prefix_line(self, text: str, line: Dict, page_min_x: float) -> bool:
        """检查是否是L2前缀行（GB7718-2025特殊格式如 "2.", "3."）"""
        # 必须匹配 "数字." 格式（如 "2.", "3."）
        if not re.match(r'^[1-9]\d*\.$', text):
            return False

        # 必须缩进最前
        if line["x"] > page_min_x + 20:
            return False

        return True

    def _parse_heading(self, text: str, line: Dict, page_min_x: float,
                       body_font: float, font_name: str = "") -> Optional[Dict]:
        """解析标题"""
        font_name_lower = font_name.lower()
        is_heiti = "heiti" in font_name_lower or "simhei" in font_name_lower
        is_bold = line.get("is_bold", False) or is_heiti

        # 检查是否缩进最前（附录允许居中）
        if line["x"] > page_min_x + 20:
            if RE_APPENDIX.match(text):
                pass
            else:
                return None

        # 附录识别（2025版：可以不加粗，但必须居中或接近居中）
        app_match = RE_APPENDIX.match(text)
        if app_match:
            # 附录可以是居中（x在页面中间）或者是黑体/粗体
            page_center = page_min_x + 200  # 估算页面中心
            is_centered = abs(line["x"] - page_center) < 100
            if is_heiti or line.get("is_bold", False) or is_centered:
                return {
                    "text": text,
                    "level": 1,
                    "size": line["size"],
                    "x": line["x"],
                    "y": line["y"],
                    "is_appendix": True,
                    "is_bold": True,
                    "main_num": None
                }

        # 必须是加粗或者是缩进最前的标准章节号格式
        is_at_margin = line["x"] <= page_min_x + 5  # 几乎在最左边
        if not is_bold and not is_at_margin:
            return None

        # L1 识别
        l1_match = RE_L1.match(text)
        if l1_match:
            num_str = l1_match.group(1)
            content = l1_match.group(2)

            if self.RE_YEAR.match(num_str):
                return None
            if len(text) > 50:
                return None
            if RE_FIG_TABLE.match(content):
                return None

            return {
                "text": text,
                "level": 1,
                "size": line["size"],
                "x": line["x"],
                "y": line["y"],
                "is_appendix": False,
                "is_bold": True,
                "main_num": int(num_str)
            }

        # L2 识别
        l2_match = RE_L2.match(text)
        if l2_match:
            num_str = l2_match.group(1)
            content = l2_match.group(2)

            if len(text) > 30:
                return None
            if "。" in content:
                return None
            if RE_FIG_TABLE.match(content):
                return None

            parts = num_str.split(".")
            if len(parts) == 2:
                return {
                    "text": text,
                    "level": 2,
                    "size": line["size"],
                    "x": line["x"],
                    "y": line["y"],
                    "is_appendix": False,
                    "is_bold": True,
                    "main_num": int(parts[0]),
                    "sub_num": int(parts[1])
                }

        return None

    def _post_process(self, headings: List[Dict]) -> List[Dict]:
        """后处理：合并附录、层级验证、过滤L3+、过滤附录下的L2、编号顺序验证"""
        headings = self._merge_appendix_next_line(headings)
        headings = self._validate_hierarchy(headings)
        headings = [h for h in headings if h["level"] <= 2]
        headings = self._filter_appendix_l2(headings)
        headings = self._sort_and_dedup(headings)
        headings = self._validate_sequence(headings)
        return headings

    def _filter_appendix_l2(self, headings: List[Dict]) -> List[Dict]:
        """过滤掉附录下的L2（附录内部小节不需要在目录中显示）"""
        if not headings:
            return headings

        # 找到第一个附录的位置
        appendix_start_idx = None
        for i, h in enumerate(headings):
            if h.get("is_appendix"):
                appendix_start_idx = i
                break

        # 如果没有附录，直接返回
        if appendix_start_idx is None:
            return headings

        # 只保留附录前的L2和附录本身（L1）
        result = []
        for i, h in enumerate(headings):
            if h["level"] == 1:
                result.append(h)
            elif h["level"] == 2:
                # 只保留附录前的L2
                if i < appendix_start_idx:
                    result.append(h)
                # 附录后的L2（附录内部小节）被过滤掉

        return result

    def _validate_sequence(self, headings: List[Dict]) -> List[Dict]:
        """
        验证 GB/ISO 标准编号顺序：
        1. L1 应该连续（1、2、3...）
        2. L2 子编号应该在对应 L1 下连续（1.1、1.2、2.1...）
        """
        if len(headings) < 2:
            return headings

        # 分离 L1 和 L2
        l1_headings = [h for h in headings if h["level"] == 1 and h.get("main_num") is not None]
        l2_headings = [h for h in headings if h["level"] == 2 and h.get("main_num") is not None]

        # 验证 L1 连续性
        if len(l1_headings) >= 2:
            l1_nums = [h["main_num"] for h in l1_headings]
            for i in range(1, len(l1_nums)):
                if l1_nums[i] != l1_nums[i-1] + 1:
                    expected = l1_nums[i-1] + 1
                    print(f"[GbtTocWorker] 警告: L1编号不连续，从 {l1_nums[i-1]} 跳至 {l1_nums[i]}，可能遗漏章节 {expected}")

        # 验证 L2 在每个 L1 下的连续性
        from collections import defaultdict
        l2_by_main = defaultdict(list)
        for h in l2_headings:
            l2_by_main[h["main_num"]].append(h)

        for main_num, l2_list in l2_by_main.items():
            if len(l2_list) >= 2:
                sub_nums = sorted([h.get("sub_num", 0) for h in l2_list])
                for i in range(1, len(sub_nums)):
                    if sub_nums[i] != sub_nums[i-1] + 1:
                        expected = sub_nums[i-1] + 1
                        print(f"[GbtTocWorker] 警告: L2子编号不连续（在{main_num}.x下），从 {main_num}.{sub_nums[i-1]} 跳至 {main_num}.{sub_nums[i]}，可能遗漏 {main_num}.{expected}")

        return headings

    def _merge_appendix_next_line(self, headings: List[Dict]) -> List[Dict]:
        """合并附录下一行标题"""
        if not headings:
            return headings

        merged = []
        i = 0
        while i < len(headings):
            current = headings[i].copy()

            if current.get("is_appendix") and i + 1 < len(headings):
                next_line = headings[i + 1]
                same_page = next_line["page"] == current["page"]
                next_is_heading = (RE_L1.match(next_line["text"]) or
                                  RE_L2.match(next_line["text"]) or
                                  RE_APPENDIX.match(next_line["text"]))

                # 2025版：下一行可以不加粗
                if same_page and not next_is_heading:
                    current["text"] = current["text"] + " " + next_line["text"]
                    i += 1

            merged.append(current)
            i += 1

        return merged

    def _validate_hierarchy(self, headings: List[Dict]) -> List[Dict]:
        """层级验证：L2的主编号需与当前L1一致，子编号递增"""
        if not headings:
            return headings

        headings.sort(key=lambda x: (x["page"], x["y"]))
        validated = []
        current_l1_num = None
        last_l2_sub_num = 0

        for h in headings:
            if h["level"] == 1:
                current_l1_num = h.get("main_num")
                last_l2_sub_num = 0
                validated.append(h)
            elif h["level"] == 2:
                main_num = h.get("main_num")
                sub_num = h.get("sub_num", 0)

                if current_l1_num is not None and main_num != current_l1_num:
                    continue
                if sub_num <= last_l2_sub_num:
                    continue

                last_l2_sub_num = sub_num
                validated.append(h)

        return validated

    def _build_toc_list(self, headings: List[Dict]) -> List[List]:
        """构建TOC，修正层级跳跃"""
        toc = []
        prev_level = 0

        for h in headings:
            level = h["level"]
            if prev_level == 0:
                level = 1
            elif level > prev_level + 1:
                level = prev_level + 1
            toc.append([level, h["text"], h["page"]])
            prev_level = level

        return toc


# 保持向后兼容
AutoTocWorker = GbtTocWorker
