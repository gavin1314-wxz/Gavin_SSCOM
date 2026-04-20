#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自定义文本浏览器组件 - 优化显示性能和线程安全

功能说明:
    - 数据接收和显示
    - 线程安全的数据缓存
    - 批量UI更新
    - 历史记录管理
    - 搜索功能

作者: Gavin
版本: 2.0.0
日期: 2026-02-06
"""

from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Signal, QTimer, QLocale, QPoint, QMutex, QMutexLocker
from PySide6.QtWidgets import QMenu, QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QCheckBox, QTextEdit, QMessageBox, QTextBrowser, QFontDialog, QColorDialog
from PySide6.QtGui import QAction, QTextCursor, QColor, QTextCharFormat, QFont
import re
import sys
from collections import deque
import logging
import os

# 配置日志
logger = logging.getLogger(__name__)
CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


class SearchDialog(QDialog):
    """搜索对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_browser = parent
        self.init_ui()
        self.search_results = []
        self.current_result_index = -1
        
    def init_ui(self):
        # 获取系统语言
        locale = QLocale.system()
        language = locale.language()
        
        if language == QLocale.Chinese:
            self.setWindowTitle("搜索")
            search_label_text = "搜索内容:"
            regex_checkbox_text = "正则表达式"
            case_checkbox_text = "区分大小写"
            search_button_text = "搜索"
            next_button_text = "下一个"
            prev_button_text = "上一个"
            close_button_text = "关闭"
        else:
            self.setWindowTitle("Search")
            search_label_text = "Search for:"
            regex_checkbox_text = "Regular Expression"
            case_checkbox_text = "Case Sensitive"
            search_button_text = "Search"
            next_button_text = "Next"
            prev_button_text = "Previous"
            close_button_text = "Close"
        
        self.setFixedSize(400, 150)
        layout = QVBoxLayout()
        
        # 搜索输入框
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel(search_label_text))
        self.search_input = QLineEdit()
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)
        
        # 选项
        options_layout = QHBoxLayout()
        self.regex_checkbox = QCheckBox(regex_checkbox_text)
        self.case_checkbox = QCheckBox(case_checkbox_text)
        options_layout.addWidget(self.regex_checkbox)
        options_layout.addWidget(self.case_checkbox)
        layout.addLayout(options_layout)
        
        # 按钮
        button_layout = QHBoxLayout()
        self.search_button = QPushButton(search_button_text)
        self.next_button = QPushButton(next_button_text)
        self.prev_button = QPushButton(prev_button_text)
        self.close_button = QPushButton(close_button_text)
        
        button_layout.addWidget(self.search_button)
        button_layout.addWidget(self.prev_button)
        button_layout.addWidget(self.next_button)
        button_layout.addWidget(self.close_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # 连接信号
        self.search_button.clicked.connect(self.search)
        self.next_button.clicked.connect(self.find_next)
        self.prev_button.clicked.connect(self.find_previous)
        self.close_button.clicked.connect(self.close)
        self.search_input.returnPressed.connect(self.search)
        
        # 初始状态
        self.next_button.setEnabled(False)
        self.prev_button.setEnabled(False)
    
    def search(self):
        """执行搜索"""
        search_text = self.search_input.text().strip()
        if not search_text:
            return
        
        # 清除之前的搜索结果
        self.clear_highlights()
        self.search_results = []
        self.current_result_index = -1
        
        # 获取文本内容
        document = self.parent_browser.document()
        text_content = document.toPlainText()
        
        try:
            if self.regex_checkbox.isChecked():
                # 正则表达式搜索
                flags = 0 if self.case_checkbox.isChecked() else re.IGNORECASE
                pattern = re.compile(search_text, flags)
                matches = pattern.finditer(text_content)
                self.search_results = [(match.start(), match.end()) for match in matches]
            else:
                # 普通搜索
                search_text_lower = search_text if self.case_checkbox.isChecked() else search_text.lower()
                text_to_search = text_content if self.case_checkbox.isChecked() else text_content.lower()
                
                start = 0
                while True:
                    pos = text_to_search.find(search_text_lower, start)
                    if pos == -1:
                        break
                    self.search_results.append((pos, pos + len(search_text)))
                    start = pos + 1
        except re.error as e:
            QMessageBox.warning(self, "搜索错误" if QLocale.system().language() == QLocale.Chinese else "Search Error", 
                              f"正则表达式错误: {str(e)}" if QLocale.system().language() == QLocale.Chinese else f"Regular expression error: {str(e)}")
            return
        
        if self.search_results:
            self.highlight_results()
            self.current_result_index = 0
            self.goto_result(0)
            self.next_button.setEnabled(len(self.search_results) > 1)
            self.prev_button.setEnabled(len(self.search_results) > 1)
        else:
            QMessageBox.information(self, "搜索结果" if QLocale.system().language() == QLocale.Chinese else "Search Result", 
                                   "未找到匹配项" if QLocale.system().language() == QLocale.Chinese else "No matches found")
    
    def highlight_results(self):
        """高亮显示搜索结果"""
        cursor = QTextCursor(self.parent_browser.document())
        format = QTextCharFormat()
        format.setBackground(QColor(255, 165, 0))  # 橙色背景
        format.setForeground(QColor(0, 0, 0))  # 黑色前景
        
        for start, end in self.search_results:
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            cursor.setCharFormat(format)
    
    def clear_highlights(self):
        """清除高亮显示"""
        if not hasattr(self, 'search_results') or not self.search_results:
            return
            
        cursor = QTextCursor(self.parent_browser.document())
        for start, end in self.search_results:
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            default_format = QTextCharFormat()
            cursor.mergeCharFormat(default_format)
        
        cursor.clearSelection()
    
    def goto_result(self, index):
        """跳转到指定的搜索结果"""
        if 0 <= index < len(self.search_results):
            start, end = self.search_results[index]
            cursor = self.parent_browser.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            self.parent_browser.setTextCursor(cursor)
            self.parent_browser.ensureCursorVisible()
    
    def find_next(self):
        """查找下一个"""
        if self.search_results:
            self.current_result_index = (self.current_result_index + 1) % len(self.search_results)
            self.goto_result(self.current_result_index)
    
    def find_previous(self):
        """查找上一个"""
        if self.search_results:
            self.current_result_index = (self.current_result_index - 1) % len(self.search_results)
            self.goto_result(self.current_result_index)
    
    def closeEvent(self, event):
        """关闭对话框时清除高亮"""
        self.clear_highlights()
        super().closeEvent(event)


class MyTextBrowser(QTextBrowser):
    """
    自定义文本浏览器
    
    功能:
        - 线程安全的数据接收
        - 批量UI更新
        - 历史记录管理
        - 搜索功能
        - 主题切换
    """
    
    # 定义信号
    sendData = Signal(str)
    colorSchemeSelected = Signal(str)
    
    # 预置颜色主题
    COLOR_SCHEMES = {
        "Yellow / Black": ("#FFFF00", "#000000"),
        "White / Black": ("#FFFFFF", "#000000"),
        "Black / White": ("#000000", "#FFFFFF"),
        "White / Blue": ("#FFFFFF", "#003366"),
        "Black / Cyan": ("#000000", "#00FFFF"),
        "Black / Floral White": ("#000000", "#FFFAF0"),
        "Floral White / Dark Cyan": ("#FFFAF0", "#008B8B"),
        "Monochrome": ("#C0C0C0", "#000000"),
        "Tomorrow": ("#4D4D4C", "#FFFFFF"),
        "Desert": ("#000000", "#CDB79E"),
        "Espresso": ("#FFFFFF", "#2D2D2D"),
        "Chalkboard": ("#E0E0E0", "#222222"),
        "Solarized Dark": ("#839496", "#002B36"),
        "Solarized Light": ("#657B83", "#FDF6E3"),
        "Zenburn": ("#DCDCCC", "#3F3F3F"),
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fresh_flag = True
        self.input_buffer = ""
        
        # 滚动条信号连接
        self.verticalScrollBar().sliderMoved.connect(self.on_scroll)
        try:
            self.verticalScrollBar().valueChanged.connect(self._on_scroll_value_changed)
        except Exception:
            pass
        
        # 设置为可编辑模式以支持键盘输入
        self.setReadOnly(False)
        self.setUndoRedoEnabled(False)
        try:
            self.document().setUndoRedoEnabled(False)
        except Exception:
            pass
        
        # 数据缓存 - 使用QMutex保证线程安全
        self.data_buffer = deque()
        self._mutex = QMutex()
        self.max_buffer_size = 1000
        self.max_display_lines = 5000
        self.batch_size = 50
        self.max_batch_chars = 128 * 1024
        self.max_merge_chars = 8 * 1024
        try:
            self.document().setMaximumBlockCount(self.max_display_lines)
        except Exception:
            pass
        
        # 定时器用于批量更新UI
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.process_buffered_data)
        self.update_timer.setSingleShot(False)
        self.update_interval = 100
        self._tx_prefix_format = QtGui.QTextCharFormat()
        self._tx_prefix_format.setForeground(QtGui.QColor(255, 140, 0))

        # 历史日志
        self._logger_ref = None
        self._history_files = []
        self._history_positions = {}
        self._history_active_idx = 0
        self._history_chunk_bytes = 64 * 1024
        self._enable_history_load = True
        self._pending_rollover = None
        self._pending_history_refresh_from_previous = False
        self._rollover_refresh_timer = QTimer(self)
        self._rollover_refresh_timer.setSingleShot(True)
        self._rollover_refresh_timer.setInterval(120)
        self._rollover_refresh_timer.timeout.connect(self._apply_pending_rollover_refresh)

        # 当前颜色主题
        self._current_scheme = "Zenburn"
        try:
            self.apply_color_scheme(self._current_scheme)
        except Exception:
            pass

    def on_scroll(self):
        """滚动条拖动事件"""
        scroll_bar = self.verticalScrollBar()
        
        if scroll_bar.value() == scroll_bar.maximum():
            self.fresh_flag = True
        else:
            self.fresh_flag = False
            
        if scroll_bar.value() == scroll_bar.minimum():
            self._load_history_if_possible()

    def _on_scroll_value_changed(self, value):
        """滚动条值改变事件"""
        if value == self.verticalScrollBar().minimum():
            self._load_history_if_possible()
        
    def keyPressEvent(self, event):
        """键盘事件处理"""
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self.sendData.emit(self.input_buffer)
            self.input_buffer = ""
            self.update_input_display()
            self.fresh_flag = True
            return
        elif event.key() == Qt.Key_Tab:
            data_to_send = self.input_buffer + '\x09'
            self.sendData.emit(data_to_send)
            self.input_buffer = ""
            self.update_input_display()
            self.fresh_flag = True
            event.accept()
            return
        elif event.key() == Qt.Key_Backspace:
            if self.input_buffer:
                self.input_buffer = self.input_buffer[:-1]
                self.update_input_display()
            return
        elif event.key() == Qt.Key_Escape:
            self.input_buffer = ""
            self.update_input_display()
            return
        elif event.key() == Qt.Key_F5:
            self.clear()
            self.input_buffer = ""
            return
            
        text = event.text()
        if text and text.isprintable():
            self.input_buffer += text
            self.update_input_display()
            return
            
        super().keyPressEvent(event)
        
    def update_input_display(self):
        """更新输入显示"""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.setTextCursor(cursor)
        
        text = self.toPlainText()
        lines = text.split('\n')
        
        if not lines or not lines[-1].startswith("> "):
            if text and not text.endswith('\n'):
                self.append("")
            self.insertPlainText("> " + self.input_buffer.replace('\x09', ''))
        else:
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.select(QTextCursor.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.insertText("> " + self.input_buffer.replace('\x09', ''))
            
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.setTextCursor(cursor)
        
        if self.fresh_flag:
            self.moveCursor(QTextCursor.End)
        
    def filter_garbled_text(self, data):
        """过滤乱码字符"""
        if not data:
            return ""
        if CONTROL_CHAR_RE.search(data) is None:
            return data
        return CONTROL_CHAR_RE.sub('', data)
    
    def append_received_data(self, data, is_hex=False, add_timestamp=False, timestamp_str=""):
        """
        将接收到的数据添加到缓存队列（线程安全）
        
        Args:
            data: 数据内容
            is_hex: 是否为HEX格式
            add_timestamp: 是否添加时间戳
            timestamp_str: 时间戳字符串
        """
        if data is None:
            return
        if isinstance(data, (bytes, bytearray)):
            data = bytes(data).decode('utf-8', 'ignore')
        elif not isinstance(data, str):
            data = str(data)

        if not data and not (add_timestamp and timestamp_str):
            return

        with QMutexLocker(self._mutex):
            can_merge = False
            if self.data_buffer:
                last_item = self.data_buffer[-1]
                last_data = last_item.get('data', '')
                cur_is_tx = data.startswith("[TX STR]") or data.startswith("[TX HEX]")
                last_is_tx = isinstance(last_data, str) and (
                    last_data.startswith("[TX STR]") or last_data.startswith("[TX HEX]")
                )
                can_merge = (
                    not cur_is_tx and
                    not last_is_tx and
                    last_item.get('is_hex') == is_hex and
                    last_item.get('add_timestamp') == add_timestamp and
                    last_item.get('timestamp_str') == timestamp_str and
                    isinstance(last_data, str) and
                    len(last_data) < self.max_merge_chars
                )

            if can_merge:
                self.data_buffer[-1]['data'] += data
            else:
                self.data_buffer.append({
                    'data': data,
                    'is_hex': is_hex,
                    'add_timestamp': add_timestamp,
                    'timestamp_str': timestamp_str
                })
            
            # 限制缓存大小
            while len(self.data_buffer) > self.max_buffer_size:
                self.data_buffer.popleft()
        
        # 启动定时器（如果还没启动）
        if not self.update_timer.isActive():
            self.update_timer.start(self.update_interval)

    def attach_logger(self, logger):
        """绑定日志器"""
        self._logger_ref = logger
        self._refresh_history_sequence(start_from_previous=False)

    def on_logger_new_part(self, new_path: str, part_index: int, base_path: str):
        """日志分片回调"""
        self._pending_rollover = (new_path, part_index, base_path)
        self._pending_history_refresh_from_previous = True
        self._rollover_refresh_timer.start()

    def archive_and_clear_display(self):
        """归档并清空显示"""
        try:
            self.clear_buffer()
        except Exception:
            pass
        try:
            self.clear()
        except Exception:
            pass
        self.fresh_flag = True

    def _get_visible_block_range(self):
        """获取可见区域块范围"""
        try:
            h = self.viewport().height()
            top_cursor = self.cursorForPosition(QPoint(0, 0))
            bottom_cursor = self.cursorForPosition(QPoint(0, max(0, h - 1)))
            return top_cursor.blockNumber(), bottom_cursor.blockNumber()
        except Exception:
            doc = self.document()
            return max(0, doc.blockCount() - 50), doc.blockCount() - 1

    def prune_outside_visible(self, keep_margin=200):
        """裁剪可视区域外的内容"""
        try:
            doc = self.document()
            bc0 = doc.blockCount()
            if bc0 <= 0:
                return
            top_b, bot_b = self._get_visible_block_range()
            preserve_from = max(0, top_b - keep_margin)
            preserve_to = min(bc0 - 1, bot_b + keep_margin)
            if preserve_to < preserve_from:
                preserve_from, preserve_to = 0, min(bc0 - 1, max(0, bc0 - 1))

            top_to_remove = preserve_from
            keep_len = max(1, preserve_to - preserve_from + 1)
            tail_to_remove = max(0, bc0 - top_to_remove - keep_len)

            if top_to_remove > 0:
                c = QTextCursor(doc)
                c.movePosition(QTextCursor.Start)
                for _ in range(top_to_remove):
                    c.select(QTextCursor.BlockUnderCursor)
                    c.removeSelectedText()
                    c.deleteChar()
                    
            if tail_to_remove > 0:
                c2 = QTextCursor(doc)
                c2.movePosition(QTextCursor.End)
                for _ in range(tail_to_remove):
                    c2.movePosition(QTextCursor.StartOfBlock)
                    c2.select(QTextCursor.BlockUnderCursor)
                    c2.removeSelectedText()
                    c2.deleteChar()
        except Exception:
            pass

    def prune_after_rollover(self):
        """分片后裁剪"""
        self.fresh_flag = True
        self.scroll_to_bottom()

    def _apply_pending_rollover_refresh(self):
        """延后处理日志分片后的轻量刷新，避免在切分瞬间阻塞UI。"""
        rollover = self._pending_rollover
        start_from_previous = self._pending_history_refresh_from_previous
        self._pending_rollover = None
        self._pending_history_refresh_from_previous = False

        try:
            self.prune_after_rollover()
        except Exception:
            pass

        if not rollover:
            self._refresh_history_sequence(start_from_previous=start_from_previous)
            return

        new_path, _part_index, _base_path = rollover
        new_seq = []
        for path in [new_path, *self._history_files]:
            if not path or path in new_seq:
                continue
            try:
                if os.path.exists(path):
                    new_seq.append(path)
            except Exception:
                continue

        if not new_seq:
            self._refresh_history_sequence(start_from_previous=start_from_previous)
            return

        self._history_files = new_seq
        self._history_positions = {}
        for path in self._history_files:
            try:
                self._history_positions[path] = os.path.getsize(path)
            except Exception:
                self._history_positions[path] = 0

        if start_from_previous and len(self._history_files) >= 2:
            self._history_active_idx = 1
        else:
            self._history_active_idx = 0

    def _refresh_history_sequence(self, start_from_previous: bool):
        """刷新历史文件序列"""
        self._history_files = []
        self._history_positions = {}
        self._history_active_idx = 0
        lg = self._logger_ref
        if lg is None:
            return
        try:
            base = getattr(lg, 'base_path_used', '') or ''
            try:
                cur_path = lg.file.name if getattr(lg, 'file', None) else base
            except Exception:
                cur_path = base
            idx = int(getattr(lg, 'current_part_index', 1) or 1)

            seq = []
            if cur_path and os.path.exists(cur_path):
                seq.append(cur_path)
            if base:
                for i in range(idx - 1, 1, -1):
                    try:
                        from logger import SerialLogger
                        p = SerialLogger._make_part_path(base, i)
                        if os.path.exists(p):
                            seq.append(p)
                    except Exception:
                        pass
                if os.path.exists(base) and base not in seq:
                    seq.append(base)

            self._history_files = seq
            for p in self._history_files:
                try:
                    self._history_positions[p] = os.path.getsize(p)
                except Exception:
                    self._history_positions[p] = 0

            if start_from_previous and len(self._history_files) >= 2:
                self._history_active_idx = 1
            else:
                self._history_active_idx = 0
        except Exception:
            pass

    def _load_history_if_possible(self):
        """加载历史记录"""
        if not self._enable_history_load:
            return
        if not self._history_files:
            self._refresh_history_sequence(start_from_previous=False)
            if not self._history_files:
                return
            # 懒加载：attach_logger 时文件未创建，_history_files 为空。
            # 此处首次调用时文件已有本次会话的全部实时数据，
            # 将当前文件读取指针置 0，避免从文件末尾往前读出已显示数据导致重复。
            cur_file = self._history_files[0]
            self._history_positions[cur_file] = 0
        text = self._read_prev_chunk_from_history()
        if text:
            self._prepend_text(text)

    def _read_prev_chunk_from_history(self) -> str:
        """从历史文件读取数据块"""
        while self._history_active_idx < len(self._history_files):
            path = self._history_files[self._history_active_idx]
            pos = int(self._history_positions.get(path, 0))
            if pos <= 0:
                self._history_active_idx += 1
                continue
            to_read = min(self._history_chunk_bytes, pos)
            start = pos - to_read
            try:
                with open(path, 'rb') as f:
                    f.seek(start)
                    data = f.read(to_read)
                text = data.decode('utf-8', 'ignore')
                # 统一行尾为 \n，避免 \r 作为普通字符显示导致"不换行"
                text = text.replace('\r\n', '\n').replace('\r', '\n')
                # 若不在文件开头，丢弃首个不完整行（字节切块可能从行中间开始）
                if start > 0:
                    first_nl = text.find('\n')
                    if first_nl != -1:
                        text = text[first_nl + 1:]
                self._history_positions[path] = start
                return text
            except Exception:
                self._history_active_idx += 1
        return ''

    def _prepend_text(self, text: str):
        """在文档开头插入文本"""
        try:
            old_val = self.verticalScrollBar().value()
            old_max = self.verticalScrollBar().maximum()
            doc_cursor = QTextCursor(self.document())
            doc_cursor.movePosition(QTextCursor.Start)

            # Qt 的 insertText 把 \n 当软换行而非段落分隔符，
            # 必须逐行 insertText + insertBlock 才能正确换行。
            lines = text.split('\n')
            if lines and lines[-1] == '':
                lines = lines[:-1]

            self.setUpdatesEnabled(False)
            doc_cursor.beginEditBlock()
            try:
                for line in lines:
                    doc_cursor.insertText(line)
                    doc_cursor.insertBlock()
            finally:
                doc_cursor.endEditBlock()
                self.setUpdatesEnabled(True)

            new_max = self.verticalScrollBar().maximum()
            delta = new_max - old_max
            self.verticalScrollBar().setValue(old_val + delta)
        except Exception:
            self.setUpdatesEnabled(True)
    
    def process_buffered_data(self):
        """批量处理缓存的数据（在主线程中执行）"""
        # 从缓存中取出数据
        batch_data = []
        with QMutexLocker(self._mutex):
            max_items = max(1, self.batch_size)
            max_chars = max(1024, self.max_batch_chars)
            total_chars = 0
            while self.data_buffer and len(batch_data) < max_items and total_chars < max_chars:
                item = self.data_buffer.popleft()
                batch_data.append(item)
                try:
                    total_chars += len(item.get('data', ''))
                except Exception:
                    pass
        
        if not batch_data:
            self.update_timer.stop()
            return
        
        # 保存当前光标和滚动条位置
        cursor = self.textCursor()
        scroll_bar = self.verticalScrollBar()
        was_at_bottom = scroll_bar.value() == scroll_bar.maximum()
        
        # 批量插入数据
        cursor.movePosition(QTextCursor.End)
        tx_prefix_format = self._tx_prefix_format
        updates_enabled = self.updatesEnabled()

        self.setUpdatesEnabled(False)
        cursor.beginEditBlock()
        try:
            plain_parts = []

            def flush_plain_parts():
                if plain_parts:
                    cursor.insertText(''.join(plain_parts))
                    plain_parts.clear()

            for item in batch_data:
                filtered_data = self.filter_data(item['data'], item.get('is_hex', False))

                if item['add_timestamp'] and item['timestamp_str']:
                    flush_plain_parts()
                    cursor.insertText(item['timestamp_str'])

                if not filtered_data:
                    continue
                
                # 处理发送回显前缀着色
                try:
                    if filtered_data.startswith("[TX STR]") or filtered_data.startswith("[TX HEX]"):
                        flush_plain_parts()
                        end_idx = filtered_data.find("] ")
                        if end_idx != -1:
                            prefix = filtered_data[:end_idx + 2]
                            remainder = filtered_data[end_idx + 2:]
                        else:
                            space_idx = filtered_data.find(" ")
                            if space_idx != -1:
                                prefix = filtered_data[:space_idx + 1]
                                remainder = filtered_data[space_idx + 1:]
                            else:
                                prefix = filtered_data
                                remainder = ""

                        prev_format = cursor.charFormat()
                        cursor.insertText(prefix, tx_prefix_format)
                        cursor.setCharFormat(prev_format)
                        if remainder:
                            cursor.insertText(remainder)
                            try:
                                if filtered_data.startswith("[TX HEX]"):
                                    if not (remainder.endswith("\n") or remainder.endswith("\r")):
                                        cursor.insertText("\r\n")
                            except Exception:
                                pass
                    else:
                        plain_parts.append(filtered_data)
                except Exception:
                    plain_parts.append(filtered_data)
            flush_plain_parts()
        finally:
            cursor.endEditBlock()
            self.setUpdatesEnabled(updates_enabled)
            self.viewport().update()
        
        # 限制显示行数
        self.limit_display_lines()
        
        # 如果之前在底部，保持在底部
        if was_at_bottom and self.fresh_flag:
            scroll_bar.setValue(scroll_bar.maximum())

        with QMutexLocker(self._mutex):
            has_more_data = bool(self.data_buffer)
        if not has_more_data and self.update_timer.isActive():
            self.update_timer.stop()
        
        self.check_and_update_scroll_status()
    
    def limit_display_lines(self):
        """限制显示行数"""
        document = self.document()
        limit = max(0, int(self.max_display_lines))
        if limit <= 0:
            return
        if document.maximumBlockCount() != limit:
            document.setMaximumBlockCount(limit)
    
    def filter_data(self, data, is_hex=False):
        """过滤数据"""
        if is_hex:
            return data
        return self.filter_garbled_text(data)

    def wheelEvent(self, event):
        """滚轮事件"""
        QtWidgets.QTextBrowser.wheelEvent(self, event)
        scroll_bar = self.verticalScrollBar()
        
        if scroll_bar.value() == scroll_bar.maximum():
            self.fresh_flag = True
        else:
            self.fresh_flag = False
    
    def clear_buffer(self):
        """清空数据缓存"""
        with QMutexLocker(self._mutex):
            self.data_buffer.clear()
        if self.update_timer.isActive():
            self.update_timer.stop()
    
    def set_buffer_size(self, size):
        """设置缓存大小"""
        self.max_buffer_size = max(100, size)
    
    def set_update_interval(self, interval_ms):
        """设置更新间隔"""
        self.update_interval = max(10, interval_ms)
        if self.update_timer.isActive():
            self.update_timer.stop()
            self.update_timer.start(self.update_interval)
    
    def set_batch_size(self, size):
        """设置批量处理大小"""
        self.batch_size = max(10, size)

    def set_max_display_lines(self, size):
        """设置最大显示行数"""
        self.max_display_lines = max(1000, size)
        try:
            self.document().setMaximumBlockCount(self.max_display_lines)
        except Exception:
            pass
    
    def get_buffer_status(self):
        """获取缓存状态"""
        with QMutexLocker(self._mutex):
            return {
                'buffer_count': len(self.data_buffer),
                'max_buffer_size': self.max_buffer_size,
                'update_interval': self.update_interval,
                'batch_size': self.batch_size,
                'timer_active': self.update_timer.isActive()
            }
    
    def force_update(self):
        """强制立即处理所有缓存数据"""
        while True:
            with QMutexLocker(self._mutex):
                if not self.data_buffer:
                    break
            self.process_buffered_data()
    
    def check_and_update_scroll_status(self):
        """检查并更新滚动状态"""
        scroll_bar = self.verticalScrollBar()
        if scroll_bar.value() == scroll_bar.maximum():
            self.fresh_flag = True
    
    def scroll_to_bottom(self):
        """滚动到底部"""
        scroll_bar = self.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())
        self.fresh_flag = True
    
    def show_search_dialog(self):
        """显示搜索对话框"""
        dialog = SearchDialog(self)
        dialog.exec()
    
    def change_font_size(self, size_change):
        """更改字体大小"""
        try:
            current_style = self.styleSheet()
            import re
            
            font_size_match = re.search(r'font-size:\s*(\d+)pt', current_style, re.IGNORECASE)
            if font_size_match:
                current_size = int(font_size_match.group(1))
            else:
                current_size = self.font().pointSize()
            
            new_size = max(6, current_size + size_change)
            
            cleaned_style = re.sub(r'font-size:[^;]*;?', '', current_style, flags=re.IGNORECASE)
            cleaned_style = re.sub(r';+', ';', cleaned_style)
            cleaned_style = cleaned_style.strip()
            
            if cleaned_style and not cleaned_style.endswith(';'):
                cleaned_style += ';'
            
            if cleaned_style:
                new_style = f"QTextBrowser {{ font-size: {new_size}pt; }} {cleaned_style}"
            else:
                new_style = f"QTextBrowser {{ font-size: {new_size}pt; }}"
            self.setStyleSheet(new_style)
            
            logger.debug(f"字体大小已调整为: {new_size}pt")
        except Exception as e:
            logger.error(f"字体大小调整失败: {e}")
    
    def change_text_color(self):
        """更改文本颜色"""
        try:
            current_color = self.palette().color(self.foregroundRole())
            color = QColorDialog.getColor(current_color, self)
            if color.isValid():
                current_style = self.styleSheet()
                import re
                
                cleaned_style = re.sub(r'color:[^;]*;?', '', current_style, flags=re.IGNORECASE)
                cleaned_style = re.sub(r';+', ';', cleaned_style)
                cleaned_style = cleaned_style.strip()
                
                if cleaned_style and not cleaned_style.endswith(';'):
                    cleaned_style += ';'
                
                if cleaned_style:
                    if 'QTextBrowser' in cleaned_style:
                        new_style = re.sub(r'(QTextBrowser\s*\{[^}]*)(\})', 
                                          f'\\1 color: {color.name()};\\2', cleaned_style)
                    else:
                        new_style = f"QTextBrowser {{ color: {color.name()}; }} {cleaned_style}"
                else:
                    new_style = f"QTextBrowser {{ color: {color.name()}; }}"
                self.setStyleSheet(new_style)
                
                logger.debug(f"文本颜色已更改为: {color.name()}")
        except Exception as e:
            logger.error(f"文本颜色设置失败: {e}")

    def apply_color_scheme(self, scheme_name: str):
        """应用颜色主题"""
        try:
            fg_bg = MyTextBrowser.COLOR_SCHEMES.get(scheme_name)
            if not fg_bg:
                fg_bg = ("#E0E0E0", "#2B2B2B")
                scheme_name = "Espresso"
            fg, bg = fg_bg
            size_pt = max(6, self.font().pointSize() or 10)
            family = self.font().family() or "Consolas"
            style = f"QTextBrowser {{ color: {fg}; background-color: {bg}; font: {size_pt}pt \"{family}\"; }}"
            self.setStyleSheet(style)
            self._current_scheme = scheme_name
        except Exception as e:
            logger.error(f"应用颜色主题失败: {e}")
    
    def contextMenuEvent(self, event):
        """右键菜单"""
        locale = QLocale.system()
        language = locale.language()
        
        menu = QMenu(self)
        menu_font = QFont()
        menu_font.setPointSize(9)
        menu.setFont(menu_font)
        menu.setStyleSheet("QMenu { font-size: 9pt; } QAction { font-size: 9pt; }")
        
        if language == QLocale.Chinese:
            copy_action = QAction("复制", self)
            select_all_action = QAction("全选", self)
            search_action = QAction("搜索...", self)
            clear_action = QAction("清空", self)
            scroll_to_bottom_action = QAction("滚动到底部", self)
            font_size_increase_action = QAction("增大字体", self)
            font_size_decrease_action = QAction("减小字体", self)
            text_color_action = QAction("文字颜色...", self)
        else:
            copy_action = QAction("Copy", self)
            select_all_action = QAction("Select All", self)
            search_action = QAction("Search...", self)
            clear_action = QAction("Clear", self)
            scroll_to_bottom_action = QAction("Scroll to Bottom", self)
            font_size_increase_action = QAction("Increase Font Size", self)
            font_size_decrease_action = QAction("Decrease Font Size", self)
            text_color_action = QAction("Text Color...", self)
        
        copy_action.triggered.connect(self.copy)
        select_all_action.triggered.connect(self.selectAll)
        search_action.triggered.connect(self.show_search_dialog)
        clear_action.triggered.connect(self.clear)
        scroll_to_bottom_action.triggered.connect(self.scroll_to_bottom)
        font_size_increase_action.triggered.connect(lambda: self.change_font_size(1))
        font_size_decrease_action.triggered.connect(lambda: self.change_font_size(-1))
        text_color_action.triggered.connect(self.change_text_color)
        
        copy_action.setEnabled(self.textCursor().hasSelection())
        
        menu.addAction(copy_action)
        menu.addAction(select_all_action)
        menu.addSeparator()
        menu.addAction(search_action)
        menu.addSeparator()
        
        font_menu = menu.addMenu("字体设置" if language == QLocale.Chinese else "Font Settings")
        font_menu.addAction(font_size_increase_action)
        font_menu.addAction(font_size_decrease_action)
        font_menu.addSeparator()
        font_menu.addAction(text_color_action)
        
        theme_menu = menu.addMenu("配色主题" if language == QLocale.Chinese else "Color Theme")
        for name in MyTextBrowser.COLOR_SCHEMES.keys():
            act = QAction(name, self)
            act.triggered.connect(lambda checked=False, n=name: (self.apply_color_scheme(n), self.colorSchemeSelected.emit(n)))
            theme_menu.addAction(act)

        menu.addSeparator()
        menu.addAction(clear_action)
        menu.addAction(scroll_to_bottom_action)
        
        menu.exec(event.globalPos())
