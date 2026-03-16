#!/usr/bin/env python3
"""测试手动添加目录的逻辑验证功能 - 独立函数版本"""

import re


def extract_number_from_title(title: str) -> int:
    """从标题中提取数字用于排序"""
    numbers = re.findall(r'\d+', title)
    if numbers:
        return int(numbers[0])

    cn_nums = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
        '百': 100, '千': 1000, '零': 0
    }

    match = re.search(r'第([一二三四五六七八九十百千零]+)[章节条款]', title)
    if match:
        cn_str = match.group(1)
        result = 0
        temp = 0
        for char in cn_str:
            if char in cn_nums:
                num = cn_nums[char]
                if num >= 10:
                    if temp == 0:
                        temp = 1
                    result += temp * num
                    temp = 0
                else:
                    temp = temp * 10 + num if temp > 0 else num
        result += temp
        return result

    for char in title:
        if char in cn_nums and cn_nums[char] > 0:
            return cn_nums[char]

    return 0


def detect_doc_type(toc: list) -> str:
    """检测文档类型"""
    if not toc:
        return "unknown"

    has_chapter = False
    has_article = False
    has_gbt_keywords = False
    gbt_keywords = ['前言', '范围', '规范性引用', '术语', '技术要求', '试验方法', '附录']

    for entry in toc:
        if len(entry) >= 2:
            title = str(entry[1])
            if '章' in title and '第' in title[:5]:
                has_chapter = True
            if '条' in title and '第' in title:
                has_article = True
            if any(kw in title for kw in gbt_keywords):
                has_gbt_keywords = True

    if has_chapter or has_article:
        return "legal"
    elif has_gbt_keywords:
        return "gbt"
    return "unknown"


def validate_legal_toc(toc: list, new_level: int, new_title: str,
                       new_page: int, new_num: int) -> list:
    """法律法规验证 - 严格"""
    issues = []
    if new_num <= 0:
        return issues

    same_level = [(i, e) for i, e in enumerate(toc) if e[0] == new_level]
    prev_entry = next_entry = None

    for i, (idx, entry) in enumerate(same_level):
        e_num = extract_number_from_title(entry[1])
        if e_num > 0:
            if e_num < new_num:
                prev_entry = entry
            elif e_num > new_num and next_entry is None:
                next_entry = entry

    if prev_entry:
        prev_num = extract_number_from_title(prev_entry[1])
        if prev_num > 0 and new_num > prev_num and new_page < prev_entry[2]:
            issues.append(f"编号{new_num} > {prev_num}，但页码{new_page} < {prev_entry[2]}")

    if next_entry:
        next_num = extract_number_from_title(next_entry[1])
        if next_num > 0 and new_num < next_num and new_page > next_entry[2]:
            issues.append(f"编号{new_num} < {next_num}，但页码{new_page} > {next_entry[2]}")

    if new_level == 2:
        parent = next((e for e in toc if e[0] == 1 and e[2] <= new_page), None)
        if parent and new_page < parent[2]:
            issues.append(f"条页码{new_page} < 所属章页码{parent[2]}")
        elif not parent:
            first_ch = next((e for e in toc if e[0] == 1), None)
            if first_ch and new_page < first_ch[2]:
                issues.append(f"条页码{new_page} < 第一章页码{first_ch[2]}")

    return issues


def validate_gbt_toc(toc: list, new_level: int, new_title: str,
                     new_page: int, new_num: int) -> list:
    """GB/T标准验证 - 宽松"""
    issues = []
    same_level = [e for e in toc if e[0] == new_level]

    if not same_level:
        return issues

    total = sum(e[2] for e in same_level)
    avg = total / len(same_level)
    max_page = max(e[2] for e in same_level)

    if new_page > max_page + 50:
        issues.append(f"页码{new_page}远大于最大页码{max_page}")

    if new_page < avg - 30:
        later = [e for e in same_level if e[2] > new_page + 10]
        if len(later) > len(same_level) / 2:
            issues.append(f"页码{new_page}远小于平均{avg:.0f}")

    return issues


def test_all():
    """运行所有测试"""
    print("=" * 50)
    print("测试数字提取")
    print("=" * 50)
    tests = [
        ("第一章", 1), ("第十二条", 12), ("第一百零一条", 101),
        ("第二十条", 20), ("前言", 0), ("GB/T 7718", 7718),
    ]
    for t, exp in tests:
        r = extract_number_from_title(t)
        print(f"{'✓' if r == exp else '✗'} '{t}' -> {r}")

    print("\n" + "=" * 50)
    print("测试文档类型检测")
    print("=" * 50)
    type_tests = [
        ([[1, "第一章", 1], [2, "第一条", 1]], "legal"),
        ([[1, "前言", 1], [1, "范围", 2]], "gbt"),
        ([[1, "简介", 1]], "unknown"),
    ]
    for toc, exp in type_tests:
        r = detect_doc_type(toc)
        print(f"{'✓' if r == exp else '✗'} {r} (期望: {exp})")

    print("\n" + "=" * 50)
    print("测试法律法规验证")
    print("=" * 50)
    toc = [[1, "第二章", 15], [2, "第十条", 15]]
    issues = validate_legal_toc(toc, 2, "第九条", 16, 9)
    print(f"添加'第九条 第16页': {len(issues)} 个问题")
    for i in issues:
        print(f"  ! {i}")

    print("\n" + "=" * 50)
    print("测试GB/T验证")
    print("=" * 50)
    toc = [[1, "前言", 1], [1, "范围", 2], [1, "技术要求", 5]]
    issues = validate_gbt_toc(toc, 1, "附录A", 100, 0)
    print(f"添加'附录A 第100页': {len(issues)} 个问题")
    for i in issues:
        print(f"  ! {i}")

    print("\n" + "=" * 50)
    print("测试完成!")
    print("=" * 50)


if __name__ == "__main__":
    test_all()
