#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志管理模块 - 负责串口会话的日志记录和管理

功能说明:
    - 串口数据日志记录(TX/RX)
    - 日志文件自动分片
    - 午夜自动切换
    - 异步写入机制
    - 资源安全释放

作者: Gavin
版本: 2.0.0
日期: 2026-02-06
"""

from PySide6 import QtWidgets
from PySide6.QtCore import QSettings, QStandardPaths, QThread, Signal, QObject
import os
import threading
import queue
from datetime import datetime
import logging

# 配置日志
logger = logging.getLogger(__name__)


class AsyncLogWriter(QObject):
    """
    异步日志写入器
    
    功能:
        - 在后台线程中写入日志
        - 避免阻塞主线程
        - 确保数据完整性
    """
    
    # 信号
    writeError = Signal(str)
    _CMD_STOP = "__STOP__"
    _CMD_SWITCH = "__SWITCH__"
    
    def __init__(self):
        super().__init__()
        self._queue = queue.Queue()
        self._thread = None
        self._running = False
        self._accepting = False
        self._current_file = None
        self._lock = threading.Lock()
        
    def start(self):
        """启动写入线程"""
        if self._running and self._thread and self._thread.is_alive():
            return
        self._queue = queue.Queue()
        self._accepting = True
        self._running = True
        self._thread = threading.Thread(target=self._write_loop, daemon=True)
        self._thread.start()
        logger.debug("异步日志写入线程已启动")
            
    def stop(self, timeout=5.0):
        """
        停止写入线程
        
        Args:
            timeout: 等待超时时间（秒）
        """
        if not self._running:
            return

        self._accepting = False
        self._queue.put((self._CMD_STOP, None))

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        if self._thread and self._thread.is_alive():
            logger.warning("异步日志写入线程未能在超时时间内退出")

        self._thread = None
        self._running = False
        with self._lock:
            self._current_file = None
                        
    def set_file(self, file_handle):
        """设置当前写入的文件"""
        if file_handle is None:
            return
        self.start()
        self._queue.put((self._CMD_SWITCH, file_handle))
            
    def write(self, data: str or bytes):
        """
        写入数据到队列
        
        Args:
            data: 要写入的数据
        """
        if self._running and self._accepting:
            self._queue.put(data)

    @staticmethod
    def _close_file_handle(file_handle):
        """关闭文件句柄。"""
        if not file_handle:
            return
        try:
            file_handle.flush()
        except Exception as e:
            logger.error(f"刷新日志文件失败: {e}")
        try:
            file_handle.close()
            logger.debug("日志文件已关闭")
        except Exception as e:
            logger.error(f"关闭日志文件失败: {e}")
            
    def _write_loop(self):
        """写入线程主循环"""
        logger.info("日志写入线程已启动")
        
        while True:
            try:
                # 等待数据，设置超时以便检查运行状态
                item = self._queue.get(timeout=0.5)

                if isinstance(item, tuple) and len(item) == 2:
                    cmd, payload = item
                    if cmd == self._CMD_SWITCH:
                        with self._lock:
                            old_file = self._current_file
                            self._current_file = payload
                        if old_file and old_file is not payload:
                            self._close_file_handle(old_file)
                        continue
                    if cmd == self._CMD_STOP:
                        break
                    data = payload
                else:
                    data = item
                    
                # 写入文件
                with self._lock:
                    current_file = self._current_file
                    if current_file:
                        try:
                            if isinstance(data, bytes):
                                current_file.write(data)
                            else:
                                current_file.write(data)
                                
                            # 定期刷新缓冲区
                            if self._queue.empty():
                                current_file.flush()
                                
                        except Exception as e:
                            logger.error(f"写入日志失败: {e}")
                            self.writeError.emit(str(e))
                            
            except queue.Empty:
                # 超时，检查运行状态
                continue
            except Exception as e:
                logger.exception(f"日志写入循环异常: {e}")

        with self._lock:
            current_file = self._current_file
            self._current_file = None
        if current_file:
            self._close_file_handle(current_file)

        self._running = False
        logger.info("日志写入线程已退出")


class _RolloverSignaler(QObject):
    """从后台线程安全地通知主线程日志分片完成（避免主线程文件I/O阻塞）"""
    rolloverComplete = Signal(object, str, int, str)  # (file_obj, new_path, part_index, base_path)


class SerialLogger:
    """
    串口日志管理器
    
    功能:
        - 管理串口会话日志
        - 支持宏模板
        - 午夜自动滚动
        - 文件大小分片
        - 异步写入
    """

    def __init__(self):
        """初始化日志管理器"""
        self.parent = None
        self.file = None
        self.is_logging = False
        self.session_name = ''
        self.port_name = ''
        self.last_date = None
        self.chunk_size_kb = 512
        self.current_part_index = 1
        self.base_path_used = ''
        self.add_newline = False
        
        # 异步写入器
        self._async_writer = AsyncLogWriter()
        
        # 分片回调
        self.on_new_part = None

        # 异步分片状态（避免主线程文件I/O阻塞）
        self._rollover_in_progress = False
        self._rollover_signaler = _RolloverSignaler()
        self._rollover_signaler.rolloverComplete.connect(self._on_rollover_complete)

        # 配置项（默认值）
        self.filename_template = 'C:/Logs/%Y-%M-%D_%h-%m-%s.log'
        self.prompt_filename = False
        self.append = True
        self.start_upon_connect = True
        self.raw = False
        self.midnight_rollover = True
        self.custom_connect = '[%Y%M%D_%h:%m:%s] connect'
        self.custom_disconnect = '[%Y%M%D_%h:%m:%s] disconnect'
        self.custom_each_line = '[%h:%m:%s]'
        self.only_custom_data = False

        # 线程锁
        self._lock = threading.Lock()
        
        self.load_from_qsettings()

    def set_parent(self, parent):
        """设置父窗口"""
        self.parent = parent

    # -- 设置加载/保存 --
    def load_from_qsettings(self):
        """从QSettings加载配置"""
        try:
            s = QSettings(QSettings.IniFormat, QSettings.UserScope, 'Gavin', 'Gavin_com')
            self.filename_template = s.value('logging/filename_template', self.filename_template)
            self.prompt_filename = s.value('logging/prompt_filename', self.prompt_filename, type=bool)
            self.append = s.value('logging/append', self.append, type=bool)
            self.start_upon_connect = s.value('logging/start_upon_connect', self.start_upon_connect, type=bool)
            self.raw = s.value('logging/raw', self.raw, type=bool)
            self.midnight_rollover = s.value('logging/midnight_rollover', self.midnight_rollover, type=bool)
            self.custom_connect = s.value('logging/custom_connect', self.custom_connect)
            self.custom_disconnect = s.value('logging/custom_disconnect', self.custom_disconnect)
            self.custom_each_line = s.value('logging/custom_each_line', self.custom_each_line)
            self.only_custom_data = s.value('logging/only_custom_data', self.only_custom_data, type=bool)
            self.add_newline = s.value('logging/add_newline', self.add_newline, type=bool)
            
            # 分片大小（KB）
            try:
                self.chunk_size_kb = s.value('logging/chunk_size_kb', self.chunk_size_kb, type=int)
            except Exception:
                val = s.value('logging/chunk_size_kb', self.chunk_size_kb)
                try:
                    self.chunk_size_kb = int(val)
                except Exception:
                    pass
                    
            logger.debug("日志配置已从QSettings加载")
        except Exception as e:
            logger.error(f"加载日志配置失败: {e}")

    def apply_settings(self, cfg: dict):
        """应用配置字典"""
        for k, v in cfg.items():
            setattr(self, k, v)

    # -- 宏展开 --
    @staticmethod
    def _twod(n):
        """格式化为两位数字"""
        return f"{n:02d}"

    @staticmethod
    def _sanitize_component(name: str) -> str:
        """
        清理文件名组件
        
        Args:
            name: 原始名称
            
        Returns:
            str: 清理后的安全名称
        """
        if not name:
            return 'UnknownPort'
        reserved = {
            'CON','PRN','AUX','NUL',
            'COM1','COM2','COM3','COM4','COM5','COM6','COM7','COM8','COM9',
            'LPT1','LPT2','LPT3','LPT4','LPT5','LPT6','LPT7','LPT8','LPT9'
        }
        n = name.strip()
        # 替换不安全字符
        n = n.replace(':','_').replace('\\','_').replace('/','_')
        n = n.rstrip('.')
        if n.upper() in reserved:
            n = f"Serial-{n}"
        return n

    def expand_macros(self, template: str, session: str) -> str:
        """
        展开模板中的宏
        
        Args:
            template: 模板字符串
            session: 会话名称
            
        Returns:
            str: 展开后的字符串
        """
        now = datetime.now()
        safe_port = self._sanitize_component(self.port_name or session or '')
        mapping = {
            '%Y': f"{now.year}",
            '%M': self._twod(now.month),
            '%D': self._twod(now.day),
            '%h': self._twod(now.hour),
            '%m': self._twod(now.minute),
            '%s': self._twod(now.second),
            '%H': safe_port,
            '%S': session or '',
        }
        out = template
        for k, v in mapping.items():
            out = out.replace(k, v)
        return out

    @staticmethod
    def _make_part_path(base_path: str, part_index: int) -> str:
        """生成分片文件路径"""
        root, ext = os.path.splitext(base_path)
        suffix = f"_part{part_index}"
        return f"{root}{suffix}{ext}"

    def _ensure_dir(self, path: str) -> bool:
        """确保目录存在"""
        dir_path = os.path.dirname(path)
        if not dir_path:
            return True
        try:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                logger.info(f"创建日志目录: {dir_path}")
            return True
        except Exception as e:
            logger.error(f"创建日志目录失败: {dir_path} ({e})")
            return False

    def _open_file(self, path: str):
        """
        打开日志文件
        
        Args:
            path: 文件路径
            
        Returns:
            bool: 是否成功打开
        """
        # 规范化路径
        path = os.path.normpath(path)
        self._ensure_dir(path)
        mode = 'ab' if self.raw else ('a' if self.append else 'w')
        opened_file = None
        opened_path = path

        try:
            logger.info(f"尝试打开日志文件: {path}")
            if self.raw:
                opened_file = open(path, mode)
            else:
                opened_file = open(path, mode, encoding='utf-8')
        except Exception as e:
            logger.error(f"主路径打开失败: {path} ({e})，准备回退")
            # 回退到安全目录
            try:
                base = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or os.path.expanduser('~')
            except Exception:
                base = os.path.expanduser('~')

            fallback_dir = os.path.join(base, 'SSCOMLogs', self.port_name or 'UnknownPort')
            fallback_path = os.path.join(fallback_dir, os.path.basename(path))
            fallback_path = os.path.normpath(fallback_path)

            if not self._ensure_dir(fallback_path):
                logger.error(f"无法创建回退目录: {os.path.dirname(fallback_path)}")
                self.is_logging = False
                return False

            try:
                logger.info(f"尝试打开回退日志文件: {fallback_path}")
                if self.raw:
                    opened_file = open(fallback_path, mode)
                else:
                    opened_file = open(fallback_path, mode, encoding='utf-8')
                opened_path = fallback_path
                logger.warning(f"日志路径不可用，已回退到: {fallback_path}")
            except Exception as e2:
                logger.error(f"日志文件打开失败: {fallback_path} ({e2})")
                self.is_logging = False
                return False

        with self._lock:
            self.file = opened_file
            self.is_logging = True
            self.last_date = datetime.now().date()

        self._async_writer.start()
        self._async_writer.set_file(opened_file)

        logger.info(f"日志文件已打开: {opened_path}")
        return True

    def _choose_filename_prompt(self, initial: str) -> str:
        """显示文件选择对话框"""
        try:
            if self.parent is None:
                return initial
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self.parent, '选择日志文件', initial, 
                'Log Files (*.log);;All Files (*)'
            )
            return path or initial
        except Exception as e:
            logger.error(f"显示文件选择对话框失败: {e}")
            return initial

    def on_connect(self, session_name: str, parent=None, port_name: str=None):
        """
        连接建立时的处理
        
        Args:
            session_name: 会话名称
            parent: 父窗口
            port_name: 端口名称
        """
        if parent is not None:
            self.parent = parent
        self.session_name = session_name
        self.port_name = port_name or session_name
        
        if not self.start_upon_connect:
            return
            
        # 计算日志文件名
        path = self.expand_macros(self.filename_template, session_name)
        if self.prompt_filename:
            path = self._choose_filename_prompt(path)
            
        ok = self._open_file(path)
        if ok:
            self.base_path_used = self.file.name
            self.current_part_index = 1
            # 写自定义连接行
            self._write_custom_line(self.custom_connect)

    def on_disconnect(self):
        """断开连接时的处理"""
        try:
            # 写自定义断开行
            if self.is_logging:
                self._write_custom_line(self.custom_disconnect)
        finally:
            # 停止异步写入
            self._async_writer.stop(timeout=3.0)
            
            # 关闭文件
            with self._lock:
                closed_name = getattr(self.file, 'name', 'unknown')
                self.file = None
                self.is_logging = False
                self.session_name = ''
                self.port_name = ''
            logger.info(f"日志文件已关闭: {closed_name}")

    def _rotate_if_needed(self):
        """检查是否需要按日期切换日志文件"""
        if not self.is_logging:
            return
        if not self.midnight_rollover:
            return
            
        now_date = datetime.now().date()
        if self.last_date is None:
            self.last_date = now_date
            return
            
        if now_date != self.last_date and ('%D' in self.filename_template or 
                                            '%Y' in self.filename_template or 
                                            '%M' in self.filename_template):
            # 重新打开新日志文件
            logger.info("日期变更，切换日志文件")
            try:
                path = self.expand_macros(self.filename_template, self.session_name)
                if self._open_file(path):
                    self.base_path_used = self.file.name
                    self.current_part_index = 1
            except Exception as e:
                logger.error(f"切换日志文件失败: {e}")

    def _size_rollover_if_needed(self):
        """检查是否需要按大小分片（异步执行，不阻塞主线程）"""
        if not self.is_logging or self._rollover_in_progress:
            return
        try:
            limit_bytes = int(self.chunk_size_kb) * 1024
            if limit_bytes <= 0:
                return
        except Exception:
            return

        try:
            with self._lock:
                cur_file = self.file
            if cur_file is None:
                return
            current_size = os.path.getsize(cur_file.name)
            if current_size >= limit_bytes:
                logger.info(f"日志文件大小超过限制 ({current_size} >= {limit_bytes})，将在后台创建分片")
                self._rollover_in_progress = True
                self.current_part_index += 1
                new_path = self._make_part_path(self.base_path_used, self.current_part_index)
                # 在后台线程中执行文件创建，避免主线程文件I/O卡顿
                t = threading.Thread(
                    target=self._do_size_rollover_bg,
                    args=(new_path, self.current_part_index, self.base_path_used),
                    daemon=True
                )
                t.start()
        except Exception as e:
            logger.error(f"检查日志分片失败: {e}")
            self._rollover_in_progress = False

    def _do_size_rollover_bg(self, new_path: str, part_index: int, base_path: str):
        """后台线程：创建新分片文件并切换，避免主线程文件I/O阻塞"""
        new_file = None
        actual_path = new_path
        try:
            new_path_norm = os.path.normpath(new_path)
            dir_path = os.path.dirname(new_path_norm)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            mode = 'ab' if self.raw else ('a' if self.append else 'w')
            try:
                if self.raw:
                    new_file = open(new_path_norm, mode)
                else:
                    new_file = open(new_path_norm, mode, encoding='utf-8')
                actual_path = new_path_norm
            except Exception as e:
                logger.error(f"分片文件创建失败: {new_path_norm} ({e})，尝试回退路径")
                try:
                    from PySide6.QtCore import QStandardPaths
                    base_dir = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or os.path.expanduser('~')
                except Exception:
                    base_dir = os.path.expanduser('~')
                fallback_dir = os.path.join(base_dir, 'SSCOMLogs', self.port_name or 'UnknownPort')
                fallback_path = os.path.normpath(os.path.join(fallback_dir, os.path.basename(new_path_norm)))
                os.makedirs(os.path.dirname(fallback_path), exist_ok=True)
                if self.raw:
                    new_file = open(fallback_path, mode)
                else:
                    new_file = open(fallback_path, mode, encoding='utf-8')
                actual_path = fallback_path
                logger.warning(f"分片使用回退路径: {fallback_path}")

            # 通过异步写入器队列切换文件（线程安全）
            self._async_writer.set_file(new_file)
            # 通知主线程分片完成（通过Qt信号，自动序列化到主线程）
            self._rollover_signaler.rolloverComplete.emit(new_file, actual_path, part_index, base_path)
        except Exception as e:
            logger.error(f"后台日志分片失败: {e}")
            self._rollover_in_progress = False

    def _on_rollover_complete(self, new_file, new_path: str, part_index: int, base_path: str):
        """分片完成回调（由信号在主线程中执行）"""
        self._rollover_in_progress = False
        with self._lock:
            if not self.is_logging:
                return
            self.file = new_file
            self.current_part_index = part_index
        # 写入分片起始标记行
        self._write_custom_line('[%Y%M%D_%h:%m:%s] new part')
        # 通知外部（如UI刷新历史记录）
        try:
            if callable(self.on_new_part):
                self.on_new_part(new_path, part_index, base_path)
        except Exception as e:
            logger.error(f"调用分片回调失败: {e}")

    def _format_each_prefix(self) -> str:
        """格式化每行前缀"""
        return self.expand_macros(self.custom_each_line, self.session_name)

    def _write_custom_line(self, text: str):
        """写入自定义行"""
        if not self.is_logging:
            return
        try:
            line = self.expand_macros(text, self.session_name)
            # 仅在需要且当前文本未以换行结尾时追加换行
            if self.add_newline and not (line.endswith('\n') or line.endswith('\r')):
                suffix = '\r\n'
            else:
                suffix = ''
                
            if self.raw:
                self._async_writer.write((line + suffix).encode('utf-8'))
            else:
                self._async_writer.write(line + suffix)
                
        except Exception as e:
            logger.error(f"写入自定义行失败: {e}")

    def log_rx(self, data: bytes):
        """
        记录接收数据
        
        Args:
            data: 接收到的字节数据
        """
        if not self.is_logging:
            return
            
        self._rotate_if_needed()
        
        if self.only_custom_data:
            self._write_custom_line(self._format_each_prefix())
            self._size_rollover_if_needed()
            return
            
        try:
            if self.raw:
                self._async_writer.write(data)
            else:
                prefix = self._format_each_prefix()
                try:
                    text = data.decode('utf-8', 'ignore')
                except Exception:
                    text = ' '.join(f"{x:02X}" for x in data)
                    
                # 仅当尾部非CR/LF时追加换行
                if self.add_newline and not (text.endswith('\n') or text.endswith('\r')):
                    suffix = '\r\n'
                else:
                    suffix = ''
                    
                self._async_writer.write(f"{prefix} {text}{suffix}")
                
        except Exception as e:
            logger.error(f"记录RX数据失败: {e}")
            
        self._size_rollover_if_needed()

    def log_tx(self, data: bytes):
        """
        记录发送数据
        
        Args:
            data: 发送的字节数据
        """
        if not self.is_logging:
            return
            
        self._rotate_if_needed()
        
        if self.only_custom_data:
            self._write_custom_line(self._format_each_prefix())
            self._size_rollover_if_needed()
            return
            
        try:
            if self.raw:
                self._async_writer.write(data)
            else:
                prefix = self._format_each_prefix()
                try:
                    text = data.decode('utf-8', 'ignore')
                except Exception:
                    text = ' '.join(f"{x:02X}" for x in data)
                    
                # 仅当尾部非CR/LF时追加换行
                if self.add_newline and not (text.endswith('\n') or text.endswith('\r')):
                    suffix = '\r\n'
                else:
                    suffix = ''
                    
                self._async_writer.write(f"{prefix} TX {text}{suffix}")
                
        except Exception as e:
            logger.error(f"记录TX数据失败: {e}")
            
        self._size_rollover_if_needed()

    def get_status(self) -> dict:
        """
        获取日志状态
        
        Returns:
            dict: 状态信息
        """
        return {
            'is_logging': self.is_logging,
            'session_name': self.session_name,
            'port_name': self.port_name,
            'file_path': getattr(self.file, 'name', None),
            'current_part': self.current_part_index,
            'last_date': self.last_date.isoformat() if self.last_date else None
        }
