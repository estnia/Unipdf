#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memory Manager - 内存管理服务

提供内存监控、自动清理和阈值管理功能，
防止大文档处理时出现内存不足问题。
"""

import gc
import os
from typing import Optional, Dict

# PDF engine
try:
    import fitz
except ImportError:
    import pymupdf as fitz

# 尝试导入 psutil，如未安装则使用备用方案
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class MemoryManager:
    """
    内存管理器

    监控应用程序内存使用情况，在超过阈值时自动触发清理。
    支持配置阈值、自定义清理回调和内存统计信息。

    Example:
        manager = MemoryManager(threshold_mb=500)
        if manager.check_and_cleanup():
            print("内存清理已触发")

        # 获取内存信息
        info = manager.get_memory_info()
        print(f"当前使用: {info['rss_mb']:.1f} MB")
    """

    def __init__(self, threshold_mb: int = 500, critical_mb: int = 1000):
        """
        初始化内存管理器

        Args:
            threshold_mb: 警告阈值（MB），超过时触发清理
            critical_mb: 危险阈值（MB），超过时强制清理
        """
        self._threshold = threshold_mb * 1024 * 1024  # 转换为字节
        self._critical = critical_mb * 1024 * 1024
        self._cleanup_hooks = []
        self._last_cleanup_rss = 0

    def add_cleanup_hook(self, callback):
        """添加清理钩子函数"""
        self._cleanup_hooks.append(callback)

    def remove_cleanup_hook(self, callback):
        """移除清理钩子函数"""
        if callback in self._cleanup_hooks:
            self._cleanup_hooks.remove(callback)

    def check_and_cleanup(self, force: bool = False) -> bool:
        """
        检查内存使用情况并触发清理

        Args:
            force: 是否强制清理，忽略阈值

        Returns:
            True 表示已触发清理，False 表示未达到阈值
        """
        current_rss = self._get_rss_bytes()

        # 检查是否超过危险阈值
        if current_rss > self._critical or force:
            self._do_cleanup(aggressive=True)
            return True

        # 检查是否超过警告阈值
        if current_rss > self._threshold:
            self._do_cleanup(aggressive=False)
            return True

        return False

    def _do_cleanup(self, aggressive: bool = False):
        """执行内存清理"""
        # 清理 fitz 内部缓存
        try:
            if aggressive:
                fitz.TOOLS.store_shrink(100)
                fitz.TOOLS.gc_alloc(1)
            else:
                fitz.TOOLS.store_shrink(100)
        except Exception:
            pass

        # 执行 Python GC
        gc.collect()
        if aggressive:
            gc.collect(1)  # 清理一代对象
            gc.collect(2)  # 清理二代对象

        # 调用外部清理钩子
        for hook in self._cleanup_hooks:
            try:
                hook(aggressive=aggressive)
            except Exception:
                pass

        # 记录清理后内存
        self._last_cleanup_rss = self._get_rss_bytes()

    def get_memory_info(self) -> Dict:
        """
        获取内存使用信息

        Returns:
            包含内存统计信息的字典
        """
        if HAS_PSUTIL:
            try:
                process = psutil.Process(os.getpid())
                mem_info = process.memory_info()
                return {
                    'rss_mb': mem_info.rss / 1024 / 1024,
                    'vms_mb': mem_info.vms / 1024 / 1024,
                    'percent': process.memory_percent(),
                    'threshold_mb': self._threshold / 1024 / 1024,
                    'critical_mb': self._critical / 1024 / 1024,
                    'is_available': True
                }
            except Exception:
                pass

        # 备用方案（Linux）
        try:
            with open(f'/proc/{os.getpid()}/status', 'r') as f:
                content = f.read()
                vmrss = self._parse_proc_status(content, 'VmRSS')
                if vmrss:
                    return {
                        'rss_mb': vmrss / 1024,
                        'vms_mb': 0,
                        'percent': 0,
                        'threshold_mb': self._threshold / 1024 / 1024,
                        'critical_mb': self._critical / 1024 / 1024,
                        'is_available': True
                    }
        except Exception:
            pass

        return {
            'rss_mb': 0,
            'vms_mb': 0,
            'percent': 0,
            'threshold_mb': self._threshold / 1024 / 1024,
            'critical_mb': self._critical / 1024 / 1024,
            'is_available': False
        }

    def _get_rss_bytes(self) -> int:
        """获取当前 RSS 内存（字节）"""
        if HAS_PSUTIL:
            try:
                process = psutil.Process(os.getpid())
                return process.memory_info().rss
            except Exception:
                pass

        # 备用方案（Linux）
        try:
            with open(f'/proc/{os.getpid()}/status', 'r') as f:
                content = f.read()
                vmrss = self._parse_proc_status(content, 'VmRSS')
                if vmrss:
                    return vmrss * 1024
        except Exception:
            pass

        return 0

    @staticmethod
    def _parse_proc_status(content: str, key: str) -> Optional[int]:
        """解析 /proc/pid/status 内容"""
        for line in content.split('\n'):
            if line.startswith(f'{key}:'):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        return int(parts[1])  # KB
                    except ValueError:
                        pass
        return None

    def get_system_memory(self) -> Dict:
        """获取系统总内存信息"""
        if HAS_PSUTIL:
            try:
                mem = psutil.virtual_memory()
                return {
                    'total_mb': mem.total / 1024 / 1024,
                    'available_mb': mem.available / 1024 / 1024,
                    'percent': mem.percent,
                    'is_available': True
                }
            except Exception:
                pass

        return {
            'total_mb': 0,
            'available_mb': 0,
            'percent': 0,
            'is_available': False
        }

    @property
    def threshold_mb(self) -> int:
        """获取当前阈值（MB）"""
        return int(self._threshold / 1024 / 1024)

    @threshold_mb.setter
    def threshold_mb(self, value: int):
        """设置阈值（MB）"""
        self._threshold = value * 1024 * 1024

    @property
    def critical_mb(self) -> int:
        """获取当前危险阈值（MB）"""
        return int(self._critical / 1024 / 1024)

    @critical_mb.setter
    def critical_mb(self, value: int):
        """设置危险阈值（MB）"""
        self._critical = value * 1024 * 1024


def get_cache_config_by_memory() -> Dict[str, int]:
    """
    根据系统内存大小返回推荐的缓存配置

    Returns:
        {'max_outer': int, 'max_inner': int, 'base_cache': int}
    """
    if HAS_PSUTIL:
        try:
            total_mb = psutil.virtual_memory().total / 1024 / 1024

            if total_mb < 4096:  # < 4GB
                return {
                    'max_outer': 5,
                    'max_inner': 25,
                    'base_cache': 50
                }
            elif total_mb < 8192:  # 4-8GB
                return {
                    'max_outer': 10,
                    'max_inner': 50,
                    'base_cache': 100
                }
            else:  # > 8GB
                return {
                    'max_outer': 15,
                    'max_inner': 75,
                    'base_cache': 150
                }
        except Exception:
            pass

    # 默认配置（保守模式）
    return {
        'max_outer': 5,
        'max_inner': 25,
        'base_cache': 50
    }
