from PySide6.QtWidgets import QLineEdit, QApplication
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression

class MyHexQlineText(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        regx = QRegularExpression("[A-Fa-f0-9]{4}")
        validator = QRegularExpressionValidator(regx, self)
        self.setValidator(validator)
