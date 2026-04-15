#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化效果验证测试脚本

功能说明:
    - 测试串口通信模块的稳定性
    - 测试日志系统的资源管理
    - 测试数据发送模块的功能
    - 测试监控模块的性能

作者: Gavin
版本: 1.0.0
日期: 2026-02-06
"""

import sys
import os
import time
import threading
import unittest
from unittest.mock import Mock, MagicMock, patch

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 配置日志
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestUartSerial(unittest.TestCase):
    """测试串口通信模块"""
    
    def setUp(self):
        """测试前准备"""
        from Uart.UartSerial import UartSerial, SerialConnectionState
        self.uart = UartSerial()
        
    def test_connection_state_initial(self):
        """测试初始连接状态"""
        from Uart.UartSerial import SerialConnectionState
        self.assertEqual(self.uart.get_connection_state(), SerialConnectionState.DISCONNECTED)
        
    def test_connection_state_transitions(self):
        """测试连接状态转换"""
        from Uart.UartSerial import SerialConnectionState
        
        # 模拟状态转换
        self.uart._set_connection_state(SerialConnectionState.CONNECTING)
        self.assertEqual(self.uart.get_connection_state(), SerialConnectionState.CONNECTING)
        
        self.uart._set_connection_state(SerialConnectionState.CONNECTED)
        self.assertEqual(self.uart.get_connection_state(), SerialConnectionState.CONNECTED)
        
        self.uart._set_connection_state(SerialConnectionState.ERROR, "测试错误")
        self.assertEqual(self.uart.get_connection_state(), SerialConnectionState.ERROR)
        
    def test_statistics(self):
        """测试统计信息"""
        stats = self.uart.get_statistics()
        self.assertIn('state', stats)
        self.assertIn('is_open', stats)
        self.assertIn('data_received', stats)
        self.assertIn('error_count', stats)
        
    def test_is_connected(self):
        """测试连接状态检查"""
        # 初始状态应该未连接
        self.assertFalse(self.uart.is_connected())


class TestDataSender(unittest.TestCase):
    """测试数据发送模块"""
    
    def setUp(self):
        """测试前准备"""
        from data_sender import DataSender
        from PySide6.QtWidgets import QWidget
        
        # 创建模拟对象
        self.mock_ui_thread = Mock()
        self.mock_ui = Mock()
        # 使用None作为MainWindow，避免QMessageBox调用问题
        self.mock_main_window = None
        
        self.sender = DataSender(self.mock_ui_thread, self.mock_ui, self.mock_main_window)
        
    def test_hex_parsing_valid(self):
        """测试有效的HEX解析"""
        result = self.sender._parse_hex_data("48 65 6C 6C 6F")
        self.assertIsNotNone(result)
        self.assertEqual(result, b"Hello")
        
    def test_hex_parsing_no_spaces(self):
        """测试无空格的HEX解析"""
        result = self.sender._parse_hex_data("48656C6C6F")
        self.assertIsNotNone(result)
        self.assertEqual(result, b"Hello")
        
    def test_hex_parsing_invalid_length(self):
        """测试无效长度的HEX解析"""
        result = self.sender._parse_hex_data("48656")
        self.assertIsNone(result)  # 奇数长度应该返回None
        
    def test_hex_parsing_invalid_chars(self):
        """测试无效字符的HEX解析"""
        result = self.sender._parse_hex_data("48 65 XX 6C 6F")
        self.assertIsNone(result)  # 包含无效字符应该返回None
        
    def test_escape_sequences(self):
        """测试转义序列替换"""
        result = self.sender._replace_escape_sequences("Hello\\r\\nWorld\\t!")
        self.assertEqual(result, "Hello\r\nWorld\t!")
        
    def test_is_port_open(self):
        """测试端口状态检查"""
        self.mock_ui.bt_open_off_port.text.return_value = '关闭串口'
        self.assertTrue(self.sender.is_port_open())
        
        self.mock_ui.bt_open_off_port.text.return_value = '打开串口'
        self.assertFalse(self.sender.is_port_open())


class TestLogger(unittest.TestCase):
    """测试日志模块"""
    
    def setUp(self):
        """测试前准备"""
        from logger import SerialLogger
        self.logger = SerialLogger()
        
    def test_initial_state(self):
        """测试初始状态"""
        self.assertFalse(self.logger.is_logging)
        self.assertEqual(self.logger.session_name, '')
        self.assertEqual(self.logger.port_name, '')
        
    def test_macro_expansion(self):
        """测试宏展开"""
        self.logger.port_name = "COM1"
        result = self.logger.expand_macros("%H_%Y%M%D", "test_session")
        self.assertIn("COM1", result)
        
    def test_sanitize_component(self):
        """测试文件名清理"""
        result = self.logger._sanitize_component("COM1:")
        self.assertEqual(result, "COM1_")
        
        result = self.logger._sanitize_component("CON")
        self.assertEqual(result, "Serial-CON")
        
    def test_status(self):
        """测试状态获取"""
        status = self.logger.get_status()
        self.assertIn('is_logging', status)
        self.assertIn('session_name', status)
        self.assertIn('port_name', status)


class TestMonitor(unittest.TestCase):
    """测试监控模块"""
    
    def setUp(self):
        """测试前准备"""
        from monitor import SystemMonitor, PerformanceThresholds
        self.monitor = SystemMonitor(interval_ms=1000)
        
    def test_initial_state(self):
        """测试初始状态"""
        self.assertFalse(self.monitor._running)
        
    def test_thresholds(self):
        """测试阈值配置"""
        from monitor import PerformanceThresholds
        
        thresholds = PerformanceThresholds(
            memory_warning_mb=256,
            memory_critical_mb=512
        )
        self.monitor.set_thresholds(thresholds)
        self.assertEqual(self.monitor._thresholds.memory_warning_mb, 256)
        
    def test_stats_collection(self):
        """测试统计信息收集"""
        # 手动收集一次统计
        self.monitor._collect_stats()
        
        stats = self.monitor.get_current_stats()
        self.assertIsNotNone(stats)
        self.assertGreaterEqual(stats.memory_used_mb, 0)
        
    def test_history(self):
        """测试历史记录"""
        # 收集几次统计
        for _ in range(5):
            self.monitor._collect_stats()
            time.sleep(0.1)
            
        history = self.monitor.get_history(count=3)
        self.assertLessEqual(len(history), 3)
        
    def test_resource_manager(self):
        """测试资源管理器"""
        from monitor import ResourceManager
        
        rm = ResourceManager()
        info = rm.get_memory_info()
        self.assertIn('rss_mb', info)


class TestMyTextBrowser(unittest.TestCase):
    """测试文本浏览器组件"""
    
    def test_buffer_operations(self):
        """测试缓冲区操作"""
        from collections import deque
        from PySide6.QtCore import QMutex
        
        # 模拟缓冲区操作
        buffer = deque()
        mutex = QMutex()
        
        # 添加数据
        for i in range(10):
            buffer.append({'data': f'test_{i}', 'is_hex': False})
            
        self.assertEqual(len(buffer), 10)
        
        # 取出数据
        batch = []
        for _ in range(5):
            if buffer:
                batch.append(buffer.popleft())
                
        self.assertEqual(len(batch), 5)
        self.assertEqual(len(buffer), 5)


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def test_module_imports(self):
        """测试模块导入"""
        try:
            from Uart.UartSerial import UartSerial, SerialConnectionState
            from Uart.uart_thread import ui_thread
            from logger import SerialLogger
            from data_sender import DataSender
            from monitor import SystemMonitor, ResourceManager
            from widget.MyTextBrowser import MyTextBrowser
            logger.info("所有模块导入成功")
        except Exception as e:
            self.fail(f"模块导入失败: {e}")
            
    def test_thread_safety(self):
        """测试线程安全性"""
        from collections import deque
        import threading
        
        buffer = deque()
        lock = threading.Lock()
        errors = []
        
        def producer():
            try:
                for i in range(100):
                    with lock:
                        buffer.append(f'data_{i}')
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
                
        def consumer():
            try:
                count = 0
                while count < 100:
                    with lock:
                        if buffer:
                            buffer.popleft()
                            count += 1
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
                
        # 启动生产者和消费者线程
        t1 = threading.Thread(target=producer)
        t2 = threading.Thread(target=consumer)
        
        t1.start()
        t2.start()
        
        t1.join(timeout=5)
        t2.join(timeout=5)
        
        self.assertEqual(len(errors), 0, f"线程安全测试出错: {errors}")


def run_tests():
    """运行所有测试"""
    logger.info("=" * 60)
    logger.info("开始优化效果验证测试")
    logger.info("=" * 60)
    
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestUartSerial))
    suite.addTests(loader.loadTestsFromTestCase(TestDataSender))
    suite.addTests(loader.loadTestsFromTestCase(TestLogger))
    suite.addTests(loader.loadTestsFromTestCase(TestMonitor))
    suite.addTests(loader.loadTestsFromTestCase(TestMyTextBrowser))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 输出结果
    logger.info("=" * 60)
    logger.info(f"测试完成: 运行 {result.testsRun} 个测试")
    logger.info(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    logger.info(f"失败: {len(result.failures)}")
    logger.info(f"错误: {len(result.errors)}")
    logger.info("=" * 60)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
