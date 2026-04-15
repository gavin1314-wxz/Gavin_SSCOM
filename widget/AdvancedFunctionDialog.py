from PySide6 import QtCore, QtWidgets
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QListWidget, 
                               QStackedWidget, QListWidgetItem, QWidget, QLabel,
                               QGroupBox, QCheckBox, QRadioButton, QLineEdit, 
                               QPushButton, QSpinBox, QFormLayout)
from PySide6.QtCore import QSettings, QStandardPaths, Signal
from .AutoReplyDialog import AutoReplyDialog
import logging

# 配置日志记录器
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class MonitorConfigWidget(QWidget):
    """监控配置功能页面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 文件名模板
        file_group = QGroupBox('日志文件名')
        fg_layout = QHBoxLayout(file_group)
        self.ed_filename = QLineEdit()
        default_base = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or ''
        self.ed_filename.setPlaceholderText(f'例如: {default_base}/SSCOMLogs/%H/%Y-%M-%D_%h-%m-%s.log')
        self.bt_browse = QPushButton('...')
        self.bt_browse.setFixedWidth(40)
        self.bt_browse.clicked.connect(self.on_browse)
        fg_layout.addWidget(self.ed_filename)
        fg_layout.addWidget(self.bt_browse)
        layout.addWidget(file_group)

        # 选项
        opt_group = QGroupBox('选项')
        og = QVBoxLayout(opt_group)
        self.cb_prompt = QCheckBox('打开时提示选择文件')
        self.cb_start_on_connect = QCheckBox('连接后自动开始日志')
        self.cb_raw = QCheckBox('原始二进制日志')
        self.cb_midnight = QCheckBox('午夜自动新建日志（需使用 %D）')
        self.cb_add_newline = QCheckBox('行末追加换行')
        
        # 覆盖/追加
        hor = QHBoxLayout()
        self.rb_overwrite = QRadioButton('覆盖写入')
        self.rb_append = QRadioButton('追加写入')
        self.rb_append.setChecked(True)
        hor.addWidget(self.rb_overwrite)
        hor.addWidget(self.rb_append)
        
        # 分片大小（K）
        hl_chunk = QHBoxLayout()
        hl_chunk.addWidget(QLabel('分片大小（K）：'))
        self.sb_chunk_size = QSpinBox()
        self.sb_chunk_size.setRange(1, 1024*1024)
        self.sb_chunk_size.setSingleStep(64)
        self.sb_chunk_size.setValue(512)
        self.sb_chunk_size.setToolTip('当日志文件超过该大小时，自动创建新的日志文件')
        hl_chunk.addWidget(self.sb_chunk_size)
        hl_chunk.addStretch(1)
        
        og.addWidget(self.cb_prompt)
        og.addLayout(hor)
        og.addWidget(self.cb_start_on_connect)
        og.addWidget(self.cb_raw)
        og.addWidget(self.cb_midnight)
        og.addWidget(self.cb_add_newline)
        og.addLayout(hl_chunk)
        layout.addWidget(opt_group)

        # 自定义日志数据
        custom_group = QGroupBox('自定义日志内容')
        cg = QVBoxLayout(custom_group)
        hl1 = QHBoxLayout()
        hl1.addWidget(QLabel('连接时写入:'))
        self.ed_on_connect = QLineEdit('[%Y%M%D_%h:%m:%s] connect')
        hl1.addWidget(self.ed_on_connect)
        hl2 = QHBoxLayout()
        hl2.addWidget(QLabel('断开时写入:'))
        self.ed_on_disconnect = QLineEdit('[%Y%M%D_%h:%m:%s] disconnect')
        hl2.addWidget(self.ed_on_disconnect)
        hl3 = QHBoxLayout()
        hl3.addWidget(QLabel('每行前缀:'))
        self.ed_each_line = QLineEdit('[%h:%m:%s]')
        hl3.addWidget(self.ed_each_line)
        self.cb_only_custom = QCheckBox('仅写入自定义内容')
        cg.addLayout(hl1)
        cg.addLayout(hl2)
        cg.addLayout(hl3)
        cg.addWidget(self.cb_only_custom)
        layout.addWidget(custom_group)

        # 宏帮助
        help_group = QGroupBox('宏说明')
        hg = QVBoxLayout(help_group)
        tips = QLabel('宏: %Y 年, %M 月(2位), %D 日(2位), %h 时(2位), %m 分(2位), %s 秒(2位), %H 当前串口名(自动文件名安全，如 COM5→port_COM5), %S 会话名(如 COM3@115200)')
        tips.setWordWrap(True)
        hg.addWidget(tips)
        layout.addWidget(help_group)
        
        layout.addStretch()
    
    def on_browse(self):
        """浏览文件对话框"""
        default_dir = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or QtCore.QDir.homePath()
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, '选择日志文件', f'{default_dir}/SSCOMLogs/log.txt', 'Log Files (*.log);;All Files (*)')
        if path:
            self.ed_filename.setText(path)
    
    def load_from_settings(self):
        """从设置加载配置"""
        s = QSettings(QSettings.IniFormat, QSettings.UserScope, 'Gavin', 'Gavin_com')
        default_template = f"{QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)}/SSCOMLogs/%H/%Y-%M-%D_%h-%m-%s.log"
        self.ed_filename.setText(s.value('logging/filename_template', default_template))
        self.cb_prompt.setChecked(s.value('logging/prompt_filename', False, type=bool))
        append = s.value('logging/append', True, type=bool)
        self.rb_append.setChecked(append)
        self.rb_overwrite.setChecked(not append)
        self.cb_start_on_connect.setChecked(s.value('logging/start_upon_connect', True, type=bool))
        self.cb_raw.setChecked(s.value('logging/raw', False, type=bool))
        self.cb_midnight.setChecked(s.value('logging/midnight_rollover', True, type=bool))
        self.cb_add_newline.setChecked(s.value('logging/add_newline', False, type=bool))
        self.ed_on_connect.setText(s.value('logging/custom_connect', '[%Y%M%D_%h:%m:%s] connect'))
        self.ed_on_disconnect.setText(s.value('logging/custom_disconnect', '[%Y%M%D_%h:%m:%s] disconnect'))
        self.ed_each_line.setText(s.value('logging/custom_each_line', '[%h:%m:%s]'))
        self.cb_only_custom.setChecked(s.value('logging/only_custom_data', False, type=bool))
        try:
            self.sb_chunk_size.setValue(s.value('logging/chunk_size_kb', 512, type=int))
        except Exception:
            val = s.value('logging/chunk_size_kb', 512)
            try:
                self.sb_chunk_size.setValue(int(val))
            except Exception:
                self.sb_chunk_size.setValue(512)
    
    def save_to_settings(self):
        """保存配置到设置"""
        s = QSettings(QSettings.IniFormat, QSettings.UserScope, 'Gavin', 'Gavin_com')
        s.setValue('logging/filename_template', self.ed_filename.text().strip())
        s.setValue('logging/prompt_filename', self.cb_prompt.isChecked())
        s.setValue('logging/append', self.rb_append.isChecked())
        s.setValue('logging/start_upon_connect', self.cb_start_on_connect.isChecked())
        s.setValue('logging/raw', self.cb_raw.isChecked())
        s.setValue('logging/midnight_rollover', self.cb_midnight.isChecked())
        s.setValue('logging/add_newline', self.cb_add_newline.isChecked())
        s.setValue('logging/custom_connect', self.ed_on_connect.text())
        s.setValue('logging/custom_disconnect', self.ed_on_disconnect.text())
        s.setValue('logging/custom_each_line', self.ed_each_line.text())
        s.setValue('logging/only_custom_data', self.cb_only_custom.isChecked())
        s.setValue('logging/chunk_size_kb', self.sb_chunk_size.value())


class PlaceholderWidget(QWidget):
    """占位符功能页面"""
    
    def __init__(self, title="功能开发中", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addStretch()
        
        label = QLabel(title)
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setStyleSheet("font-size: 16px; color: #666; padding: 20px;")
        layout.addWidget(label)
        
        layout.addStretch()


class SystemSettingsWidget(QWidget):
    """系统设置页面：配置导出/导入 + 自动重连超时"""

    exportRequested = Signal()
    importRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ---- 自动重连设置 ----
        reconnect_group = QGroupBox('断线自动重连')
        rg_layout = QVBoxLayout(reconnect_group)
        rg_layout.setSpacing(8)

        rg_desc = QLabel(
            '串口意外断开后，程序将每隔 1 秒自动检测并尝试重新连接，\n'
            '超时后停止重连并恢复到"打开串口"状态（不弹出错误提示）。'
        )
        rg_desc.setWordWrap(True)
        rg_desc.setStyleSheet('color: #555;')
        rg_layout.addWidget(rg_desc)

        form = QFormLayout()
        form.setSpacing(6)
        self.sb_reconnect_timeout = QSpinBox()
        self.sb_reconnect_timeout.setRange(5, 3600)
        self.sb_reconnect_timeout.setSingleStep(10)
        self.sb_reconnect_timeout.setValue(60)
        self.sb_reconnect_timeout.setSuffix(' 秒')
        self.sb_reconnect_timeout.setToolTip('断线后自动重连的最大等待时间，默认 60 秒')
        form.addRow('重连超时时长：', self.sb_reconnect_timeout)
        rg_layout.addLayout(form)
        layout.addWidget(reconnect_group)

        # ---- 配置备份/恢复 ----
        backup_group = QGroupBox('配置备份与恢复')
        g_layout = QVBoxLayout(backup_group)
        g_layout.setSpacing(8)

        desc = QLabel(
            '将所有配置（串口参数、发送设置、自定义按钮、过滤器等）保存为 JSON 文件，\n'
            '可在重装系统或迁移设备后一键恢复。'
        )
        desc.setWordWrap(True)
        desc.setStyleSheet('color: #555;')
        g_layout.addWidget(desc)

        btn_row = QHBoxLayout()
        self.bt_export = QPushButton('导出配置…')
        self.bt_export.setToolTip('将所有配置导出为 JSON 文件')
        self.bt_import = QPushButton('导入配置…')
        self.bt_import.setToolTip('从 JSON 文件恢复所有配置')
        btn_row.addWidget(self.bt_export)
        btn_row.addWidget(self.bt_import)
        btn_row.addStretch()
        g_layout.addLayout(btn_row)

        layout.addWidget(backup_group)
        layout.addStretch()

        self.bt_export.clicked.connect(self.exportRequested)
        self.bt_import.clicked.connect(self.importRequested)

    def load_settings(self):
        s = QSettings(QSettings.IniFormat, QSettings.UserScope, 'Gavin', 'Gavin_com')
        self.sb_reconnect_timeout.setValue(s.value('system/reconnect_timeout_sec', 60, int))

    def save_settings(self):
        s = QSettings(QSettings.IniFormat, QSettings.UserScope, 'Gavin', 'Gavin_com')
        s.setValue('system/reconnect_timeout_sec', self.sb_reconnect_timeout.value())
        s.sync()


class AdvancedFunctionDialog(QDialog):
    """高级功能对话框：左侧功能列表 + 右侧功能内容"""

    exportConfigRequested = Signal()
    importConfigRequested = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('高级功能')
        self.resize(800, 600)
        self.init_ui()
        self.setup_functions()
    
    def init_ui(self):
        """初始化UI布局"""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 左侧功能列表
        self.function_list = QListWidget()
        self.function_list.setMaximumWidth(200)
        self.function_list.setMinimumWidth(150)
        self.function_list.currentRowChanged.connect(self.on_function_changed)
        
        # 右侧功能内容区域
        self.content_stack = QStackedWidget()
        
        # 底部按钮区域
        button_layout = QVBoxLayout()
        button_layout.addWidget(self.content_stack)
        
        # 确认/取消/应用按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.bt_ok = QPushButton('确定')
        self.bt_cancel = QPushButton('取消')
        self.bt_apply = QPushButton('应用')
        self.bt_ok.clicked.connect(self.accept)
        self.bt_cancel.clicked.connect(self.reject)
        self.bt_apply.clicked.connect(self.apply_settings)
        btn_layout.addWidget(self.bt_ok)
        btn_layout.addWidget(self.bt_cancel)
        btn_layout.addWidget(self.bt_apply)
        
        button_layout.addLayout(btn_layout)
        
        # 添加到主布局
        main_layout.addWidget(self.function_list)
        main_layout.addLayout(button_layout)
    
    def setup_functions(self):
        """设置功能列表和对应的内容页面"""
        # 监控功能
        monitor_item = QListWidgetItem("日志监控")
        self.function_list.addItem(monitor_item)
        self.monitor_widget = MonitorConfigWidget()
        self.content_stack.addWidget(self.monitor_widget)
        
        # 自动应答功能
        auto_reply_item = QListWidgetItem("自动应答")
        self.function_list.addItem(auto_reply_item)
        self.auto_reply_widget = AutoReplyDialog()
        self.content_stack.addWidget(self.auto_reply_widget)
        
        # 其他功能占位符
        placeholder_functions = [
            "数据分析",
            "自动化脚本",
            "协议解析",
            "性能监控",
        ]

        for func_name in placeholder_functions:
            item = QListWidgetItem(func_name)
            self.function_list.addItem(item)
            placeholder = PlaceholderWidget(f"{func_name}\n功能开发中...")
            self.content_stack.addWidget(placeholder)

        # 系统设置页
        sys_item = QListWidgetItem("系统设置")
        self.function_list.addItem(sys_item)
        self.system_settings_widget = SystemSettingsWidget()
        self.system_settings_widget.exportRequested.connect(self.exportConfigRequested)
        self.system_settings_widget.importRequested.connect(self.importConfigRequested)
        self.content_stack.addWidget(self.system_settings_widget)
        
        # 默认选择第一个功能
        self.function_list.setCurrentRow(0)
    
    def on_function_changed(self, index):
        """功能列表选择改变时切换内容页面"""
        self.content_stack.setCurrentIndex(index)
    
    def accept(self):
        """确定按钮点击处理"""
        logger.info("AdvancedFunctionDialog: 点击确定按钮")
        # 保存监控配置
        if hasattr(self, 'monitor_widget'):
            logger.info("保存监控配置")
            self.monitor_widget.save_to_settings()
        # 保存自动应答配置
        if hasattr(self, 'auto_reply_widget'):
            logger.info("保存自动应答配置")
            self.auto_reply_widget.save_settings()
        # 保存系统设置
        if hasattr(self, 'system_settings_widget'):
            self.system_settings_widget.save_settings()
        logger.info("AdvancedFunctionDialog: 配置保存完成，关闭对话框")
        super().accept()
    
    def apply_settings(self):
        """应用按钮点击处理"""
        logger.info("AdvancedFunctionDialog: 点击应用按钮")
        # 保存监控配置
        if hasattr(self, 'monitor_widget'):
            logger.info("应用监控配置")
            self.monitor_widget.save_to_settings()
        # 保存自动应答配置
        if hasattr(self, 'auto_reply_widget'):
            logger.info("应用自动应答配置")
            self.auto_reply_widget.apply_settings()
        # 保存系统设置
        if hasattr(self, 'system_settings_widget'):
            self.system_settings_widget.save_settings()
        logger.info("AdvancedFunctionDialog: 配置应用完成")
    
    def load_settings(self):
        """加载设置"""
        logger.info("AdvancedFunctionDialog: 开始加载设置")
        if hasattr(self, 'monitor_widget'):
            logger.info("加载监控配置")
            self.monitor_widget.load_from_settings()
        if hasattr(self, 'auto_reply_widget'):
            logger.info("加载自动应答配置")
            self.auto_reply_widget.load_settings()
        if hasattr(self, 'system_settings_widget'):
            self.system_settings_widget.load_settings()
        logger.info("AdvancedFunctionDialog: 设置加载完成")