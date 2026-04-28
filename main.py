from PySide6.QtCore import *
from Uart.uart_thread import *
from datetime import datetime
import time
from PySide6.QtGui import QIntValidator, QTextCursor, QIcon
from PySide6 import QtCore, QtWidgets
from PySide6.QtWidgets import (QApplication, QMessageBox, QGridLayout, QFileDialog,
                               QInputDialog, QMenu, QDialog)
from widget.MyTextBrowser import MyTextBrowser
from UI_Serial import Ui_Kero_Serial
from functools import partial
import sys
import re
import os
import subprocess
import logging
import serial
import threading
from collections import deque
from widget.AdvancedFunctionDialog import AdvancedFunctionDialog
from widget.SerialSettingsDialog import SerialSettingsDialog
from logger import SerialLogger
from widget.AutoReplyEngine import AutoReplyEngine


# 配置Python logging模块
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def normalize_saved_log_text(text: str) -> str:
    """Normalize Qt/plain-text line separators before writing a log file."""
    if not text:
        return ""
    return (
        text.replace('\r\n', '\n')
            .replace('\r', '\n')
            .replace('\u2028', '\n')
            .replace('\u2029', '\n')
    )

# 获取软件版本号
def get_app_version():
    try:
        # 尝试读取打包时生成的版本文件
        if hasattr(sys, '_MEIPASS'):
            # 打包后的环境，从临时目录读取
            version_file = os.path.join(sys._MEIPASS, 'version.txt')
        else:
            # 开发环境，从当前目录读取
            version_file = os.path.join(os.path.dirname(__file__), 'version.txt')
        
        if os.path.exists(version_file):
            with open(version_file, 'r', encoding='utf-8') as f:
                version = f.read().strip()
                if version:
                    return version
    except Exception as e:
        logger.warning("读取版本文件失败: %s", e)
    
    # 如果读取版本文件失败，尝试通过git获取（仅开发环境）
    try:
        result = subprocess.run(['git', 'rev-list', '--count', 'HEAD'], 
                              capture_output=True, text=True, cwd=os.path.dirname(__file__))
        if result.returncode == 0:
            git_count = int(result.stdout.strip())
            major_ver = 1
            minor_ver = 0
            patch_ver_h = git_count // 100
            patch_ver_l = git_count % 100
            return f"{major_ver}.{minor_ver}.{patch_ver_h}.{patch_ver_l}"
    except:
        pass
    
    # 默认版本号
    return "1.0.0.0"

APP_VERSION = get_app_version()

_multistring_adapter = None

DEFAULT_BAUD_ARRAY = ('300', '600', '1200', '2400','4800', '9600',  '14400', '19200', '38400', '57600', '115200', '230400', '460800', '921600', '1000000', '1500000', '2000000')
GET_PORT_ARRAY = []

# 全局串口设置变量，用于存储当前的串口配置
SERIAL_SETTINGS = {
    'baud_index': 10,  # 默认115200 (在新数组中的索引是10)
    'data_bits_index': 0,  # 默认8位
    'parity_index': 0,  # 默认无校验
    'stop_bits_index': 0,  # 默认1位停止位
    'flow_control': 'none',  # 流控模式: 'none', 'rtscts', 'xonxoff'
    'timeout': 1.0
}

serial_logger = SerialLogger()
auto_reply_engine = AutoReplyEngine()

FILTER_UPDATE_INTERVAL_MS = 1000
FILTER_MAX_CHUNKS_PER_TICK = 64
FILTER_MAX_QUEUE_CHUNKS = 2000
_filter_pending_chunks = deque()
_filter_update_timer = None
RECEIVE_UPDATE_INTERVAL_MS = 40
RECEIVE_MAX_CHUNKS_PER_TICK = 128
RECEIVE_MAX_BYTES_PER_TICK = 512 * 1024
RECEIVE_MAX_QUEUE_BYTES = 8 * 1024 * 1024
RECEIVE_MERGE_THRESHOLD = 64 * 1024
_receive_pending_chunks = deque()
_receive_pending_bytes = 0
_receive_dropped_bytes = 0
_receive_update_timer = None

# ---- 断线自动重连监视器 ----
_reconnect_timer = None        # QTimer，每 1s 触发一次
_reconnect_deadline = None     # 超时时刻（time.time() 值）
_reconnect_port = None         # 断线时记录的端口号
_reconnect_baud = None         # 断线时记录的波特率
_reconnect_active = False      # 是否处于自动重连状态

class MyWindow(QtWidgets.QMainWindow, Ui_Kero_Serial):  # 继承QWidget和Ui_Form
    def __init__(self):
        super(MyWindow, self).__init__()  # 超级加载
        self.setupUi(self)  # 初始化界面
        self.tabWidget_2.tabCloseRequested.connect(self.tabClose)
        # Main标签(index=0)不可关闭，隐藏其关闭按钮
        self.tabWidget_2.tabBar().setTabButton(0, QtWidgets.QTabBar.RightSide, None)
        self.btSaveLog.clicked.connect(self.slot_btn_chooseDir)
        
        # 初始化统计变量
        self.send_packet_count = 0
        self.send_byte_count = 0
        self.recv_packet_count = 0
        self.recv_byte_count = 0
        self.last_update_time = time.time()
        self.send_rate = 0.0
        self.recv_rate = 0.0
        
        # 创建定时器用于更新速率
        self.stats_timer = QtCore.QTimer()
        self.stats_timer.timeout.connect(self.update_stats_display)
        self.stats_timer.start(1000)  # 每秒更新一次

        # 绑定日志器与接收区，支持分片后清空与上滑读取历史
        try:
            if hasattr(self, 'textBrowserShow') and self.textBrowserShow is not None:
                self.textBrowserShow.attach_logger(serial_logger)
                serial_logger.on_new_part = self.textBrowserShow.on_logger_new_part
        except Exception as e:
            logger.warning("绑定日志历史加载失败: %s", e)

    def tabClose(self, index):
        # Main标签(index=0)不允许关闭
        if index == 0:
            return
        # 获取要关闭的标签页
        tab_widget = self.tabWidget_2.widget(index)
        if tab_widget:
            # 查找该标签页中的过滤控件，获取控件ID
            regexp_widget = tab_widget.findChild(QtWidgets.QLineEdit)
            if regexp_widget and "Filter_Regexp_" in regexp_widget.objectName():
                # 提取控件ID
                control_id = regexp_widget.objectName().replace("Filter_Regexp_", "")
                
                # 删除对应的配置项
                mSetting = QSettings(QSettings.IniFormat, QSettings.UserScope, "Gavin", "Gavin_com")
                
                # 删除该过滤标签页的所有配置
                config_keys_to_remove = [
                    f"filter_regexp_{control_id}",
                    f"filter_case_sensitive_{control_id}", 
                    f"filter_invert_mode_{control_id}"
                ]
                
                for key in config_keys_to_remove:
                    if mSetting.contains(key):
                        mSetting.remove(key)
                        logger.debug("已删除配置项: %s", key)
                
                # 重新计算并更新过滤标签页数量
                remaining_count = 0
                for tab_idx in range(self.tabWidget_2.count()):
                    if tab_idx != index:  # 跳过即将删除的标签页
                        tab = self.tabWidget_2.widget(tab_idx)
                        if tab:
                            regexp = tab.findChild(QtWidgets.QLineEdit)
                            if regexp and "Filter_Regexp_" in regexp.objectName():
                                remaining_count += 1
                
                mSetting.setValue("filter_tab_count", remaining_count)
                mSetting.sync()
                logger.debug("更新过滤标签页数量为: %s", remaining_count)
        
        # 移除标签页
        self.tabWidget_2.removeTab(index)

    def slot_btn_chooseDir(self):
        uart_port = GET_PORT_ARRAY[ui.comboBox_port.currentIndex()]
        time_str = datetime.now().strftime('%Y%m%d-%H%M%S')
        default_name = './' + uart_port + '_' + time_str + '.log'
        fileName2,Type = QFileDialog.getSaveFileName(self, "文件保存", default_name, "Log Files (*.log)")
        if not fileName2:
            return
        try:
            try:
                self.textBrowserShow.force_update()
            except Exception:
                pass
            qS = normalize_saved_log_text(self.textBrowserShow.toPlainText())
            with open(fileName2, 'w', encoding='utf-8') as f:
                f.write(qS)
        except Exception as e:
            logger.error(f"保存日志失败: {e}")
    
    def update_send_stats(self, byte_count):
        """更新发送统计"""
        self.send_packet_count += 1
        self.send_byte_count += byte_count
        
    def update_recv_stats(self, byte_count):
        """更新接收统计"""
        self.recv_packet_count += 1
        self.recv_byte_count += byte_count
        
    def update_stats_display(self):
        """更新统计信息显示"""
        current_time = time.time()
        time_diff = current_time - self.last_update_time
        
        if time_diff >= 1.0:  # 每秒计算一次速率
            # 计算发送速率 (字节/秒)
            send_rate_bps = self.send_rate
            send_rate_kbps = send_rate_bps / 1024.0
            
            # 计算接收速率 (字节/秒)
            recv_rate_bps = self.recv_rate
            recv_rate_kbps = recv_rate_bps / 1024.0
            
            # 格式化显示文本
            if send_rate_kbps >= 1.0:
                send_rate_str = f"{send_rate_kbps:.2f}KB/s"
            else:
                send_rate_str = f"{send_rate_bps:.0f}B/s"
                
            if recv_rate_kbps >= 1.0:
                recv_rate_str = f"{recv_rate_kbps:.2f}KB/s"
            else:
                recv_rate_str = f"{recv_rate_bps:.0f}B/s"
            
            stats_text = f"TX:{self.send_packet_count}/{self.send_byte_count}B ({send_rate_str})\nRX:{self.recv_packet_count}/{self.recv_byte_count}B ({recv_rate_str})"
            self.label_stats.setText(stats_text)
            
            # 重置速率计算
            self.send_rate = 0.0
            self.recv_rate = 0.0
            self.last_update_time = current_time
    
    def add_send_rate(self, bytes_sent):
        """添加发送字节数到速率计算"""
        self.send_rate += bytes_sent
        
    def add_recv_rate(self, bytes_received):
        """添加接收字节数到速率计算"""
        self.recv_rate += bytes_received
    
    def closeEvent(self, event):
        """程序退出时保存所有设置"""
        try:
            # 保存设置
            save_all_settings()
            
            # 停止定时器
            if hasattr(self, 'timer_send') and self.timer_send.isActive():
                self.timer_send.stop()
            
            # 停止顺序/循环后台线程
            if hasattr(self, 'seq_worker'):
                try:
                    if self.seq_worker and self.seq_worker.isRunning():
                        self.seq_worker.stop()
                        # 等待最多 2 秒退出
                        self.seq_worker.wait(2000)
                except Exception as e:
                    logger.warning("清理顺序线程时出错: %s", e)
            
            # 停止自动重连监视器（如正在重连中）
            try:
                if '_reconnect_active' in globals() and _reconnect_active:
                    _stop_reconnect_watchdog()
            except Exception as e:
                logger.warning("停止重连监视器时出错: %s", e)

            # 关闭串口并清理线程
            if 'uithreadObj' in globals():
                try:
                    # 尝试关闭串口
                    current_port = GET_PORT_ARRAY[ui.comboBox_port.currentIndex()] if GET_PORT_ARRAY else ""
                    if current_port:
                        uithreadObj.try_off_port(current_port, 115200)
                    
                    # 等待线程结束
                    if hasattr(uithreadObj, 'uartObj') and hasattr(uithreadObj.uartObj, 'mThread'):
                        if uithreadObj.uartObj.mThread.isRunning():
                            uithreadObj.uartObj.mThread.quit()
                            uithreadObj.uartObj.mThread.wait(3000)  # 等待最多3秒
                except Exception as e:
                    logger.warning(f"清理串口线程时出错: {e}")
        except Exception as e:
            logger.error(f"程序退出时出错: {e}")
        finally:
            event.accept()


def history_filter(ui):
    """历史记录筛选功能 - 直接使用Filter_Regexp文本框内容进行筛选"""
    # 获取当前活动的过滤tab
    current_tab = ui.tabWidget_2.currentWidget()
    if not hasattr(current_tab, 'findChild'):
        return
        
    # 获取当前tab中的控件
    filter_browser = current_tab.findChild(MyTextBrowser)
    filter_regexp = current_tab.findChild(QtWidgets.QLineEdit)
    
    # 查找复选框控件
    case_sensitive_checkbox = None
    invert_mode_checkbox = None
    checkboxes = current_tab.findChildren(QtWidgets.QCheckBox)
    for checkbox in checkboxes:
        if "CaseSensitive" in checkbox.objectName():
            case_sensitive_checkbox = checkbox
        elif "InvertMode" in checkbox.objectName():
            invert_mode_checkbox = checkbox
    
    if not filter_browser or not filter_regexp:
        return
        
    # 获取Filter_Regexp文本框的内容
    filter_text = filter_regexp.text().strip()
    if not filter_text:
        return
    
    # 获取选项状态
    case_sensitive = case_sensitive_checkbox.isChecked() if case_sensitive_checkbox else False
    invert_mode = invert_mode_checkbox.isChecked() if invert_mode_checkbox else False
    
    if filter_browser:
            # 先刷新主接收区缓存，确保最新数据已渲染（否则 toPlainText 只含已显示的旧数据）
            try:
                ui.textBrowserShow.force_update()
            except Exception:
                pass
            # 获取原始数据
            original_text = ui.textBrowserShow.toPlainText()
            lines = original_text.split('\n')
            
            # 尝试正则表达式匹配，如果失败则使用关键字匹配
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                pattern = re.compile(filter_text, flags)
                if invert_mode:
                    filtered_lines = [line for line in lines if not pattern.search(line)]
                else:
                    filtered_lines = [line for line in lines if pattern.search(line)]
            except re.error:
                # 正则表达式无效，使用关键字匹配
                search_text = filter_text if case_sensitive else filter_text.lower()
                if invert_mode:
                    if case_sensitive:
                        filtered_lines = [line for line in lines if search_text not in line]
                    else:
                        filtered_lines = [line for line in lines if search_text not in line.lower()]
                else:
                    if case_sensitive:
                        filtered_lines = [line for line in lines if search_text in line]
                    else:
                        filtered_lines = [line for line in lines if search_text in line.lower()]
            
            filtered_text = '\n'.join(filtered_lines)
            
            # 更新过滤浏览器内容（走 MyTextBrowser 渲染路径，继承主题字体和颜色）
            filter_browser.clear()
            # 确保过滤浏览器的字体与主接收区一致（包括文档默认字体）
            try:
                base_font = extract_effective_font_from_widget(ui.textBrowserShow)
                filter_browser.setFont(base_font)
                try:
                    filter_browser.document().setDefaultFont(base_font)
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"[历史筛选] 字体设置失败: {e}")
            try:
                filter_browser.append_received_data(filtered_text, is_hex=False, add_timestamp=False, timestamp_str="")
                # 立即刷新，避免等待定时器
                filter_browser.force_update()
            except Exception:
                filter_browser.append(filtered_text)

def add_filter(ui):
    ui.add_cnt = ui.add_cnt + 1
    tab_new = QtWidgets.QWidget()
    tab_new_layout = QGridLayout(tab_new)
    layout_name = "gridLayout_" + str(ui.add_cnt)
    tab_new_layout.setObjectName(layout_name)
    new_verticalLayout = QtWidgets.QVBoxLayout()
    new_verticalLayout.setSpacing(3)
    verticalLayout_name = "verticalLayout_" + str(ui.add_cnt)
    new_verticalLayout.setObjectName(verticalLayout_name)
    new_FilterBrowser = MyTextBrowser(tab_new)
    FilterBrowser_name = "FilterBrowser_" + str(ui.add_cnt)
    new_FilterBrowser.setObjectName(FilterBrowser_name)
    # 确保新建的Filter使用与主接收区相同的字体样式
    new_FilterBrowser.setStyleSheet("font: 10pt \"Consolas\";")
    new_verticalLayout.addWidget(new_FilterBrowser)
    try:
        # 新建标签页的字体与主接收区保持一致
        base_font = extract_effective_font_from_widget(ui.textBrowserShow)
        new_FilterBrowser.setFont(base_font)
        try:
            new_FilterBrowser.document().setDefaultFont(base_font)
        except Exception:
            pass
        
        # 应用当前全局主题到新建过滤视图，并连接右键主题选择信号
        new_FilterBrowser.apply_color_scheme(CURRENT_COLOR_THEME)
        new_FilterBrowser.colorSchemeSelected.connect(on_theme_changed)
    except Exception as e:
        logger.warning("[新建Filter] 字体设置失败: %s", e)
    horizontalLayout_new = QtWidgets.QHBoxLayout()
    horizontalLayout_new.setSpacing(3)
    horizontalLayout_name = "horizontalLayout_" + str(ui.add_cnt)
    horizontalLayout_new.setObjectName(horizontalLayout_name)
    Regexp_new = QtWidgets.QLineEdit(tab_new)
    Regexp_new.setFixedWidth(300)  # 设置固定宽度为300px
    Regexp_new_name = "Filter_Regexp_" + str(ui.add_cnt)
    Regexp_new.setObjectName(Regexp_new_name)
    horizontalLayout_new.addWidget(Regexp_new)
    
    # 添加区分大小写单选框
    CaseSensitive_new = QtWidgets.QCheckBox(tab_new)
    CaseSensitive_new_name = "CaseSensitiveCheckBox_" + str(ui.add_cnt)
    CaseSensitive_new.setObjectName(CaseSensitive_new_name)
    CaseSensitive_new.setText("区分大小写")
    horizontalLayout_new.addWidget(CaseSensitive_new)
    
    # 添加反选模式单选框
    InvertMode_new = QtWidgets.QCheckBox(tab_new)
    InvertMode_new_name = "InvertModeCheckBox_" + str(ui.add_cnt)
    InvertMode_new.setObjectName(InvertMode_new_name)
    InvertMode_new.setText("反选模式")
    horizontalLayout_new.addWidget(InvertMode_new)
    
    # 添加历史记录过滤按钮
    HistoryFilter_new = QtWidgets.QPushButton(tab_new)
    HistoryFilter_new.setMinimumSize(QtCore.QSize(75, 0))
    HistoryFilter_new_name = "HistoryFilterButton_" + str(ui.add_cnt)
    HistoryFilter_new.setObjectName(HistoryFilter_new_name)
    HistoryFilter_new.setText("历史记录筛选")
    horizontalLayout_new.addWidget(HistoryFilter_new)
    
    horizontalLayout_new.addStretch()  # 添加弹性空间
    new_verticalLayout.addLayout(horizontalLayout_new)
    tab_new_layout.addLayout(new_verticalLayout, 0, 0, 1, 1)
    ui.tabWidget_2.addTab(tab_new, "Filter" + str(ui.add_cnt))
    
    # 连接历史记录过滤按钮的点击事件
    HistoryFilter_new.clicked.connect(partial(history_filter, ui))
    
    # 为新增的过滤输入框添加实时保存机制
    Regexp_new.textChanged.connect(lambda text, tab_id=ui.add_cnt: save_params_local(f'filter_regexp_{tab_id}', text))
    CaseSensitive_new.stateChanged.connect(lambda state, tab_id=ui.add_cnt: save_params_local(f'filter_case_sensitive_{tab_id}', state == 2))
    InvertMode_new.stateChanged.connect(lambda state, tab_id=ui.add_cnt: save_params_local(f'filter_invert_mode_{tab_id}', state == 2))
    

def _process_filter_pending_chunks():
    """批量处理过滤tab待更新数据，降低高频接收时主线程负载。"""
    global _filter_pending_chunks, _filter_update_timer

    if not _filter_pending_chunks:
        if _filter_update_timer is not None and _filter_update_timer.isActive():
            _filter_update_timer.stop()
        return

    filter_targets = []
    for j in range(1, ui.tabWidget_2.count()):
        current_tab = ui.tabWidget_2.widget(j)
        if current_tab is None:
            continue

        regexp_line = current_tab.findChild(QtWidgets.QLineEdit)
        if not regexp_line:
            continue

        filter_text = regexp_line.text().strip()
        if not filter_text:
            continue

        browser = current_tab.findChild(QtWidgets.QTextBrowser)
        if browser is None:
            continue

        invert_mode = False
        case_sensitive = False
        for checkbox in current_tab.findChildren(QtWidgets.QCheckBox):
            obj_name = checkbox.objectName()
            if "InvertMode" in obj_name:
                invert_mode = checkbox.isChecked()
            elif "CaseSensitive" in obj_name:
                case_sensitive = checkbox.isChecked()

        flags = 0 if case_sensitive else re.IGNORECASE
        regex_compiled = None
        keyword = None
        try:
            regex_compiled = re.compile(filter_text, flags)
        except re.error:
            keyword = filter_text if case_sensitive else filter_text.lower()

        filter_targets.append({
            'browser': browser,
            'invert_mode': invert_mode,
            'case_sensitive': case_sensitive,
            'regex_compiled': regex_compiled,
            'keyword': keyword
        })

    if not filter_targets:
        _filter_pending_chunks.clear()
        if _filter_update_timer is not None and _filter_update_timer.isActive():
            _filter_update_timer.stop()
        return

    pending_items = []
    while _filter_pending_chunks and len(pending_items) < FILTER_MAX_CHUNKS_PER_TICK:
        pending_items.append(_filter_pending_chunks.popleft())

    prepared_items = []
    for time_str, text in pending_items:
        if not text:
            continue
        lines = text.splitlines(True)
        if lines:
            prepared_items.append((time_str, lines))

    if not prepared_items:
        if not _filter_pending_chunks and _filter_update_timer is not None and _filter_update_timer.isActive():
            _filter_update_timer.stop()
        return

    for target in filter_targets:
        out_parts = []
        regex_compiled = target['regex_compiled']
        keyword = target['keyword']
        invert_mode = target['invert_mode']
        case_sensitive = target['case_sensitive']

        for time_str, lines in prepared_items:
            prefix = f"[{time_str}]"
            for line in lines:
                if regex_compiled is not None:
                    match_found = bool(regex_compiled.search(line))
                else:
                    line_text = line if case_sensitive else line.lower()
                    match_found = keyword in line_text

                should_display = match_found if not invert_mode else not match_found
                if should_display:
                    out_parts.append(prefix + line)

        if not out_parts:
            continue

        append_text = ''.join(out_parts)
        browser = target['browser']
        try:
            browser.append_received_data(
                data=append_text,
                is_hex=False,
                add_timestamp=False,
                timestamp_str=""
            )
        except Exception:
            browser.append(append_text)
        if getattr(browser, 'fresh_flag', False):
            browser.moveCursor(QTextCursor.End)

    if not _filter_pending_chunks and _filter_update_timer is not None and _filter_update_timer.isActive():
        _filter_update_timer.stop()

def _ensure_filter_update_timer():
    """懒初始化过滤更新定时器。"""
    global _filter_update_timer
    if _filter_update_timer is not None:
        return
    try:
        _filter_update_timer = QtCore.QTimer(ui)
    except Exception:
        _filter_update_timer = QtCore.QTimer()
    _filter_update_timer.setInterval(FILTER_UPDATE_INTERVAL_MS)
    _filter_update_timer.timeout.connect(_process_filter_pending_chunks)

def _queue_filter_text(text: str, time_str: str):
    """将文本接收数据加入过滤队列，定时批处理。"""
    global _filter_pending_chunks, _filter_update_timer
    if not text:
        return
    if ui.tabWidget_2.count() <= 1:
        return

    _ensure_filter_update_timer()
    _filter_pending_chunks.append((time_str, text))
    while len(_filter_pending_chunks) > FILTER_MAX_QUEUE_CHUNKS:
        _filter_pending_chunks.popleft()

    if _filter_update_timer is not None and not _filter_update_timer.isActive():
        _filter_update_timer.start()

def _ensure_receive_update_timer():
    """懒初始化接收显示批处理定时器。"""
    global _receive_update_timer
    if _receive_update_timer is not None:
        return
    try:
        _receive_update_timer = QtCore.QTimer(ui)
    except Exception:
        _receive_update_timer = QtCore.QTimer()
    _receive_update_timer.setInterval(RECEIVE_UPDATE_INTERVAL_MS)
    _receive_update_timer.timeout.connect(_process_receive_pending_chunks)

def _queue_received_ui_data(payload: bytes):
    """将串口接收数据加入显示队列，避免在回调中直接做重度文本处理。"""
    global _receive_pending_bytes, _receive_dropped_bytes
    if not payload:
        return

    _ensure_receive_update_timer()
    payload = bytes(payload)

    if _receive_pending_chunks and len(_receive_pending_chunks[-1]) < RECEIVE_MERGE_THRESHOLD:
        tail = _receive_pending_chunks.pop()
        _receive_pending_bytes -= len(tail)
        payload = tail + payload

    _receive_pending_chunks.append(payload)
    _receive_pending_bytes += len(payload)

    while _receive_pending_bytes > RECEIVE_MAX_QUEUE_BYTES and _receive_pending_chunks:
        dropped = _receive_pending_chunks.popleft()
        _receive_pending_bytes -= len(dropped)
        _receive_dropped_bytes += len(dropped)

    if _receive_update_timer is not None and not _receive_update_timer.isActive():
        _receive_update_timer.start()

def _flush_receive_pending_chunks():
    """尽快刷出当前积压的接收数据显示。"""
    while _receive_pending_chunks:
        _process_receive_pending_chunks()
    try:
        ui.textBrowserShow.force_update()
    except Exception:
        pass

def _process_receive_pending_chunks():
    """批量处理串口接收显示数据，降低主线程频繁解码与插入的成本。"""
    global _receive_pending_bytes, _receive_dropped_bytes, _receive_update_timer

    if not _receive_pending_chunks:
        if _receive_update_timer is not None and _receive_update_timer.isActive():
            _receive_update_timer.stop()
        return

    pending_payloads = []
    total_bytes = 0
    while _receive_pending_chunks and len(pending_payloads) < RECEIVE_MAX_CHUNKS_PER_TICK and total_bytes < RECEIVE_MAX_BYTES_PER_TICK:
        chunk = _receive_pending_chunks.popleft()
        pending_payloads.append(chunk)
        total_bytes += len(chunk)
        _receive_pending_bytes -= len(chunk)

    if not pending_payloads:
        if _receive_update_timer is not None and _receive_update_timer.isActive():
            _receive_update_timer.stop()
        return

    payload = b''.join(pending_payloads)
    show_timestamp = False
    time_str = datetime.now().strftime('%m-%d %H:%M:%S.%f')[:-3]
    timestamp_str = '[' + time_str + ']' if show_timestamp else ''

    dropped_bytes = _receive_dropped_bytes
    _receive_dropped_bytes = 0
    if dropped_bytes > 0:
        ui.textBrowserShow.append_received_data(
            data=f"\r\n[RX DROP] UI backlog skipped {dropped_bytes} bytes\r\n",
            is_hex=False,
            add_timestamp=False,
            timestamp_str=""
        )

    if ui.checkBox_show_hex.isChecked():
        out_s = payload.hex(' ').upper()
        if out_s:
            ui.textBrowserShow.append_received_data(
                data=out_s + ' ',
                is_hex=True,
                add_timestamp=show_timestamp,
                timestamp_str=timestamp_str
            )
    else:
        print_str = payload.decode('utf-8', 'ignore')
        if print_str:
            ui.textBrowserShow.append_received_data(
                data=print_str,
                is_hex=False,
                add_timestamp=show_timestamp,
                timestamp_str=timestamp_str
            )
            _queue_filter_text(print_str, time_str)

    if not _receive_pending_chunks and _receive_update_timer is not None and _receive_update_timer.isActive():
        _receive_update_timer.stop()

def _get_reconnect_timeout_sec():
    """读取系统设置中的自动重连超时秒数，默认 5 秒。"""
    mSetting = QSettings(QSettings.IniFormat, QSettings.UserScope, "Gavin", "Gavin_com")
    return mSetting.value("system/reconnect_timeout_sec", 5, int)


def _start_reconnect_watchdog(port, baud):
    """串口意外断开后调用：启动自动重连监视器。"""
    global _reconnect_timer, _reconnect_deadline, _reconnect_port, _reconnect_baud, _reconnect_active
    # 先停掉可能存在的旧计时器
    if _reconnect_timer is not None:
        _reconnect_timer.stop()
        _reconnect_timer = None

    # 强制关闭底层串口句柄，确保 OS 释放资源，避免重连时 OSError(22)
    try:
        obj = uithreadObj.uartObj
        if obj.mThread.isRunning():
            obj.mThread.request_stop()
            obj.mThread.wait(500)
        if obj.mSerial.isOpen():
            obj.mSerial.close()
    except Exception as e:
        logger.debug("[自动重连] 清理旧句柄失败（忽略）: %s", e)

    timeout_sec = _get_reconnect_timeout_sec()
    _reconnect_port = port
    _reconnect_baud = baud
    _reconnect_deadline = time.time() + timeout_sec
    _reconnect_active = True

    # 更新按钮提示（按钮保持"关闭串口"，用户可点击手动断开）
    try:
        ui.bt_open_off_port.setToolTip(f'重连中…点击手动断开（超时 {timeout_sec}s）')
    except Exception:
        pass

    _reconnect_timer = QTimer()
    _reconnect_timer.timeout.connect(_reconnect_tick)
    _reconnect_timer.start(1000)
    logger.info("[自动重连] 已启动，端口=%s，超时=%ss", port, timeout_sec)


def _stop_reconnect_watchdog():
    """停止重连监视器，不更新 UI（调用方负责 UI 处理）。"""
    global _reconnect_timer, _reconnect_deadline, _reconnect_port, _reconnect_baud, _reconnect_active
    if _reconnect_timer is not None:
        _reconnect_timer.stop()
        _reconnect_timer = None
    _reconnect_active = False
    _reconnect_deadline = None
    try:
        ui.bt_open_off_port.setToolTip('')
    except Exception:
        pass


def _reconnect_tick():
    """每 1 秒调用一次：检测端口可用性并尝试重连。"""
    global _reconnect_active
    if not _reconnect_active:
        return

    # 超时检查
    if time.time() >= _reconnect_deadline:
        logger.info("[自动重连] 超时，停止重连")
        _stop_reconnect_watchdog()
        # 静默恢复 UI 到未连接状态
        checkoutPortStatus(True)
        ui.bt_open_off_port.setText('打开串口')
        update_send_controls_enabled(False)
        refreshPort()
        try:
            serial_logger.on_disconnect()
        except Exception:
            pass
        return

    # 检查端口是否出现在系统设备列表中
    try:
        import serial.tools.list_ports as _lp
        available = [p.device for p in _lp.comports()]
        if _reconnect_port not in available:
            remaining = max(0, int(_reconnect_deadline - time.time()))
            logger.debug("[自动重连] 端口 %s 不可见，剩余 %ss", _reconnect_port, remaining)
            return
    except Exception:
        pass

    # 端口可见，先确保底层完全关闭（断开重连），再尝试打开
    try:
        obj = uithreadObj.uartObj
        if obj.mThread.isRunning():
            obj.mThread.request_stop()
            obj.mThread.wait(500)
        if obj.mSerial.isOpen():
            obj.mSerial.close()
    except Exception as e:
        logger.debug("[自动重连] 关闭旧句柄失败（忽略）: %s", e)

    # 尝试打开
    try:
        result = uithreadObj.try_open_port(_reconnect_port, _reconnect_baud)
        if result:
            port = _reconnect_port
            baud = _reconnect_baud
            _stop_reconnect_watchdog()
            # 恢复已连接 UI
            checkoutPortStatus(False)
            ui.bt_open_off_port.setText('关闭串口')
            update_send_controls_enabled(True)
            logger.info("[自动重连] 重连成功：%s @ %s", port, baud)
            try:
                session_name = f"{port}@{baud}"
                serial_logger.on_connect(session_name=session_name, parent=MainWindow, port_name=port)
            except Exception as e:
                logger.warning("[自动重连] 日志处理失败: %s", e)
        else:
            remaining = max(0, int(_reconnect_deadline - time.time()))
            logger.debug("[自动重连] 打开失败，剩余 %ss", remaining)
    except Exception as e:
        logger.error("[自动重连] 异常: %s", e)


def at_callback_handler(obj):
    code = obj.get('code', 0)
    if code == 1:
        _flush_receive_pending_chunks()
        if ui.bt_open_off_port.text() != '打开串口':
            # 记录断线时的端口和波特率，启动自动重连监视器
            port = uithreadObj.port
            baud = uithreadObj.baudrate
            _start_reconnect_watchdog(port, baud)
        return

    if code == 2:
        _flush_receive_pending_chunks()
        logger.error(obj.get("error", "串口接收错误"))
        return

    buff = obj.get('data', b'')
    if not buff:
        return
    if isinstance(buff, bytearray):
        buff = bytes(buff)
        
    # 自动应答处理 - 在显示数据之前进行匹配和应答
    try:
        auto_reply_engine.process_received_data(buff)
    except Exception as e:
        logger.warning("自动应答处理失败: %s", e)
    
    # 更新接收统计
    ui.update_recv_stats(len(buff))
    ui.add_recv_rate(len(buff))
    # 写入日志（接收数据）
    try:
        serial_logger.log_rx(buff)
    except Exception as e:
        logger.warning("接收日志写入失败: %s", e)

    _queue_received_ui_data(buff)


def configure_text_browser_buffer():
    """
    配置TextBrowser的缓存参数
    根据实际使用场景调整参数以优化性能
    """
    # 基础配置 - 适合大多数场景
    ui.textBrowserShow.set_buffer_size(40000)      # 缓存更多突发数据，避免短时间大流量挤爆显示队列
    ui.textBrowserShow.set_update_interval(50)     # 降低刷新频率，优先保证主线程稳定
    ui.textBrowserShow.set_batch_size(500)         # 单次处理更多缓存，减少多次小批量刷新
    ui.textBrowserShow.set_max_display_lines(80000)
    ui.textBrowserShow.max_batch_chars = 1024 * 1024
    ui.textBrowserShow.max_merge_chars = 128 * 1024
    
    logger.info("串口接收缓存功能已配置: 缓存=%d, 间隔=%dms, 批量=%d, 最大行=%d",
                ui.textBrowserShow.max_buffer_size, ui.textBrowserShow.update_interval,
                ui.textBrowserShow.batch_size, ui.textBrowserShow.max_display_lines)


def windows_key_press(event):
    if event == Qt.Key_F5:
        ui.textBrowserShow.clear()

# 保存参数到本地
def save_params_local(key, value):
    # 使用QSettings的标准路径，将配置保存到用户目录
    mSetting = QSettings(QSettings.IniFormat, QSettings.UserScope, "Gavin", "Gavin_com")
    mSetting.setValue(key, value)

# 保存所有设置到配置文件
def save_all_settings():
    mSetting = QSettings(QSettings.IniFormat, QSettings.UserScope, "Gavin", "Gavin_com")
    
    # 串口设置 - 使用全局设置变量
    mSetting.setValue("baud", SERIAL_SETTINGS['baud_index'])
    mSetting.setValue("data_bits", SERIAL_SETTINGS['data_bits_index'])
    mSetting.setValue("stop_bits", SERIAL_SETTINGS['stop_bits_index'])
    mSetting.setValue("parity", SERIAL_SETTINGS['parity_index'])
    
    # 保存流控设置
    mSetting.setValue("serial/flow_control", SERIAL_SETTINGS.get('flow_control', 'none'))
    mSetting.setValue("serial/timeout", SERIAL_SETTINGS.get('timeout', 1.0))
    
    # 发送设置
    mSetting.setValue("send_hex", ui.checkBox_send_hex.isChecked())
    mSetting.setValue("send_newline", ui.checkBox_send_space_ctrl.isChecked())
    mSetting.setValue("timer_send_enabled", ui.checkBox_timer_send.isChecked())
    mSetting.setValue("timer_send_interval", ui.lineEdit_ms_send.text())
    mSetting.setValue("send_data_text", ui.lineEdit_send_data.toPlainText())
    mSetting.setValue("loop_count", ui.lineEdit_loop_count.text())
    
    # 接收设置
    mSetting.setValue("show_hex", ui.checkBox_show_hex.isChecked())
    mSetting.setValue("show_add_ctrl", ui.checkBox_show_add_ctrl.isChecked())
    # 显示发送设置（不再保存字符串/HEX模式，改为自动）
    try:
        mSetting.setValue("show_send_echo", ui.checkBox_show_send.isChecked())
    except Exception:
        pass
    
    # 流控设置
    mSetting.setValue("rts_enabled", ui.checkBox_rts.isChecked())
    mSetting.setValue("dtr_enabled", ui.checkBox_dtr.isChecked())
    
    # 自定义按钮设置
    mSetting.setValue("sequential_enabled", ui.checkBox_sequential.isChecked())
    mSetting.setValue("loop_enabled", ui.checkBox_loop.isChecked())
    
    # 过滤设置
    mSetting.setValue("filter_regexp", ui.Filter_Regexp.text())
    mSetting.setValue("filter_case_sensitive_main", ui.CaseSensitiveCheckBox.isChecked())
    mSetting.setValue("filter_invert_mode_main", ui.InvertModeCheckBox.isChecked())
    
    # 保存所有过滤tab的设置
    # 遍历所有过滤tab，查找实际存在的控件
    saved_count = 0
    for tab_index in range(ui.tabWidget_2.count()):
        tab_widget = ui.tabWidget_2.widget(tab_index)
        if tab_widget:
            # 查找该tab中的过滤控件
            regexp_widget = tab_widget.findChild(QtWidgets.QLineEdit)
            case_widget = tab_widget.findChild(QtWidgets.QCheckBox, lambda w: "CaseSensitive" in w.objectName())
            invert_widget = tab_widget.findChild(QtWidgets.QCheckBox, lambda w: "InvertMode" in w.objectName())
            
            # 如果找到过滤控件，说明这是一个过滤tab（跳过主tab）
            if regexp_widget and "Filter_Regexp_" in regexp_widget.objectName():
                saved_count += 1
                try:
                    mSetting.setValue(f"filter_regexp_{saved_count}", regexp_widget.text())
                    if case_widget:
                        mSetting.setValue(f"filter_case_sensitive_{saved_count}", case_widget.isChecked())
                    if invert_widget:
                        mSetting.setValue(f"filter_invert_mode_{saved_count}", invert_widget.isChecked())
                except Exception as e:
                    logger.warning("保存过滤tab %s 设置时出错: %s", saved_count, e)
                    continue
    
    # 更新实际保存的tab数量
    mSetting.setValue("filter_tab_count", saved_count)
    
    # 自定义按钮设置
    for i in range(1, 100):  # 保存99个自定义按钮
        try:
            edit_widget = getattr(ui, f"ed_customs_set_{i}")
            button_widget = getattr(ui, f"bt_customs_send_{i}")
            mSetting.setValue(f"groupBox_customs_data_{i}", edit_widget.text())
            mSetting.setValue(f"bt_customs_send_{i}", button_widget.text())
        except AttributeError:
            # 如果某个按钮不存在，跳过
            continue
    
    # 窗口状态
    mSetting.setValue("windows_customs_status", ui.tabWidget_expand.isHidden())
    
    # 保存窗口大小和位置
    mSetting.setValue("window_width", MainWindow.width())
    mSetting.setValue("window_height", MainWindow.height())
    mSetting.setValue("window_x", MainWindow.x())
    mSetting.setValue("window_y", MainWindow.y())
    
    mSetting.sync()  # 确保立即写入文件

# 从配置文件加载文件
def load_from_local():
    # 使用QSettings的标准路径，从用户目录加载配置
    mSetting = QSettings(QSettings.IniFormat, QSettings.UserScope, "Gavin", "Gavin_com")
    # mSetting.clear()

    # 拓展面板控制
    expand_hidden = mSetting.value("windows_customs_status", False, bool)
    manual_customs_visibility = mSetting.value("windows_customs_manual", False, bool)
    if not manual_customs_visibility:
        expand_hidden = False
    
    # 设置隐藏状态
    if expand_hidden:
        ui.tabWidget_expand.setVisible(False)
        ui.tabWidget_expand.setMaximumHeight(0)
        ui.tabWidget_expand.setMinimumHeight(0)
    else:
        ui.tabWidget_expand.setVisible(True)
        ui.tabWidget_expand.setMaximumHeight(16777215)
        ui.tabWidget_expand.setMinimumHeight(0)
    
    # 串口设置 - 加载到全局设置变量
    SERIAL_SETTINGS['baud_index'] = mSetting.value("baud", 9, int)
    SERIAL_SETTINGS['data_bits_index'] = mSetting.value("data_bits", 0, int)
    SERIAL_SETTINGS['stop_bits_index'] = mSetting.value("stop_bits", 0, int)
    SERIAL_SETTINGS['parity_index'] = mSetting.value("parity", 0, int)
    
    # 加载流控设置
    SERIAL_SETTINGS['flow_control'] = mSetting.value("serial/flow_control", "none", str)
    SERIAL_SETTINGS['timeout'] = mSetting.value("serial/timeout", 1.0)
    logger.debug("从配置加载流控设置: %s", SERIAL_SETTINGS["flow_control"])
    
    # 发送设置
    ui.checkBox_send_hex.setChecked(mSetting.value("send_hex", False, bool))
    ui.checkBox_send_space_ctrl.setChecked(mSetting.value("send_newline", True, bool))
    ui.checkBox_timer_send.setChecked(mSetting.value("timer_send_enabled", False, bool))
    ui.lineEdit_ms_send.setText(mSetting.value("timer_send_interval", "1000", str))
    ui.lineEdit_send_data.setPlainText(mSetting.value("send_data_text", "", str))
    ui.lineEdit_loop_count.setText(mSetting.value("loop_count", "1", str))
    
    # 设置发送文本框的hex模式
    ui.lineEdit_send_data.set_hex_mode(ui.checkBox_send_hex.isChecked())
    
    # 接收设置
    ui.checkBox_show_hex.setChecked(mSetting.value("show_hex", False, bool))
    ui.checkBox_show_add_ctrl.setChecked(mSetting.value("show_add_ctrl", True, bool))
    # 显示发送设置（仅保留开关）
    try:
        ui.checkBox_show_send.setChecked(mSetting.value("show_send_echo", False, bool))
    except Exception:
        pass
    
    # 流控设置
    ui.checkBox_rts.setChecked(mSetting.value("rts_enabled", False, bool))
    ui.checkBox_dtr.setChecked(mSetting.value("dtr_enabled", False, bool))
    
    # 自定义按钮设置
    ui.checkBox_sequential.setChecked(mSetting.value("sequential_enabled", False, bool))
    ui.checkBox_loop.setChecked(mSetting.value("loop_enabled", False, bool))
    
    # 过滤设置
    ui.Filter_Regexp.setText(mSetting.value("filter_regexp", "", str))
    ui.CaseSensitiveCheckBox.setChecked(mSetting.value("filter_case_sensitive_main", False, bool))
    ui.InvertModeCheckBox.setChecked(mSetting.value("filter_invert_mode_main", False, bool))

    # 颜色主题设置（通过右键菜单选择，不依赖下拉框）
    theme_name = mSetting.value("recv_color_theme", "Zenburn", str)
    try:
        set_current_theme(theme_name)
    except Exception as e:
        logger.warning("恢复颜色主题失败: %s", e)
    
    # 加载保存的过滤tab
    saved_tab_count = mSetting.value("filter_tab_count", 0, int)
    for i in range(1, saved_tab_count + 1):
        try:
            # 重新创建过滤tab
            add_filter(ui)
            
            # 恢复保存的设置
            regexp_text = mSetting.value(f"filter_regexp_{i}", "", str)
            case_sensitive = mSetting.value(f"filter_case_sensitive_{i}", False, bool)
            invert_mode = mSetting.value(f"filter_invert_mode_{i}", False, bool)
            
            # 查找刚创建的控件并设置值（使用当前的add_cnt值）
            current_tab_id = ui.add_cnt
            regexp_widget = ui.tabWidget_2.findChild(QtWidgets.QLineEdit, f"Filter_Regexp_{current_tab_id}")
            case_widget = ui.tabWidget_2.findChild(QtWidgets.QCheckBox, f"CaseSensitiveCheckBox_{current_tab_id}")
            invert_widget = ui.tabWidget_2.findChild(QtWidgets.QCheckBox, f"InvertModeCheckBox_{current_tab_id}")
            
            if regexp_widget:
                regexp_widget.setText(regexp_text)
            if case_widget:
                case_widget.setChecked(case_sensitive)
            if invert_widget:
                invert_widget.setChecked(invert_mode)
                
        except Exception as e:
            logger.warning("加载过滤tab %s 设置时出错: %s", i, e)
            continue

    # 自定义按钮设置加载
    default_values = {1: "单位", 2: "help", 3: "free", 4: "ps", 5: "Hahahah"}
    for i in range(1, 100):
        try:
            edit_widget = getattr(ui, f"ed_customs_set_{i}")
            button_widget = getattr(ui, f"bt_customs_send_{i}")
            hex_checkbox = getattr(ui, f"checkBox_hex_{i}")
            delay_edit = getattr(ui, f"ed_customs_delay_{i}")
            
            # 加载编辑框文本
            default_value = default_values.get(i, "")
            edit_widget.setText(mSetting.value(f"groupBox_customs_data_{i}", default_value))
            
            # 加载按钮文本
            button_widget.setText(mSetting.value(f"bt_customs_send_{i}", str(i)))
            
            # 加载HEX复选框状态
            hex_checkbox.setChecked(mSetting.value(f"checkBox_hex_{i}", False, bool))
            
            # 加载延迟设置
            delay_edit.setText(mSetting.value(f"ed_customs_delay_{i}", "", str))
            
            # 加载序号设置
            try:
                seq_edit = getattr(ui, f"ed_customs_seq_{i}")
                seq_edit.setText(mSetting.value(f"ed_customs_seq_{i}", "", str))
            except AttributeError:
                pass
        except AttributeError:
            break
    
    # 加载完所有序号设置后，更新序号输入框的样式
    try:
        update_all_seq_styles()
    except NameError:
        pass  # 如果函数还未定义，忽略
    
    # 恢复窗口大小和位置
    window_width = mSetting.value("window_width", 1200, int)  # 默认宽度1200
    window_height = mSetting.value("window_height", 800, int)  # 默认高度800
    window_x = mSetting.value("window_x", -1, int)  # -1表示使用默认位置
    window_y = mSetting.value("window_y", -1, int)  # -1表示使用默认位置
    
    # 设置窗口大小
    MainWindow.resize(window_width, window_height)
    
    # 设置窗口位置（如果有保存的位置）
    if window_x >= 0 and window_y >= 0:
        MainWindow.move(window_x, window_y)

# 定时发送数据
timer_send = QTimer()

def InitUI():
    # 移除原有的串口设置控件初始化，这些现在在"更多设置"弹窗中处理
    # 只保留必要的初始化
    
    uithreadObj.set_dts(False)
    uithreadObj.set_rts(False)
    # 移除硬编码字体设置，允许用户自定义字体
    # ui.textBrowserShow.setStyleSheet("font: 10pt \"Consolas\";")
    # 连接右键主题选择信号（主接收区与Filter页）
    try:
        ui.textBrowserShow.colorSchemeSelected.connect(on_theme_changed)
        ui.FilterBrowser.colorSchemeSelected.connect(on_theme_changed)
    except Exception as e:
        logger.warning("主题信号连接失败: %s", e)
    refreshPort()

    # 点击按钮，打开串口
    ui.bt_open_off_port.clicked.connect(onClickOpenOffPort)
    # 点击更多设置按钮
    ui.bt_more_settings.clicked.connect(open_serial_settings_dialog)
    # 折叠/展开底部配置（按钮行右侧）
    ui.bt_toggle_bottom.clicked.connect(onToggleBottomConfig)
    # 新增：快捷按钮栏显隐切换（扩展面板后）
    try:
        ui.bt_toggle_quickbar.clicked.connect(onToggleQuickbar)
        # 默认状态：快捷按钮栏可见、切换按钮文案为“隐藏按钮”
        if hasattr(ui, 'quickbar_row'):
            ui.quickbar_row.setVisible(True)
            # 记录用户偏好：默认显示快捷按钮栏
            ui.quickbar_user_visible = True
        ui.bt_toggle_quickbar.setText('隐藏按钮')
    except Exception as e:
        logger.warning("绑定快捷按钮切换失败: %s", e)
    # 默认启动展开：显示底部内容
    ui.bottom_content_widget.setVisible(True)
    # 初始化折叠按钮图标与提示
    update_toggle_icon()
    # 点击按钮，刷新串口
    ui.comboBox_port.popupAboutToBeShown.connect(refreshPort)
    #  rts
    ui.checkBox_rts.stateChanged.connect(OnClickRTS)
    #  dts
    ui.checkBox_dtr.stateChanged.connect(OnClickDTR)
    # 设置定时发送的按钮
    ui.checkBox_timer_send.stateChanged.connect(on_timer_send_changed)
    ui.lineEdit_ms_send.setValidator(QIntValidator(0, 99999999))
    #  Clear Log
    ui.btClearLog.clicked.connect(OnClickClearLog)
    #  send data
    ui.bt_send_data.clicked.connect(OnClickSendData)
    update_send_controls_enabled(False)
    
    # 连接接收区键盘输入发送信号
    ui.textBrowserShow.sendData.connect(onTextBrowserSendData)
    
    # 连接定时发送信号
    timer_send.timeout.connect(SendDataFuntion)
    
    # 配置串口接收缓存功能
    configure_text_browser_buffer()

    # 面板可操作
    checkoutPortStatus(True)
    
    # 初始化自定义按钮事件连接
    initCustomsUI()

    # 隐藏拓展面板
    ui.bt_open_off_expand_customs.clicked.connect(OnClickOffCustomsExpand)
    # 多字符串开始/停止按钮（切换）
    ui.pushButton_stop_loop.setText("开始")
    ui.label_loop_status.setText("状态: 未运行")
    ui.pushButton_stop_loop.clicked.connect(onToggleLoopClicked)
    # 绑定多字符串导入/导出按钮
    try:
        ui.pushButton_import_sscom.clicked.connect(onImportSSCOM)
        ui.pushButton_export_sscom.clicked.connect(onExportSSCOM)
    except Exception as e:
        logger.warning("绑定导入/导出按钮失败: %s", e)
    
    # 连接设置改变信号，自动保存配置
    ui.checkBox_send_hex.stateChanged.connect(lambda: on_hex_mode_changed())
    ui.checkBox_send_space_ctrl.stateChanged.connect(lambda: save_params_local("send_newline", ui.checkBox_send_space_ctrl.isChecked()))
    ui.checkBox_show_hex.stateChanged.connect(lambda: save_params_local("show_hex", ui.checkBox_show_hex.isChecked()))
    ui.checkBox_show_add_ctrl.stateChanged.connect(lambda: save_params_local("show_add_ctrl", ui.checkBox_show_add_ctrl.isChecked()))
    ui.checkBox_sequential.stateChanged.connect(lambda: save_params_local("sequential_enabled", ui.checkBox_sequential.isChecked()))
    ui.checkBox_loop.stateChanged.connect(lambda: save_params_local("loop_enabled", ui.checkBox_loop.isChecked()))
    try:
        ui.checkBox_show_send.stateChanged.connect(lambda: save_params_local("show_send_echo", ui.checkBox_show_send.isChecked()))
    except Exception as e:
        logger.warning("绑定显示发送控件失败: %s", e)
    # 收发统计标签右键菜单
    ui.label_stats.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
    ui.label_stats.customContextMenuRequested.connect(onStatsContextMenu)

    # 在扩展面板按鈕前插入高级功能按鈕
    try:
        ui.bt_monitor = QtWidgets.QPushButton(ui.groupBox_4)
        ui.bt_monitor.setObjectName('bt_monitor')
        ui.bt_monitor.setText('高级功能')
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        ui.bt_monitor.setSizePolicy(sizePolicy)
        ui.bt_monitor.setMaximumWidth(90)
        # 将按钮插入到扩展面板按钮之前
        idx = ui.horizontalLayout_5.indexOf(ui.bt_open_off_expand_customs)
        if idx < 0:
            ui.horizontalLayout_5.addWidget(ui.bt_monitor)
        else:
            ui.horizontalLayout_5.insertWidget(idx, ui.bt_monitor)
        ui.bt_monitor.clicked.connect(open_advanced_function_dialog)
    except Exception as e:
        logger.warning("插入监控按钮失败: %s", e)

def on_hex_mode_changed():
    """处理hex模式切换"""
    is_hex = ui.checkBox_send_hex.isChecked()
    ui.lineEdit_send_data.set_hex_mode(is_hex)
    save_params_local('send_hex', is_hex)

CURRENT_COLOR_THEME = "Zenburn"

def extract_effective_font_from_widget(widget):
    """统一的字体解析函数：从样式表中提取字体大小/字体族，回填到 QFont，保证与视觉一致"""
    try:
        import re
        ss = widget.styleSheet() or ""
        size = None
        family = None
        
        # 尝试匹配 font: 12pt "Microsoft YaHei" 格式
        m = re.search(r'font:\s*(\d+)pt\s*"([^"]+)"', ss, re.IGNORECASE)
        if m:
            size = int(m.group(1))
            family = m.group(2)
        else:
            # 分别匹配 font-size 和 font-family
            m2 = re.search(r'font-size:\s*(\d+)pt', ss, re.IGNORECASE)
            if m2:
                size = int(m2.group(1))
            m3 = re.search(r'font-family:\s*"?([^";]+)"?', ss, re.IGNORECASE)
            if m3:
                family = m3.group(1).strip('"')
        
        # 获取当前字体作为基础
        f = widget.font()
        original_size = f.pointSize()
        original_family = f.family()
        
        # 应用解析出的字体属性
        if size and size > 0:
            f.setPointSize(size)
        if family:
            f.setFamily(family)
        
        # 调试输出
        logger.debug("[字体解析] 样式表: %s...", ss[:100])
        logger.debug("[字体解析] 原始字体: %s %spt", original_family, original_size)
        logger.debug("[字体解析] 解析结果: %s %spt", f.family(), f.pointSize())
        
        return f
    except Exception as e:
        logger.warning("[字体解析] 解析失败: %s", e)
        return widget.font()

def on_theme_changed(name: str):
    """当主题改变时，应用到所有接收/过滤视图并保存"""
    set_current_theme(name)

def apply_theme_to_all_browsers(name: str):
    """将主题与字体应用到主接收区及所有过滤tab中的 MyTextBrowser"""
    try:
        base_font = None
        if hasattr(ui, 'textBrowserShow'):
            # 以主接收区的实际显示字体作为全局基准（解析样式表）
            base_font = extract_effective_font_from_widget(ui.textBrowserShow)
            logger.debug("[主题应用] 主接收区基准字体: %s %spt", base_font.family(), base_font.pointSize())
            
            ui.textBrowserShow.setFont(base_font)
            try:
                ui.textBrowserShow.document().setDefaultFont(base_font)
            except Exception:
                pass
            ui.textBrowserShow.apply_color_scheme(name)
            
        # 过滤主tab内置 FilterBrowser
        if hasattr(ui, 'FilterBrowser'):
            if base_font is not None:
                logger.debug("[主题应用] 设置FilterBrowser字体: %s %spt", base_font.family(), base_font.pointSize())
                ui.FilterBrowser.setFont(base_font)
                try:
                    ui.FilterBrowser.document().setDefaultFont(base_font)
                except Exception:
                    pass
            ui.FilterBrowser.apply_color_scheme(name)
            
        # 动态过滤tab
        for i in range(ui.tabWidget_2.count()):
            tab = ui.tabWidget_2.widget(i)
            for browser in tab.findChildren(MyTextBrowser):
                if base_font is not None:
                    logger.debug("[主题应用] 设置动态Filter字体: %s %spt", base_font.family(), base_font.pointSize())
                    browser.setFont(base_font)
                    try:
                        browser.document().setDefaultFont(base_font)
                    except Exception:
                        pass
                browser.apply_color_scheme(name)
    except Exception as e:
        logger.error("应用主题失败: %s", e)

def set_current_theme(name: str):
    global CURRENT_COLOR_THEME
    CURRENT_COLOR_THEME = name
    apply_theme_to_all_browsers(name)
    save_params_local('recv_color_theme', name)

def on_timer_send_changed():
    """
    处理定时发送切换
    
    当勾选定时发送时，启动定时器；当取消勾选时，停止定时器
    """
    state = ui.checkBox_timer_send.isChecked()
    save_params_local('timer_send_enabled', state)
    
    if state:
        # 启动定时发送
        times = ui.lineEdit_ms_send.text()
        try:
            times_send = int(times)
            if times_send > 0:
                timer_send.start(times_send)
        except ValueError:
            pass  # 如果输入无效，不启动定时器
    else:
        # 停止定时发送
        if timer_send.isActive():
            timer_send.stop()

def open_serial_settings_dialog():
    """打开串口更多设置对话框"""
    try:
        dlg = SerialSettingsDialog(MainWindow)
        # 更新端口列表
        dlg.update_port_list(GET_PORT_ARRAY)
        
        # 设置当前选择的端口
        if GET_PORT_ARRAY and ui.comboBox_port.currentIndex() >= 0:
            current_port = GET_PORT_ARRAY[ui.comboBox_port.currentIndex()]
            dlg.port_combo.setCurrentText(current_port)
            
        # 从全局设置变量加载当前的串口参数
        dlg.set_current_indices({
            'baud_index': SERIAL_SETTINGS['baud_index'],
            'data_bits_index': SERIAL_SETTINGS['data_bits_index'],
            'parity_index': SERIAL_SETTINGS['parity_index'],
            'stop_bits_index': SERIAL_SETTINGS['stop_bits_index']
        })
        
        # 加载流控设置
        dlg.set_settings({
            'flow_control': SERIAL_SETTINGS.get('flow_control', 'none'),
            'timeout': SERIAL_SETTINGS.get('timeout', 1.0)
        })
        
        # 连接设置变更信号
        def on_settings_changed():
            # 获取新的设置索引
            indices = dlg.get_current_indices()
            SERIAL_SETTINGS['baud_index'] = indices['baud_index']
            SERIAL_SETTINGS['data_bits_index'] = indices['data_bits_index']
            SERIAL_SETTINGS['parity_index'] = indices['parity_index']
            SERIAL_SETTINGS['stop_bits_index'] = indices['stop_bits_index']
            
            # 保存到本地设置
            save_params_local('baud', SERIAL_SETTINGS['baud_index'])
            save_params_local('data_bits', SERIAL_SETTINGS['data_bits_index'])
            save_params_local('parity', SERIAL_SETTINGS['parity_index'])
            save_params_local('stop_bits', SERIAL_SETTINGS['stop_bits_index'])
            
        dlg.settings_changed.connect(on_settings_changed)
        
        if dlg.exec() == QDialog.Accepted:
            # 获取新设置
            new_settings = dlg.get_settings()
            
            # 更新全局设置变量，包括流控
            SERIAL_SETTINGS['flow_control'] = new_settings.get('flow_control', 'none')
            SERIAL_SETTINGS['timeout'] = new_settings.get('timeout', 1.0)
            
            # 更新主界面的端口选择
            if new_settings['port'] in GET_PORT_ARRAY:
                port_index = GET_PORT_ARRAY.index(new_settings['port'])
                ui.comboBox_port.setCurrentIndex(port_index)
            
    except Exception as e:
        QMessageBox.critical(MainWindow, '错误', f'打开串口设置失败: {e}')


def open_advanced_function_dialog():
    """打开高级功能对话框"""
    try:
        dlg = AdvancedFunctionDialog(MainWindow)
        dlg.load_settings()
        dlg.exportConfigRequested.connect(export_all_config)
        dlg.importConfigRequested.connect(import_all_config)
        if dlg.exec() == QDialog.Accepted:
            # 对话框已将配置保存到 QSettings，这里同步到日志管理器
            serial_logger.load_from_qsettings()
    except Exception as e:
        QMessageBox.critical(MainWindow, '错误', f'打开高级功能失败: {e}')



def OnClickOffCustomsExpand():
    is_hidden = not ui.tabWidget_expand.isHidden()
    
    if is_hidden:
        # 隐藏拓展面板tab控件并设置高度为0
        ui.tabWidget_expand.setVisible(False)
        ui.tabWidget_expand.setMaximumHeight(0)
        ui.tabWidget_expand.setMinimumHeight(0)
    else:
        # 显示拓展面板tab控件并恢复正常高度
        ui.tabWidget_expand.setVisible(True)
        ui.tabWidget_expand.setMaximumHeight(16777215)
        ui.tabWidget_expand.setMinimumHeight(0)
    
    # 强制更新布局
    ui.tabWidget_expand.updateGeometry()
    if hasattr(ui.tabWidget_expand.parent(), 'updateGeometry'):
        ui.tabWidget_expand.parent().updateGeometry()
    MainWindow.update()
    
    save_params_local("windows_customs_status", is_hidden)
    save_params_local("windows_customs_manual", True)

def OnClickClearLog():
    ffbrower = ui.tabWidget_2.currentWidget().findChild(QtWidgets.QTextBrowser)
    ffbrower.clear()

# 点击发送
# OnClickTimerSend函数已被on_timer_send_changed替代


# RTS流控
def OnClickRTS(state):
    if state == QtCore.Qt.Unchecked:
        uithreadObj.set_rts(False)
    elif state == QtCore.Qt.Checked:
        uithreadObj.set_rts(True)


# DTR流控
def OnClickDTR(state):
    if state == QtCore.Qt.Unchecked:
        uithreadObj.set_dts(False)
    elif state == QtCore.Qt.Checked:
        uithreadObj.set_dts(True)


# 刷新串口
def refreshPort():
    _ports = uithreadObj.initPort()
    # print(_ports)
    ui.comboBox_port.clear()
    GET_PORT_ARRAY.clear()
    if len(_ports) == 0:
        ui.comboBox_port.addItem('')
    else:
        for item in _ports:
            ui.comboBox_port.addItem(item)
            GET_PORT_ARRAY.append(item)


# 打开/关闭串口
def onClickOpenOffPort():
    if len(GET_PORT_ARRAY) == 0:
        QMessageBox.critical(MainWindow, '错误信息', '请选择串口')
    else:
        # 使用全局设置变量获取串口参数
        baud = DEFAULT_BAUD_ARRAY[SERIAL_SETTINGS['baud_index']]
        data_bits_options = ['8', '7', '6', '5']
        parity_options = ['None', 'Odd', 'Even', 'Mark', 'Space']
        stop_bits_options = ['1', '1.5', '2']
        
        data_bits = data_bits_options[SERIAL_SETTINGS['data_bits_index']]
        parity_str = parity_options[SERIAL_SETTINGS['parity_index']]
        stop_bits = stop_bits_options[SERIAL_SETTINGS['stop_bits_index']]
        
        # 校验位字符串到serial常量的映射
        parity_map = {
            'None': serial.PARITY_NONE,
            'Odd': serial.PARITY_ODD,
            'Even': serial.PARITY_EVEN,
            'Mark': serial.PARITY_MARK,
            'Space': serial.PARITY_SPACE
        }
        parity = parity_map.get(parity_str, serial.PARITY_NONE)
        
        # 保存串口设置
        save_params_local('baud', SERIAL_SETTINGS['baud_index'])
        save_params_local('data_bits', SERIAL_SETTINGS['data_bits_index'])
        save_params_local('stop_bits', SERIAL_SETTINGS['stop_bits_index'])
        save_params_local('parity', SERIAL_SETTINGS['parity_index'])
        
        port = GET_PORT_ARRAY[ui.comboBox_port.currentIndex()]
        btn_text = ui.bt_open_off_port.text()
        
        if btn_text == '关闭串口':
            # 若处于自动重连中，先静默停止监视器
            if _reconnect_active:
                _stop_reconnect_watchdog()
            if uithreadObj.try_off_port(port, baud):
                # 设置打开串口参数
                uithreadObj.set_default_parity(parity)
                uithreadObj.set_default_stopbits(float(stop_bits))
                uithreadObj.set_default_port(port)
                uithreadObj.set_default_bytesize(int(data_bits))
                uithreadObj.set_default_baudrate(baud)
                # 设置流控
                uithreadObj.set_default_flow_control(SERIAL_SETTINGS.get('flow_control', 'none'))
                ui.bt_open_off_port.setText('打开串口')
                checkoutPortStatus(True)
                update_send_controls_enabled(False)
                try:
                    serial_logger.on_disconnect()
                except Exception as e:
                    logger.warning("日志断开处理失败: %s", e)
            else:
                QMessageBox.critical(MainWindow, '错误信息', '串口被占用或已拔开，无法打开')
        if btn_text == '打开串口':
            # 在打开串口之前设置所有串口参数
            uithreadObj.set_default_parity(parity)
            uithreadObj.set_default_stopbits(float(stop_bits))
            uithreadObj.set_default_port(port)
            uithreadObj.set_default_bytesize(int(data_bits))
            uithreadObj.set_default_baudrate(baud)
            # 设置流控
            flow_control = SERIAL_SETTINGS.get('flow_control', 'none')
            uithreadObj.set_default_flow_control(flow_control)
            
            if uithreadObj.try_open_port(port, baud):
                checkoutPortStatus(False)
                ui.bt_open_off_port.setText('关闭串口')
                update_send_controls_enabled(True)
                try:
                    session_name = f"{port}@{baud}"
                    serial_logger.on_connect(session_name=session_name, parent=MainWindow, port_name=port)
                except Exception as e:
                    logger.warning("日志连接处理失败: %s", e)
            else:
                QMessageBox.critical(MainWindow, '错误信息', '串口被占用或已拔开，无法打开')


def checkoutPortStatus(isShow):
    # 只控制端口选择控件的状态
    # 其他串口设置现在在"更多设置"弹窗中
    ui.comboBox_port.setEnabled(isShow)


def update_send_controls_enabled(enabled):
    ui.bt_send_data.setEnabled(enabled)


def onToggleBottomConfig():
    """显示/隐藏底部串口配置区域（隐藏底部除按钮和统计外的全部元素）"""
    is_visible = ui.bottom_content_widget.isVisible()
    if is_visible:
        # 隐藏底部内容（串口配置、按钮行、发送区等）
        ui.bottom_content_widget.setVisible(False)
        # 隐藏时：接收区占满剩余空间，底部区域最小化
        ui.gridLayout_2.setRowStretch(1, 1)  # 接收区伸展
        ui.gridLayout_2.setRowStretch(2, 0)  # 底部区域不伸展
        # 折叠时：允许根据用户偏好显示快捷按钮栏，并动态调整高度
        base_h = 35
        pref = getattr(ui, 'quickbar_user_visible', True)
        if hasattr(ui, 'quickbar_row'):
            ui.quickbar_row.setVisible(pref)
            qb_h = ui.quickbar_row.sizeHint().height() if pref else 0
        else:
            qb_h = 0
        ui.groupBox_2.setMinimumHeight(base_h + qb_h)
        ui.groupBox_2.setMaximumHeight(base_h + qb_h)
        if hasattr(ui, 'bt_toggle_quickbar'):
            ui.bt_toggle_quickbar.setText('隐藏按钮' if pref else '显示按钮')
    else:
        # 显示底部内容
        ui.bottom_content_widget.setVisible(True)
        # 展开时：接收区为主，底部区域固定舒适高度显示内容
        ui.gridLayout_2.setRowStretch(1, 1)  # 接收区伸展
        ui.gridLayout_2.setRowStretch(2, 0)  # 底部区域不参与伸展
        # 固定底部区域的最小高度（包含顶部工具行 + 内容区）
        ui.groupBox_2.setMaximumHeight(16777215)
        ui.groupBox_2.setMinimumHeight(120)
        # 展开时根据用户偏好恢复快捷按钮栏可见性
        if hasattr(ui, 'quickbar_row'):
            pref = getattr(ui, 'quickbar_user_visible', True)
            ui.quickbar_row.setVisible(pref)
        if hasattr(ui, 'bt_toggle_quickbar'):
            ui.bt_toggle_quickbar.setText('隐藏按钮' if getattr(ui, 'quickbar_user_visible', True) else '显示按钮')
    update_toggle_icon()
    # 强制刷新布局
    ui.groupBox_2.updateGeometry()
    ui.centralwidget.updateGeometry()
    MainWindow.update()

def update_toggle_icon():
    """根据配置显示状态更新折叠按钮图标与提示"""
    expanded = ui.bottom_content_widget.isVisible()
    style = QApplication.style()
    icon = style.standardIcon(QtWidgets.QStyle.SP_ArrowDown if expanded else QtWidgets.QStyle.SP_ArrowRight)
    ui.bt_toggle_bottom.setIcon(icon)
    ui.bt_toggle_bottom.setIconSize(QtCore.QSize(16, 16))
    ui.bt_toggle_bottom.setToolTip('隐藏配置' if expanded else '显示配置')

def onToggleQuickbar():
    """显示/隐藏底部快捷按钮栏，保持其它元素布局稳定"""
    try:
        if hasattr(ui, 'quickbar_row') and hasattr(ui, 'bt_toggle_quickbar'):
            # 切换用户偏好
            current_pref = getattr(ui, 'quickbar_user_visible', True)
            new_pref = not current_pref
            ui.quickbar_user_visible = new_pref
            # 应用可见性
            ui.quickbar_row.setVisible(new_pref)
            ui.bt_toggle_quickbar.setText('隐藏按钮' if new_pref else '显示按钮')
            # 如果底部内容处于折叠状态，动态调整底部区域高度以容纳按钮栏
            if not ui.bottom_content_widget.isVisible():
                base_h = 35
                qb_h = ui.quickbar_row.sizeHint().height() if new_pref else 0
                ui.groupBox_2.setMinimumHeight(base_h + qb_h)
                ui.groupBox_2.setMaximumHeight(base_h + qb_h)
            # 强制刷新布局避免闪烁
            ui.groupBox_2.updateGeometry()
            ui.centralwidget.updateGeometry()
            MainWindow.update()
    except Exception as e:
        logger.warning("切换快捷按钮栏失败: %s", e)

def OnClickSendData():
    if ui.checkBox_send_space_ctrl.checkState() == 0:
        SendDataFuntion(True)
    else:
        SendDataFuntion(False)

def onTextBrowserSendData(data):
    """处理从接收区键盘输入发送的数据"""
    # 直接发送数据，不与发送区关联
    if ui.bt_open_off_port.text() == '关闭串口':
        # 检查是否包含Tab字符，如果包含则不添加换行符直接发送
        if '\x09' in data:
            send_data = data.encode('utf-8')
        else:
            send_data = (data + "\r\n").encode('utf-8')
        
        uithreadObj.sendBuff(send_data)
        # 更新发送统计
        ui.update_send_stats(len(send_data))
        ui.add_send_rate(len(send_data))
        # 发送回显
        echo_sent_bytes(send_data)

def SendDataFuntion(isNotNewLine=False):
    ui.checkBox_send_space_ctrl.setChecked(not isNotNewLine)
    
    # 检查是否需要启动定时发送
    if ui.checkBox_timer_send.isChecked() and not timer_send.isActive():
        times = ui.lineEdit_ms_send.text()
        try:
            times_send = int(times)
            timer_send.start(times_send)
        except:
            pass  # 如果输入无效，不启动定时器
    
    if ui.bt_open_off_port.text() == '关闭串口':
        buff = ui.lineEdit_send_data.toPlainText().strip()
        if not ui.checkBox_send_hex.isChecked():
            # 未勾选hex发送，直接发送文本数据
            if isNotNewLine:
                send_data = buff.encode('utf-8')
                uithreadObj.sendBuff(send_data)
                # 更新发送统计
                ui.update_send_stats(len(send_data))
                ui.add_send_rate(len(send_data))
                # 发送回显
                echo_sent_bytes(send_data)
            else:
                buff = buff + "\r\n"
                send_data = buff.encode('utf-8')
                uithreadObj.sendBuff(send_data)
                # 更新发送统计
                ui.update_send_stats(len(send_data))
                ui.add_send_rate(len(send_data))
                # 发送回显
                echo_sent_bytes(send_data)
        else:
            # 勾选了hex发送，需要检查hex格式
            send_list = []
            while buff != '':
                try:
                    num = int(buff[0:2], 16)
                except ValueError:
                    QMessageBox.critical(MainWindow, '警告', '请输入十六进制的数据，并以空格分开!')
                    return None
                buff = buff[2:].strip()
                send_list.append(num)
            input_s = bytes(send_list)
            uithreadObj.sendBuff(input_s)
            # 更新发送统计
            ui.update_send_stats(len(input_s))
            ui.add_send_rate(len(input_s))
            # 发送回显
            echo_sent_bytes(input_s)


#  customs AT指令窗口 ------------------------------------------------------ STRAT  -------------------------------------
class EditDoubleClickFilter(QtCore.QObject):
    """拦截字符串文本框的左键双击事件，用于快速修改对应按钮的注释"""
    def __init__(self, button):
        super().__init__()
        self._button = button

    def eventFilter(self, obj, event):
        try:
            if event.type() == QtCore.QEvent.MouseButtonDblClick and event.button() == QtCore.Qt.LeftButton:
                # 触发修改注释对话框
                DoubleOnclickCustoms(self._button)
                return True
        except Exception:
            pass
        return False

def initCustomsUI():
    """初始化多字符串UI（保留原生布局与控件）"""
    global _multistring_adapter
    _multistring_adapter = None

    def _restore_layout_visibility(layout):
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if not item:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setVisible(True)
            sub_layout = item.layout()
            if sub_layout is not None:
                _restore_layout_visibility(sub_layout)

    try:
        customs_layout = ui.groupBox_customs.layout()
        if customs_layout is not None:
            _restore_layout_visibility(customs_layout)
    except Exception as e:
        logger.warning("恢复多字符串布局可见性失败: %s", e)

    if getattr(ui, '_customs_legacy_bound', False):
        return

    ui._customs_legacy_bound = True
    ui._customs_edit_filters = []

    for i in range(1, 100):
        try:
            button = getattr(ui, f'bt_customs_send_{i}')
            edit = getattr(ui, f'ed_customs_set_{i}')
            hex_checkbox = getattr(ui, f'checkBox_hex_{i}')
            seq_edit = getattr(ui, f'ed_customs_seq_{i}')
            delay_edit = getattr(ui, f'ed_customs_delay_{i}')

            button.clicked.connect(partial(OnclickCustoms, i))
            button.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(partial(onButtonContextMenu, button, i))

            edit.textChanged.connect(partial(save_custom_button_config, i))
            hex_checkbox.stateChanged.connect(partial(save_custom_hex_config, i))
            seq_edit.textChanged.connect(partial(save_custom_seq_config, i))
            delay_edit.textChanged.connect(partial(save_custom_delay_config, i))

            edit_filter = EditDoubleClickFilter(button)
            edit.installEventFilter(edit_filter)
            ui._customs_edit_filters.append(edit_filter)
        except AttributeError:
            break

    update_all_seq_styles()
        
def save_custom_button_config(index, *args):
    """保存自定义按钮配置"""
    edit_widget = getattr(ui, f'ed_customs_set_{index}')
    save_params_local(f'groupBox_customs_data_{index}', edit_widget.text())

def save_custom_hex_config(index, *args):
    """保存自定义按钮HEX配置"""
    hex_checkbox = getattr(ui, f'checkBox_hex_{index}')
    save_params_local(f'checkBox_hex_{index}', hex_checkbox.isChecked())

def save_custom_delay_config(index, *args):
    """保存自定义按钮延迟配置"""
    delay_edit = getattr(ui, f'ed_customs_delay_{index}')
    save_params_local(f'ed_customs_delay_{index}', delay_edit.text())

def update_all_seq_styles():
    """更新所有序号输入框的样式，检查重复"""
    # 收集所有序号
    seq_map = {}  # {seq_num: [button_indices]}
    
    for i in range(1, 100):
        try:
            seq_edit = getattr(ui, f'ed_customs_seq_{i}')
            seq_text = seq_edit.text().strip()
            if seq_text:
                try:
                    seq_num = int(seq_text)
                    if seq_num > 0:
                        if seq_num not in seq_map:
                            seq_map[seq_num] = []
                        seq_map[seq_num].append(i)
                except ValueError:
                    pass
        except AttributeError:
            break
    
    # 更新所有输入框的样式
    for i in range(1, 100):
        try:
            seq_edit = getattr(ui, f'ed_customs_seq_{i}')
            seq_text = seq_edit.text().strip()
            
            if seq_text:
                try:
                    seq_num = int(seq_text)
                    if seq_num > 0:
                        # 检查是否重复
                        if len(seq_map[seq_num]) > 1:
                            # 重复序号
                            other_buttons = [btn for btn in seq_map[seq_num] if btn != i]
                            seq_edit.setStyleSheet("background-color: #ffcccc; border: 1px solid red;")
                            button_list = ', '.join(map(str, other_buttons))
                            seq_edit.setToolTip(f"序号重复！与按钮 {button_list} 的序号相同")
                        else:
                            # 唯一序号
                            seq_edit.setStyleSheet("")
                            seq_edit.setToolTip("")
                    else:
                        # 序号无效（非正整数）
                        seq_edit.setStyleSheet("background-color: #ffffcc; border: 1px solid orange;")
                        seq_edit.setToolTip("序号必须是正整数")
                except ValueError:
                    # 序号格式错误
                    seq_edit.setStyleSheet("background-color: #ffffcc; border: 1px solid orange;")
                    seq_edit.setToolTip("序号格式错误，请输入数字")
            else:
                # 清空时恢复正常样式
                seq_edit.setStyleSheet("")
                seq_edit.setToolTip("")
        except AttributeError:
            break

def save_custom_seq_config(index, *args):
    """保存自定义按钮序号配置"""
    seq_edit = getattr(ui, f'ed_customs_seq_{index}')
    seq_text = seq_edit.text().strip()
    
    # 保存配置
    save_params_local(f'ed_customs_seq_{index}', seq_text)
    
    # 更新所有序号输入框的样式
    update_all_seq_styles()

def OnclickCustoms(index):
    """点击自定义按钮 - 使用适配器处理"""
    global _multistring_adapter
    
    # 使用适配器处理点击事件
    if _multistring_adapter:
        _multistring_adapter.OnclickCustoms(index)
    else:
        # 备用：直接处理（兼容模式）
        _onclick_customs_legacy(index)

def _onclick_customs_legacy(index):
    """原有的点击处理逻辑（兼容模式）——仅发送单条，不触发顺序/循环"""
    global _onclick_customs_running

    # 防止重复调用
    if _onclick_customs_running.get(index, False):
        return

    _onclick_customs_running[index] = True

    try:
        edit = getattr(ui, f'ed_customs_set_{index}')
        text = edit.text()
        if not text:
            return
        hex_checkbox = getattr(ui, f'checkBox_hex_{index}')
        is_hex = hex_checkbox.isChecked()
        # 直接发送一次，不读取 sequential/loop 状态
        sendCustomData(text, is_hex)
    finally:
        _onclick_customs_running[index] = False

def sendCustomData(text, is_hex):
    """直接发送自定义数据，不依赖SendDataFuntion，避免与定时发送冲突"""
    if ui.bt_open_off_port.text() == '关闭串口':
        buff = text.strip()
        if not is_hex:
            # 文本模式发送
            send_data = (buff + "\r\n").encode('utf-8')
            uithreadObj.sendBuff(send_data)
            # 更新发送统计
            ui.update_send_stats(len(send_data))
            ui.add_send_rate(len(send_data))
            # 发送回显
            echo_sent_bytes(send_data)
        else:
            # HEX模式发送
            send_list = []
            while buff != '':
                try:
                    num = int(buff[0:2], 16)
                except ValueError:
                    QMessageBox.critical(MainWindow, '警告', '请输入十六进制的数据，并以空格分开!')
                    return
                buff = buff[2:].strip()
                send_list.append(num)
            input_s = bytes(send_list)
            uithreadObj.sendBuff(input_s)
            # 更新发送统计
            ui.update_send_stats(len(input_s))
            ui.add_send_rate(len(input_s))
            # 发送回显
            echo_sent_bytes(input_s)

def _replace_escape_sequences(s: str) -> str:
    r"""将 \r \n \t \e \b 等转义替换为实际字符。"""
    out = s
    out = out.replace('\\r', '\r')
    out = out.replace('\\n', '\n')
    out = out.replace('\\t', '\t')
    out = out.replace('\\e', chr(27))
    out = out.replace('\\b', '\b')
    return out

def send_quickbar(text: str, is_hex: bool, append_newline: bool = True):
    """供快捷按钮栏调用的发送函数。
    - 支持字符串中的转义序列（\\r, \\n, \\t, \\e, \\b）
    - 根据 append_newline 控制是否附加 \r\n（仅文本模式）
    - HEX 模式按空格或连续HEX字符解析
    """
    if ui.bt_open_off_port.text() != '关闭串口':
        return

    if not is_hex:
        buff = _replace_escape_sequences(text)
        data = buff.encode('utf-8')
        if append_newline:
            data += b"\r\n"
        uithreadObj.sendBuff(data)
        ui.update_send_stats(len(data))
        ui.add_send_rate(len(data))
        echo_sent_bytes(data)
    else:
        buff = text.strip().replace(' ', '')
        if len(buff) % 2 != 0:
            QMessageBox.critical(MainWindow, '警告', 'HEX长度必须为偶数，可使用空格分隔!')
            return
        send_list = []
        while buff != '':
            try:
                num = int(buff[0:2], 16)
            except ValueError:
                QMessageBox.critical(MainWindow, '警告', '请输入十六进制的数据，并以空格分开!')
                return
            buff = buff[2:]
            send_list.append(num)
        input_s = bytes(send_list)
        uithreadObj.sendBuff(input_s)
        ui.update_send_stats(len(input_s))
        ui.add_send_rate(len(input_s))
        echo_sent_bytes(input_s)

def echo_sent_bytes(data_bytes: bytes):
    """在接收区回显已发送内容，自动判断显示为字符串或HEX。
    规则：
    - 若发送区为HEX模式（`checkBox_send_hex` 勾选），按HEX显示；
    - 否则尝试按UTF-8解码并检测可打印性；不可打印或解码失败时按HEX显示。
    """
    try:
        if not hasattr(ui, 'checkBox_show_send'):
            return
        if not ui.checkBox_show_send.isChecked():
            return

        # 如果用户当前选择了HEX发送，则优先HEX回显
        send_hex_mode = False
        try:
            send_hex_mode = ui.checkBox_send_hex.isChecked()
        except Exception:
            send_hex_mode = False

        def bytes_to_hex(b: bytes) -> str:
            return ' '.join(f"{x:02X}" for x in b)

        def ensure_trailing_newline(s: str) -> str:
            # 根据日志配置决定是否追加换行；未开启则不加换行
            try:
                add_nl = getattr(serial_logger, "add_newline", False)
            except Exception:
                add_nl = False
            if not add_nl:
                return s
            # 若已以\n或\r结尾，不再额外添加换行；否则追加 CRLF（Windows友好）
            return s if (len(s) > 0 and (s.endswith('\n') or s.endswith('\r'))) else (s + '\r\n')

        if send_hex_mode:
            out_s = ensure_trailing_newline("[TX HEX] " + bytes_to_hex(data_bytes))
            ui.textBrowserShow.append_received_data(data=out_s, is_hex=True, add_timestamp=False, timestamp_str="")
            try:
                serial_logger.log_tx(data_bytes)
            except Exception as e:
                logger.warning("发送HEX日志写入失败: %s", e)
            return

        # 自动判断：能严格按UTF-8解码且主要为可打印字符就按字符串显示
        try:
            s_strict = data_bytes.decode('utf-8', 'strict')
            s_check = s_strict.replace('\n', '').replace('\r', '').replace('\t', '')
            is_printable = s_check.isprintable()
            if is_printable:
                ui.textBrowserShow.append_received_data(data=ensure_trailing_newline("[TX STR] " + s_strict), is_hex=False, add_timestamp=False, timestamp_str="")
                try:
                    serial_logger.log_tx(data_bytes)
                except Exception as e:
                    logger.warning("发送STR日志写入失败: %s", e)
            else:
                out_s = ensure_trailing_newline("[TX HEX] " + bytes_to_hex(data_bytes))
                ui.textBrowserShow.append_received_data(data=out_s, is_hex=True, add_timestamp=False, timestamp_str="")
                try:
                    serial_logger.log_tx(data_bytes)
                except Exception as e:
                    logger.warning("发送HEX日志写入失败: %s", e)
        except UnicodeDecodeError:
            out_s = ensure_trailing_newline("[TX HEX] " + bytes_to_hex(data_bytes))
            ui.textBrowserShow.append_received_data(data=out_s, is_hex=True, add_timestamp=False, timestamp_str="")
            try:
                serial_logger.log_tx(data_bytes)
            except Exception as e:
                logger.warning("发送HEX日志写入失败: %s", e)
    except Exception as e:
        logger.error("发送回显失败: %s", e)

# ---------------------- Gavin_com_multsrt.ini 兼容的导入/导出 ----------------------
def parse_sscom_ini(file_path: str):
    """解析 Gavin_com_multsrt.ini，仅提取多字符串相关条目。
    规则：
    - N1..N99: 数据行，形如 "A,<ascii>" 或 "H,<hex>"
    - N101..N199: 元数据行，形如 "x,<标签>,<延迟>"
    返回：{index: {mode:'A'|'H', content:str, label:str, delay:str}}
    """
    import re
    entries = {}
    # 兼容UTF-8/GB2312(GBK)读取，尽量避免中文乱码
    try:
        with open(file_path, 'rb') as fb:
            raw_bytes = fb.read()
        text = None
        for enc in ('utf-8-sig', 'utf-8', 'gbk', 'gb2312'):
            try:
                text = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            # 兜底，尽量不报错
            text = raw_bytes.decode('latin1')
    except Exception as e:
        raise e
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(';'):
            continue
        m = re.match(r'^N(\d+)\s*=\s*(.*)$', line)
        if not m:
            continue
        idx = int(m.group(1))
        value = m.group(2).strip()
        if 1 <= idx <= 99:
            # 数据行
            mode, content = ('A', value)
            if ',' in value:
                mode, content = value.split(',', 1)
            entries.setdefault(idx, {})
            mode_norm = (mode or 'A').strip().upper()
            # 过滤ASCII中的\r\n，因发送端会自动追加回车
            if mode_norm == 'A':
                c = content.strip()
                # 同时处理转义形式和真实换行
                c = c.replace('\\r\\n', '')
                c = c.replace('\r\n', '').replace('\n', '').replace('\r', '')
                # 仅在非空时写入，以避免清空现有UI
                if c != '':
                    entries[idx]['content'] = c
            else:
                hc = content.strip()
                if hc != '':
                    entries[idx]['content'] = hc
            entries[idx]['mode'] = mode_norm
        elif 101 <= idx <= 199:
            num = idx - 100
            parts = [p.strip() for p in value.split(',')]
            label = parts[1] if len(parts) > 1 else ''
            delay = parts[2] if len(parts) > 2 else ''
            entries.setdefault(num, {})
            # 过滤备注为“无注释”的情况，不写入label避免覆盖UI默认或已有备注
            label_norm = (label or '').strip()
            # 过滤所有包含“无注释”的占位备注（例如“22无注释”、“无注释”等）
            if label_norm and ('无注释' not in label_norm):
                entries[num]['label'] = label_norm
            if delay:
                entries[num]['delay'] = delay
    return entries

def export_all_config():
    """将所有配置（QSettings内全部键值）导出为JSON文件，供用户备份或迁移。"""
    try:
        import json
        chosen, _ = QFileDialog.getSaveFileName(
            MainWindow, '导出配置', os.path.expanduser('~/kero_serial_config.json'),
            'JSON文件 (*.json);;All Files (*)'
        )
        if not chosen:
            return
        mSetting = QSettings(QSettings.IniFormat, QSettings.UserScope, "Gavin", "Gavin_com")
        data = {}
        for key in mSetting.allKeys():
            val = mSetting.value(key)
            # QSettings 读出的值可能是 bool/int/str，统一转为可序列化类型
            if isinstance(val, bool):
                data[key] = val
            elif isinstance(val, (int, float)):
                data[key] = val
            else:
                data[key] = str(val) if val is not None else None
        with open(chosen, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        QMessageBox.information(MainWindow, '导出成功', f'所有配置已导出到:\n{chosen}')
    except Exception as e:
        QMessageBox.critical(MainWindow, '导出失败', f'导出配置失败:\n{e}')


def import_all_config():
    """从JSON文件导入所有配置并刷新UI。"""
    try:
        import json
        chosen, _ = QFileDialog.getOpenFileName(
            MainWindow, '导入配置', os.path.expanduser('~'),
            'JSON文件 (*.json);;All Files (*)'
        )
        if not chosen:
            return
        with open(chosen, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            QMessageBox.warning(MainWindow, '格式错误', '所选文件不是有效的配置文件。')
            return
        mSetting = QSettings(QSettings.IniFormat, QSettings.UserScope, "Gavin", "Gavin_com")
        for key, val in data.items():
            mSetting.setValue(key, val)
        mSetting.sync()
        # 重新加载UI
        load_from_local()
        QMessageBox.information(MainWindow, '导入成功', f'已从以下文件恢复配置:\n{chosen}\n\n部分设置（如串口号）需重新选择串口后生效。')
    except Exception as e:
        QMessageBox.critical(MainWindow, '导入失败', f'导入配置失败:\n{e}')


def import_multistring_from_sscom(file_path: str | None = None):
    """从 Gavin_com_multsrt.ini 导入到当前多字符串UI并持久化到 QSettings。
    始终弹出文件选择对话框，用户自选路径。
    """
    try:
        initial = os.path.expanduser('~')
        chosen, _ = QFileDialog.getOpenFileName(MainWindow, '选择 Gavin_com_multsrt.ini', initial, 'INI Files (*.ini);;All Files (*)')
        if not chosen:
            return
        file_path = chosen
        entries = parse_sscom_ini(file_path)

        # 计算UI可用的槽位数量
        max_ui = 0
        for idx in range(1, 100):
            try:
                getattr(ui, f'bt_customs_send_{idx}')
                getattr(ui, f'ed_customs_set_{idx}')
                getattr(ui, f'checkBox_hex_{idx}')
                getattr(ui, f'ed_customs_delay_{idx}')
                max_ui = idx
            except AttributeError:
                break

        def apply_entry_to_slot(slot_index: int, e: dict) -> bool:
            updated = False
            if 'content' in e:
                content = e.get('content', '')
                getattr(ui, f'ed_customs_set_{slot_index}').setText(content)
                save_params_local(f'groupBox_customs_data_{slot_index}', content)
                updated = True
            if 'mode' in e:
                try:
                    is_hex = (e.get('mode', 'A') or 'A').upper() == 'H'
                    getattr(ui, f'checkBox_hex_{slot_index}').setChecked(is_hex)
                    save_params_local(f'checkBox_hex_{slot_index}', is_hex)
                    updated = True
                except Exception:
                    pass
            if 'delay' in e:
                try:
                    delay = e.get('delay', '')
                    getattr(ui, f'ed_customs_delay_{slot_index}').setText(delay)
                    save_params_local(f'ed_customs_delay_{slot_index}', delay)
                    updated = True
                except Exception:
                    pass
            if e.get('label'):
                label = e.get('label', '')
                getattr(ui, f'bt_customs_send_{slot_index}').setText(label)
                save_params_local(f'bt_customs_send_{slot_index}', label)
                updated = True
            return updated

        applied = 0
        # 第一轮：按索引直接匹配，仅更新存在的条目，不清空其它
        for i in range(1, max_ui + 1):
            e = entries.get(i)
            if e:
                if apply_entry_to_slot(i, e):
                    applied += 1

        # 若没有任何直接匹配，进行顺序压缩填充（按文件中的顺序依次填到UI 1..max_ui）
        if applied == 0:
            ordered_keys = [k for k in sorted(entries.keys()) if isinstance(entries.get(k), dict)]
            j = 1
            for k in ordered_keys:
                if j > max_ui:
                    break
                e = entries.get(k, {})
                if apply_entry_to_slot(j, e):
                    applied += 1
                j += 1

        QMessageBox.information(MainWindow, '导入成功', f'已应用 {applied} 条配置\n(未覆盖的条目保持原状)')
    except Exception as e:
        QMessageBox.critical(MainWindow, '导入失败', f'解析或应用配置失败:\n{e}')

def export_multistring_to_sscom(file_path: str | None = None):
    """将当前多字符串配置导出为 Gavin_com_multsrt.ini 可读格式（仅多字符串项）。"""
    try:
        default_path = os.path.join(os.path.expanduser('~'), 'Gavin_com_multsrt.ini')
        if not file_path:
            initial = default_path
            chosen, _ = QFileDialog.getSaveFileName(MainWindow, '保存为 Gavin_com_multsrt.ini', initial, 'INI Files (*.ini);;All Files (*)')
            if not chosen:
                return
            file_path = chosen
        lines = []
        lines.append('; Gavin_com 导出的 SSCOM5.1 兼容配置（仅多字符串）')
        lines.append('; "=" 后的 H 表示 HEX，A 表示 ASCII')
        for i in range(1, 100):
            try:
                btn = getattr(ui, f'bt_customs_send_{i}')
                edit = getattr(ui, f'ed_customs_set_{i}')
                delay_edit = getattr(ui, f'ed_customs_delay_{i}')
                hex_checkbox = getattr(ui, f'checkBox_hex_{i}')
            except AttributeError:
                break
            label = (btn.text() or str(i)).strip()
            delay = (delay_edit.text() or '1000').strip()
            is_hex = hex_checkbox.isChecked()
            mode = 'H' if is_hex else 'A'
            content = (edit.text() or '').strip()
            if not is_hex:
                # 以转义形式写入CRLF，避免工具误解
                content = content.replace('\\', '\\\\').replace('\r\n', '\\r\\n').replace('\n', '\\r\\n')
            lines.append(f'N{100+i}=0,{label},{delay}')
            lines.append(f'N{i}={mode},{content}')
        # 附加语言键以提高兼容性（部分工具可能读取）
        lines.append('N1100=,中文')
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        QMessageBox.information(MainWindow, '导出成功', f'配置已导出到:\n{file_path}')
    except Exception as e:
        QMessageBox.critical(MainWindow, '导出失败', f'写入文件失败:\n{e}')

def onImportSSCOM():
    import_multistring_from_sscom(None)

def onExportSSCOM():
    # 允许用户选择保存位置，预填默认路径
    export_multistring_to_sscom(None)

# 全局变量，用于控制循环执行
loop_running = False

# 全局变量，用于防止OnclickCustoms函数重复调用
_onclick_customs_running = {}

# 后台线程：顺序/循环执行
class SequenceWorker(QtCore.QThread):
    progress = QtCore.Signal(int, int)  # 当前循环次数, 最大循环次数（0 表示无限）
    statusChanged = QtCore.Signal(str)
    sendLength = QtCore.Signal(int)
    finishedSignal = QtCore.Signal(str)  # 'completed' | 'stopped' | 'error'

    def __init__(self, sequence_items, is_loop, max_loops, parent=None):
        super().__init__(parent)
        self.sequence_items = sequence_items
        self.is_loop = is_loop
        self.max_loops = max_loops
        self._running = True
        self._stop_event = threading.Event()

    def stop(self):
        self._running = False
        self._stop_event.set()

    def _wait_delay(self, delay_ms):
        if delay_ms <= 0:
            return self._running
        return not self._stop_event.wait(delay_ms / 1000.0)

    def run(self):
        loop_count = 0
        # 初始化状态
        if self.is_loop:
            self.statusChanged.emit(f"状态: 运行中 (0/{self.max_loops if self.max_loops > 0 else '∞'})")
        else:
            self.statusChanged.emit("状态: 运行中")

        while True:
            for item in self.sequence_items:
                if not self._running:
                    self.statusChanged.emit("状态: 已停止")
                    self.finishedSignal.emit("stopped")
                    return
                try:
                    buff = item['text'].strip()
                    if not item['is_hex']:
                        data = (buff + "\r\n").encode('utf-8')
                    else:
                        send_list = []
                        while buff != '':
                            num = int(buff[0:2], 16)
                            buff = buff[2:].strip()
                            send_list.append(num)
                        data = bytes(send_list)
                    uithreadObj.sendBuff(data)
                    self.sendLength.emit(len(data))
                except Exception as e:
                    self.statusChanged.emit(f"发送异常: {e}")
                # 延迟（毫秒）
                delay_ms = int(item.get('delay', 0))
                if not self._wait_delay(delay_ms):
                    self.statusChanged.emit("状态: 已停止")
                    self.finishedSignal.emit("stopped")
                    return

            if not self.is_loop:
                break

            loop_count += 1
            self.progress.emit(loop_count, self.max_loops)

            if self.max_loops > 0 and loop_count >= self.max_loops:
                self.statusChanged.emit(f"状态: 已完成 ({loop_count}/{self.max_loops})")
                break

        self.finishedSignal.emit("completed")

# 开始/停止按钮点击处理
def onToggleLoopClicked():
    if loop_running:
        stopLoopExecution()
    else:
        startLoopExecution()

# 开始循环或单次顺序执行（后台线程）
def startLoopExecution():
    global loop_running

    # 收集所有有序号的按钮
    sequence_items = []
    used_seq_nums = set()
    duplicate_seq_nums = []
    for i in range(1, 100):
        try:
            seq_edit = getattr(ui, f'ed_customs_seq_{i}')
            seq_text = seq_edit.text()
            if seq_text and seq_text.strip():
                try:
                    seq_num = int(seq_text)
                    if seq_num > 0:
                        if seq_num in used_seq_nums:
                            if seq_num not in duplicate_seq_nums:
                                duplicate_seq_nums.append(seq_num)
                            continue
                        used_seq_nums.add(seq_num)

                        edit = getattr(ui, f'ed_customs_set_{i}')
                        hex_checkbox = getattr(ui, f'checkBox_hex_{i}')
                        delay_edit = getattr(ui, f'ed_customs_delay_{i}')
                        sequence_items.append({
                            'index': i,
                            'seq_num': seq_num,
                            'text': edit.text(),
                            'is_hex': hex_checkbox.isChecked(),
                            'delay': int(delay_edit.text()) if delay_edit.text() else 0
                        })
                except ValueError:
                    pass
        except AttributeError:
            break

    # 重复序号提示
    if duplicate_seq_nums:
        duplicate_str = ', '.join(map(str, duplicate_seq_nums))
        QMessageBox.warning(MainWindow, '序号重复警告',
                            f'发现重复的序号: {duplicate_str}\n\n'
                            f'请修正重复的序号设置后再执行顺序发送。\n'
                            f'每个序号只能使用一次。')
        return

    if not sequence_items:
        return

    # 按序号排序
    sequence_items.sort(key=lambda x: x['seq_num'])

    # 循环配置
    is_loop = ui.checkBox_loop.isChecked()
    max_loops = 0
    if is_loop:
        try:
            max_loops = int(ui.lineEdit_loop_count.text()) if ui.lineEdit_loop_count.text() else 0
        except ValueError:
            max_loops = 0
        if max_loops <= 0:
            max_loops = 0  # 0 表示无限循环

    # 启动后台线程
    ui.seq_worker = SequenceWorker(sequence_items, is_loop, max_loops)

    # 连接信号到 UI
    ui.seq_worker.statusChanged.connect(lambda s: ui.label_loop_status.setText(s))
    ui.seq_worker.progress.connect(lambda count, total: ui.label_loop_status.setText(f"状态: 运行中 ({count}/{total if total>0 else '∞'})"))
    ui.seq_worker.sendLength.connect(lambda n: (ui.update_send_stats(n), ui.add_send_rate(n)))

    def _on_finished(reason):
        global loop_running
        loop_running = False
        ui.pushButton_stop_loop.setText("开始")
        if not is_loop:
            ui.label_loop_status.setText("状态: 已完成")

    ui.seq_worker.finishedSignal.connect(_on_finished)

    loop_running = True
    ui.pushButton_stop_loop.setText("停止")
    ui.seq_worker.start()

# 停止循环执行
def stopLoopExecution():
    global loop_running
    loop_running = False
    worker = getattr(ui, 'seq_worker', None)
    try:
        if worker and worker.isRunning():
            worker.stop()
    except Exception:
        pass
    # 等待后台线程或当前循环自然停止，再恢复“开始”
    ui.label_loop_status.setText("状态: 停止中...")

def DoubleOnclickCustoms(button):
    current_text = button.text()
    text, ok = QInputDialog.getText(button, '备注', '请输入备注：', QLineEdit.Normal, current_text)
    if text and ok:
        button.setText(str(text))
        logger.debug("%s %s", button.objectName(), text)
        save_params_local(button.objectName(), str(text))

# 查找第一个空闲索引
def find_first_empty_index():
    for i in range(1, 100):
        try:
            button = getattr(ui, f'bt_customs_send_{i}')
            button_text = button.text()
            if not button_text or button_text == str(i):
                return i
        except AttributeError:
            break
    return 0

# 清空所有条目
def clear_all_entries():
    reply = QMessageBox.question(MainWindow, '确认', '确定要清空所有条目吗？', 
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    if reply == QMessageBox.Yes:
        for i in range(1, 100):
            try:
                getattr(ui, f'bt_customs_send_{i}').setText(str(i))
                getattr(ui, f'ed_customs_set_{i}').setText('')
                try:
                    getattr(ui, f'checkBox_hex_{i}').setChecked(False)
                    save_params_local(f'checkBox_hex_{i}', False)
                except Exception:
                    pass
                try:
                    getattr(ui, f'ed_customs_delay_{i}').setText('')
                    save_params_local(f'ed_customs_delay_{i}', '')
                except Exception:
                    pass
                try:
                    getattr(ui, f'ed_customs_seq_{i}').setText('')
                    save_params_local(f'ed_customs_seq_{i}', '')
                except Exception:
                    pass
                save_params_local(f'bt_customs_send_{i}', str(i))
                save_params_local(f'groupBox_customs_data_{i}', '')
            except AttributeError:
                break

        # 清空后刷新序号样式（去除重复高亮等）
        try:
            update_all_seq_styles()
        except NameError:
            pass

# 添加新条目
def add_new_entry():
    empty_index = find_first_empty_index()
    if empty_index > 0 and empty_index <= 99:
        text, ok = QInputDialog.getText(ui.groupBox_customs, '新增条目', '请输入备注：')
        if text and ok:
            getattr(ui, f'bt_customs_send_{empty_index}').setText(text)
            save_params_local(f'bt_customs_send_{empty_index}', text)
    else:
        QMessageBox.information(MainWindow, '提示', '已达到最大条目数量！')

# 收发状态标签右键菜单
def onStatsContextMenu(pos):
    menu = QMenu()
    resetAction = menu.addAction("重置")
    
    action = menu.exec(ui.label_stats.mapToGlobal(pos))
    
    if action == resetAction:
        reset_stats()

def reset_stats():
    """重置收发统计数据"""
    reply = QMessageBox.question(MainWindow, '确认', '确定要重置收发统计数据吗？', 
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    if reply == QMessageBox.Yes:
        # 重置统计变量
        ui.send_packet_count = 0
        ui.send_byte_count = 0
        ui.recv_packet_count = 0
        ui.recv_byte_count = 0
        ui.send_rate = 0.0
        ui.recv_rate = 0.0
        ui.last_update_time = time.time()
        
        # 立即更新显示
        stats_text = "TX:0/0B (0B/s)\nRX:0/0B (0B/s)"
        ui.label_stats.setText(stats_text)

# 按钮右键菜单
def onButtonContextMenu(button, index, pos):
    menu = QMenu()
    clearAction = menu.addAction("清空所有条目")
    deleteAction = menu.addAction("清空此条目")
    editCommentAction = menu.addAction("修改注释")
    
    action = menu.exec(button.mapToGlobal(pos))
    
    if action == clearAction:
        clear_all_entries()
    
    elif action == editCommentAction:
        # 调用修改注释功能
        DoubleOnclickCustoms(button)
    
    elif action == deleteAction:
        # 清空该条目
        reply = QMessageBox.question(MainWindow, '确认', f'确定要清空条目 {button.text()} 吗？', 
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # 直接清空当前条目，不移动其他条目
            getattr(ui, f'bt_customs_send_{index}').setText(str(index))
            getattr(ui, f'ed_customs_set_{index}').setText('')
            # 同步清空HEX勾选、延迟与序号输入框
            try:
                getattr(ui, f'checkBox_hex_{index}').setChecked(False)
                save_params_local(f'checkBox_hex_{index}', False)
            except Exception:
                pass
            try:
                getattr(ui, f'ed_customs_delay_{index}').setText('')
                save_params_local(f'ed_customs_delay_{index}', '')
            except Exception:
                pass
            try:
                getattr(ui, f'ed_customs_seq_{index}').setText('')
                save_params_local(f'ed_customs_seq_{index}', '')
            except Exception:
                pass
            save_params_local(f'bt_customs_send_{index}', str(index))
            save_params_local(f'groupBox_customs_data_{index}', "")
            # 刷新序号样式
            try:
                update_all_seq_styles()
            except NameError:
                pass


if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    
    MainWindow = QtWidgets.QMainWindow()
    MainWindow.setWindowIcon(QIcon('res/sscom.ico'))
    ui = MyWindow()
    ui.add_cnt = 0

    # 禁止拉伸窗口大小
    # MainWindow.setFixedSize(MainWindow.width(), MainWindow.height())
    # # !!!修复DesignerQT5自定义QWidget时候，window不会设置调用setCentralWidget设置在中心
    MainWindow.setCentralWidget(ui.centralwidget)
    # # 设置电脑键盘回调
    ui.centralwidget.set_connect_key_press(windows_key_press)
    dk = app.primaryScreen().availableGeometry()

    # 定时发送数据已在InitUI中初始化
    ui.AddButton.clicked.connect(partial(add_filter, ui))
    ui.HistoryFilterButton.clicked.connect(partial(history_filter, ui))
    uithreadObj = ui_thread()
    uithreadObj.set_default_at_result_callBack(at_callback_handler)
    
    # 设置自动应答引擎的发送回调
    auto_reply_engine.set_send_callback(lambda data: uithreadObj.sendBuff(data))
    
    # 加载自动应答配置
    auto_reply_engine.load_settings()
    # ui.label.setFont(QFont("Microsoft YaHei", 18))   #设置label的字体和大小
    browser_document = ui.textBrowserShow.document()
    browser_document.setMaximumBlockCount(100000)
    InitUI()
    # 绑定快捷按钮栏的发送回调，并在首次运行时填充示例按钮
    try:
        if hasattr(ui, 'quick_button_bar') and ui.quick_button_bar is not None:
            ui.quick_button_bar.set_sender(send_quickbar)
            # 如果当前未配置任何按钮，提供几个示例便于上手
            if not ui.quick_button_bar.has_any_buttons():
                # 直接调用内部追加（避免弹窗），仅首次初始化
                try:
                    ui.quick_button_bar._append_button({'label': 'SN', 'text': 'product_get_sn\\n', 'is_hex': False, 'append_newline': True, 'color': 'Green'})
                    ui.quick_button_bar._append_button({'label': 'AT', 'text': 'AT\\r', 'is_hex': False, 'append_newline': False, 'color': 'Blue'})
                    ui.quick_button_bar._append_button({'label': '0x55AA', 'text': '55 AA 01 02', 'is_hex': True, 'append_newline': False, 'color': 'Orange'})
                    ui.quick_button_bar._save_settings()
                except Exception as e:
                    logger.warning("初始化示例快捷按钮失败: %s", e)
    except Exception as e:
        logger.warning("绑定快捷按钮栏失败: %s", e)
    # 初始化日志管理器父窗口与配置
    try:
        serial_logger.set_parent(MainWindow)
        serial_logger.load_from_qsettings()
    except Exception as e:
        logger.warning("初始化日志管理器失败: %s", e)
    # 从上次记录获取面板设置显示
    load_from_local()
    # 居中显示
    # MainWindow.move((int)(dk.width() / 2 - MainWindow.width() / 2), (int)(dk.height() / 2 - MainWindow.height() / 2))
    _translate = QtCore.QCoreApplication.translate
    MainWindow.setWindowTitle(
        _translate("Gavin_com", f"Gavin_com 串口调试助手 v{APP_VERSION}"))
    MainWindow.show()
    refreshPort()
    sys.exit(app.exec())
