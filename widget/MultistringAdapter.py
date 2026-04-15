#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多字符串面板适配器 - 将新的MultistringWidget集成到main.py

功能说明:
    - 保持原有API兼容性
    - 数据同步
    - 信号转发
    - 配置迁移

作者: Gavin
版本: 4.0.0
日期: 2026-02-06
"""

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget
from functools import partial
import logging

from widget.MultistringWidget import MultistringWidget

# 配置日志
logger = logging.getLogger(__name__)


class MultistringAdapter(QObject):
    """
    多字符串面板适配器
    
    将新的MultistringWidget集成到现有的main.py中，
    保持原有的函数调用接口
    """
    
    # 信号转发
    sendCommand = Signal(int, str, bool, int)  # index, command, is_hex, delay_ms
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.panel = None
        self.ui = None
        self.uithreadObj = None
        self.MainWindow = None
        self.groupBox_customs = None
        
        # 保持与原有代码兼容的状态变量
        self._loop_running = False
        self._onclick_customs_running = {}
        self._seq_worker = None
        
        # 保存原始函数引用（用于补丁）
        self._original_startLoopExecution = None
        self._original_stopLoopExecution = None
        
    def setup(self, groupBox_customs, ui, uithreadObj, MainWindow):
        """
        设置适配器
        
        Args:
            groupBox_customs: 父容器（原来的groupBox_customs）
            ui: UI对象
            uithreadObj: 串口线程对象
            MainWindow: 主窗口对象
        """
        self.ui = ui
        self.uithreadObj = uithreadObj
        self.MainWindow = MainWindow
        self.groupBox_customs = groupBox_customs
        
        logger.info(f"开始设置MultistringAdapter，父控件: {groupBox_customs.objectName() if groupBox_customs else 'None'}")
        
        # 创建新的面板
        self.panel = MultistringWidget(row_count=36)
        
        # 连接信号
        self.panel.sendCommand.connect(self._on_send_command)
        self.panel.startSequential.connect(self._on_start_sequential)
        self.panel.stopSequential.connect(self._on_stop_sequential)
        self.panel.importConfig.connect(self._on_import_config)
        self.panel.exportConfig.connect(self._on_export_config)
        
        # 将新面板添加到groupBox_customs的布局中
        if groupBox_customs:
            # 获取现有布局
            layout = groupBox_customs.layout()
            if layout:
                logger.info(f"找到现有布局，项目数: {layout.count()}")
                
                # 隐藏布局中的所有原有控件（但不删除）
                for i in range(layout.count()):
                    item = layout.itemAt(i)
                    if item and item.widget():
                        widget = item.widget()
                        widget.setVisible(False)
                        logger.info(f"隐藏控件: {widget.objectName()}")
                    elif item and item.layout():
                        # 隐藏子布局中的所有控件
                        sub_layout = item.layout()
                        for j in range(sub_layout.count()):
                            sub_item = sub_layout.itemAt(j)
                            if sub_item and sub_item.widget():
                                sub_item.widget().setVisible(False)
                
                # 在布局末尾添加新面板
                layout.addWidget(self.panel)
                logger.info("新面板已添加到布局")
            else:
                # 如果没有布局，创建新布局
                layout = QVBoxLayout(groupBox_customs)
                layout.setContentsMargins(2, 2, 2, 2)
                layout.setSpacing(2)
                layout.addWidget(self.panel)
                logger.info("创建新布局并添加面板")
        
        # 确保面板可见
        self.panel.show()
        self.panel.setVisible(True)
        
        # 强制更新
        if groupBox_customs:
            groupBox_customs.update()
            groupBox_customs.repaint()
        
        # 迁移数据
        self._migrate_data()
        
        # 自动打补丁：替换main模块中的函数
        self._patch_main_module()
        
        logger.info("MultistringAdapter设置完成")
        
    def _patch_main_module(self):
        """自动打补丁，替换main模块中的函数"""
        try:
            import sys
            main_module = sys.modules.get('__main__')
            if main_module is None:
                return
                
            # 保存原始函数引用
            if hasattr(main_module, 'startLoopExecution'):
                self._original_startLoopExecution = main_module.startLoopExecution
            if hasattr(main_module, 'stopLoopExecution'):
                self._original_stopLoopExecution = main_module.stopLoopExecution
                
            # 替换为适配器的方法
            main_module.startLoopExecution = self.startLoopExecution
            main_module.stopLoopExecution = self.stopLoopExecution
            
            logger.info("main模块函数已自动打补丁")
        except Exception as e:
            logger.warning(f"自动打补丁失败: {e}")
            
    def _migrate_data(self):
        """从旧UI迁移数据到新面板"""
        try:
            for i in range(1, 37):  # 迁移前36行
                try:
                    # 获取旧数据
                    old_edit = getattr(self.ui, f'ed_customs_set_{i}', None)
                    old_hex = getattr(self.ui, f'checkBox_hex_{i}', None)
                    old_seq = getattr(self.ui, f'ed_customs_seq_{i}', None)
                    old_delay = getattr(self.ui, f'ed_customs_delay_{i}', None)
                    
                    if old_edit and old_edit.text():
                        self.panel.set_row_data(
                            index=i,
                            command=old_edit.text(),
                            is_hex=old_hex.isChecked() if old_hex else False,
                            sequence=old_seq.text() if old_seq else "",
                            delay=old_delay.text() if old_delay else ""
                        )
                except Exception as e:
                    logger.warning(f"迁移第{i}行数据失败: {e}")
                    
            logger.info("数据迁移完成")
        except Exception as e:
            logger.error(f"数据迁移失败: {e}")
            
    def _on_send_command(self, index, command, is_hex, delay_ms):
        """处理发送命令"""
        # 调用原有的发送逻辑
        self._send_custom_data(index, command, is_hex, delay_ms)
        
    def _send_custom_data(self, index, text, is_hex, delay_ms):
        """
        发送自定义数据
        保持与原有sendCustomData函数相同的逻辑
        """
        if self.ui.bt_open_off_port.text() == '关闭串口':
            buff = text.strip()
            
            if not buff:
                return
                
            if not is_hex:
                # 文本模式发送
                send_data = (buff + "\r\n").encode('utf-8')
                self.uithreadObj.sendBuff(send_data)
                # 更新发送统计
                self.ui.update_send_stats(len(send_data))
                self.ui.add_send_rate(len(send_data))
                # 发送回显
                self._echo_sent_bytes(send_data)
            else:
                # HEX模式发送
                send_list = []
                while buff != '':
                    try:
                        num = int(buff[0:2], 16)
                    except ValueError:
                        from PySide6.QtWidgets import QMessageBox
                        QMessageBox.critical(self.MainWindow, '警告', '请输入十六进制的数据，并以空格分开!')
                        return
                    buff = buff[2:].strip()
                    send_list.append(num)
                input_s = bytes(send_list)
                self.uithreadObj.sendBuff(input_s)
                # 更新发送统计
                self.ui.update_send_stats(len(input_s))
                self.ui.add_send_rate(len(input_s))
                # 发送回显
                self._echo_sent_bytes(input_s)
                
            # 处理延迟
            if delay_ms > 0:
                import time
                from PySide6.QtWidgets import QApplication
                start_time = time.time()
                while (time.time() - start_time) < (delay_ms / 1000.0):
                    QApplication.processEvents()
                    time.sleep(0.001)
                    
    def _echo_sent_bytes(self, data_bytes):
        """在接收区回显已发送内容"""
        try:
            if not hasattr(self.ui, 'checkBox_show_send'):
                return
            if not self.ui.checkBox_show_send.isChecked():
                return

            # 如果用户当前选择了HEX发送，则优先HEX回显
            send_hex_mode = False
            try:
                send_hex_mode = self.ui.checkBox_send_hex.isChecked()
            except Exception:
                send_hex_mode = False

            def bytes_to_hex(b):
                return ' '.join(f"{x:02X}" for x in b)

            if send_hex_mode:
                out_s = "[TX HEX] " + bytes_to_hex(data_bytes)
                self.ui.textBrowserShow.append_received_data(
                    data=out_s, is_hex=True, add_timestamp=False, timestamp_str=""
                )
                return

            # 自动判断：能严格按UTF-8解码且主要为可打印字符就按字符串显示
            try:
                s_strict = data_bytes.decode('utf-8', 'strict')
                s_check = s_strict.replace('\n', '').replace('\r', '').replace('\t', '')
                is_printable = s_check.isprintable()
            except Exception:
                is_printable = False

            if is_printable:
                out_s = "[TX STR] " + s_strict
                self.ui.textBrowserShow.append_received_data(
                    data=out_s, is_hex=False, add_timestamp=False, timestamp_str=""
                )
            else:
                out_s = "[TX HEX] " + bytes_to_hex(data_bytes)
                self.ui.textBrowserShow.append_received_data(
                    data=out_s, is_hex=True, add_timestamp=False, timestamp_str=""
                )
        except Exception as e:
            logger.error(f"发送回显失败: {e}")
            
    def _on_start_sequential(self):
        """开始顺序执行"""
        self._start_loop_execution()
        
    def _on_stop_sequential(self):
        """停止顺序执行"""
        self._stop_loop_execution()
        
    def _start_loop_execution(self):
        """开始循环执行 - 使用后台线程，避免阻塞UI"""
        import sys
        main_module = sys.modules.get('__main__')
        SequenceWorker = getattr(main_module, 'SequenceWorker', None)

        # 收集有序号且有内容的行
        rows_data = self.panel.get_all_data()
        sequenced_rows = []
        used_seqs = set()
        dup_seqs = []

        for data in rows_data:
            if data['sequence'] and data['command']:
                try:
                    seq = int(data['sequence'])
                    if seq > 0:
                        if seq in used_seqs:
                            if seq not in dup_seqs:
                                dup_seqs.append(seq)
                            continue
                        used_seqs.add(seq)
                        delay_ms = 0
                        try:
                            delay_ms = int(data['delay']) if data['delay'] else 0
                        except ValueError:
                            pass
                        sequenced_rows.append({
                            'index': data['index'],
                            'seq_num': seq,
                            'text': data['command'],
                            'is_hex': data['is_hex'],
                            'delay': delay_ms
                        })
                except ValueError:
                    pass

        if dup_seqs:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self.MainWindow, '序号重复',
                f'发现重复序号: {", ".join(map(str, dup_seqs))}\n请修正后重试。'
            )
            self.panel.set_running_state(False, '序号重复')
            return

        if not sequenced_rows:
            self.panel.set_running_state(False, '无序列项')
            return

        # 按序号排序
        sequenced_rows.sort(key=lambda x: x['seq_num'])

        # 循环配置
        is_loop = self.panel.loop_checkbox.isChecked()
        max_loops = 0
        if is_loop:
            try:
                max_loops = int(self.panel.loop_count_edit.text()) if self.panel.loop_count_edit.text() else 0
            except ValueError:
                max_loops = 0

        if SequenceWorker is None:
            logger.error('SequenceWorker 不可用')
            self.panel.set_running_state(False, '内部错误')
            return

        self._seq_worker = SequenceWorker(sequenced_rows, is_loop, max_loops)

        def _on_status(s):
            self.panel.set_running_state(True, s.replace('状态: ', ''))

        def _on_progress(count, total):
            label = f"运行中 ({count}/{total if total > 0 else '∞'})"
            self.panel.set_running_state(True, label)

        def _on_finished(reason):
            self._loop_running = False
            self.panel.set_running_state(
                False, '已完成' if reason == 'completed' else '已停止'
            )

        self._seq_worker.statusChanged.connect(_on_status)
        self._seq_worker.progress.connect(_on_progress)
        self._seq_worker.finishedSignal.connect(_on_finished)

        self._loop_running = True
        self._seq_worker.start()
        
    def _stop_loop_execution(self):
        """停止循环执行"""
        self._loop_running = False
        worker = getattr(self, '_seq_worker', None)
        if worker and worker.isRunning():
            worker.stop()
        self.panel.set_running_state(False, '已停止')
        
    def _on_import_config(self):
        """导入配置"""
        try:
            logger.info("导入配置")
        except Exception as e:
            logger.error(f"导入配置失败: {e}")
            
    def _on_export_config(self):
        """导出配置"""
        try:
            logger.info("导出配置")
        except Exception as e:
            logger.error(f"导出配置失败: {e}")
            
    # ========== 兼容原有API ==========
    
    def initCustomsUI(self):
        """初始化多字符串UI（兼容原有函数）"""
        logger.debug("MultistringAdapter.initCustomsUI被调用")
        # 新面板已经初始化完成，无需额外操作
        
    def OnclickCustoms(self, index):
        """点击自定义按钮（兼容原有函数）"""
        # 防止重复调用
        if self._onclick_customs_running.get(index, False):
            return
            
        self._onclick_customs_running[index] = True
        
        try:
            data = self.panel.get_row_data(index)
            if data and data['command']:
                delay_ms = 0
                try:
                    delay_ms = int(data['delay']) if data['delay'] else 0
                except ValueError:
                    pass
                    
                self._send_custom_data(index, data['command'], data['is_hex'], delay_ms)
        finally:
            self._onclick_customs_running[index] = False
            
    def DoubleOnclickCustoms(self, index):
        """双击自定义按钮（兼容原有函数）"""
        # 可以实现编辑注释功能
        pass
        
    def save_custom_button_config(self, index, text):
        """保存自定义按钮配置（兼容原有函数）"""
        # 新面板自动保存，无需额外操作
        pass
        
    def save_custom_hex_config(self, index, is_hex):
        """保存HEX配置（兼容原有函数）"""
        pass
        
    def save_custom_delay_config(self, index, delay):
        """保存延迟配置（兼容原有函数）"""
        pass
        
    def save_custom_seq_config(self, index, seq):
        """保存序号配置（兼容原有函数）"""
        self.panel._check_duplicate_sequences()
        
    def update_all_seq_styles(self):
        """更新所有序号样式（兼容原有函数）"""
        self.panel._check_duplicate_sequences()
        
    def startLoopExecution(self):
        """开始循环执行（兼容原有函数）"""
        self._start_loop_execution()
        
    def stopLoopExecution(self):
        """停止循环执行（兼容原有函数）"""
        self._stop_loop_execution()
        
    def get_panel(self):
        """获取面板实例"""
        return self.panel
        
    def sync_to_old_ui(self):
        """将新面板数据同步回旧UI（用于保存配置）"""
        try:
            all_data = self.panel.get_all_data()
            for data in all_data:
                index = data['index']
                try:
                    # 同步到旧UI控件
                    old_edit = getattr(self.ui, f'ed_customs_set_{index}', None)
                    old_hex = getattr(self.ui, f'checkBox_hex_{index}', None)
                    old_seq = getattr(self.ui, f'ed_customs_seq_{index}', None)
                    old_delay = getattr(self.ui, f'ed_customs_delay_{index}', None)
                    
                    if old_edit:
                        old_edit.setText(data['command'])
                    if old_hex:
                        old_hex.setChecked(data['is_hex'])
                    if old_seq:
                        old_seq.setText(data['sequence'])
                    if old_delay:
                        old_delay.setText(data['delay'])
                        
                except Exception as e:
                    logger.warning(f"同步第{index}行数据失败: {e}")
                    
            logger.info("数据同步完成")
        except Exception as e:
            logger.error(f"数据同步失败: {e}")


# 全局适配器实例
_multistring_adapter = None


def init_multistring_adapter(groupBox_customs, ui, uithreadObj, MainWindow):
    """
    初始化多字符串适配器
    
    Args:
        groupBox_customs: 父容器（ui.groupBox_customs）
        ui: UI对象
        uithreadObj: 串口线程对象
        MainWindow: 主窗口对象
        
    Returns:
        MultistringAdapter: 适配器实例
    """
    global _multistring_adapter
    
    if _multistring_adapter is None:
        _multistring_adapter = MultistringAdapter()
        _multistring_adapter.setup(groupBox_customs, ui, uithreadObj, MainWindow)
        logger.info("多字符串适配器已初始化")
    
    return _multistring_adapter


def get_multistring_adapter():
    """获取多字符串适配器实例"""
    return _multistring_adapter
