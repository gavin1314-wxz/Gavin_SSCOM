#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多字符串组件 - 美化版（无内置滚动区域）

功能说明:
    - 现代化的UI设计
    - 流畅的动画效果
    - 保持原有功能逻辑
    - 不包含内置滚动区域，适合放入外部滚动容器

作者: Gavin
版本: 3.0.0
日期: 2026-02-06
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QCheckBox, QFrame,
    QSizePolicy, QMenu
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
import logging

# 配置日志
logger = logging.getLogger(__name__)


class ModernPushButton(QPushButton):
    """现代化按钮"""
    
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setMinimumHeight(26)
        self.setMaximumHeight(30)
        self.setCursor(Qt.PointingHandCursor)
        self._setup_style()
        
    def _setup_style(self):
        self.setStyleSheet("""
            ModernPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4a90d9, stop:1 #357abd);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 2px 8px;
                font-family: "Microsoft YaHei";
                font-size: 11px;
                font-weight: 500;
            }
            ModernPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5aa0e9, stop:1 #458acd);
            }
            ModernPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a70b9, stop:1 #1a5a9d);
            }
        """)


class ModernLineEdit(QLineEdit):
    """现代化输入框"""
    
    def __init__(self, parent=None, placeholder=""):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(24)
        self.setMaximumHeight(28)
        self._setup_style()
        
    def _setup_style(self):
        self.setStyleSheet("""
            ModernLineEdit {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 2px 6px;
                font-family: "Consolas", "Microsoft YaHei";
                font-size: 11px;
                color: #212529;
            }
            ModernLineEdit:focus {
                background-color: #ffffff;
                border: 2px solid #4a90d9;
            }
        """)


class ModernCheckBox(QCheckBox):
    """现代化复选框"""
    
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._setup_style()
        
    def _setup_style(self):
        self.setStyleSheet("""
            ModernCheckBox {
                font-family: "Microsoft YaHei";
                font-size: 11px;
                color: #495057;
            }
            ModernCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 2px solid #adb5bd;
                background-color: white;
            }
            ModernCheckBox::indicator:checked {
                background-color: #4a90d9;
                border-color: #4a90d9;
            }
        """)


class MultistringRow(QWidget):
    """多字符串单行组件"""
    
    buttonClicked = Signal(int)
    textChanged = Signal(int, str)
    hexChanged = Signal(int, bool)
    seqChanged = Signal(int, str)
    delayChanged = Signal(int, str)
    contextMenuRequested = Signal(int, object)
    
    def __init__(self, index, parent=None):
        super().__init__(parent)
        self.index = index
        self._setup_ui()
        self._connect_signals()
        
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(4)
        
        # 发送按钮
        self.send_btn = ModernPushButton(f"{self.index}")
        self.send_btn.setFixedWidth(40)
        layout.addWidget(self.send_btn)
        
        # 命令输入框
        self.cmd_edit = ModernLineEdit(placeholder="命令...")
        self.cmd_edit.setMinimumWidth(150)
        self.cmd_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.cmd_edit, stretch=4)
        
        # HEX复选框
        self.hex_checkbox = ModernCheckBox("H")
        self.hex_checkbox.setFixedWidth(25)
        layout.addWidget(self.hex_checkbox)
        
        # 序号输入框
        self.seq_edit = ModernLineEdit(placeholder="序")
        self.seq_edit.setFixedWidth(30)
        self.seq_edit.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.seq_edit)
        
        # 延迟输入框
        self.delay_edit = ModernLineEdit(placeholder="ms")
        self.delay_edit.setFixedWidth(40)
        self.delay_edit.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.delay_edit)
        
    def _connect_signals(self):
        self.send_btn.clicked.connect(lambda: self.buttonClicked.emit(self.index))
        self.cmd_edit.textChanged.connect(lambda text: self.textChanged.emit(self.index, text))
        self.hex_checkbox.stateChanged.connect(lambda state: self.hexChanged.emit(self.index, bool(state)))
        self.seq_edit.textChanged.connect(lambda text: self.seqChanged.emit(self.index, text))
        self.delay_edit.textChanged.connect(lambda text: self.delayChanged.emit(self.index, text))
        
        self.send_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self.send_btn.customContextMenuRequested.connect(
            lambda pos: self.contextMenuRequested.emit(self.index, self.send_btn.mapToGlobal(pos))
        )
        
    def get_data(self):
        return {
            'index': self.index,
            'command': self.cmd_edit.text(),
            'is_hex': self.hex_checkbox.isChecked(),
            'sequence': self.seq_edit.text(),
            'delay': self.delay_edit.text()
        }
        
    def set_data(self, command="", is_hex=False, sequence="", delay=""):
        self.cmd_edit.setText(command)
        self.hex_checkbox.setChecked(is_hex)
        self.seq_edit.setText(sequence)
        self.delay_edit.setText(delay)
        
    def highlight_duplicate_seq(self, is_duplicate=True):
        if is_duplicate:
            self.seq_edit.setStyleSheet("""
                ModernLineEdit {
                    background-color: #fff3cd;
                    border: 2px solid #ffc107;
                }
            """)
        else:
            self.seq_edit.setStyleSheet("")


class MultistringWidget(QWidget):
    """多字符串组件（无内置滚动区域版本）"""
    
    sendCommand = Signal(int, str, bool, int)
    startSequential = Signal()
    stopSequential = Signal()
    importConfig = Signal()
    exportConfig = Signal()
    
    def __init__(self, row_count=36, parent=None):
        super().__init__(parent)
        self.row_count = row_count
        self.rows = []
        self._is_running = False
        self._setup_ui()
        self._create_rows()
        
    def _setup_ui(self):
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)
        
        # 顶部控制区域
        control_frame = QFrame()
        control_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
            }
        """)
        control_layout = QVBoxLayout(control_frame)
        control_layout.setContentsMargins(4, 4, 4, 4)
        control_layout.setSpacing(4)
        
        # 导入导出按钮
        import_export_layout = QHBoxLayout()
        self.import_btn = ModernPushButton("📥 导入")
        self.import_btn.clicked.connect(self.importConfig.emit)
        import_export_layout.addWidget(self.import_btn)
        
        self.export_btn = ModernPushButton("📤 导出")
        self.export_btn.clicked.connect(self.exportConfig.emit)
        import_export_layout.addWidget(self.export_btn)
        import_export_layout.addStretch()
        control_layout.addLayout(import_export_layout)
        
        # 顺序/循环控制
        mode_layout = QHBoxLayout()
        self.sequential_checkbox = ModernCheckBox("顺序")
        mode_layout.addWidget(self.sequential_checkbox)
        
        self.loop_checkbox = ModernCheckBox("循环")
        mode_layout.addWidget(self.loop_checkbox)
        
        mode_layout.addWidget(QLabel("次数:"))
        self.loop_count_edit = ModernLineEdit(placeholder="1")
        self.loop_count_edit.setFixedWidth(35)
        mode_layout.addWidget(self.loop_count_edit)
        
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #28a745; font-weight: 500;")
        mode_layout.addWidget(self.status_label)
        mode_layout.addStretch()
        
        self.start_btn = ModernPushButton("▶ 开始")
        self.start_btn.setFixedWidth(60)
        self.start_btn.clicked.connect(self._on_start_stop)
        mode_layout.addWidget(self.start_btn)
        
        control_layout.addLayout(mode_layout)
        main_layout.addWidget(control_frame)
        
        # 表头
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #e9ecef; border-radius: 3px;")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(4, 2, 4, 2)
        header_layout.setSpacing(4)
        
        headers = [("序号", 40), ("命令", 150), ("H", 25), ("序", 30), ("延迟", 40)]
        for text, width in headers:
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-weight: bold; font-size: 10px; color: #495057;")
            if width > 0:
                lbl.setFixedWidth(width)
            header_layout.addWidget(lbl, stretch=1 if width == 150 else 0)
            
        main_layout.addWidget(header_frame)
        
        # 行容器（直接添加到布局，不嵌套滚动区域）
        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(1)
        self.rows_layout.setAlignment(Qt.AlignTop)
        
        main_layout.addWidget(self.rows_container, stretch=1)
        
    def _create_rows(self):
        for i in range(1, self.row_count + 1):
            row = MultistringRow(i)
            row.buttonClicked.connect(self._on_row_clicked)
            row.textChanged.connect(self._on_text_changed)
            row.hexChanged.connect(self._on_hex_changed)
            row.seqChanged.connect(self._on_seq_changed)
            row.delayChanged.connect(self._on_delay_changed)
            row.contextMenuRequested.connect(self._on_context_menu)
            
            self.rows.append(row)
            self.rows_layout.addWidget(row)
            
    def _on_row_clicked(self, index):
        row = self.rows[index - 1]
        data = row.get_data()
        delay_ms = 0
        try:
            delay_ms = int(data['delay']) if data['delay'] else 0
        except ValueError:
            pass
        self.sendCommand.emit(index, data['command'], data['is_hex'], delay_ms)
        
    def _on_text_changed(self, index, text):
        pass
        
    def _on_hex_changed(self, index, is_hex):
        pass
        
    def _on_seq_changed(self, index, seq):
        self._check_duplicate_sequences()
        
    def _check_duplicate_sequences(self):
        seq_map = {}
        for row in self.rows:
            seq_text = row.seq_edit.text().strip()
            if seq_text:
                try:
                    seq_num = int(seq_text)
                    if seq_num > 0:
                        if seq_num not in seq_map:
                            seq_map[seq_num] = []
                        seq_map[seq_num].append(row)
                except ValueError:
                    pass
                    
        for row in self.rows:
            seq_text = row.seq_edit.text().strip()
            is_duplicate = False
            if seq_text:
                try:
                    seq_num = int(seq_text)
                    if seq_num in seq_map and len(seq_map[seq_num]) > 1:
                        is_duplicate = True
                except ValueError:
                    pass
            row.highlight_duplicate_seq(is_duplicate)
            
    def _on_delay_changed(self, index, delay):
        pass
        
    def _on_context_menu(self, index, global_pos):
        menu = QMenu(self)
        
        edit_action = QAction("✏️ 编辑", self)
        edit_action.triggered.connect(lambda: self._edit_row(index))
        menu.addAction(edit_action)
        
        clear_action = QAction("🗑️ 清空", self)
        clear_action.triggered.connect(lambda: self._clear_row(index))
        menu.addAction(clear_action)
        
        copy_action = QAction("📋 复制", self)
        copy_action.triggered.connect(lambda: self._copy_row(index))
        menu.addAction(copy_action)
        
        paste_action = QAction("📄 粘贴", self)
        paste_action.triggered.connect(lambda: self._paste_row(index))
        menu.addAction(paste_action)
        
        menu.exec(global_pos)
        
    def _edit_row(self, index):
        pass
        
    def _clear_row(self, index):
        row = self.rows[index - 1]
        row.set_data()
        
    def _copy_row(self, index):
        row = self.rows[index - 1]
        data = row.get_data()
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(f"{data['command']}|{data['is_hex']}|{data['sequence']}|{data['delay']}")
        
    def _paste_row(self, index):
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        try:
            parts = text.split('|')
            if len(parts) >= 4:
                row = self.rows[index - 1]
                row.set_data(parts[0], parts[1] == 'True', parts[2], parts[3])
        except Exception:
            pass
            
    def _on_start_stop(self):
        if self._is_running:
            self._stop_execution()
        else:
            self._start_execution()
            
    def _start_execution(self):
        self._is_running = True
        self.start_btn.setText("⏹ 停止")
        self.status_label.setText("运行中")
        self.status_label.setStyleSheet("color: #dc3545; font-weight: 500;")
        # 无论顺序/循环如何勾选，统一通知外部开始执行
        self.startSequential.emit()
            
    def _stop_execution(self):
        self._is_running = False
        self.start_btn.setText("▶ 开始")
        self.status_label.setText("已停止")
        self.status_label.setStyleSheet("color: #6c757d; font-weight: 500;")
        self.stopSequential.emit()
        
    def set_row_data(self, index, command="", is_hex=False, sequence="", delay=""):
        if 1 <= index <= len(self.rows):
            self.rows[index - 1].set_data(command, is_hex, sequence, delay)
            
    def get_row_data(self, index):
        if 1 <= index <= len(self.rows):
            return self.rows[index - 1].get_data()
        return None
        
    def get_all_data(self):
        return [row.get_data() for row in self.rows]
        
    def set_all_data(self, data_list):
        for i, data in enumerate(data_list):
            if i < len(self.rows):
                self.rows[i].set_data(
                    data.get('command', ''),
                    data.get('is_hex', False),
                    data.get('sequence', ''),
                    data.get('delay', '')
                )
                
    def clear_all(self):
        for row in self.rows:
            row.set_data()
            
    def set_running_state(self, is_running, status_text=""):
        self._is_running = is_running
        if is_running:
            self.start_btn.setText("⏹ 停止")
            self.status_label.setText(status_text or "运行中")
            self.status_label.setStyleSheet("color: #dc3545; font-weight: 500;")
        else:
            self.start_btn.setText("▶ 开始")
            self.status_label.setText(status_text or "就绪")
            self.status_label.setStyleSheet("color: #28a745; font-weight: 500;")
