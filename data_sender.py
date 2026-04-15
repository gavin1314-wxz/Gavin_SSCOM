#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据发送模块 - 统一的数据发送接口

功能说明:
    - 统一的数据发送接口
    - 支持文本/HEX模式
    - 支持转义序列处理
    - 支持换行符控制
    - 发送统计和回显

作者: Gavin
版本: 1.0.0
日期: 2026-02-06
"""

import logging
from typing import Optional, Tuple
from PySide6.QtWidgets import QMessageBox

# 配置日志
logger = logging.getLogger(__name__)


class DataSender:
    """
    数据发送器类
    
    提供统一的数据发送接口，支持多种发送模式
    """
    
    def __init__(self, ui_thread_obj, ui_obj, main_window):
        """
        初始化数据发送器
        
        Args:
            ui_thread_obj: UI线程对象
            ui_obj: UI对象
            main_window: 主窗口对象
        """
        self.uithreadObj = ui_thread_obj
        self.ui = ui_obj
        self.MainWindow = main_window
        
    def is_port_open(self) -> bool:
        """检查串口是否已打开"""
        try:
            return self.ui.bt_open_off_port.text() == '关闭串口'
        except Exception:
            return False
    
    def send_data(self, text: str, is_hex: bool = False, 
                  append_newline: bool = True, 
                  process_escapes: bool = False) -> Optional[bytes]:
        """
        统一的数据发送接口
        
        Args:
            text: 要发送的文本
            is_hex: 是否为HEX模式
            append_newline: 是否追加换行符
            process_escapes: 是否处理转义序列
            
        Returns:
            bytes: 发送的字节数据，失败返回None
        """
        if not self.is_port_open():
            logger.warning("串口未打开，无法发送数据")
            return None
        
        try:
            buff = text.strip()
            
            if not is_hex:
                # 文本模式
                if process_escapes:
                    buff = self._replace_escape_sequences(buff)
                
                data = buff.encode('utf-8')
                if append_newline:
                    data += b"\r\n"
                    
            else:
                # HEX模式
                data = self._parse_hex_data(buff)
                if data is None:
                    return None
            
            # 发送数据
            result = self.uithreadObj.sendBuff(data)
            if result is None:
                logger.error("数据发送失败")
                return None
            
            # 更新统计
            self._update_stats(len(data))
            
            # 发送回显
            self._echo_sent_data(data)
            
            logger.debug(f"成功发送 {len(data)} 字节数据")
            return data
            
        except Exception as e:
            logger.exception(f"发送数据异常: {e}")
            return None
    
    def send_raw_bytes(self, data: bytes) -> bool:
        """
        直接发送字节数据
        
        Args:
            data: 要发送的字节数据
            
        Returns:
            bool: 是否发送成功
        """
        if not self.is_port_open():
            logger.warning("串口未打开，无法发送数据")
            return False
        
        try:
            result = self.uithreadObj.sendBuff(data)
            if result is None:
                logger.error("数据发送失败")
                return False
            
            # 更新统计
            self._update_stats(len(data))
            
            # 发送回显
            self._echo_sent_data(data)
            
            logger.debug(f"成功发送 {len(data)} 字节原始数据")
            return True
            
        except Exception as e:
            logger.exception(f"发送原始数据异常: {e}")
            return False
    
    def _parse_hex_data(self, text: str) -> Optional[bytes]:
        """
        解析HEX数据
        
        Args:
            text: HEX字符串
            
        Returns:
            bytes: 解析后的字节数据，失败返回None
        """
        # 移除空格
        buff = text.replace(' ', '')
        
        # 检查长度
        if len(buff) % 2 != 0:
            QMessageBox.critical(
                self.MainWindow, 
                '警告', 
                'HEX长度必须为偶数，可使用空格分隔!'
            )
            return None
        
        send_list = []
        while buff != '':
            try:
                num = int(buff[0:2], 16)
            except ValueError:
                QMessageBox.critical(
                    self.MainWindow, 
                    '警告', 
                    '请输入十六进制的数据，并以空格分开!'
                )
                return None
            buff = buff[2:]
            send_list.append(num)
            
        return bytes(send_list)
    
    @staticmethod
    def _replace_escape_sequences(s: str) -> str:
        """
        替换转义序列为实际字符
        
        Args:
            s: 包含转义序列的字符串
            
        Returns:
            str: 替换后的字符串
        """
        out = s
        out = out.replace('\\r', '\r')
        out = out.replace('\\n', '\n')
        out = out.replace('\\t', '\t')
        out = out.replace('\\e', chr(27))
        out = out.replace('\\b', '\b')
        return out
    
    def _update_stats(self, byte_count: int):
        """更新发送统计"""
        try:
            self.ui.update_send_stats(byte_count)
            self.ui.add_send_rate(byte_count)
        except Exception as e:
            logger.error(f"更新发送统计失败: {e}")
    
    def _echo_sent_data(self, data: bytes):
        """
        回显发送的数据
        
        Args:
            data: 发送的字节数据
        """
        try:
            if not hasattr(self.ui, 'checkBox_show_send'):
                return
            if not self.ui.checkBox_show_send.isChecked():
                return
            
            # 检查是否为HEX发送模式
            send_hex_mode = False
            try:
                send_hex_mode = self.ui.checkBox_send_hex.isChecked()
            except Exception:
                send_hex_mode = False
            
            # 转换为显示文本
            if send_hex_mode:
                display_text = ' '.join(f"{x:02X}" for x in data)
            else:
                try:
                    display_text = data.decode('utf-8', 'ignore')
                except Exception:
                    display_text = ' '.join(f"{x:02X}" for x in data)
            
            # 添加发送标记
            prefix = "[TX HEX] " if send_hex_mode else "[TX STR] "
            
            # 显示在接收区
            try:
                self.ui.textBrowser.append_received_data(
                    prefix + display_text,
                    add_timestamp=False
                )
            except Exception as e:
                logger.error(f"回显发送数据失败: {e}")
                
        except Exception as e:
            logger.error(f"发送回显处理失败: {e}")
    
    def get_send_mode(self) -> Tuple[bool, bool]:
        """
        获取当前发送模式
        
        Returns:
            Tuple[bool, bool]: (是否HEX模式, 是否追加换行)
        """
        try:
            is_hex = self.ui.checkBox_send_hex.isChecked()
            append_newline = not self.ui.checkBox_send_space_ctrl.isChecked()
            return is_hex, append_newline
        except Exception as e:
            logger.error(f"获取发送模式失败: {e}")
            return False, True


# 全局数据发送器实例
data_sender: Optional[DataSender] = None


def init_data_sender(ui_thread_obj, ui_obj, main_window):
    """
    初始化全局数据发送器
    
    Args:
        ui_thread_obj: UI线程对象
        ui_obj: UI对象
        main_window: 主窗口对象
    """
    global data_sender
    data_sender = DataSender(ui_thread_obj, ui_obj, main_window)
    logger.info("数据发送器已初始化")


def send_data(text: str, is_hex: bool = False, 
              append_newline: bool = True, 
              process_escapes: bool = False) -> Optional[bytes]:
    """
    便捷函数：发送数据
    
    Args:
        text: 要发送的文本
        is_hex: 是否为HEX模式
        append_newline: 是否追加换行符
        process_escapes: 是否处理转义序列
        
    Returns:
        bytes: 发送的字节数据，失败返回None
    """
    if data_sender is None:
        logger.error("数据发送器未初始化")
        return None
    return data_sender.send_data(text, is_hex, append_newline, process_escapes)


def send_raw_bytes(data: bytes) -> bool:
    """
    便捷函数：发送原始字节数据
    
    Args:
        data: 要发送的字节数据
        
    Returns:
        bool: 是否发送成功
    """
    if data_sender is None:
        logger.error("数据发送器未初始化")
        return False
    return data_sender.send_raw_bytes(data)
