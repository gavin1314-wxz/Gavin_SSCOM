import sys

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import *


# widget.MineWidget   ESP8266.setCentralWidget(self.centralwidget)

class MineWidget(QWidget):
    # 定义一个信号变量，1个参数
    signalMineWidget = Signal(object)

    def set_connect_key_press(self, fun):
        self.signalMineWidget.connect(fun)

    # 检测键盘回车按键
    def keyPressEvent(self, event):
        self.signalMineWidget.emit(event.key())

    def mousePressEvent(self, event):
        self.signalMineWidget.emit(event.button())

    # 添加一个退出的提示事件
    def closeEvent(self, event):
        self.signalMineWidget.emit(1111)
