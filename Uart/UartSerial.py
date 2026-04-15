#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
串口通信模块 - 提供底层串口操作功能

功能说明:
    - 串口打开/关闭/配置
    - 数据发送/接收
    - 流控制(RTS/CTS, XON/XOFF)
    - 连接状态管理
    - 异常自动恢复

作者: Gavin
版本: 2.0.0
日期: 2026-02-06
"""

import serial
import serial.tools.list_ports
from PySide6.QtCore import QTimer, QObject
import time
import logging
from enum import Enum
from PySide6.QtCore import Signal, QThread

# 配置日志
logger = logging.getLogger(__name__)


class SerialConnectionState(Enum):
    """
    串口连接状态枚举
    
    状态流转:
        DISCONNECTED -> CONNECTING -> CONNECTED
        CONNECTED -> DISCONNECTING -> DISCONNECTED
        CONNECTED -> ERROR -> RECONNECTING -> CONNECTING
    """
    DISCONNECTED = "disconnected"      # 未连接
    CONNECTING = "connecting"          # 正在连接
    CONNECTED = "connected"            # 已连接
    DISCONNECTING = "disconnecting"    # 正在断开
    RECONNECTING = "reconnecting"      # 正在重连
    ERROR = "error"                    # 错误状态


class UartRecieveThread(QThread):
    """
    串口接收线程类
    
    功能:
        - 在独立线程中监听串口数据
        - 支持优雅退出
        - 异常自动检测和报告
    """

    def __init__(self, run):
        """
        初始化接收线程
        
        Args:
            run: 线程运行函数
        """
        super(UartRecieveThread, self).__init__()
        self.runfun = run
        self._is_running = False
        self._stop_requested = False

    def run(self):
        """线程主函数"""
        self._is_running = True
        self._stop_requested = False
        try:
            self.runfun()
        except Exception as e:
            logger.exception(f"接收线程异常: {e}")
        finally:
            self._is_running = False

    def request_stop(self):
        """请求停止线程（优雅退出）"""
        self._stop_requested = True
        logger.debug("接收线程停止请求已发送")

    def is_running(self):
        """检查线程是否正在运行"""
        return self._is_running and not self._stop_requested


class UartSerial(QObject):
    """
    串口通信主类
    
    功能:
        - 串口配置和管理
        - 数据收发
        - 连接状态监控
        - 异常处理和恢复
    
    信号:
        signalRecieve: 接收到数据时触发
        connectionStateChanged: 连接状态改变时触发
        errorOccurred: 发生错误时触发
    """
    
    # 定义信号变量
    signalRecieve = Signal(object)
    connectionStateChanged = Signal(str)  # 状态改变信号
    errorOccurred = Signal(str)           # 错误信号

    # 状态码定义
    CODE_RECIEVE = 0
    CODE_DISCONNECT = 1
    CODE_ERROR = 2

    def __init__(self):
        """初始化串口对象"""
        super(UartSerial, self).__init__()
        self.mThread = UartRecieveThread(self.data_receive)
        self.mSerial = serial.Serial()
        self.data_num_received = 0
        self._connection_state = SerialConnectionState.DISCONNECTED
        self._last_error = None
        self._error_count = 0
        self._max_errors = 5  # 最大连续错误次数
        self._receive_emit_interval = 0.05  # 50ms批量上报一次，进一步降低UI线程唤醒频率
        self._receive_emit_bytes = 16384    # 累积到16KB立即上报，优先保证高吞吐稳定性
        self._idle_sleep = 0.003

        # 配置串口默认值
        self.mSerial.timeout = 1.0
        self.mSerial.write_timeout = 1.0

    def _emit_received_data(self, payload: bytes):
        """统一发送接收数据，减少高频信号带来的UI压力"""
        if not payload:
            return

        data = {
            'code': self.CODE_RECIEVE,
            'data': payload,
            'length': len(payload)
        }
        self.data_num_received += len(payload)
        self.signalRecieve.emit(data)

    def _set_connection_state(self, state: SerialConnectionState, error_msg: str = None):
        """
        设置连接状态
        
        Args:
            state: 新状态
            error_msg: 错误信息（可选）
        """
        old_state = self._connection_state
        self._connection_state = state
        
        if error_msg:
            self._last_error = error_msg
            logger.error(f"串口状态从 {old_state.value} 变为 {state.value}: {error_msg}")
        else:
            logger.info(f"串口状态从 {old_state.value} 变为 {state.value}")
        
        self.connectionStateChanged.emit(state.value)

    def get_connection_state(self) -> SerialConnectionState:
        """获取当前连接状态"""
        return self._connection_state

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connection_state == SerialConnectionState.CONNECTED and self.mSerial.isOpen()

    def init(self, _port="/dev/ttyUSB0", _baudrate=115200, _bytesize=8, 
             _stopbits="N", _parity=serial.PARITY_NONE, _flow_control='none'):
        """
        初始化串口参数
        
        Args:
            _port: 串口名称
            _baudrate: 波特率
            _bytesize: 数据位
            _stopbits: 停止位
            _parity: 校验位
            _flow_control: 流控制模式
        """
        self.mSerial.port = _port
        self.mSerial.baudrate = _baudrate
        self.mSerial.bytesize = _bytesize
        self.mSerial.stopbits = _stopbits
        self.mSerial.parity = _parity
        self.set_flow_control(_flow_control)
        self.data_num_received = 0

    def is_port_open(self, _port_name, _baudrate):
        """
        检查串口是否可用
        
        Args:
            _port_name: 串口名称
            _baudrate: 波特率
            
        Returns:
            bool: 串口是否可用
        """
        try:
            # 保存当前配置
            original_port = self.mSerial.port
            original_baud = self.mSerial.baudrate
            
            self.mSerial.port = _port_name
            self.mSerial.baudrate = _baudrate
            is_available = not self.mSerial.isOpen()
            
            # 恢复原始配置
            self.mSerial.port = original_port
            self.mSerial.baudrate = original_baud
            
            return is_available
        except Exception as e:
            logger.warning(f"检查串口状态时出错: {e}")
            return False

    def port_close(self, _port_name=None, _baudrate=None):
        """
        关闭串口
        
        Args:
            _port_name: 串口名称（可选）
            _baudrate: 波特率（可选）
            
        Returns:
            bool: 是否成功关闭
        """
        self._set_connection_state(SerialConnectionState.DISCONNECTING)
        
        try:
            # 请求线程停止
            if self.mThread.isRunning():
                self.mThread.request_stop()
                # 等待线程结束，设置超时
                if not self.mThread.wait(3000):  # 等待最多3秒
                    logger.warning("接收线程未能在3秒内结束，强制终止")
                    self.mThread.terminate()
                    self.mThread.wait(1000)
            
            # 关闭串口
            if self.mSerial.isOpen():
                self.mSerial.close()
                logger.info(f"串口 {self.mSerial.port} 已关闭")
            
            self._set_connection_state(SerialConnectionState.DISCONNECTED)
            self._error_count = 0  # 重置错误计数
            return True
            
        except Exception as e:
            logger.exception(f"关闭串口时出错: {e}")
            self._set_connection_state(SerialConnectionState.ERROR, str(e))
            return False

    def get_all_port(self):
        """
        检测所有存在的串口
        
        Returns:
            list: 串口名称列表
        """
        self.port_list_name = []
        try:
            port_list = list(serial.tools.list_ports.comports())
            
            if len(port_list) <= 0:
                return []
            else:
                for port in port_list:
                    self.port_list_name.append(port[0])
                    
        except Exception as e:
            logger.error(f"获取串口列表时出错: {e}")
            
        return self.port_list_name

    def try_port_open(self, _port, _baudrate=115200, _bytesize=8, 
                      _parity=serial.PARITY_NONE, _stopbits=serial.STOPBITS_ONE, 
                      _flow_control='none'):
        """
        打开串口
        
        Args:
            _port: 串口名称
            _baudrate: 波特率
            _bytesize: 数据位
            _parity: 校验位
            _stopbits: 停止位
            _flow_control: 流控模式 ('none', 'rtscts', 'xonxoff')
            
        Returns:
            bool: 是否成功打开
        """
        self._set_connection_state(SerialConnectionState.CONNECTING)
        
        # 如果串口已经打开，先关闭
        if self.mSerial.isOpen():
            logger.debug("串口已打开，先关闭")
            self.port_close()
        
        # 配置串口参数
        self.mSerial.port = _port
        self.mSerial.baudrate = _baudrate
        self.mSerial.bytesize = _bytesize
        self.mSerial.parity = _parity
        self.mSerial.stopbits = _stopbits
        
        # 设置流控
        logger.debug(f"UartSerial.try_port_open 设置流控: {_flow_control}")
        self.set_flow_control(_flow_control)
        
        try:
            # 打开串口
            self.mSerial.open()
            
            if self.mSerial.isOpen():
                logger.info(f"串口 {_port} 打开成功，波特率 {_baudrate}")
                self._set_connection_state(SerialConnectionState.CONNECTED)
                self._error_count = 0
                
                # 启动接收线程
                if not self.mThread.isRunning():
                    self.mThread.start()
                    logger.debug("接收线程已启动")
                
                return True
            else:
                raise serial.SerialException("串口打开后状态异常")
                
        except serial.SerialException as e:
            error_msg = f"串口打开失败: {e}"
            logger.error(error_msg)
            self._set_connection_state(SerialConnectionState.ERROR, error_msg)
            return False
        except Exception as e:
            error_msg = f"打开串口时发生未知错误: {e}"
            logger.exception(error_msg)
            self._set_connection_state(SerialConnectionState.ERROR, error_msg)
            return False

    def set_rts(self, IsTrue):
        """设置RTS信号"""
        try:
            self.mSerial.setRTS(IsTrue)
        except Exception as e:
            logger.error(f"设置RTS失败: {e}")

    def set_dts(self, IsTrue):
        """设置DTR信号"""
        try:
            self.mSerial.setDTR(IsTrue)
        except Exception as e:
            logger.error(f"设置DTR失败: {e}")

    def get_rts(self):
        """获取RTS状态"""
        try:
            return self.mSerial.rts
        except Exception as e:
            logger.error(f"获取RTS状态失败: {e}")
            return False

    def get_dts(self):
        """获取DTR状态"""
        try:
            return self.mSerial.dtr
        except Exception as e:
            logger.error(f"获取DTR状态失败: {e}")
            return False

    def set_bytesize(self, _bytesize):
        """设置数据位"""
        try:
            self.mSerial.bytesize = _bytesize
        except Exception as e:
            logger.error(f"设置数据位失败: {e}")

    def set_parity(self, _parity):
        """设置校验位"""
        try:
            self.mSerial.parity = _parity
        except Exception as e:
            logger.error(f"设置校验位失败: {e}")

    def set_stopbits(self, _stopbits):
        """设置停止位"""
        try:
            self.mSerial.stopbits = _stopbits
        except Exception as e:
            logger.error(f"设置停止位失败: {e}")

    def set_flow_control(self, flow_control):
        """
        设置流控制模式
        
        Args:
            flow_control: 流控制模式
                - 'none': 无流控
                - 'rtscts': 硬件流控 (RTS/CTS)
                - 'xonxoff': 软件流控 (XON/XOFF)
        """
        try:
            if flow_control == 'rtscts':
                self.mSerial.rtscts = True
                self.mSerial.xonxoff = False
                logger.debug("设置硬件流控: rtscts=True, xonxoff=False")
            elif flow_control == 'xonxoff':
                self.mSerial.rtscts = False
                self.mSerial.xonxoff = True
                logger.debug("设置软件流控: rtscts=False, xonxoff=True")
            else:
                self.mSerial.rtscts = False
                self.mSerial.xonxoff = False
                logger.debug("无流控: rtscts=False, xonxoff=False")
        except Exception as e:
            logger.error(f"设置流控失败: {e}")

    def data_receive(self):
        """
        接收数据主循环
        
        在独立线程中运行，持续监听串口数据
        支持优雅退出和异常恢复
        """
        logger.info("接收线程已启动")
        consecutive_errors = 0
        max_consecutive_errors = 3
        pending_buffer = bytearray()
        last_emit_time = time.monotonic()

        def flush_pending(force: bool = False):
            nonlocal last_emit_time

            if not pending_buffer:
                last_emit_time = time.monotonic()
                return False

            now = time.monotonic()
            should_emit = force
            if not should_emit:
                should_emit = (
                    len(pending_buffer) >= self._receive_emit_bytes or
                    (now - last_emit_time) >= self._receive_emit_interval
                )

            if not should_emit:
                return False

            payload = bytes(pending_buffer)
            pending_buffer.clear()
            last_emit_time = now
            self._emit_received_data(payload)
            return True
        
        while not self.mThread._stop_requested:
            try:
                # 检查串口是否打开
                if not self.mSerial.isOpen():
                    flush_pending(force=True)
                    logger.warning("串口未打开，接收线程退出")
                    break
                
                # 获取可读字节数
                try:
                    num = self.mSerial.in_waiting
                except Exception as e:
                    # 串口可能已断开
                    logger.error(f"读取串口状态失败: {e}")
                    consecutive_errors += 1
                    
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("连续错误次数过多，报告断开")
                        flush_pending(force=True)
                        self._handle_disconnect()
                        return
                    
                    time.sleep(0.1)
                    continue
                
                # 重置错误计数
                consecutive_errors = 0
                
                # 读取数据
                if num > 0:
                    try:
                        buff = self.mSerial.read(num)
                        if buff:
                            pending_buffer.extend(buff)
                            flush_pending()
                    except Exception as e:
                        logger.error(f"读取数据失败: {e}")
                        flush_pending(force=True)
                        self._handle_error(f"读取数据失败: {e}")
                        return
                else:
                    flush_pending()
                
                # 短暂休眠，避免CPU占用过高
                time.sleep(self._idle_sleep)
                
            except Exception as e:
                logger.exception(f"接收循环异常: {e}")
                consecutive_errors += 1
                
                if consecutive_errors >= max_consecutive_errors:
                    flush_pending(force=True)
                    self._handle_error(f"接收线程异常: {e}")
                    return
                
                time.sleep(0.1)
        
        flush_pending(force=True)
        logger.info("接收线程已退出")

    def _handle_disconnect(self):
        """处理串口断开"""
        # 先停止接收线程并关闭串口，确保释放 OS 句柄
        try:
            if self.mThread.isRunning():
                self.mThread.request_stop()
        except Exception:
            pass
        try:
            if self.mSerial.isOpen():
                self.mSerial.close()
                logger.info("_handle_disconnect: 串口已关闭")
        except Exception as e:
            logger.warning(f"_handle_disconnect: 关闭串口失败: {e}")
        data = {
            'code': self.CODE_DISCONNECT,
            'data': b'',
            'length': 0,
            'error': self._last_error or "串口已断开"
        }
        self._set_connection_state(SerialConnectionState.DISCONNECTED)
        self.signalRecieve.emit(data)

    def _handle_error(self, error_msg: str):
        """处理错误"""
        self._error_count += 1
        # 关闭串口句柄，避免后续重连时出现 OSError(22)
        try:
            if self.mSerial.isOpen():
                self.mSerial.close()
                logger.info("_handle_error: 串口已关闭")
        except Exception as e:
            logger.warning(f"_handle_error: 关闭串口失败: {e}")
        data = {
            'code': self.CODE_ERROR,
            'data': b'',
            'length': 0,
            'error': error_msg
        }
        self._set_connection_state(SerialConnectionState.ERROR, error_msg)
        self.errorOccurred.emit(error_msg)
        self.signalRecieve.emit(data)

    def setCallBack(self, function):
        """
        设置数据接收回调
        
        Args:
            function: 回调函数
        """
        try:
            self.signalRecieve.connect(function)
        except Exception as e:
            logger.error(f"连接信号失败: {e}")

    def send_data(self, buff=b"", isHexSend=False, _port="", _baudrate=115200):
        """
        发送数据
        
        Args:
            buff: 要发送的数据
            isHexSend: 是否为HEX发送
            _port: 串口名称（可选）
            _baudrate: 波特率（可选）
            
        Returns:
            int: 发送的字节数，失败返回None
        """
        if not self.mSerial.isOpen():
            logger.warning("串口未打开，无法发送数据")
            return None
        
        try:
            if buff:
                # HEX发送处理
                if isHexSend and isinstance(buff, str):
                    buff = buff.strip()
                    send_list = []
                    temp_buff = buff
                    while temp_buff != '':
                        try:
                            num = int(temp_buff[0:2], 16)
                        except ValueError:
                            logger.error("HEX数据格式错误")
                            return None
                        temp_buff = temp_buff[2:].strip()
                        send_list.append(num)
                    buff = bytes(send_list)
                
                # 发送数据
                if isinstance(buff, str):
                    buff = buff.encode('utf-8')
                
                num_written = self.mSerial.write(buff)
                self.mSerial.flush()  # 确保数据发送
                logger.debug(f"发送了 {num_written} 字节数据")
                return num_written
                
        except serial.SerialTimeoutException as e:
            logger.error(f"发送超时: {e}")
            self._handle_error(f"发送超时: {e}")
            return None
        except Exception as e:
            logger.exception(f"发送数据失败: {e}")
            self._handle_error(f"发送失败: {e}")
            return None

    def get_statistics(self) -> dict:
        """
        获取串口统计信息
        
        Returns:
            dict: 统计信息字典
        """
        return {
            'state': self._connection_state.value,
            'port': self.mSerial.port,
            'baudrate': self.mSerial.baudrate,
            'bytesize': self.mSerial.bytesize,
            'parity': self.mSerial.parity,
            'stopbits': self.mSerial.stopbits,
            'is_open': self.mSerial.isOpen(),
            'data_received': self.data_num_received,
            'error_count': self._error_count,
            'last_error': self._last_error
        }
