#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统监控模块 - 提供内存和性能监控功能

功能说明:
    - 内存使用监控
    - CPU占用监控
    - 性能统计
    - 资源告警

作者: Gavin
版本: 1.0.0
日期: 2026-02-06
"""

import psutil
import logging
import threading
from typing import Optional, Callable, Dict
from dataclasses import dataclass, field
from datetime import datetime
from PySide6.QtCore import QObject, Signal, QTimer

# 配置日志
logger = logging.getLogger(__name__)


@dataclass
class SystemStats:
    """系统统计信息数据类"""
    timestamp: datetime = field(default_factory=datetime.now)
    memory_used_mb: float = 0.0
    memory_percent: float = 0.0
    cpu_percent: float = 0.0
    thread_count: int = 0
    handle_count: int = 0
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'memory_used_mb': round(self.memory_used_mb, 2),
            'memory_percent': round(self.memory_percent, 2),
            'cpu_percent': round(self.cpu_percent, 2),
            'thread_count': self.thread_count,
            'handle_count': self.handle_count
        }


@dataclass
class PerformanceThresholds:
    """性能阈值配置"""
    memory_warning_mb: float = 512.0      # 内存警告阈值(MB)
    memory_critical_mb: float = 1024.0    # 内存严重阈值(MB)
    memory_warning_percent: float = 70.0   # 内存百分比警告阈值
    memory_critical_percent: float = 85.0  # 内存百分比严重阈值
    cpu_warning_percent: float = 50.0      # CPU警告阈值
    cpu_critical_percent: float = 80.0     # CPU严重阈值


class SystemMonitor(QObject):
    """
    系统监控器类
    
    功能:
        - 实时监控系统资源使用
        - 性能阈值告警
        - 统计数据收集
    
    信号:
        statsUpdated: 统计更新信号
        memoryWarning: 内存警告信号
        memoryCritical: 内存严重告警信号
        cpuWarning: CPU警告信号
        cpuCritical: CPU严重告警信号
    """
    
    # 定义信号
    statsUpdated = Signal(object)  # SystemStats
    memoryWarning = Signal(float, float)  # used_mb, percent
    memoryCritical = Signal(float, float)  # used_mb, percent
    cpuWarning = Signal(float)  # percent
    cpuCritical = Signal(float)  # percent
    
    def __init__(self, parent=None, interval_ms: int = 5000):
        """
        初始化系统监控器
        
        Args:
            parent: 父对象
            interval_ms: 监控间隔（毫秒）
        """
        super().__init__(parent)
        
        self._interval_ms = max(1000, interval_ms)
        self._thresholds = PerformanceThresholds()
        self._timer = QTimer()
        self._timer.timeout.connect(self._collect_stats)
        self._running = False
        
        # 历史数据
        self._history: list[SystemStats] = []
        self._max_history_size = 100
        self._history_lock = threading.Lock()
        
        # 告警状态（防止重复告警）
        self._memory_warning_sent = False
        self._memory_critical_sent = False
        self._cpu_warning_sent = False
        self._cpu_critical_sent = False
        
        # 进程对象
        self._process: Optional[psutil.Process] = None
        try:
            self._process = psutil.Process()
        except Exception as e:
            logger.error(f"获取进程对象失败: {e}")
    
    def start(self):
        """启动监控"""
        if not self._running:
            self._running = True
            self._timer.start(self._interval_ms)
            logger.info(f"系统监控已启动，间隔: {self._interval_ms}ms")
    
    def stop(self):
        """停止监控"""
        if self._running:
            self._running = False
            self._timer.stop()
            logger.info("系统监控已停止")
    
    def set_interval(self, interval_ms: int):
        """设置监控间隔"""
        self._interval_ms = max(1000, interval_ms)
        if self._running:
            self._timer.stop()
            self._timer.start(self._interval_ms)
    
    def set_thresholds(self, thresholds: PerformanceThresholds):
        """设置性能阈值"""
        self._thresholds = thresholds
        logger.debug("性能阈值已更新")
    
    def _collect_stats(self):
        """收集系统统计信息"""
        try:
            stats = SystemStats()
            stats.timestamp = datetime.now()
            
            if self._process:
                # 获取内存信息
                mem_info = self._process.memory_info()
                stats.memory_used_mb = mem_info.rss / (1024 * 1024)
                stats.memory_percent = self._process.memory_percent()
                
                # 获取CPU信息
                stats.cpu_percent = self._process.cpu_percent(interval=None)
                
                # 获取线程和句柄数
                stats.thread_count = self._process.num_threads()
                try:
                    stats.handle_count = self._process.num_handles()
                except Exception:
                    stats.handle_count = 0
            
            # 保存历史
            with self._history_lock:
                self._history.append(stats)
                if len(self._history) > self._max_history_size:
                    self._history.pop(0)
            
            # 发送统计更新信号
            self.statsUpdated.emit(stats)
            
            # 检查阈值
            self._check_thresholds(stats)
            
        except Exception as e:
            logger.error(f"收集统计信息失败: {e}")
    
    def _check_thresholds(self, stats: SystemStats):
        """检查性能阈值"""
        # 内存检查
        if stats.memory_used_mb >= self._thresholds.memory_critical_mb or \
           stats.memory_percent >= self._thresholds.memory_critical_percent:
            if not self._memory_critical_sent:
                self._memory_critical_sent = True
                self.memoryCritical.emit(stats.memory_used_mb, stats.memory_percent)
                logger.warning(f"内存严重告警: {stats.memory_used_mb:.1f}MB ({stats.memory_percent:.1f}%)")
        elif stats.memory_used_mb >= self._thresholds.memory_warning_mb or \
             stats.memory_percent >= self._thresholds.memory_warning_percent:
            if not self._memory_warning_sent:
                self._memory_warning_sent = True
                self.memoryWarning.emit(stats.memory_used_mb, stats.memory_percent)
                logger.warning(f"内存警告: {stats.memory_used_mb:.1f}MB ({stats.memory_percent:.1f}%)")
        else:
            # 重置告警状态
            self._memory_warning_sent = False
            self._memory_critical_sent = False
        
        # CPU检查
        if stats.cpu_percent >= self._thresholds.cpu_critical_percent:
            if not self._cpu_critical_sent:
                self._cpu_critical_sent = True
                self.cpuCritical.emit(stats.cpu_percent)
                logger.warning(f"CPU严重告警: {stats.cpu_percent:.1f}%")
        elif stats.cpu_percent >= self._thresholds.cpu_warning_percent:
            if not self._cpu_warning_sent:
                self._cpu_warning_sent = True
                self.cpuWarning.emit(stats.cpu_percent)
                logger.warning(f"CPU警告: {stats.cpu_percent:.1f}%")
        else:
            self._cpu_warning_sent = False
            self._cpu_critical_sent = False
    
    def get_current_stats(self) -> Optional[SystemStats]:
        """获取当前统计信息"""
        with self._history_lock:
            return self._history[-1] if self._history else None
    
    def get_history(self, count: int = 0) -> list[SystemStats]:
        """
        获取历史统计信息
        
        Args:
            count: 返回数量（0表示全部）
            
        Returns:
            list: 历史统计列表
        """
        with self._history_lock:
            if count <= 0:
                return self._history.copy()
            return self._history[-count:].copy()
    
    def get_average_stats(self, seconds: int = 60) -> Optional[SystemStats]:
        """
        获取平均统计信息
        
        Args:
            seconds: 时间范围（秒）
            
        Returns:
            SystemStats: 平均统计信息
        """
        with self._history_lock:
            if not self._history:
                return None
            
            now = datetime.now()
            recent_stats = [
                s for s in self._history 
                if (now - s.timestamp).total_seconds() <= seconds
            ]
            
            if not recent_stats:
                return None
            
            avg = SystemStats()
            avg.memory_used_mb = sum(s.memory_used_mb for s in recent_stats) / len(recent_stats)
            avg.memory_percent = sum(s.memory_percent for s in recent_stats) / len(recent_stats)
            avg.cpu_percent = sum(s.cpu_percent for s in recent_stats) / len(recent_stats)
            avg.thread_count = recent_stats[-1].thread_count
            avg.handle_count = recent_stats[-1].handle_count
            
            return avg
    
    def reset_thresholds(self):
        """重置告警状态"""
        self._memory_warning_sent = False
        self._memory_critical_sent = False
        self._cpu_warning_sent = False
        self._cpu_critical_sent = False
        logger.debug("告警状态已重置")


class ResourceManager:
    """
    资源管理器类
    
    功能:
        - 内存优化
        - 垃圾回收
        - 资源清理
    """
    
    def __init__(self):
        self._gc_threshold_mb = 256
        self._last_gc_memory = 0
    
    def check_and_optimize(self, current_memory_mb: float) -> bool:
        """
        检查并执行内存优化
        
        Args:
            current_memory_mb: 当前内存使用（MB）
            
        Returns:
            bool: 是否执行了优化
        """
        optimized = False
        
        # 检查是否需要垃圾回收
        if current_memory_mb > self._gc_threshold_mb:
            if current_memory_mb - self._last_gc_memory > 50:  # 增加超过50MB
                import gc
                gc.collect()
                self._last_gc_memory = current_memory_mb
                optimized = True
                logger.info("执行垃圾回收")
        
        return optimized
    
    def force_gc(self):
        """强制垃圾回收"""
        import gc
        gc.collect()
        logger.info("强制垃圾回收已执行")
    
    def get_memory_info(self) -> Dict:
        """获取内存信息"""
        try:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            
            return {
                'rss_mb': mem_info.rss / (1024 * 1024),
                'vms_mb': mem_info.vms / (1024 * 1024),
                'percent': process.memory_percent(),
                'available_mb': psutil.virtual_memory().available / (1024 * 1024)
            }
        except Exception as e:
            logger.error(f"获取内存信息失败: {e}")
            return {}


# 全局监控器实例
_global_monitor: Optional[SystemMonitor] = None
_global_resource_manager: Optional[ResourceManager] = None


def init_monitor(parent=None, interval_ms: int = 5000) -> SystemMonitor:
    """
    初始化全局监控器
    
    Args:
        parent: 父对象
        interval_ms: 监控间隔
        
    Returns:
        SystemMonitor: 监控器实例
    """
    global _global_monitor, _global_resource_manager
    
    if _global_monitor is None:
        _global_monitor = SystemMonitor(parent, interval_ms)
        _global_resource_manager = ResourceManager()
        logger.info("全局监控器已初始化")
    
    return _global_monitor


def get_monitor() -> Optional[SystemMonitor]:
    """获取全局监控器"""
    return _global_monitor


def get_resource_manager() -> Optional[ResourceManager]:
    """获取资源管理器"""
    return _global_resource_manager


def start_monitoring():
    """启动监控"""
    if _global_monitor:
        _global_monitor.start()


def stop_monitoring():
    """停止监控"""
    if _global_monitor:
        _global_monitor.stop()
