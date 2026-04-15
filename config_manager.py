#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块 - 统一管理应用程序配置

功能说明:
    - 配置加载和保存
    - 配置验证
    - 默认值管理
    - 配置迁移

作者: Gavin
版本: 1.0.0
日期: 2026-02-06
"""

from PySide6.QtCore import QSettings
from typing import Any, Dict, Optional, List
import logging

# 配置日志
logger = logging.getLogger(__name__)


class ConfigManager:
    """
    配置管理器类
    
    统一管理应用程序的所有配置项
    """
    
    # 默认配置值
    DEFAULTS = {
        # 串口设置
        'serial': {
            'baud_index': 10,  # 115200
            'data_bits_index': 0,  # 8位
            'parity_index': 0,  # 无校验
            'stop_bits_index': 0,  # 1位
            'flow_control': 'none',
            'timeout': 1.0,
            'rts_enabled': False,
            'dtr_enabled': False,
        },
        # 显示设置
        'display': {
            'show_hex': False,
            'show_timestamp': False,
            'auto_scroll': True,
            'font_size': 10,
            'color_scheme': 'Zenburn',
        },
        # 发送设置
        'send': {
            'hex_mode': False,
            'append_newline': True,
            'timer_interval_ms': 1000,
        },
        # 日志设置
        'logging': {
            'enabled': True,
            'filename_template': 'C:/Logs/%Y-%M-%D_%h-%m-%s.log',
            'chunk_size_kb': 512,
            'midnight_rollover': True,
        },
        # 监控设置
        'monitor': {
            'enabled': True,
            'interval_ms': 5000,
            'memory_warning_mb': 512,
            'memory_critical_mb': 1024,
            'cpu_warning_percent': 50,
            'cpu_critical_percent': 80,
        },
        # 自动重连设置
        'auto_reconnect': {
            'enabled': False,
            'max_attempts': 3,
            'interval_ms': 2000,
        },
    }
    
    def __init__(self, organization: str = "Gavin", application: str = "Gavin_com"):
        """
        初始化配置管理器
        
        Args:
            organization: 组织名称
            application: 应用程序名称
        """
        self.settings = QSettings(QSettings.IniFormat, QSettings.UserScope, 
                                  organization, application)
        self._cache: Dict[str, Any] = {}
        self._modified_keys: set = set()
        
    def get(self, key: str, default: Any = None, group: str = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键名
            default: 默认值
            group: 配置组名
            
        Returns:
            配置值
        """
        cache_key = f"{group}/{key}" if group else key
        
        # 先从缓存获取
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # 从QSettings获取
        full_key = f"{group}/{key}" if group else key
        value = self.settings.value(full_key, default)
        
        # 缓存值
        self._cache[cache_key] = value
        
        return value
    
    def set(self, key: str, value: Any, group: str = None):
        """
        设置配置值
        
        Args:
            key: 配置键名
            value: 配置值
            group: 配置组名
        """
        cache_key = f"{group}/{key}" if group else key
        full_key = f"{group}/{key}" if group else key
        
        # 更新缓存
        self._cache[cache_key] = value
        self._modified_keys.add(cache_key)
        
        # 写入QSettings
        self.settings.setValue(full_key, value)
        
    def get_group(self, group: str) -> Dict[str, Any]:
        """
        获取整个配置组
        
        Args:
            group: 配置组名
            
        Returns:
            配置字典
        """
        if group in self.DEFAULTS:
            result = self.DEFAULTS[group].copy()
            
            # 从QSettings加载已保存的值
            self.settings.beginGroup(group)
            for key in self.settings.allKeys():
                result[key] = self.settings.value(key)
            self.settings.endGroup()
            
            return result
        
        return {}
    
    def set_group(self, group: str, values: Dict[str, Any]):
        """
        设置整个配置组
        
        Args:
            group: 配置组名
            values: 配置字典
        """
        self.settings.beginGroup(group)
        for key, value in values.items():
            self.settings.setValue(key, value)
            cache_key = f"{group}/{key}"
            self._cache[cache_key] = value
            self._modified_keys.add(cache_key)
        self.settings.endGroup()
        
    def save(self):
        """保存所有修改的配置"""
        self.settings.sync()
        self._modified_keys.clear()
        logger.debug(f"配置已保存，共 {len(self._cache)} 项")
        
    def load_defaults(self):
        """加载默认配置"""
        for group, values in self.DEFAULTS.items():
            for key, value in values.items():
                cache_key = f"{group}/{key}"
                if cache_key not in self._cache:
                    self._cache[cache_key] = value
                    
        logger.debug("默认配置已加载")
        
    def reset_to_defaults(self, group: str = None):
        """
        重置为默认配置
        
        Args:
            group: 配置组名，None表示全部重置
        """
        if group:
            if group in self.DEFAULTS:
                self.set_group(group, self.DEFAULTS[group])
                logger.info(f"配置组 '{group}' 已重置为默认值")
        else:
            for g, values in self.DEFAULTS.items():
                self.set_group(g, values)
            logger.info("所有配置已重置为默认值")
            
    def get_modified_keys(self) -> List[str]:
        """获取已修改的配置键列表"""
        return list(self._modified_keys)
    
    def is_modified(self) -> bool:
        """检查是否有未保存的修改"""
        return len(self._modified_keys) > 0
    
    def clear_cache(self):
        """清除配置缓存"""
        self._cache.clear()
        self._modified_keys.clear()
        
    def export_config(self) -> Dict[str, Any]:
        """
        导出所有配置
        
        Returns:
            配置字典
        """
        config = {}
        
        for group in self.DEFAULTS.keys():
            config[group] = self.get_group(group)
            
        return config
    
    def import_config(self, config: Dict[str, Any]):
        """
        导入配置
        
        Args:
            config: 配置字典
        """
        for group, values in config.items():
            if isinstance(values, dict):
                self.set_group(group, values)
                
        logger.info("配置已导入")


# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None


def init_config(organization: str = "Gavin", application: str = "Gavin_com") -> ConfigManager:
    """
    初始化全局配置管理器
    
    Args:
        organization: 组织名称
        application: 应用程序名称
        
    Returns:
        ConfigManager: 配置管理器实例
    """
    global _config_manager
    
    if _config_manager is None:
        _config_manager = ConfigManager(organization, application)
        _config_manager.load_defaults()
        logger.info("全局配置管理器已初始化")
    
    return _config_manager


def get_config() -> Optional[ConfigManager]:
    """获取全局配置管理器"""
    return _config_manager


def get_setting(key: str, default: Any = None, group: str = None) -> Any:
    """
    便捷函数：获取配置值
    
    Args:
        key: 配置键名
        default: 默认值
        group: 配置组名
        
    Returns:
        配置值
    """
    if _config_manager:
        return _config_manager.get(key, default, group)
    return default


def set_setting(key: str, value: Any, group: str = None):
    """
    便捷函数：设置配置值
    
    Args:
        key: 配置键名
        value: 配置值
        group: 配置组名
    """
    if _config_manager:
        _config_manager.set(key, value, group)
