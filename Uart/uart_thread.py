#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
串口线程管理模块 - 提供UI层与串口底层的桥接

功能说明:
    - 串口操作线程封装
    - 连接状态管理
    - 自动重连机制
    - 异常处理和恢复

作者: Gavin
版本: 2.0.0
日期: 2026-02-06
"""

import os
import sys
import logging
import time
from typing import Optional, Callable

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/' + '..'))

from PySide6.QtCore import QObject, Signal, QTimer
from Uart.UartSerial import UartSerial, SerialConnectionState

# 配置日志
logger = logging.getLogger(__name__)


class ui_thread(QObject):
    """
    串口UI线程管理类
    
    功能:
        - 封装串口操作，提供线程安全接口
        - 管理连接状态和自动重连
        - 提供信号机制与UI交互
    
    信号:
        signalParseCMD: 数据接收信号
        connectionStateChanged: 连接状态改变信号
        errorOccurred: 错误信号
        autoReconnectAttempt: 自动重连尝试信号
    """
    
    # 定义信号
    signalParseCMD = Signal(object)
    connectionStateChanged = Signal(str)
    errorOccurred = Signal(str)
    autoReconnectAttempt = Signal(int, int)  # 当前尝试次数, 最大尝试次数

    def __init__(self, _baudrate=115200, isHexSend=False, isCtrlSend=True, 
                 _port="/dev/ttyUSB0", _bytesize=8, _stopbits="N",
                 _parity=None, _flow_control='none'):
        """
        初始化串口线程管理器
        
        Args:
            _baudrate: 波特率
            isHexSend: 是否HEX发送
            isCtrlSend: 是否控制发送
            _port: 串口名称
            _bytesize: 数据位
            _stopbits: 停止位
            _parity: 校验位
            _flow_control: 流控模式
        """
        super(ui_thread, self).__init__()
        
        # 初始化串口对象
        self.uartObj = UartSerial()
        
        # 配置参数
        self.port = _port
        self.baudrate = _baudrate
        self.bytesize = _bytesize
        self.stopbits = _stopbits
        self.parity = _parity if _parity is not None else __import__('serial').PARITY_NONE
        self.flow_control = _flow_control
        self.isHexSend = isHexSend
        self.isCtrlSend = isCtrlSend
        
        # 连接信号
        self.uartObj.signalRecieve.connect(self.getUartData)
        self.uartObj.connectionStateChanged.connect(self._on_connection_state_changed)
        self.uartObj.errorOccurred.connect(self._on_error_occurred)
        
        # 自动重连配置
        self._auto_reconnect = False
        self._max_reconnect_attempts = 3
        self._reconnect_interval = 2000  # 毫秒
        self._reconnect_attempts = 0
        self._reconnect_timer = QTimer()
        self._reconnect_timer.timeout.connect(self._attempt_reconnect)
        self._reconnect_timer.setSingleShot(True)
        
        # 连接断开回调
        self._disconnect_callback: Optional[Callable] = None
        
        logger.info(f"ui_thread初始化完成: port={_port}, baudrate={_baudrate}")

    def initPort(self):
        """
        初始化并获取可用串口列表
        
        Returns:
            list: 可用串口名称列表
        """
        try:
            ports = self.uartObj.get_all_port()
            logger.debug(f"发现 {len(ports)} 个串口: {ports}")
            return ports
        except Exception as e:
            logger.error(f"获取串口列表失败: {e}")
            return []

    def sendBuff(self, strCmd, _port="", _baudrate=0, isCtrlSend=True):
        """
        发送数据缓冲区
        
        Args:
            strCmd: 要发送的数据
            _port: 串口名称（可选，使用默认配置）
            _baudrate: 波特率（可选，使用默认配置）
            isCtrlSend: 是否控制发送
            
        Returns:
            int: 发送的字节数，失败返回None
        """
        # 使用默认配置
        if _port == "":
            _port = self.port
        if _baudrate == 0:
            _baudrate = self.baudrate
            
        try:
            result = self.uartObj.send_data(strCmd, self.isHexSend, _port, _baudrate)
            if result is None:
                logger.warning("数据发送失败")
            else:
                logger.debug(f"成功发送 {result} 字节")
            return result
        except Exception as e:
            logger.exception(f"发送数据异常: {e}")
            self.errorOccurred.emit(f"发送失败: {e}")
            return None

    def try_off_port(self, _port, baud):
        """
        关闭串口
        
        Args:
            _port: 串口名称
            baud: 波特率
            
        Returns:
            bool: 是否成功关闭
        """
        logger.info(f"正在关闭串口: {_port}")
        
        # 停止自动重连
        self._stop_auto_reconnect()
        
        try:
            result = self.uartObj.port_close(_port, baud)
            if result:
                logger.info("串口关闭成功")
            else:
                logger.warning("串口关闭失败")
            return result
        except Exception as e:
            logger.exception(f"关闭串口异常: {e}")
            return False

    def try_open_port(self, _port, baud):
        """
        打开串口
        
        Args:
            _port: 串口名称
            baud: 波特率
            
        Returns:
            bool: 是否成功打开
        """
        logger.info(f"正在打开串口: {_port} @ {baud}")
        
        # 重置重连计数
        self._reconnect_attempts = 0
        
        try:
            result = self.uartObj.try_port_open(
                _port, baud, self.bytesize, self.parity, 
                self.stopbits, self.flow_control
            )
            
            if result:
                # 更新当前配置
                self.port = _port
                self.baudrate = baud
                logger.info("串口打开成功")
            else:
                logger.warning("串口打开失败")
                # 如果启用自动重连，开始重连
                if self._auto_reconnect:
                    self._start_auto_reconnect()
                    
            return result
        except Exception as e:
            logger.exception(f"打开串口异常: {e}")
            self.errorOccurred.emit(f"打开串口失败: {e}")
            return False

    def is_port_busy(self, _port):
        """
        检查串口是否被占用
        
        Args:
            _port: 串口名称
            
        Returns:
            bool: 是否被占用
        """
        try:
            return not self.uartObj.is_port_open(_port, 9600)
        except Exception as e:
            logger.error(f"检查串口状态失败: {e}")
            return True

    def set_rts(self, IsTrue):
        """设置RTS信号"""
        try:
            self.uartObj.set_rts(IsTrue)
            logger.debug(f"RTS设置为: {IsTrue}")
        except Exception as e:
            logger.error(f"设置RTS失败: {e}")

    def set_dts(self, IsTrue):
        """设置DTR信号"""
        try:
            self.uartObj.set_dts(IsTrue)
            logger.debug(f"DTR设置为: {IsTrue}")
        except Exception as e:
            logger.error(f"设置DTR失败: {e}")

    def get_rts(self):
        """获取RTS状态"""
        try:
            return self.uartObj.get_rts()
        except Exception as e:
            logger.error(f"获取RTS状态失败: {e}")
            return False

    def get_dts(self):
        """获取DTR状态"""
        try:
            return self.uartObj.get_dts()
        except Exception as e:
            logger.error(f"获取DTR状态失败: {e}")
            return False

    def getUartData(self, obj):
        """
        处理接收到的串口数据
        
        Args:
            obj: 数据对象，包含code、data、length等字段
        """
        try:
            # 检查是否为断开或错误状态
            if obj.get('code') == self.uartObj.CODE_DISCONNECT:
                logger.warning("检测到串口断开")
                if self._disconnect_callback:
                    self._disconnect_callback(obj)
                # 如果启用自动重连，开始重连
                if self._auto_reconnect:
                    self._start_auto_reconnect()
                    
            elif obj.get('code') == self.uartObj.CODE_ERROR:
                logger.error(f"串口错误: {obj.get('error', '未知错误')}")
                
            # 添加描述信息并转发
            obj['des'] = '【模块-->MCU】 设置模块为 station 模式成功'
            self.signalParseCMD.emit(obj)
            
        except Exception as e:
            logger.exception(f"处理接收数据异常: {e}")

    def _on_connection_state_changed(self, state: str):
        """连接状态改变回调"""
        logger.info(f"连接状态改变: {state}")
        self.connectionStateChanged.emit(state)

    def _on_error_occurred(self, error_msg: str):
        """错误发生回调"""
        logger.error(f"串口错误: {error_msg}")
        self.errorOccurred.emit(error_msg)

    # ========== 配置设置方法 ==========
    
    def set_default_port(self, _port):
        """设置默认端口"""
        self.port = _port
        logger.debug(f"默认端口设置为: {_port}")

    def set_default_baudrate(self, _baudrate):
        """设置默认波特率"""
        self.baudrate = _baudrate
        logger.debug(f"默认波特率设置为: {_baudrate}")

    def set_default_parity(self, _parity):
        """设置默认校验位"""
        self.parity = _parity
        self.uartObj.set_parity(_parity)
        logger.debug(f"默认校验位设置为: {_parity}")

    def set_default_bytesize(self, _bytesize):
        """设置默认数据位"""
        self.bytesize = _bytesize
        self.uartObj.set_bytesize(_bytesize)
        logger.debug(f"默认数据位设置为: {_bytesize}")

    def set_default_stopbits(self, _stopbits):
        """设置默认停止位"""
        self.stopbits = _stopbits
        self.uartObj.set_stopbits(_stopbits)
        logger.debug(f"默认停止位设置为: {_stopbits}")

    def set_default_flow_control(self, _flow_control):
        """
        设置默认流控制模式
        
        Args:
            _flow_control: 流控制模式
                - 'none': 无流控
                - 'rtscts': 硬件流控 (RTS/CTS)
                - 'xonxoff': 软件流控 (XON/XOFF)
        """
        self.flow_control = _flow_control
        self.uartObj.set_flow_control(_flow_control)
        logger.debug(f"默认流控设置为: {_flow_control}")

    def set_default_at_result_callBack(self, function):
        """
        设置默认回调函数
        
        Args:
            function: 回调函数
        """
        try:
            self.signalParseCMD.connect(function)
            logger.debug("回调函数已设置")
        except Exception as e:
            logger.error(f"设置回调函数失败: {e}")

    def set_disconnect_callback(self, callback: Callable):
        """
        设置断开连接回调
        
        Args:
            callback: 回调函数，接收数据对象参数
        """
        self._disconnect_callback = callback
        logger.debug("断开连接回调已设置")

    # ========== 自动重连功能 ==========
    
    def set_auto_reconnect(self, enabled: bool, max_attempts: int = 3, 
                          interval_ms: int = 2000):
        """
        配置自动重连
        
        Args:
            enabled: 是否启用
            max_attempts: 最大重连次数
            interval_ms: 重连间隔（毫秒）
        """
        self._auto_reconnect = enabled
        self._max_reconnect_attempts = max_attempts
        self._reconnect_interval = interval_ms
        logger.info(f"自动重连设置: enabled={enabled}, max_attempts={max_attempts}, "
                   f"interval={interval_ms}ms")

    def _start_auto_reconnect(self):
        """开始自动重连"""
        if self._reconnect_attempts < self._max_reconnect_attempts:
            self._reconnect_attempts += 1
            logger.info(f"开始第 {self._reconnect_attempts}/{self._max_reconnect_attempts} "
                       f"次自动重连")
            self.autoReconnectAttempt.emit(
                self._reconnect_attempts, 
                self._max_reconnect_attempts
            )
            self._reconnect_timer.start(self._reconnect_interval)
        else:
            logger.warning(f"已达到最大重连次数 ({self._max_reconnect_attempts})，停止重连")
            self.errorOccurred.emit(f"自动重连失败，已尝试 {self._max_reconnect_attempts} 次")

    def _stop_auto_reconnect(self):
        """停止自动重连"""
        if self._reconnect_timer.isActive():
            self._reconnect_timer.stop()
            logger.debug("自动重连已停止")
        self._reconnect_attempts = 0

    def _attempt_reconnect(self):
        """执行重连尝试"""
        try:
            logger.info(f"尝试重连: {self.port} @ {self.baudrate}")
            result = self.uartObj.try_port_open(
                self.port, self.baudrate, self.bytesize, 
                self.parity, self.stopbits, self.flow_control
            )
            
            if result:
                logger.info("自动重连成功")
                self._reconnect_attempts = 0  # 重置计数
            else:
                logger.warning("自动重连失败，将继续尝试")
                self._start_auto_reconnect()  # 继续下一次重连
                
        except Exception as e:
            logger.exception(f"自动重连异常: {e}")
            self._start_auto_reconnect()  # 继续下一次重连

    # ========== 统计信息 ==========
    
    def get_statistics(self) -> dict:
        """
        获取串口统计信息
        
        Returns:
            dict: 统计信息字典
        """
        stats = self.uartObj.get_statistics()
        stats['auto_reconnect'] = {
            'enabled': self._auto_reconnect,
            'attempts': self._reconnect_attempts,
            'max_attempts': self._max_reconnect_attempts
        }
        return stats

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.uartObj.is_connected()
