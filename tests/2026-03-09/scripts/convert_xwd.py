#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XWD 文件读取器 - 将 XWD 转换为 PNG
"""

import struct
import sys

from PIL import Image


def read_xwd(filename):
    """读取 XWD 文件并返回 PIL Image"""
    with open(filename, 'rb') as f:
        data = f.read()

    # XWD 文件头部结构 (C 结构体)
    # struct xwd_file_header {
    #     unsigned int header_size;       # 4 bytes - 头部大小
    #     unsigned int file_version;      # 4 bytes - 版本号 (通常为 7)
    #     unsigned int pixmap_format;     # 4 bytes - 像素图格式
    #     unsigned int pixmap_depth;      # 4 bytes - 像素图深度
    #     unsigned int pixmap_width;      # 4 bytes - 宽度
    #     unsigned int pixmap_height;     # 4 bytes - 高度
    #     ... 更多字段
    # }

    # 读取头部基本信息
    header_size = struct.unpack('>I', data[0:4])[0]  # 大端序
    version = struct.unpack('>I', data[4:8])[0]

    if version != 7:
        # 尝试小端序
        header_size = struct.unpack('<I', data[0:4])[0]
        version = struct.unpack('<I', data[4:8])[0]
        endian = '<'
    else:
        endian = '>'

    print(f"XWD 版本: {version}")
    print(f"头部大小: {header_size}")

    # 读取更多头部信息
    pixmap_format = struct.unpack(endian + 'I', data[8:12])[0]
    pixmap_depth = struct.unpack(endian + 'I', data[12:16])[0]
    pixmap_width = struct.unpack(endian + 'I', data[16:20])[0]
    pixmap_height = struct.unpack(endian + 'I', data[20:24])[0]

    print(f"图像尺寸: {pixmap_width}x{pixmap_height}")
    print(f"像素深度: {pixmap_depth}")
    print(f"像素格式: {pixmap_format}")

    # 跳过头部的颜色表和其他元数据
    # XWD 文件结构: 头部 + 颜色表 + 像素数据

    # 读取 xoffset, byte_order, bitmap_unit 等
    xoffset = struct.unpack(endian + 'I', data[24:28])[0]
    byte_order = struct.unpack(endian + 'I', data[28:32])[0]
    bitmap_unit = struct.unpack(endian + 'I', data[32:36])[0]
    bitmap_bit_order = struct.unpack(endian + 'I', data[36:40])[0]
    bitmap_pad = struct.unpack(endian + 'I', data[40:44])[0]
    bits_per_pixel = struct.unpack(endian + 'I', data[44:48])[0]
    bytes_per_line = struct.unpack(endian + 'I', data[48:52])[0]
    visual_class = struct.unpack(endian + 'I', data[52:56])[0]
    red_mask = struct.unpack(endian + 'I', data[56:60])[0]
    green_mask = struct.unpack(endian + 'I', data[60:64])[0]
    blue_mask = struct.unpack(endian + 'I', data[64:68])[0]
    bits_per_rgb = struct.unpack(endian + 'I', data[68:72])[0]
    colormap_entries = struct.unpack(endian + 'I', data[72:76])[0]
    ncolors = struct.unpack(endian + 'I', data[76:80])[0]
    window_width = struct.unpack(endian + 'I', data[80:84])[0]
    window_height = struct.unpack(endian + 'I', data[84:88])[0]
    window_x = struct.unpack(endian + 'I', data[88:92])[0]
    window_y = struct.unpack(endian + 'I', data[92:96])[0]
    window_bdrwidth = struct.unpack(endian + 'I', data[96:100])[0]

    print(f"每像素位数: {bits_per_pixel}")
    print(f"每行字节数: {bytes_per_line}")
    print(f"颜色数: {ncolors}")

    # 计算像素数据起始位置
    # 头部后面是窗口名称字符串，然后是颜色表，最后是像素数据

    # 读取窗口名称 (以 null 结尾的字符串)
    name_start = 100  # 固定头部之后
    name_end = data.find(b'\x00', name_start)
    window_name = data[name_start:name_end].decode('utf-8', errors='ignore') if name_end > name_start else ""
    print(f"窗口名称: {window_name}")

    # 颜色表在窗口名称之后
    colormap_start = name_end + 1 if name_end > 0 else header_size
    # 对齐到 4 字节边界
    colormap_start = (colormap_start + 3) & ~3

    # 像素数据在颜色表之后
    pixel_data_start = colormap_start + ncolors * 12  # 每个颜色表项 12 字节

    print(f"像素数据起始: {pixel_data_start}")

    # 提取像素数据
    pixel_data = data[pixel_data_start:]

    # 创建图像
    if bits_per_pixel == 24 or bits_per_pixel == 32:
        # RGB/RGBA 数据
        mode = 'RGB' if bits_per_pixel == 24 else 'RGBA'

        # 计算实际的行字节数
        actual_bytes_per_line = bytes_per_line if bytes_per_line > 0 else pixmap_width * (bits_per_pixel // 8)

        # 创建图像
        img = Image.new('RGB', (pixmap_width, pixmap_height))
        pixels = img.load()

        # 解析像素数据 (BGR 格式，需要转换为 RGB)
        for y in range(pixmap_height):
            for x in range(pixmap_width):
                offset = pixel_data_start + y * actual_bytes_per_line + x * 4

                if offset + 4 > len(data):
                    continue

                # 读取 BGRA
                b, g, r, a = data[offset:offset+4]
                pixels[x, y] = (r, g, b)

        return img
    else:
        raise ValueError(f"不支持的像素深度: {bits_per_pixel}")


def main():
    input_file = "/tmp/test_screenshot.xwd"
    output_file = "/home/feifei/Unipdf/screenshot_test.png"

    print(f"读取 XWD 文件: {input_file}")
    print("-" * 50)

    try:
        img = read_xwd(input_file)
        img.save(output_file, "PNG")
        print("-" * 50)
        print(f"✅ 已保存: {output_file}")
        print(f"   尺寸: {img.size}")
        return 0
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
