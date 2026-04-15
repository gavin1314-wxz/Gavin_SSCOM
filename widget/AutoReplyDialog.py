from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QPushButton, QComboBox, QLineEdit, 
                             QCheckBox, QHeaderView, QMessageBox, QLabel, QGroupBox)
from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtGui import QFont
import json
import logging

# 配置日志记录器
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class AutoReplyDialog(QDialog):
    """自动应答配置对话框"""
    
    # 信号：配置发生变化
    config_changed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        logger.info("初始化AutoReplyDialog")
        self.setWindowTitle("自动应答配置")
        self.setModal(True)
        self.resize(800, 600)
        
        # 自动应答规则列表
        self.reply_rules = []
        
        # 初始化UI
        self.setup_ui()
        
        # 加载设置
        logger.info("开始加载自动应答配置")
        self.load_settings()
        logger.info("AutoReplyDialog初始化完成")
        
    def setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout(self)
        
        # 说明标签
        info_label = QLabel("配置自动应答规则：当接收到匹配的数据时，自动发送对应的应答数据")
        info_label.setStyleSheet("color: #666; margin: 5px;")
        layout.addWidget(info_label)
        
        # 表格区域
        table_group = QGroupBox("应答规则配置")
        table_layout = QVBoxLayout(table_group)
        
        # 创建表格
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "匹配类型", "匹配内容", "应答类型", "应答内容", "启用"
        ])
        
        # 设置表格选择行为和样式
        self.table.setSelectionBehavior(QTableWidget.SelectRows)  # 选择整行
        self.table.setSelectionMode(QTableWidget.SingleSelection)  # 单选模式
        self.table.setAlternatingRowColors(True)  # 交替行颜色
        
        # 设置表格样式，增强选中效果
        self.table.setStyleSheet("""
            QTableWidget {
                gridline-color: #d0d0d0;
                background-color: white;
                alternate-background-color: #f5f5f5;
            }
            QTableWidget::item:selected {
                background-color: #3daee9;
                color: white;
            }
            QTableWidget::item:hover {
                background-color: #e3f2fd;
            }
            QTableWidget QHeaderView::section {
                background-color: #f0f0f0;
                padding: 4px;
                border: 1px solid #d0d0d0;
                font-weight: bold;
            }
        """)
        
        # 设置表格列宽
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        
        self.table.setColumnWidth(0, 100)  # 匹配类型
        self.table.setColumnWidth(2, 100)  # 应答类型
        self.table.setColumnWidth(4, 60)   # 启用
        
        table_layout.addWidget(self.table)
        layout.addWidget(table_group)
        
        # 操作按钮区域
        button_layout = QHBoxLayout()
        
        self.add_btn = QPushButton("添加规则")
        self.delete_btn = QPushButton("删除规则")
        self.move_up_btn = QPushButton("上移")
        self.move_down_btn = QPushButton("下移")
        self.clear_btn = QPushButton("清空所有")
        
        button_layout.addWidget(self.add_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addWidget(self.move_up_btn)
        button_layout.addWidget(self.move_down_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # 启用自动应答复选框
        self.enable_checkbox = QCheckBox("启用自动应答")
        self.enable_checkbox.setChecked(True)
        layout.addWidget(self.enable_checkbox)
        
        # 连接信号
        self.add_btn.clicked.connect(self.add_rule)
        self.delete_btn.clicked.connect(self.delete_rule)
        self.move_up_btn.clicked.connect(self.move_up)
        self.move_down_btn.clicked.connect(self.move_down)
        self.clear_btn.clicked.connect(self.clear_all)
        
    def add_rule(self):
        """添加新规则"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # 匹配类型下拉框
        match_type_combo = QComboBox()
        match_type_combo.addItems(["字符串", "HEX"])
        match_type_combo.currentTextChanged.connect(self.on_config_changed)
        self.table.setCellWidget(row, 0, match_type_combo)
        
        # 匹配内容输入框
        match_content = QLineEdit()
        match_content.setPlaceholderText("输入要匹配的内容...")
        match_content.textChanged.connect(self.on_config_changed)
        self.table.setCellWidget(row, 1, match_content)
        
        # 应答类型下拉框
        reply_type_combo = QComboBox()
        reply_type_combo.addItems(["字符串", "HEX"])
        reply_type_combo.currentTextChanged.connect(self.on_config_changed)
        self.table.setCellWidget(row, 2, reply_type_combo)
        
        # 应答内容输入框
        reply_content = QLineEdit()
        reply_content.setPlaceholderText("输入应答内容...")
        reply_content.textChanged.connect(self.on_config_changed)
        self.table.setCellWidget(row, 3, reply_content)
        
        # 启用复选框
        enabled_checkbox = QCheckBox()
        enabled_checkbox.setChecked(True)
        enabled_checkbox.stateChanged.connect(self.on_config_changed)
        self.table.setCellWidget(row, 4, enabled_checkbox)
        
        self.on_config_changed()
        
    def delete_rule(self):
        """删除选中的规则"""
        current_row = self.table.currentRow()
        if current_row >= 0:
            self.table.removeRow(current_row)
            self.on_config_changed()
        else:
            QMessageBox.information(self, "提示", "请先选择要删除的规则")
            
    def move_up(self):
        """上移规则"""
        current_row = self.table.currentRow()
        if current_row > 0:
            self.swap_rows(current_row, current_row - 1)
            self.table.setCurrentCell(current_row - 1, 0)
            self.on_config_changed()
            
    def move_down(self):
        """下移规则"""
        current_row = self.table.currentRow()
        if current_row >= 0 and current_row < self.table.rowCount() - 1:
            self.swap_rows(current_row, current_row + 1)
            self.table.setCurrentCell(current_row + 1, 0)
            self.on_config_changed()
            
    def swap_rows(self, row1, row2):
        """交换两行的内容"""
        for col in range(self.table.columnCount()):
            widget1 = self.table.cellWidget(row1, col)
            widget2 = self.table.cellWidget(row2, col)
            
            # 临时移除控件
            self.table.removeCellWidget(row1, col)
            self.table.removeCellWidget(row2, col)
            
            # 交换控件
            self.table.setCellWidget(row1, col, widget2)
            self.table.setCellWidget(row2, col, widget1)
            
    def clear_all(self):
        """清空所有规则"""
        reply = QMessageBox.question(self, "确认", "确定要清空所有规则吗？", 
                                   QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.table.setRowCount(0)
            self.on_config_changed()
            
    def get_rules(self):
        """获取当前配置的所有规则"""
        rules = []
        for row in range(self.table.rowCount()):
            match_type_combo = self.table.cellWidget(row, 0)
            match_content = self.table.cellWidget(row, 1)
            reply_type_combo = self.table.cellWidget(row, 2)
            reply_content = self.table.cellWidget(row, 3)
            enabled_checkbox = self.table.cellWidget(row, 4)
            
            if (match_type_combo and match_content and reply_type_combo and 
                reply_content and enabled_checkbox):
                
                rule = {
                    'match_type': match_type_combo.currentText(),
                    'match_content': match_content.text(),
                    'reply_type': reply_type_combo.currentText(),
                    'reply_content': reply_content.text(),
                    'enabled': enabled_checkbox.isChecked()
                }
                rules.append(rule)
                
        return rules
        
    def set_rules(self, rules):
        """设置规则列表"""
        self.table.setRowCount(0)
        for rule in rules:
            self.add_rule()
            row = self.table.rowCount() - 1
            
            # 设置匹配类型
            match_type_combo = self.table.cellWidget(row, 0)
            if match_type_combo:
                match_type_combo.setCurrentText(rule.get('match_type', '字符串'))
                
            # 设置匹配内容
            match_content = self.table.cellWidget(row, 1)
            if match_content:
                match_content.setText(rule.get('match_content', ''))
                
            # 设置应答类型
            reply_type_combo = self.table.cellWidget(row, 2)
            if reply_type_combo:
                reply_type_combo.setCurrentText(rule.get('reply_type', '字符串'))
                
            # 设置应答内容
            reply_content = self.table.cellWidget(row, 3)
            if reply_content:
                reply_content.setText(rule.get('reply_content', ''))
                
            # 设置启用状态
            enabled_checkbox = self.table.cellWidget(row, 4)
            if enabled_checkbox:
                enabled_checkbox.setChecked(rule.get('enabled', True))
                
    def on_config_changed(self):
        """配置发生变化时的处理"""
        self.config_changed.emit()
        
    def save_settings(self):
        """保存设置到QSettings和AutoReplyEngine"""
        logger.info("开始保存自动应答配置")
        from .AutoReplyEngine import AutoReplyRule
        
        # 保存到QSettings - 使用与main.py相同的格式
        settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "Gavin", "Gavin_com")
        rules = self.get_rules()
        enabled = self.enable_checkbox.isChecked()
        
        logger.info(f"准备保存 {len(rules)} 条规则，启用状态: {enabled}")
        for i, rule in enumerate(rules):
            logger.debug(f"规则 {i+1}: {rule}")
        
        settings.setValue("auto_reply/rules", json.dumps(rules))
        settings.setValue("auto_reply/enabled", enabled)
        settings.sync()  # 确保立即写入
        logger.info("配置已保存到QSettings")
        
        # 同步到全局AutoReplyEngine
        try:
            # 尝试多种方式获取auto_reply_engine实例
            import sys
            import __main__
            
            engine_instance = None
            
            # 方法1: 尝试从__main__模块获取
            if hasattr(__main__, 'auto_reply_engine'):
                engine_instance = __main__.auto_reply_engine
                logger.info(f"通过__main__模块找到auto_reply_engine实例: {engine_instance}")
            
            # 方法2: 尝试从sys.modules['__main__']获取
            elif '__main__' in sys.modules and hasattr(sys.modules['__main__'], 'auto_reply_engine'):
                engine_instance = sys.modules['__main__'].auto_reply_engine
                logger.info(f"通过sys.modules['__main__']找到auto_reply_engine实例: {engine_instance}")
            
            # 方法3: 尝试从globals()获取（如果在同一个模块中）
            elif 'auto_reply_engine' in globals():
                engine_instance = globals()['auto_reply_engine']
                logger.info(f"通过globals()找到auto_reply_engine实例: {engine_instance}")
            
            # 方法4: 尝试从sys.modules['main']获取（原方法）
            elif 'main' in sys.modules and hasattr(sys.modules['main'], 'auto_reply_engine'):
                engine_instance = sys.modules['main'].auto_reply_engine
                logger.info(f"通过sys.modules['main']找到auto_reply_engine实例: {engine_instance}")
            
            if engine_instance:
                logger.info(f"当前引擎规则数量: {len(engine_instance.rules)}")
                logger.info(f"当前引擎启用状态: {engine_instance.enabled}")
                
                engine_rules = []
                for rule_dict in rules:
                    engine_rule = AutoReplyRule(
                        match_type=rule_dict['match_type'],
                        match_content=rule_dict['match_content'],
                        reply_type=rule_dict['reply_type'],
                        reply_content=rule_dict['reply_content'],
                        enabled=rule_dict['enabled']
                    )
                    engine_rules.append(engine_rule)
                
                logger.info(f"准备设置 {len(engine_rules)} 条新规则到引擎")
                engine_instance.set_rules(engine_rules)
                engine_instance.set_enabled(enabled)
                logger.info(f"成功同步 {len(engine_rules)} 条规则到AutoReplyEngine，启用状态: {enabled}")
                
                # 验证设置是否生效
                logger.info(f"设置后引擎规则数量: {len(engine_instance.rules)}")
                logger.info(f"设置后引擎启用状态: {engine_instance.enabled}")
            else:
                logger.warning("无法找到auto_reply_engine实例，尝试所有方法都失败")
        except Exception as e:
            logger.error(f"同步自动应答规则到引擎失败: {e}")
            # 尝试备用方法：通过父窗口获取
            try:
                parent_window = self.parent()
                while parent_window and not hasattr(parent_window, 'auto_reply_engine'):
                    parent_window = parent_window.parent()
                
                if parent_window and hasattr(parent_window, 'auto_reply_engine'):
                    engine_rules = []
                    for rule_dict in rules:
                        engine_rule = AutoReplyRule(
                            match_type=rule_dict['match_type'],
                            match_content=rule_dict['match_content'],
                            reply_type=rule_dict['reply_type'],
                            reply_content=rule_dict['reply_content'],
                            enabled=rule_dict['enabled']
                        )
                        engine_rules.append(engine_rule)
                    parent_window.auto_reply_engine.set_rules(engine_rules)
                    parent_window.auto_reply_engine.set_enabled(enabled)
                    logger.info(f"通过父窗口成功同步 {len(engine_rules)} 条规则到AutoReplyEngine")
                else:
                    logger.error("无法找到AutoReplyEngine实例")
            except Exception as e2:
                logger.error(f"备用同步方法也失败: {e2}")
                print(f"同步自动应答规则到引擎失败: {e}, 备用方法: {e2}")
        
        logger.info("自动应答配置保存完成")
        
    def load_settings(self):
        """从QSettings加载设置"""
        logger.info("开始从QSettings加载自动应答配置")
        # 使用与main.py相同的格式
        settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "Gavin", "Gavin_com")
        rules_json = settings.value("auto_reply/rules", "[]")
        enabled = settings.value("auto_reply/enabled", True, type=bool)
        
        logger.info(f"从QSettings读取到规则JSON: {rules_json}")
        logger.info(f"从QSettings读取到启用状态: {enabled}")
        
        try:
            rules = json.loads(rules_json)
            logger.info(f"成功解析 {len(rules)} 条规则")
            for i, rule in enumerate(rules):
                logger.debug(f"加载规则 {i+1}: {rule}")
            self.set_rules(rules)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"解析规则JSON失败: {e}，添加示例规则")
            # 如果加载失败，添加一个示例规则
            self.add_rule()
            
        self.enable_checkbox.setChecked(enabled)
        logger.info(f"自动应答配置加载完成，启用状态设置为: {enabled}")
            
    def apply_settings(self):
        """应用设置"""
        logger.info("开始应用自动应答设置")
        if self.validate_rules():
            logger.info("规则验证通过，开始保存配置")
            self.save_settings()
            self.config_changed.emit()
            logger.info("自动应答设置应用完成")
        else:
            logger.warning("规则验证失败，取消应用设置")
            
    def validate_rules(self):
        """验证规则的有效性"""
        rules = self.get_rules()
        for i, rule in enumerate(rules):
            if not rule['match_content'].strip():
                QMessageBox.warning(self, "警告", f"第{i+1}行的匹配内容不能为空")
                return False
            if not rule['reply_content'].strip():
                QMessageBox.warning(self, "警告", f"第{i+1}行的应答内容不能为空")
                return False
                
            # 验证HEX格式
            if rule['match_type'] == 'HEX':
                try:
                    bytes.fromhex(rule['match_content'].replace(' ', ''))
                except ValueError:
                    QMessageBox.warning(self, "警告", f"第{i+1}行的匹配内容HEX格式无效")
                    return False
                    
            if rule['reply_type'] == 'HEX':
                try:
                    bytes.fromhex(rule['reply_content'].replace(' ', ''))
                except ValueError:
                    QMessageBox.warning(self, "警告", f"第{i+1}行的应答内容HEX格式无效")
                    return False
                    
        return True