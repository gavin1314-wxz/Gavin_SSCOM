import sys
from PySide6.QtGui import *
from PySide6.QtWidgets import *
from PySide6.QtCore import *

class UserPushButton(QPushButton):
    doubleClicked = Signal()
    def __init__(self, *args, **kwargs):
        QPushButton.__init__(self, *args, **kwargs)
        # 不要拦截原生的clicked信号，让它正常工作
        # 我们使用mousePressEvent来检测双击
        self._click_count = 0
        self._last_click_time = 0

    def mousePressEvent(self, event):
        # 调用父类的mousePressEvent以保持正常的按钮行为
        super().mousePressEvent(event)
        
        # 检测双击
        import time
        current_time = time.time() * 1000  # 转换为毫秒
        
        if current_time - self._last_click_time < 300:  # 300ms内的第二次点击认为是双击
            self._click_count += 1
            if self._click_count == 2:
                # 这是双击
                self.doubleClicked.emit()
                self._click_count = 0
        else:
            self._click_count = 1
        
        self._last_click_time = current_time
    
