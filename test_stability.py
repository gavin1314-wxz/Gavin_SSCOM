#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
长时间稳定性测试脚本

功能说明:
    - 模拟长时间运行的串口通信
    - 内存泄漏检测
    - 性能监控
    - 异常恢复测试

作者: Gavin
版本: 1.0.0
日期: 2026-02-06
"""

import sys
import os
import time
import threading
import random
import string
from datetime import datetime, timedelta
from typing import Optional
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('stability_test.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class StabilityTest:
    """稳定性测试类"""
    
    def __init__(self, duration_hours: float = 1.0):
        """
        初始化稳定性测试
        
        Args:
            duration_hours: 测试持续时间（小时）
        """
        self.duration_hours = duration_hours
        self.start_time = None
        self.end_time = None
        self.is_running = False
        
        # 测试统计
        self.stats = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'memory_samples': [],
            'cpu_samples': [],
            'error_count': 0,
            'recovery_count': 0
        }
        
        # 测试组件
        self.uart_serial = None
        self.data_sender = None
        self.monitor = None
        
    def setup(self):
        """设置测试环境"""
        logger.info("=" * 60)
        logger.info("开始设置稳定性测试环境")
        logger.info("=" * 60)
        
        try:
            # 导入测试模块
            from Uart.UartSerial import UartSerial, SerialConnectionState
            from monitor import SystemMonitor, PerformanceThresholds
            
            # 创建串口对象（不实际打开串口）
            self.uart_serial = UartSerial()
            
            # 创建监控器
            self.monitor = SystemMonitor(interval_ms=5000)
            self.monitor.statsUpdated.connect(self._on_stats_updated)
            
            # 设置较低的阈值用于测试
            thresholds = PerformanceThresholds(
                memory_warning_mb=256,
                memory_critical_mb=512,
                cpu_warning_percent=30,
                cpu_critical_percent=50
            )
            self.monitor.set_thresholds(thresholds)
            
            logger.info("测试环境设置完成")
            return True
            
        except Exception as e:
            logger.exception(f"设置测试环境失败: {e}")
            return False
            
    def _on_stats_updated(self, stats):
        """监控统计更新回调"""
        self.stats['memory_samples'].append(stats.memory_used_mb)
        self.stats['cpu_samples'].append(stats.cpu_percent)
        
        # 限制样本数量
        if len(self.stats['memory_samples']) > 1000:
            self.stats['memory_samples'].pop(0)
        if len(self.stats['cpu_samples']) > 1000:
            self.stats['cpu_samples'].pop(0)
            
    def run_connection_state_test(self):
        """运行连接状态测试"""
        logger.info("开始连接状态测试...")
        
        from Uart.UartSerial import SerialConnectionState
        
        test_states = [
            SerialConnectionState.DISCONNECTED,
            SerialConnectionState.CONNECTING,
            SerialConnectionState.CONNECTED,
            SerialConnectionState.ERROR,
            SerialConnectionState.DISCONNECTING,
            SerialConnectionState.DISCONNECTED
        ]
        
        for state in test_states:
            try:
                self.uart_serial._set_connection_state(state, "测试" if state == SerialConnectionState.ERROR else None)
                time.sleep(0.1)
                self.stats['total_operations'] += 1
                self.stats['successful_operations'] += 1
            except Exception as e:
                logger.error(f"状态转换失败: {e}")
                self.stats['failed_operations'] += 1
                self.stats['error_count'] += 1
                
        logger.info("连接状态测试完成")
        
    def run_data_buffer_test(self, iterations: int = 1000):
        """运行数据缓冲区测试"""
        logger.info(f"开始数据缓冲区测试 ({iterations} 次迭代)...")
        
        from collections import deque
        
        buffer = deque()
        max_size = 1000
        
        for i in range(iterations):
            try:
                # 模拟数据接收
                data_size = random.randint(10, 1000)
                data = {
                    'data': ''.join(random.choices(string.ascii_letters + string.digits, k=data_size)),
                    'is_hex': random.choice([True, False]),
                    'timestamp': datetime.now()
                }
                
                buffer.append(data)
                
                # 限制缓冲区大小
                while len(buffer) > max_size:
                    buffer.popleft()
                    
                # 模拟处理
                if len(buffer) >= 50:
                    for _ in range(25):
                        if buffer:
                            buffer.popleft()
                            
                self.stats['total_operations'] += 1
                self.stats['successful_operations'] += 1
                
                if i % 100 == 0:
                    time.sleep(0.01)  # 短暂休眠，避免CPU占用过高
                    
            except Exception as e:
                logger.error(f"缓冲区操作失败: {e}")
                self.stats['failed_operations'] += 1
                self.stats['error_count'] += 1
                
        logger.info("数据缓冲区测试完成")
        
    def run_hex_parsing_test(self, iterations: int = 1000):
        """运行HEX解析测试"""
        logger.info(f"开始HEX解析测试 ({iterations} 次迭代)...")
        
        from data_sender import DataSender
        
        # 创建模拟对象
        mock_ui_thread = type('MockUiThread', (), {'sendBuff': lambda x: len(x)})()
        mock_ui = type('MockUi', (), {
            'bt_open_off_port': type('MockBtn', (), {'text': lambda: '关闭串口'})(),
            'checkBox_show_send': type('MockCheck', (), {'isChecked': lambda: False})()
        })()
        
        sender = DataSender(mock_ui_thread, mock_ui, None)
        
        test_cases = [
            "48 65 6C 6C 6F",  # "Hello"
            "48656C6C6F",      # 无空格
            "00 01 02 03 FF",  # 包含00和FF
            "DE AD BE EF",     # 常见测试值
        ]
        
        for i in range(iterations):
            try:
                test_data = random.choice(test_cases)
                result = sender._parse_hex_data(test_data)
                
                if result is not None:
                    self.stats['successful_operations'] += 1
                else:
                    self.stats['failed_operations'] += 1
                    
                self.stats['total_operations'] += 1
                
                if i % 100 == 0:
                    time.sleep(0.01)
                    
            except Exception as e:
                logger.error(f"HEX解析失败: {e}")
                self.stats['failed_operations'] += 1
                self.stats['error_count'] += 1
                
        logger.info("HEX解析测试完成")
        
    def run_memory_stress_test(self, duration_seconds: int = 60):
        """运行内存压力测试"""
        logger.info(f"开始内存压力测试 ({duration_seconds} 秒)...")
        
        data_store = []
        start_time = time.time()
        
        while time.time() - start_time < duration_seconds:
            try:
                # 分配内存
                chunk_size = random.randint(1024, 1024 * 1024)  # 1KB to 1MB
                data = bytearray(chunk_size)
                data_store.append(data)
                
                # 随机释放内存
                if len(data_store) > 100:
                    indices_to_remove = random.sample(range(len(data_store)), 50)
                    for idx in sorted(indices_to_remove, reverse=True):
                        data_store.pop(idx)
                        
                self.stats['total_operations'] += 1
                self.stats['successful_operations'] += 1
                
                time.sleep(0.01)
                
            except MemoryError:
                logger.warning("内存不足，清理数据存储")
                data_store.clear()
                self.stats['recovery_count'] += 1
                import gc
                gc.collect()
            except Exception as e:
                logger.error(f"内存压力测试失败: {e}")
                self.stats['failed_operations'] += 1
                self.stats['error_count'] += 1
                
        # 清理
        data_store.clear()
        import gc
        gc.collect()
        
        logger.info("内存压力测试完成")
        
    def run_thread_safety_test(self, duration_seconds: int = 30):
        """运行线程安全测试"""
        logger.info(f"开始线程安全测试 ({duration_seconds} 秒)...")
        
        from collections import deque
        import threading
        
        buffer = deque()
        lock = threading.Lock()
        errors = []
        stop_event = threading.Event()
        
        def producer():
            try:
                while not stop_event.is_set():
                    with lock:
                        buffer.append(random.randint(0, 1000))
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
                
        def consumer():
            try:
                while not stop_event.is_set():
                    with lock:
                        if buffer:
                            buffer.popleft()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
                
        # 启动多个生产者和消费者
        threads = []
        for _ in range(3):
            t = threading.Thread(target=producer)
            t.start()
            threads.append(t)
            
        for _ in range(3):
            t = threading.Thread(target=consumer)
            t.start()
            threads.append(t)
            
        # 运行指定时间
        time.sleep(duration_seconds)
        stop_event.set()
        
        # 等待线程结束
        for t in threads:
            t.join(timeout=5)
            
        if errors:
            logger.error(f"线程安全测试发现 {len(errors)} 个错误")
            for e in errors:
                logger.error(f"  - {e}")
            self.stats['error_count'] += len(errors)
        else:
            logger.info("线程安全测试通过")
            
        self.stats['total_operations'] += 1000
        self.stats['successful_operations'] += 1000
        
    def generate_report(self) -> str:
        """生成测试报告"""
        report = []
        report.append("=" * 60)
        report.append("稳定性测试报告")
        report.append("=" * 60)
        report.append(f"测试开始时间: {self.start_time}")
        report.append(f"测试结束时间: {self.end_time}")
        report.append(f"测试持续时间: {self.duration_hours} 小时")
        report.append("")
        report.append("测试统计:")
        report.append(f"  总操作数: {self.stats['total_operations']}")
        report.append(f"  成功操作: {self.stats['successful_operations']}")
        report.append(f"  失败操作: {self.stats['failed_operations']}")
        report.append(f"  成功率: {self.stats['successful_operations'] / max(self.stats['total_operations'], 1) * 100:.2f}%")
        report.append(f"  错误次数: {self.stats['error_count']}")
        report.append(f"  恢复次数: {self.stats['recovery_count']}")
        report.append("")
        
        if self.stats['memory_samples']:
            memory_samples = self.stats['memory_samples']
            report.append("内存使用统计:")
            report.append(f"  平均内存: {sum(memory_samples) / len(memory_samples):.2f} MB")
            report.append(f"  最小内存: {min(memory_samples):.2f} MB")
            report.append(f"  最大内存: {max(memory_samples):.2f} MB")
            report.append(f"  内存增长: {memory_samples[-1] - memory_samples[0]:.2f} MB")
            report.append("")
            
        if self.stats['cpu_samples']:
            cpu_samples = self.stats['cpu_samples']
            report.append("CPU使用统计:")
            report.append(f"  平均CPU: {sum(cpu_samples) / len(cpu_samples):.2f}%")
            report.append(f"  最小CPU: {min(cpu_samples):.2f}%")
            report.append(f"  最大CPU: {max(cpu_samples):.2f}%")
            report.append("")
            
        # 评估结果
        success_rate = self.stats['successful_operations'] / max(self.stats['total_operations'], 1)
        if success_rate >= 0.99 and self.stats['error_count'] < 10:
            result = "PASS"
        elif success_rate >= 0.95:
            result = "WARNING"
        else:
            result = "FAIL"
            
        report.append(f"测试结果: {result}")
        report.append("=" * 60)
        
        return "\n".join(report)
        
    def run(self):
        """运行稳定性测试"""
        logger.info("=" * 60)
        logger.info(f"开始稳定性测试，计划运行 {self.duration_hours} 小时")
        logger.info("=" * 60)
        
        if not self.setup():
            logger.error("测试环境设置失败，中止测试")
            return False
            
        self.start_time = datetime.now()
        self.end_time = self.start_time + timedelta(hours=self.duration_hours)
        self.is_running = True
        
        # 启动监控
        if self.monitor:
            self.monitor.start()
            
        try:
            # 运行各项测试
            test_cycle = 0
            while self.is_running and datetime.now() < self.end_time:
                test_cycle += 1
                logger.info(f"开始测试周期 #{test_cycle}")
                
                # 连接状态测试
                self.run_connection_state_test()
                
                # 数据缓冲区测试
                self.run_data_buffer_test(iterations=1000)
                
                # HEX解析测试
                self.run_hex_parsing_test(iterations=1000)
                
                # 内存压力测试（每10个周期运行一次）
                if test_cycle % 10 == 0:
                    self.run_memory_stress_test(duration_seconds=30)
                    
                # 线程安全测试（每5个周期运行一次）
                if test_cycle % 5 == 0:
                    self.run_thread_safety_test(duration_seconds=10)
                    
                # 检查是否继续
                remaining = self.end_time - datetime.now()
                logger.info(f"测试周期 #{test_cycle} 完成，剩余时间: {remaining}")
                
                # 短暂休息
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("测试被用户中断")
        except Exception as e:
            logger.exception(f"测试过程中发生错误: {e}")
        finally:
            self.is_running = False
            
            # 停止监控
            if self.monitor:
                self.monitor.stop()
                
            # 生成报告
            report = self.generate_report()
            logger.info("\n" + report)
            
            # 保存报告到文件
            with open('stability_test_report.txt', 'w', encoding='utf-8') as f:
                f.write(report)
                
        return True


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='串口工具稳定性测试')
    parser.add_argument('-d', '--duration', type=float, default=0.1,
                       help='测试持续时间（小时），默认0.1小时（6分钟）')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='启用详细日志输出')
                       
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        
    # 创建并运行测试
    test = StabilityTest(duration_hours=args.duration)
    test.run()


if __name__ == '__main__':
    main()
