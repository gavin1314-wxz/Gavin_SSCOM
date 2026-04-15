#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
串口设置对话框 - 主要的串口配置界面

功能说明:
    - 串口参数配置
    - 设置保存和加载
    - 异常处理和日志记录
    - 配置验证

作者: Gavin
版本: 2.0.0
日期: 2026-02-06
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
                             QLabel, QComboBox, QPushButton, QGroupBox, 
                             QDialogButtonBox, QSpacerItem, QSizePolicy, QCheckBox,
                             QMessageBox)
from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtGui import QFont
import logging

# 配置日志
logger = logging.getLogger(__name__)


class SerialSettingsDialog(QDialog):
    """串口设置对话框 - 主要的串口配置界面"""
    
    # 定义信号，用于通知主窗口设置已更改
    settings_changed = Signal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("串口设置")
        self.setModal(True)
        self.resize(200, 350)
        
        # 设置窗口图标（如果有的话）
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        # 存储默认波特率数组，与main.py保持一致
        self.DEFAULT_BAUD_ARRAY = [
            '300', '600', '1200', '2400', '4800', '9600', '14400', '19200', 
            '38400', '57600', '115200', '230400', '460800', '921600','1000000','1500000','2000000'
        ]
        
        try:
            self.init_ui()
            # 初始化时自动加载设置
            self.load_settings()
            logger.debug("SerialSettingsDialog初始化完成")
        except Exception as e:
            logger.exception(f"SerialSettingsDialog初始化失败: {e}")
            QMessageBox.critical(self, "错误", f"初始化设置对话框失败: {e}")
        
    def init_ui(self):
        """初始化UI界面"""
        try:
            main_layout = QVBoxLayout(self)
            main_layout.setSpacing(10)
            
            # 串口基本设置组
            basic_group = QGroupBox("串口基本设置")
            basic_layout = QFormLayout(basic_group)
            basic_layout.setSpacing(8)
            
            # 端口号 - 对应 comboBox_port
            self.port_combo = QComboBox()
            self.port_combo.setEditable(False)
            basic_layout.addRow("端口号:", self.port_combo)
            
            # 波特率 - 对应 comboBox_baud
            self.baud_combo = QComboBox()
            self.baud_combo.setEditable(True)
            self.baud_combo.addItems(self.DEFAULT_BAUD_ARRAY)
            self.baud_combo.setCurrentIndex(10)  # 默认选择115200，与main.py保持一致
            basic_layout.addRow("波特率:", self.baud_combo)
            
            # 数据位 - 对应 comboBox_Bit
            self.data_bits_combo = QComboBox()
            self.data_bits_combo.addItems(['8', '7', '6', '5'])
            self.data_bits_combo.setCurrentIndex(0)  # 默认8位
            basic_layout.addRow("数据位:", self.data_bits_combo)
            
            # 校验位 - 对应 comboBox_check，与main.py的格式完全一致
            self.parity_combo = QComboBox()
            self.parity_combo.addItems(['None', 'Odd', 'Even', 'Mark', 'Space'])
            self.parity_combo.setCurrentIndex(0)  # 默认无校验
            basic_layout.addRow("校验位:", self.parity_combo)
            
            # 停止位 - 对应 comboBox_stop
            self.stop_bits_combo = QComboBox()
            self.stop_bits_combo.addItems(['1', '1.5', '2'])
            self.stop_bits_combo.setCurrentIndex(0)  # 默认1位
            basic_layout.addRow("停止位:", self.stop_bits_combo)
            
            main_layout.addWidget(basic_group)
            
            # 高级设置组
            advanced_group = QGroupBox("高级设置")
            advanced_layout = QFormLayout(advanced_group)
            advanced_layout.setSpacing(8)
            
            # 流控制
            self.flow_control_combo = QComboBox()
            flow_control_items = [
                ('无流控', 'none'),
                ('硬件流控 (RTS/CTS)', 'rtscts'),
                ('软件流控 (XON/XOFF)', 'xonxoff')
            ]
            for text, value in flow_control_items:
                self.flow_control_combo.addItem(text, value)
            self.flow_control_combo.setCurrentIndex(0)
            advanced_layout.addRow("流控制:", self.flow_control_combo)
            
            # 超时设置
            self.timeout_combo = QComboBox()
            self.timeout_combo.setEditable(True)
            timeout_values = ['0.1', '0.5', '1.0', '2.0', '5.0', '10.0', '无超时']
            self.timeout_combo.addItems(timeout_values)
            self.timeout_combo.setCurrentText('1.0')
            advanced_layout.addRow("读取超时(秒):", self.timeout_combo)
            
            # RTS和DTR控制
            rts_dtr_layout = QHBoxLayout()
            self.rts_checkbox = QCheckBox("RTS")
            self.dtr_checkbox = QCheckBox("DTR")
            rts_dtr_layout.addWidget(self.rts_checkbox)
            rts_dtr_layout.addWidget(self.dtr_checkbox)
            rts_dtr_layout.addStretch()
            advanced_layout.addRow("信号控制:", rts_dtr_layout)
            
            main_layout.addWidget(advanced_group)
            
            # 添加弹簧
            spacer = QSpacerItem(20, 10, QSizePolicy.Minimum, QSizePolicy.Expanding)
            main_layout.addItem(spacer)
            
            # 按钮区域
            button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            button_box.accepted.connect(self.accept)
            button_box.rejected.connect(self.reject)
            
            main_layout.addWidget(button_box)
            
        except Exception as e:
            logger.exception(f"初始化UI失败: {e}")
            raise
        
    def update_port_list(self, ports):
        """更新端口列表"""
        try:
            current_port = self.port_combo.currentText()
            self.port_combo.clear()
            self.port_combo.addItems(ports)
            
            # 尝试恢复之前选择的端口
            index = self.port_combo.findText(current_port)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
                
            logger.debug(f"端口列表已更新: {len(ports)} 个端口")
        except Exception as e:
            logger.error(f"更新端口列表失败: {e}")
            
    def get_current_indices(self):
        """获取当前选择的索引，与main.py中的控件索引格式一致"""
        return {
            'port_index': self.port_combo.currentIndex(),
            'baud_index': self.baud_combo.currentIndex(),
            'data_bits_index': self.data_bits_combo.currentIndex(),
            'parity_index': self.parity_combo.currentIndex(),
            'stop_bits_index': self.stop_bits_combo.currentIndex()
        }
        
    def set_current_indices(self, indices):
        """设置当前选择的索引"""
        try:
            if 'port_index' in indices and indices['port_index'] >= 0:
                self.port_combo.setCurrentIndex(indices['port_index'])
            if 'baud_index' in indices and indices['baud_index'] >= 0:
                self.baud_combo.setCurrentIndex(indices['baud_index'])
            if 'data_bits_index' in indices and indices['data_bits_index'] >= 0:
                self.data_bits_combo.setCurrentIndex(indices['data_bits_index'])
            if 'parity_index' in indices and indices['parity_index'] >= 0:
                self.parity_combo.setCurrentIndex(indices['parity_index'])
            if 'stop_bits_index' in indices and indices['stop_bits_index'] >= 0:
                self.stop_bits_combo.setCurrentIndex(indices['stop_bits_index'])
        except Exception as e:
            logger.error(f"设置索引失败: {e}")
            
    def get_settings(self):
        """获取当前设置，格式与main.py中的串口配置一致"""
        try:
            timeout_text = self.timeout_combo.currentText()
            timeout_value = None if timeout_text == '无超时' else float(timeout_text)
            
            # 验证波特率
            baud_text = self.baud_combo.currentText()
            try:
                baudrate = int(baud_text) if baud_text.isdigit() else 115200
            except ValueError:
                logger.warning(f"无效的波特率值: {baud_text}，使用默认值115200")
                baudrate = 115200
            
            return {
                'port': self.port_combo.currentText(),
                'baudrate': baudrate,
                'bytesize': int(self.data_bits_combo.currentText()),
                'parity': self.parity_combo.currentText(),
                'stopbits': float(self.stop_bits_combo.currentText()),
                'flow_control': self.flow_control_combo.currentData(),
                'timeout': timeout_value,
                'rts_enabled': self.rts_checkbox.isChecked(),
                'dtr_enabled': self.dtr_checkbox.isChecked()
            }
        except Exception as e:
            logger.exception(f"获取设置失败: {e}")
            # 返回默认设置
            return {
                'port': '',
                'baudrate': 115200,
                'bytesize': 8,
                'parity': 'None',
                'stopbits': 1.0,
                'flow_control': 'none',
                'timeout': 1.0,
                'rts_enabled': False,
                'dtr_enabled': False
            }
        
    def set_settings(self, settings):
        """设置配置值"""
        try:
            if 'port' in settings:
                index = self.port_combo.findText(settings['port'])
                if index >= 0:
                    self.port_combo.setCurrentIndex(index)
                    
            if 'baudrate' in settings:
                baud_str = str(settings['baudrate'])
                index = self.baud_combo.findText(baud_str)
                if index >= 0:
                    self.baud_combo.setCurrentIndex(index)
                else:
                    self.baud_combo.setCurrentText(baud_str)
                
            if 'bytesize' in settings:
                self.data_bits_combo.setCurrentText(str(settings['bytesize']))
                
            if 'parity' in settings:
                index = self.parity_combo.findText(settings['parity'])
                if index >= 0:
                    self.parity_combo.setCurrentIndex(index)
                    
            if 'stopbits' in settings:
                self.stop_bits_combo.setCurrentText(str(settings['stopbits']))
                
            if 'flow_control' in settings:
                for i in range(self.flow_control_combo.count()):
                    if self.flow_control_combo.itemData(i) == settings['flow_control']:
                        self.flow_control_combo.setCurrentIndex(i)
                        break
                    
            if 'timeout' in settings:
                if settings['timeout'] is None:
                    self.timeout_combo.setCurrentText('无超时')
                else:
                    self.timeout_combo.setCurrentText(str(settings['timeout']))
                    
            if 'rts_enabled' in settings:
                self.rts_checkbox.setChecked(settings['rts_enabled'])
                
            if 'dtr_enabled' in settings:
                self.dtr_checkbox.setChecked(settings['dtr_enabled'])
                
            logger.debug("设置已应用")
        except Exception as e:
            logger.error(f"设置配置值失败: {e}")
                
    def load_settings_from_main(self, main_ui):
        """从主界面的控件加载当前设置"""
        try:
            # 同步端口列表
            port_items = []
            for i in range(main_ui.comboBox_port.count()):
                port_items.append(main_ui.comboBox_port.itemText(i))
            self.update_port_list(port_items)
            
            # 同步当前选择
            self.port_combo.setCurrentIndex(main_ui.comboBox_port.currentIndex())
            self.baud_combo.setCurrentIndex(main_ui.comboBox_baud.currentIndex())
            self.data_bits_combo.setCurrentIndex(main_ui.comboBox_Bit.currentIndex())
            self.parity_combo.setCurrentIndex(main_ui.comboBox_check.currentIndex())
            self.stop_bits_combo.setCurrentIndex(main_ui.comboBox_stop.currentIndex())
            
            # 同步RTS和DTR状态
            self.rts_checkbox.setChecked(main_ui.checkBox_rts.isChecked())
            self.dtr_checkbox.setChecked(main_ui.checkBox_dtr.isChecked())
            
            logger.debug("已从主界面加载设置")
        except Exception as e:
            logger.error(f"从主界面加载设置失败: {e}")
        
    def apply_settings_to_main(self, main_ui):
        """将设置应用到主界面的控件"""
        try:
            main_ui.comboBox_port.setCurrentIndex(self.port_combo.currentIndex())
            main_ui.comboBox_baud.setCurrentIndex(self.baud_combo.currentIndex())
            main_ui.comboBox_Bit.setCurrentIndex(self.data_bits_combo.currentIndex())
            main_ui.comboBox_check.setCurrentIndex(self.parity_combo.currentIndex())
            main_ui.comboBox_stop.setCurrentIndex(self.stop_bits_combo.currentIndex())
            
            # 同步RTS和DTR状态
            main_ui.checkBox_rts.setChecked(self.rts_checkbox.isChecked())
            main_ui.checkBox_dtr.setChecked(self.dtr_checkbox.isChecked())
            
            # 发射设置更改信号
            self.settings_changed.emit(self.get_settings())
            
            logger.debug("设置已应用到主界面")
        except Exception as e:
            logger.error(f"应用设置到主界面失败: {e}")
            
    def load_settings(self):
        """从QSettings加载设置"""
        try:
            settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "Gavin", "Gavin_com")
            
            # 加载基本设置，使用与main.py相同的键名
            baud_index = settings.value("baud", 10, int)
            if 0 <= baud_index < self.baud_combo.count():
                self.baud_combo.setCurrentIndex(baud_index)
            
            data_bits_index = settings.value("data_bits", 0, int)
            if 0 <= data_bits_index < self.data_bits_combo.count():
                self.data_bits_combo.setCurrentIndex(data_bits_index)
            
            parity_index = settings.value("parity", 0, int)
            if 0 <= parity_index < self.parity_combo.count():
                self.parity_combo.setCurrentIndex(parity_index)
                    
            stop_bits_index = settings.value("stop_bits", 0, int)
            if 0 <= stop_bits_index < self.stop_bits_combo.count():
                self.stop_bits_combo.setCurrentIndex(stop_bits_index)
            
            # 加载高级设置
            flow_control = settings.value('serial/flow_control', 'none', type=str)
            logger.debug(f"加载流控设置: {flow_control}")
            for i in range(self.flow_control_combo.count()):
                if self.flow_control_combo.itemData(i) == flow_control:
                    self.flow_control_combo.setCurrentIndex(i)
                    logger.debug(f"设置流控下拉框索引: {i}")
                    break
                    
            timeout = settings.value('serial/timeout', 1.0)
            if timeout is None or timeout == 'None':
                self.timeout_combo.setCurrentText('无超时')
            else:
                try:
                    self.timeout_combo.setCurrentText(str(float(timeout)))
                except (ValueError, TypeError):
                    self.timeout_combo.setCurrentText('1.0')
                    
            # 加载RTS和DTR设置
            rts_enabled = settings.value("rts_enabled", False, bool)
            self.rts_checkbox.setChecked(rts_enabled)
            
            dtr_enabled = settings.value("dtr_enabled", False, bool)
            self.dtr_checkbox.setChecked(dtr_enabled)
            
            logger.debug("设置已从QSettings加载")
        except Exception as e:
            logger.error(f"加载设置失败: {e}")
            
    def save_settings(self):
        """保存设置到QSettings，使用与main.py相同的键名"""
        try:
            settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "Gavin", "Gavin_com")
            
            # 保存基本设置索引，与main.py保持一致
            settings.setValue("baud", self.baud_combo.currentIndex())
            settings.setValue("data_bits", self.data_bits_combo.currentIndex())
            settings.setValue("stop_bits", self.stop_bits_combo.currentIndex())
            settings.setValue("parity", self.parity_combo.currentIndex())
            
            # 保存高级设置
            settings.setValue('serial/flow_control', self.flow_control_combo.currentData())
            settings.setValue('serial/timeout', self.get_settings()['timeout'])
            
            # 保存RTS和DTR设置
            settings.setValue("rts_enabled", self.rts_checkbox.isChecked())
            settings.setValue("dtr_enabled", self.dtr_checkbox.isChecked())
            
            # 确保设置立即写入
            settings.sync()
            
            logger.debug("设置已保存到QSettings")
        except Exception as e:
            logger.error(f"保存设置失败: {e}")
            
    def accept(self):
        """确定按钮点击"""
        try:
            # 验证设置
            settings = self.get_settings()
            if not settings['port']:
                QMessageBox.warning(self, "警告", "未选择串口端口")
                return
                
            if settings['baudrate'] <= 0:
                QMessageBox.warning(self, "警告", "波特率必须大于0")
                return
                
            self.save_settings()
            # 发射设置更改信号
            self.settings_changed.emit(settings)
            
            logger.info("设置已确认并保存")
            super().accept()
        except Exception as e:
            logger.exception(f"确认设置时出错: {e}")
            QMessageBox.critical(self, "错误", f"保存设置失败: {e}")
            
    def reject(self):
        """取消按钮点击"""
        logger.debug("设置对话框被取消")
        super().reject()
