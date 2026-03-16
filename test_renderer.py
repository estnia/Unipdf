#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for the new renderer modules.

Tests:
1. renderer_base (pure Python, no Qt)
2. qt_renderer (Qt conversion)
3. renderer (backward compatible)
"""

import sys
import os
import time

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("Renderer Module Test")
print("=" * 60)

# Find test PDF
test_pdf = "demo/10中华人民共和国标准化法.pdf"
if not os.path.exists(test_pdf):
    print(f"❌ Test PDF not found: {test_pdf}")
    # Try to find any PDF
    for root, dirs, files in os.walk("demo"):
        for f in files:
            if f.endswith(".pdf") and not f.startswith("._"):
                test_pdf = os.path.join(root, f)
                break
        if os.path.exists(test_pdf):
            break

if not os.path.exists(test_pdf):
    print("❌ No test PDF found in demo directory")
    sys.exit(1)

print(f"Test PDF: {test_pdf}")
print()

# ========================================================================
# Test 1: renderer_base (Pure Python)
# ========================================================================
print("-" * 60)
print("Test 1: renderer_base (Pure Python, no Qt)")
print("-" * 60)

try:
    from pdfviewer.core.renderer_base import (
        render_page_to_pil,
        render_thumbnail_to_pil,
        get_page_text_dict,
        get_document_info,
        extract_page_text,
        HAS_PIL
    )

    print(f"✓ Imports successful (HAS_PIL={HAS_PIL})")

    if not HAS_PIL:
        print("⚠ PIL not available, skipping PIL tests")
    else:
        # Test document info
        print("\nTesting get_document_info()...")
        doc_info = get_document_info(test_pdf)
        print(f"  ✓ Document info: {doc_info['page_count']} pages, title='{doc_info['title'][:20]}...'")

        # Test page info
        from pdfviewer.core.renderer_base import get_page_info
        page_info = get_page_info(test_pdf, 0)
        print(f"  ✓ Page info: {page_info['width']:.1f} x {page_info['height']:.1f} pts")

        # Test text extraction
        print("\nTesting extract_page_text()...")
        text = extract_page_text(test_pdf, 0)
        print(f"  ✓ Extracted {len(text)} characters from page 1")
        if text:
            preview = text[:100].replace('\n', ' ')
            print(f"    Preview: {preview}...")

        # Test PIL rendering
        print("\nTesting render_page_to_pil()...")
        start = time.time()
        pil_image = render_page_to_pil(test_pdf, page_idx=0, zoom=1.0, dpi_scale=1.0)
        elapsed = time.time() - start
        print(f"  ✓ Rendered PIL Image: {pil_image.size[0]}x{pil_image.size[1]} in {elapsed:.3f}s")
        print(f"    Mode: {pil_image.mode}, Format: {pil_image.format or 'N/A'}")

        # Test thumbnail rendering
        print("\nTesting render_thumbnail_to_pil()...")
        thumb = render_thumbnail_to_pil(test_pdf, page_idx=0, max_size=128)
        print(f"  ✓ Rendered thumbnail: {thumb.size[0]}x{thumb.size[1]}")
        assert max(thumb.size) <= 128, "Thumbnail size exceeds max_size"
        print(f"    ✓ Thumbnail size check passed (max <= 128)")

        # Test text dict extraction
        print("\nTesting get_page_text_dict()...")
        text_dict = get_page_text_dict(test_pdf, 0)
        print(f"  ✓ Got text dict with {len(text_dict.get('blocks', []))} blocks")

        # Save test output
        output_path = "/tmp/test_renderer_output.png"
        pil_image.save(output_path)
        print(f"\n  ✓ Saved test image to: {output_path}")

    print("\n✅ renderer_base tests passed!")

except Exception as e:
    print(f"\n❌ renderer_base test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# ========================================================================
# Test 2: qt_renderer (Qt conversion)
# ========================================================================
print("-" * 60)
print("Test 2: qt_renderer (Qt conversion)")
print("-" * 60)

try:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QPixmap

    # Need QApplication for Qt
    app = QApplication.instance() or QApplication(sys.argv)

    from pdfviewer.ui.qt_renderer import (
        pil_to_qpixmap,
        pil_to_qimage,
        render_page_to_pixmap,
        render_thumbnail_to_pixmap,
        HAS_PIL
    )

    print(f"✓ Imports successful (HAS_PIL={HAS_PIL})")

    if HAS_PIL:
        # Test PIL to QPixmap conversion
        print("\nTesting pil_to_qpixmap()...")
        pil_img = render_page_to_pil(test_pdf, 0, zoom=1.0)
        qpixmap = pil_to_qpixmap(pil_img)
        print(f"  ✓ Converted PIL {pil_img.size} → QPixmap {qpixmap.width()}x{qpixmap.height()}")

        # Test PIL to QImage conversion
        print("\nTesting pil_to_qimage()...")
        qimage = pil_to_qimage(pil_img)
        print(f"  ✓ Converted PIL → QImage {qimage.width()}x{qimage.height()}")

        # Test direct render to QPixmap
        print("\nTesting render_page_to_pixmap()...")
        start = time.time()
        qpixmap = render_page_to_pixmap(test_pdf, page_idx=0, zoom=1.5)
        elapsed = time.time() - start
        print(f"  ✓ Rendered QPixmap: {qpixmap.width()}x{qpixmap.height()} in {elapsed:.3f}s")

        # Test thumbnail
        print("\nTesting render_thumbnail_to_pixmap()...")
        thumb_pixmap = render_thumbnail_to_pixmap(test_pdf, page_idx=0, max_size=128)
        print(f"  ✓ Rendered thumbnail: {thumb_pixmap.width()}x{thumb_pixmap.height()}")

        # Test QImage to PIL (roundtrip)
        print("\nTesting qimage_to_pil() roundtrip...")
        from pdfviewer.ui.qt_renderer import qimage_to_pil
        qimage = pil_to_qimage(pil_img)
        pil_roundtrip = qimage_to_pil(qimage)
        print(f"  ✓ Roundtrip: PIL {pil_img.size} → QImage → PIL {pil_roundtrip.size}")
        assert pil_img.size == pil_roundtrip.size, "Size mismatch after roundtrip"
        print(f"    ✓ Size preserved correctly")

    print("\n✅ qt_renderer tests passed!")

except Exception as e:
    print(f"\n❌ qt_renderer test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# ========================================================================
# Test 3: renderer (backward compatible)
# ========================================================================
print("-" * 60)
print("Test 3: renderer (backward compatible)")
print("-" * 60)

try:
    try:
        import fitz
    except ImportError:
        import pymupdf as fitz

    from pdfviewer.core.renderer import (
        render_page,
        render_thumbnail,
        render_page_to_image,
        get_page_text_dict
    )

    print("✓ Imports successful")

    # Test with fitz.Document (legacy path)
    print("\nTesting render_page() with fitz.Document...")
    doc = fitz.open(test_pdf)
    try:
        start = time.time()
        qpixmap = render_page(doc, page_idx=0, zoom=1.0)
        elapsed = time.time() - start
        print(f"  ✓ Rendered: {qpixmap.width()}x{qpixmap.height()} in {elapsed:.3f}s (legacy path)")
    finally:
        doc.close()

    # Test with string path (new path)
    print("\nTesting render_page() with string path...")
    start = time.time()
    qpixmap = render_page(test_pdf, page_idx=0, zoom=1.0)
    elapsed = time.time() - start
    print(f"  ✓ Rendered: {qpixmap.width()}x{qpixmap.height()} in {elapsed:.3f}s (new path)")

    # Test render_thumbnail
    print("\nTesting render_thumbnail()...")
    thumb = render_thumbnail(test_pdf, page_idx=0, max_size=128)
    print(f"  ✓ Thumbnail: {thumb.width()}x{thumb.height()}")

    # Test render_page_to_image
    print("\nTesting render_page_to_image()...")
    qimage = render_page_to_image(test_pdf, page_idx=0, zoom=1.0)
    print(f"  ✓ QImage: {qimage.width()}x{qimage.height()}")

    # Test text functions (backward compatible)
    print("\nTesting get_page_text_dict()...")
    doc = fitz.open(test_pdf)
    try:
        text_dict = get_page_text_dict(doc, 0)
        print(f"  ✓ Got text dict with {len(text_dict.get('blocks', []))} blocks (legacy path)")
    finally:
        doc.close()

    # Test with string
    text_dict = get_page_text_dict(test_pdf, 0)
    print(f"  ✓ Got text dict with {len(text_dict.get('blocks', []))} blocks (new path)")

    print("\n✅ renderer (backward compatible) tests passed!")

except Exception as e:
    print(f"\n❌ renderer test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# ========================================================================
# Test 4: Performance comparison
# ========================================================================
print("-" * 60)
print("Test 4: Performance comparison")
print("-" * 60)

if HAS_PIL:
    try:
        try:
            import fitz
        except ImportError:
            import pymupdf as fitz

        # Legacy path: fitz.Document → QPixmap
        print("\nLegacy path (fitz.Document → QPixmap):")
        doc = fitz.open(test_pdf)
        try:
            times = []
            for i in range(3):
                start = time.time()
                pix = render_page(doc, page_idx=0, zoom=1.0)
                times.append(time.time() - start)
            avg_time = sum(times) / len(times)
            print(f"  Average: {avg_time:.3f}s (over 3 runs)")
        finally:
            doc.close()

        # New path: string → PIL → QPixmap
        print("\nNew path (string → PIL → QPixmap):")
        times = []
        for i in range(3):
            start = time.time()
            qpixmap = render_page_to_pixmap(test_pdf, page_idx=0, zoom=1.0)
            times.append(time.time() - start)
        avg_time = sum(times) / len(times)
        print(f"  Average: {avg_time:.3f}s (over 3 runs)")

        print("\n✅ Performance comparison complete")

    except Exception as e:
        print(f"⚠ Performance test skipped: {e}")

print()

# ========================================================================
# Summary
# ========================================================================
print("=" * 60)
print("Test Summary")
print("=" * 60)
print("✅ renderer_base: Pure Python rendering - PASSED")
print("✅ qt_renderer: Qt conversion utilities - PASSED")
print("✅ renderer: Backward compatible wrapper - PASSED")
print()
print("All renderer module tests passed successfully!")
print("=" * 60)
