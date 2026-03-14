#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
法律法规文档 TOC Worker - 针对法律条文结构优化

支持格式:
- 第一章、第二章...（第[中文数字]章）
- 第一节、第二节...（第[中文数字]节）
- 第一条、第二条...（第[中文数字]条）
- 第X条 标题（如"第一条 为了规范..."）
"""

import re
from typing import Optional, List, Dict, Any

from .base_toc_worker import BaseTocWorker, register_toc_worker


# 法律法规专用正则
RE_CHAPTER = re.compile(r'^第[一二三四五六七八九十百千零]+章')
RE_SECTION = re.compile(r'^第[一二三四五六七八九十零]+节')
RE_ARTICLE = re.compile(r'^第[一二三四五六七八九十百千零]+条')

# 中文数字转阿拉伯数字
CN_NUMBERS = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '百': 100, '千': 1000
}


def cn_to_number(cn_str: str) -> int:
    """中文数字转阿拉伯数字（支持零）"""
    if not cn_str:
        return 0

    # 处理包含"零"的情况（如"一百零一"）
    cn_str = cn_str.replace('零', '')

    result = 0
    temp = 0
    for char in cn_str:
        if char in CN_NUMBERS:
            num = CN_NUMBERS[char]
            if num >= 10:
                if temp == 0:
                    temp = 1
                result += temp * num
                temp = 0
            else:
                temp = temp * 10 + num if temp > 0 else num
    result += temp
    return result if result > 0 else 0


def extract_article_num(text: str) -> int:
    """从"第X条"中提取数字"""
    match = RE_ARTICLE.match(text)
    if match:
        cn_num = match.group(0)[1:-1]
        return cn_to_number(cn_num)
    return 0


def extract_chapter_num(text: str) -> int:
    """从"第X章"中提取数字"""
    match = RE_CHAPTER.match(text)
    if match:
        cn_num = match.group(0)[1:-1]
        return cn_to_number(cn_num)
    return 0


@register_toc_worker
class LegalTocWorker(BaseTocWorker):
    """法律法规文档目录生成器"""

    DOC_TYPE = "legal"
    DOC_TYPE_NAME = "法律法规"

    def _get_max_pages(self) -> int:
        """法律文档扫描前70页（食品安全法有154条，共61页）"""
        return 70

    def _extract_toc(self) -> List[Dict[str, Any]]:
        """提取目录条目（支持跨行章标题）"""
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

                # 跨行章标题（如 "第一章" + "总则"）
                if heading_info and heading_info.get("chapter_num"):
                    # 检查下一行是否是章的标题文本
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        next_text = next_line["text"].strip()
                        # 下一行不是条、不是节、不是章，且距离较近
                        if (next_text and
                            not RE_ARTICLE.match(next_text) and
                            not RE_SECTION.match(next_text) and
                            not RE_CHAPTER.match(next_text) and
                            abs(next_line["y"] - line["y"]) < 30 and
                            len(next_text) < 20):
                            heading_info["text"] = f"{text} {next_text}"
                            i += 1

                # 过滤掉误识别的注释（如"第六十三条所规定的..."）
                if heading_info and heading_info.get("article_num"):
                    # 注释特征：包含解释性词汇或过长内容
                    explanatory_phrases = ['所规定的', '所称', '指的是', '意味着', '责令限期改']
                    has_explanatory = any(phrase in text for phrase in explanatory_phrases)
                    has_semicolon = '；' in text or ';' in text
                    # 正式条文标题通常较短（<30字），过长的可能是正文引用
                    is_too_long = len(text) > 30
                    # 如果是注释而非正式条文标题，跳过
                    if has_explanatory or has_semicolon or is_too_long:
                        i += 1
                        continue

                if heading_info:
                    heading_info["page"] = page_idx + 1
                    heading_info["line_idx"] = i
                    headings.append(heading_info)

                i += 1

        return headings

    def _is_header_footer(self, text: str, y: float, page_height: float,
                          font_size: float, body_font: float) -> bool:
        # 纯数字页码
        if text.isdigit():
            if y < page_height * 0.1 or y > page_height * 0.9:
                return True
        # 极端位置
        if y < page_height * 0.05 or y > page_height * 0.95:
            return True
        return False

    def _extract_lines(self, page) -> List[Dict[str, Any]]:
        """提取页面文本行（法律文档专用版本，检测黑体）"""
        lines = []
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if block["type"] != 0:
                continue

            for line in block["lines"]:
                text = ""
                size = 0
                x0 = None
                y0 = None
                is_bold = False
                flags = 0

                for span in line["spans"]:
                    text += span["text"]
                    size = max(size, span["size"])
                    flags |= span.get("flags", 0)

                    font_name = span.get("font", "").lower()
                    if "bold" in font_name or "black" in font_name or "heavy" in font_name:
                        is_bold = True
                    # 中文字体粗体（黑体/宋体视为加粗）
                    if any(kw in font_name for kw in ["heiti", "simhei", "heiti", "song", "fangson", "fangsong"]):
                        is_bold = True

                    if x0 is None:
                        x0 = span["bbox"][0]
                        y0 = span["bbox"][1]

                text = text.strip()
                if not text:
                    continue

                is_bold = is_bold or (flags & 16) != 0

                lines.append({
                    "text": text,
                    "size": size,
                    "x": x0 if x0 is not None else 0,
                    "y": y0 if y0 is not None else 0,
                    "is_bold": is_bold,
                    "flags": flags
                })

        return lines

    def _parse_heading(self, text: str, line: Dict, page_min_x: float,
                       body_font: float, font_name: str = "") -> Optional[Dict]:
        """解析法律条文标题"""
        is_bold = line.get("is_bold", False)

        # 第一章、第二章...（L1）- 章标题格式为"第X章 标题"
        # 必须是黑体（正式的章标题），过滤掉目录页的非黑体章标题
        chapter_match = RE_CHAPTER.match(text)
        if chapter_match and is_bold:
            chapter_num = extract_chapter_num(text)
            return {
                "text": text,
                "level": 1,
                "size": line["size"],
                "x": line["x"],
                "y": line["y"],
                "is_bold": is_bold,
                "chapter_num": chapter_num
            }

        # 第一节、第二节...（L2）- 节标题需要加粗
        if is_bold:
            section_match = RE_SECTION.match(text)
            if section_match:
                section_num = cn_to_number(section_match.group(1))
                return {
                    "text": text,
                    "level": 2,
                    "size": line["size"],
                    "x": line["x"],
                    "y": line["y"],
                    "is_bold": True,
                    "section_num": section_num
                }

        # 第一条、第二条...（L2，作为章的下级）
        # 食品安全法2021：条在最左边（顶格），但不一定是黑体
        if RE_ARTICLE.match(text):
            article_num = extract_article_num(text)
            # 如果在最左边（顶格）或者是黑体，则认为是条
            is_at_margin = line["x"] <= page_min_x + 10
            if is_bold or is_at_margin:
                return {
                    "text": text[:50],
                    "level": 2,
                    "size": line["size"],
                    "x": line["x"],
                    "y": line["y"],
                    "is_bold": is_bold,
                    "article_num": article_num
                }

        return None

    def _post_process(self, headings: List[Dict]) -> List[Dict]:
        """后处理：检查是否有章，修正层级，验证编号顺序"""
        headings = self._sort_and_dedup(headings)

        # 检查是否有章（L1）
        chapters = [h for h in headings if h.get("chapter_num", 0) > 0]
        has_chapter = len(chapters) > 0

        if has_chapter:
            # 首先按条号对章进行排序（章号小的排在前面）
            chapters.sort(key=lambda h: h["chapter_num"])

            # 获取所有条
            articles = [h for h in headings if h.get("article_num", 0) > 0]

            # 为每个章找到其开始的条号
            # 章的开始条号 = 该章出现后的第一个条的条号
            for i, chapter in enumerate(chapters):
                chapter_page = chapter["page"]
                chapter_y = chapter["y"]

                # 找到该章后的第一个条
                next_article_num = None
                for article in articles:
                    if article["page"] > chapter_page:
                        # 如果条在章后面的页面
                        if next_article_num is None or article["article_num"] < next_article_num:
                            next_article_num = article["article_num"]
                    elif article["page"] == chapter_page and article["y"] > chapter_y:
                        # 如果条在同一页面但y坐标更大
                        if next_article_num is None or article["article_num"] < next_article_num:
                            next_article_num = article["article_num"]

                chapter["article_num_start"] = next_article_num

            # 为每个条找到所属的章
            for article in articles:
                article_num = article["article_num"]
                # 找到该条应该属于哪个章
                assigned_chapter = None
                for i, chapter in enumerate(chapters):
                    chapter_start = chapter.get("article_num_start", 0)
                    if chapter_start is None:
                        continue
                    if i + 1 < len(chapters):
                        next_chapter_start = chapters[i + 1].get("article_num_start", float('inf'))
                        if chapter_start <= article_num < next_chapter_start:
                            assigned_chapter = chapter
                            break
                    else:
                        # 最后一章
                        if article_num >= chapter_start:
                            assigned_chapter = chapter
                            break

                # 更新条的层级和所属关系
                if assigned_chapter:
                    article["level"] = 2
                    article["parent_chapter"] = assigned_chapter["chapter_num"]
                else:
                    # 如果条没有对应的章，提升为L1
                    article["level"] = 1

            # 重新构建headings列表：按顺序包含章和条
            result = []
            for chapter in chapters:
                result.append(chapter)
                # 添加该章下的所有条
                chapter_articles = [a for a in articles if a.get("parent_chapter") == chapter["chapter_num"]]
                chapter_articles.sort(key=lambda a: a["article_num"])
                result.extend(chapter_articles)

            # 添加没有章的条（如果有）
            orphan_articles = [a for a in articles if "parent_chapter" not in a]
            result.extend(orphan_articles)

            headings = result
        else:
            # 如果没有章，将所有条（L2）提升为L1
            for h in headings:
                if h.get("article_num", 0) > 0:
                    h["level"] = 1

        # 验证编号顺序
        headings = self._validate_sequence(headings)

        return headings

    def _validate_sequence(self, headings: List[Dict]) -> List[Dict]:
        """
        验证法律法规编号顺序：
        1. 章应该连续（第一章、第二章...）
        2. 条应该连续（第一条、第二条...）
        3. 条应该在其所属的章范围内
        """
        if len(headings) < 2:
            return headings

        # 分离章和条
        chapters = [h for h in headings if h.get("chapter_num", 0) > 0]
        articles = [h for h in headings if h.get("article_num", 0) > 0]

        # 验证章的连续性
        if len(chapters) >= 2:
            chapter_nums = [h["chapter_num"] for h in chapters]
            for i in range(1, len(chapter_nums)):
                if chapter_nums[i] != chapter_nums[i-1] + 1:
                    # 发现断点，标记可能遗漏的章
                    expected = chapter_nums[i-1] + 1
                    print(f"[LegalTocWorker] 警告: 章号不连续，从第{chapter_nums[i-1]}章跳至第{chapter_nums[i]}章，可能遗漏第{expected}章")

        # 验证条的连续性
        if len(articles) >= 2:
            # 按条号去重，保留第一个出现的（通常是正式条文而非引用）
            seen_nums = set()
            unique_articles = []
            for h in articles:
                num = h["article_num"]
                if num not in seen_nums:
                    seen_nums.add(num)
                    unique_articles.append(h)

            # 按条号排序后检查连续性
            sorted_articles = sorted(unique_articles, key=lambda x: x["article_num"])
            for i in range(1, len(sorted_articles)):
                prev_num = sorted_articles[i-1]["article_num"]
                curr_num = sorted_articles[i]["article_num"]
                if curr_num != prev_num + 1:
                    gap = curr_num - prev_num - 1
                    expected = prev_num + 1
                    print(f"[LegalTocWorker] 警告: 条号不连续，从第{prev_num}条跳至第{curr_num}条，可能遗漏第{expected}条（共遗漏{gap}条）")

        return headings

    def _build_toc_list(self, headings: List[Dict]) -> List[List]:
        """构建TOC列表（保持原始层级）"""
        return [[h["level"], h["text"], h["page"]] for h in headings]
