from PySide6.QtCore import QObject, Signal, QTimer, QSettings
from PySide6.QtWidgets import QApplication
import json
import time
import re
from typing import List, Dict, Optional, Callable


class AutoReplyRule:
    """自动应答规则类"""
    
    def __init__(self, match_type: str, match_content: str, 
                 reply_type: str, reply_content: str, enabled: bool = True):
        self.match_type = match_type  # "字符串" 或 "HEX"
        self.match_content = match_content
        self.reply_type = reply_type  # "字符串" 或 "HEX"
        self.reply_content = reply_content
        self.enabled = enabled
        self.match_count = 0  # 匹配次数统计
        self.last_match_time = 0  # 最后匹配时间
        
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'match_type': self.match_type,
            'match_content': self.match_content,
            'reply_type': self.reply_type,
            'reply_content': self.reply_content,
            'enabled': self.enabled
        }
        
    @classmethod
    def from_dict(cls, data: Dict) -> 'AutoReplyRule':
        """从字典创建规则"""
        return cls(
            match_type=data.get('match_type', '字符串'),
            match_content=data.get('match_content', ''),
            reply_type=data.get('reply_type', '字符串'),
            reply_content=data.get('reply_content', ''),
            enabled=data.get('enabled', True)
        )
        
    def matches(self, data: bytes) -> bool:
        """检查数据是否匹配此规则"""
        if not self.enabled or not self.match_content.strip():
            return False
            
        try:
            if self.match_type == "字符串":
                # 字符串匹配 - 尝试UTF-8和ASCII解码
                try:
                    text_data = data.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        text_data = data.decode('ascii', errors='ignore')
                    except:
                        return False
                        
                return self.match_content in text_data
                
            elif self.match_type == "HEX":
                # HEX匹配
                match_bytes = bytes.fromhex(self.match_content.replace(' ', ''))
                return match_bytes in data
                
        except Exception:
            return False
            
        return False
        
    def get_reply_data(self) -> bytes:
        """获取应答数据"""
        try:
            if self.reply_type == "字符串":
                # 字符串类型自动添加回车换行
                content = self.reply_content
                if not content.endswith('\r\n') and not content.endswith('\n'):
                    content += '\r\n'
                return content.encode('utf-8')
            elif self.reply_type == "HEX":
                return bytes.fromhex(self.reply_content.replace(' ', ''))
        except Exception:
            return b''
            
        return b''


class AutoReplyEngine(QObject):
    """自动应答引擎"""
    
    # 信号定义
    reply_sent = Signal(str, bytes, str)  # 规则描述, 应答数据, 匹配内容
    match_found = Signal(str, str)  # 规则描述, 匹配内容
    error_occurred = Signal(str)  # 错误信息
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.rules: List[AutoReplyRule] = []
        self.enabled = False
        self.send_callback: Optional[Callable[[bytes], None]] = None
        
        # 性能统计
        self.total_matches = 0
        self.total_replies = 0
        self.last_process_time = 0
        
        # 防抖动定时器 - 避免频繁匹配
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self._process_pending_data)
        self.pending_data = b''
        
        self.load_settings()
        
    def set_enabled(self, enabled: bool):
        """设置启用状态"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"AutoReplyEngine.set_enabled: 设置启用状态从 {self.enabled} 到 {enabled}")
        self.enabled = enabled
        logger.info(f"AutoReplyEngine.set_enabled: 启用状态已更新为 {self.enabled}")
        
    def is_enabled(self) -> bool:
        """获取启用状态"""
        return self.enabled
        
    def set_send_callback(self, callback: Callable[[bytes], None]):
        """设置发送回调函数"""
        self.send_callback = callback
        
    def add_rule(self, rule: AutoReplyRule):
        """添加规则"""
        self.rules.append(rule)
        
    def remove_rule(self, index: int):
        """移除规则"""
        if 0 <= index < len(self.rules):
            del self.rules[index]
            
    def clear_rules(self):
        """清空所有规则"""
        self.rules.clear()
        
    def set_rules(self, rules: List[AutoReplyRule]):
        """设置规则列表"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"AutoReplyEngine.set_rules: 接收到 {len(rules)} 条新规则")
        for i, rule in enumerate(rules):
            logger.debug(f"新规则 {i+1}: 匹配={rule.match_content}, 应答={rule.reply_content}, 启用={rule.enabled}")
        
        self.rules = rules.copy()
        logger.info(f"AutoReplyEngine.set_rules: 规则列表已更新，当前共有 {len(self.rules)} 条规则")
        
        # 验证规则是否正确设置
        for i, rule in enumerate(self.rules):
            logger.debug(f"当前规则 {i+1}: 匹配={rule.match_content}, 应答={rule.reply_content}, 启用={rule.enabled}")
        
    def get_rules(self) -> List[AutoReplyRule]:
        """获取规则列表"""
        return self.rules.copy()
        
    def process_received_data(self, data: bytes):
        """处理接收到的数据"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.debug(f"AutoReplyEngine.process_received_data: 接收到数据 {data}, 启用状态: {self.enabled}, 规则数量: {len(self.rules)}")
        
        if not self.enabled or not self.rules:
            logger.debug(f"自动应答未启用或无规则，跳过处理")
            return
            
        start_time = time.perf_counter()
        
        try:
            # 使用防抖动机制，避免频繁处理
            self.pending_data += data
            self.debounce_timer.stop()
            self.debounce_timer.start(10)  # 10ms延迟
            logger.debug(f"数据已添加到待处理队列，启动防抖动定时器")
            
        except Exception as e:
            logger.error(f"处理接收数据时出错: {str(e)}")
            self.error_occurred.emit(f"处理接收数据时出错: {str(e)}")
            
    def _process_pending_data(self):
        """处理待处理的数据"""
        import logging
        logger = logging.getLogger(__name__)
        
        if not self.pending_data:
            logger.debug("没有待处理数据")
            return
            
        data = self.pending_data
        self.pending_data = b''
        
        logger.debug(f"开始处理数据: {data}")
        
        try:
            # 按优先级顺序检查规则（列表顺序即为优先级）
            for i, rule in enumerate(self.rules):
                logger.debug(f"检查规则 {i+1}: 匹配类型={rule.match_type}, 匹配内容={rule.match_content}, 启用={rule.enabled}")
                
                if rule.matches(data):
                    self.total_matches += 1
                    rule.match_count += 1
                    rule.last_match_time = time.time()
                    
                    # 发出匹配信号
                    match_desc = f"规则{i+1}: {rule.match_content}"
                    logger.info(f"匹配成功: {match_desc}")
                    self.match_found.emit(match_desc, rule.match_content)
                    
                    # 发送应答
                    reply_data = rule.get_reply_data()
                    logger.info(f"准备发送应答数据: {reply_data}")
                    
                    if reply_data and self.send_callback:
                        try:
                            logger.info(f"调用发送回调函数发送数据: {reply_data}")
                            self.send_callback(reply_data)
                            self.total_replies += 1
                            
                            # 发出应答发送信号
                            self.reply_sent.emit(match_desc, reply_data, rule.match_content)
                            logger.info(f"应答发送成功")
                            
                        except Exception as e:
                            logger.error(f"发送应答数据时出错: {str(e)}")
                            self.error_occurred.emit(f"发送应答数据时出错: {str(e)}")
                    elif not reply_data:
                        logger.warning(f"应答数据为空")
                    elif not self.send_callback:
                        logger.error(f"发送回调函数未设置")
                    
                    # 只匹配第一个符合条件的规则（优先级处理）
                    break
                else:
                    logger.debug(f"规则 {i+1} 不匹配")
                    
        except Exception as e:
            logger.error(f"处理数据匹配时出错: {str(e)}")
            self.error_occurred.emit(f"处理数据匹配时出错: {str(e)}")
            
        # 更新处理时间统计
        self.last_process_time = time.perf_counter()
        
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        return {
            'total_matches': self.total_matches,
            'total_replies': self.total_replies,
            'rules_count': len(self.rules),
            'enabled_rules_count': len([r for r in self.rules if r.enabled]),
            'last_process_time': self.last_process_time,
            'rule_stats': [
                {
                    'index': i,
                    'match_content': rule.match_content,
                    'match_count': rule.match_count,
                    'last_match_time': rule.last_match_time,
                    'enabled': rule.enabled
                }
                for i, rule in enumerate(self.rules)
            ]
        }
        
    def reset_statistics(self):
        """重置统计信息"""
        self.total_matches = 0
        self.total_replies = 0
        for rule in self.rules:
            rule.match_count = 0
            rule.last_match_time = 0
            
    def save_settings(self):
        """保存设置"""
        settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "Gavin", "Gavin_com")
        
        # 保存规则
        rules_data = [rule.to_dict() for rule in self.rules]
        settings.setValue("auto_reply/rules", json.dumps(rules_data))
        
        # 保存启用状态
        settings.setValue("auto_reply/enabled", self.enabled)
        
    def load_settings(self):
        """加载设置"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info("AutoReplyEngine开始加载设置")
        # 使用与main.py相同的格式
        settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "Gavin", "Gavin_com")
        
        # 加载规则
        try:
            rules_json = settings.value("auto_reply/rules", "[]")
            logger.info(f"从QSettings读取到规则JSON: {rules_json}")
            
            rules_data = json.loads(rules_json)
            self.rules = [AutoReplyRule.from_dict(rule_dict) for rule_dict in rules_data]
            logger.info(f"成功加载 {len(self.rules)} 条自动应答规则")
            
            for i, rule in enumerate(self.rules):
                logger.debug(f"规则 {i+1}: 匹配={rule.match_content}, 应答={rule.reply_content}, 启用={rule.enabled}")
                
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning(f"加载自动应答规则失败: {e}")
            self.rules = []
            
        # 加载启用状态
        self.enabled = settings.value("auto_reply/enabled", False, type=bool)
        logger.info(f"自动应答引擎启用状态: {self.enabled}")
        logger.info("AutoReplyEngine设置加载完成")
        
    def validate_rule(self, rule: AutoReplyRule) -> tuple[bool, str]:
        """验证规则的有效性"""
        if not rule.match_content.strip():
            return False, "匹配内容不能为空"
            
        if not rule.reply_content.strip():
            return False, "应答内容不能为空"
            
        # 验证HEX格式
        if rule.match_type == "HEX":
            try:
                bytes.fromhex(rule.match_content.replace(' ', ''))
            except ValueError:
                return False, "匹配内容HEX格式无效"
                
        if rule.reply_type == "HEX":
            try:
                bytes.fromhex(rule.reply_content.replace(' ', ''))
            except ValueError:
                return False, "应答内容HEX格式无效"
                
        return True, ""
        
    def import_rules_from_dict_list(self, rules_data: List[Dict]):
        """从字典列表导入规则"""
        try:
            new_rules = []
            for rule_dict in rules_data:
                rule = AutoReplyRule.from_dict(rule_dict)
                valid, error_msg = self.validate_rule(rule)
                if valid:
                    new_rules.append(rule)
                else:
                    self.error_occurred.emit(f"导入规则失败: {error_msg}")
                    
            self.rules = new_rules
            return True
        except Exception as e:
            self.error_occurred.emit(f"导入规则时出错: {str(e)}")
            return False
            
    def export_rules_to_dict_list(self) -> List[Dict]:
        """导出规则为字典列表"""
        return [rule.to_dict() for rule in self.rules]