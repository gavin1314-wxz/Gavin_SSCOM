# -*- coding: utf-8 -*-
from PySide6 import QtCore, QtWidgets, QtGui

class MapButtonDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, label="", text="", is_hex=False, append_newline=True, color="Green"):
        super().__init__(parent)
        self.setWindowTitle("快捷按钮设置")
        self.resize(380, 260)
        layout = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        self.ed_label = QtWidgets.QLineEdit(label)
        self.ed_text = QtWidgets.QTextEdit(text)
        self.cb_hex = QtWidgets.QCheckBox("HEX模式")
        self.cb_hex.setChecked(is_hex)
        self.cb_newline = QtWidgets.QCheckBox("追加换行(\r\n)")
        self.cb_newline.setChecked(append_newline)
        self.cb_newline.setEnabled(not is_hex)
        self.cb_hex.stateChanged.connect(lambda s: self.cb_newline.setEnabled(s == QtCore.Qt.Unchecked))
        self.cmb_color = QtWidgets.QComboBox()
        self.cmb_color.addItems(["Green", "Red", "Blue", "Gray", "Orange"])
        idx = self.cmb_color.findText(color)
        if idx >= 0:
            self.cmb_color.setCurrentIndex(idx)

        form.addRow("标签:", self.ed_label)
        form.addRow("发送内容:", self.ed_text)
        form.addRow("模式:", self.cb_hex)
        form.addRow("换行:", self.cb_newline)
        form.addRow("颜色:", self.cmb_color)
        layout.addLayout(form)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_values(self):
        return {
            'label': self.ed_label.text().strip(),
            'text': self.ed_text.toPlainText(),
            'is_hex': self.cb_hex.isChecked(),
            'append_newline': self.cb_newline.isChecked(),
            'color': self.cmb_color.currentText(),
        }


class QuickButton(QtWidgets.QPushButton):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(cfg.get('label', ''), parent)
        self.payload = cfg.get('text', '')
        self.is_hex = bool(cfg.get('is_hex', False))
        self.append_newline = bool(cfg.get('append_newline', True))
        self.color = cfg.get('color', 'Green')
        # 限制每个按钮最大宽度为80像素
        self.setMaximumWidth(80)
        # 垂直方向固定，避免占用额外空间
        self.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Fixed)
        self.update_style()

    def update_style(self):
        colors = {
            'Green': '#3CB371',
            'Red': '#E74C3C',
            'Blue': '#3498DB',
            'Gray': '#95A5A6',
            'Orange': '#E67E22'
        }
        # 按下态/悬停态颜色（Qt5风格的明显反馈）
        pressed_colors = {
            'Green': '#2E8B57',
            'Red': '#C0392B',
            'Blue': '#2C81C8',
            'Gray': '#7F8C8D',
            'Orange': '#CF6D17'
        }
        hover_colors = {
            'Green': '#45D381',
            'Red': '#FF6B5A',
            'Blue': '#47A9F0',
            'Gray': '#AEB6BF',
            'Orange': '#F39C3A'
        }
        c = colors.get(self.color, '#3CB371')
        pc = pressed_colors.get(self.color, '#2E8B57')
        hc = hover_colors.get(self.color, '#45D381')
        # 降低按钮最小高度，提升紧凑度
        self.setMinimumHeight(18)
        self.setStyleSheet(
            f"""
QPushButton {{
    background: {c};
    color: white;
    border-radius: 4px;
    border: 1px solid rgba(0,0,0,0.25);
    padding: 1px 6px;
}}
QPushButton:hover {{
    background: {hc};
    border: 1px solid #55aaff;
}}
QPushButton:pressed {{
    background: {pc};
    border: 1px solid #666;
    padding-top: 3px;   /* 模拟按下的视觉位移 */
    padding-bottom: 0px;
}}
            """
        )


class QuickButtonBar(QtWidgets.QWidget):
    send_requested = QtCore.Signal(str, bool, bool)  # text, is_hex, append_newline
    ADD_GROUP_SENTINEL = "__add_group__"
    DEFAULT_GROUP_NAME = "默认"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sender = None
        self._buttons = []
        self._groups = []
        self._active_group_name = self.DEFAULT_GROUP_NAME
        self._group_signal_blocked = False
        self.setObjectName('QuickButtonBar')
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        # 高度自适应按钮内容，不占用额外空间
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.group_combo = QtWidgets.QComboBox(self)
        self.group_combo.setFixedWidth(60)
        self.group_combo.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.group_combo.currentIndexChanged.connect(self._on_group_changed)
        self.group_combo.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.group_combo.customContextMenuRequested.connect(self._on_group_combo_menu)
        outer.addWidget(self.group_combo)

        self.scroll = QtWidgets.QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.container = QtWidgets.QWidget()
        self.container.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self.h = QtWidgets.QHBoxLayout(self.container)
        self.h.setContentsMargins(0, 0, 0, 0)
        self.h.setSpacing(4)
        self.h.addStretch()
        self.scroll.setWidget(self.container)
        outer.addWidget(self.scroll)

        # 右键菜单（空白处）
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_bar_context_menu)

    def set_sender(self, func):
        """设置发送回调: func(text: str, is_hex: bool, append_newline: bool)"""
        self._sender = func
        # 也允许外部直接连接信号
        self.send_requested.connect(func)

    # -- 持久化 --
    def _settings(self):
        return QtCore.QSettings(QtCore.QSettings.IniFormat, QtCore.QSettings.UserScope, 'Gavin', 'Gavin_com')

    def _ensure_default_group(self):
        if self._groups:
            return
        self._groups.append({
            'name': self.DEFAULT_GROUP_NAME,
            'buttons': []
        })
        self._active_group_name = self.DEFAULT_GROUP_NAME

    def _find_group_index(self, group_name: str) -> int:
        for i, group in enumerate(self._groups):
            if group.get('name') == group_name:
                return i
        return -1

    def _normalize_group_name(self, name: str) -> str:
        return (name or "").strip()

    def _button_to_cfg(self, btn: QuickButton) -> dict:
        return {
            'label': btn.text(),
            'text': btn.payload,
            'is_hex': btn.is_hex,
            'append_newline': btn.append_newline,
            'color': btn.color
        }

    def _sync_group_from_widgets(self, group_name: str = None):
        group_name = self._normalize_group_name(group_name or self._active_group_name)
        idx = self._find_group_index(group_name)
        if idx < 0:
            return
        self._groups[idx]['buttons'] = [self._button_to_cfg(btn) for btn in self._buttons]

    def _clear_button_widgets(self):
        for btn in self._buttons:
            self.h.removeWidget(btn)
            btn.deleteLater()
        self._buttons = []
        self._update_height()

    def _rebuild_group_selector(self, selected_group: str = None):
        self._ensure_default_group()
        selected_group = self._normalize_group_name(selected_group or self._active_group_name)

        self._group_signal_blocked = True
        self.group_combo.clear()
        for group in self._groups:
            group_name = group.get('name', self.DEFAULT_GROUP_NAME)
            self.group_combo.addItem(group_name, group_name)
        self.group_combo.insertSeparator(self.group_combo.count())
        self.group_combo.addItem("新建", self.ADD_GROUP_SENTINEL)

        idx = self._find_group_index(selected_group)
        if idx < 0:
            idx = 0
            selected_group = self._groups[0].get('name', self.DEFAULT_GROUP_NAME)
        self.group_combo.setCurrentIndex(idx)
        self._group_signal_blocked = False
        self._active_group_name = selected_group

    def _load_group_buttons(self, group_name: str = None):
        group_name = self._normalize_group_name(group_name or self._active_group_name)
        idx = self._find_group_index(group_name)
        if idx < 0:
            self._ensure_default_group()
            idx = 0
            group_name = self._groups[0].get('name', self.DEFAULT_GROUP_NAME)
            self._active_group_name = group_name

        self._clear_button_widgets()
        for cfg in self._groups[idx].get('buttons', []):
            self._append_button(cfg)
        self._update_height()

    def _load_settings(self):
        s = self._settings()
        groups_count = s.value('quickbar/groups/count', 0, int)
        try:
            groups_count = int(groups_count)
        except Exception:
            groups_count = 0

        self._groups = []
        if groups_count > 0:
            for i in range(groups_count):
                name = self._normalize_group_name(s.value(f'quickbar/groups/{i}/name', self.DEFAULT_GROUP_NAME, str))
                if not name:
                    name = f"{self.DEFAULT_GROUP_NAME}{i+1}"
                button_count = s.value(f'quickbar/groups/{i}/button_count', 0, int)
                try:
                    button_count = int(button_count)
                except Exception:
                    button_count = 0
                buttons = []
                for j in range(button_count):
                    buttons.append({
                        'label': s.value(f'quickbar/groups/{i}/buttons/{j}/label', f'B{j+1}'),
                        'text': s.value(f'quickbar/groups/{i}/buttons/{j}/text', ''),
                        'is_hex': s.value(f'quickbar/groups/{i}/buttons/{j}/is_hex', False, bool),
                        'append_newline': s.value(f'quickbar/groups/{i}/buttons/{j}/append_newline', True, bool),
                        'color': s.value(f'quickbar/groups/{i}/buttons/{j}/color', 'Green')
                    })
                self._groups.append({
                    'name': name,
                    'buttons': buttons
                })
        else:
            # 兼容旧版单分组配置，自动迁移到默认分组
            count = s.value('quickbar/count', 0, int)
            try:
                count = int(count)
            except Exception:
                count = 0
            buttons = []
            for i in range(count):
                buttons.append({
                    'label': s.value(f'quickbar/{i}/label', f'B{i+1}'),
                    'text': s.value(f'quickbar/{i}/text', ''),
                    'is_hex': s.value(f'quickbar/{i}/is_hex', False, bool),
                    'append_newline': s.value(f'quickbar/{i}/append_newline', True, bool),
                    'color': s.value(f'quickbar/{i}/color', 'Green')
                })
            self._groups.append({
                'name': self.DEFAULT_GROUP_NAME,
                'buttons': buttons
            })

        self._ensure_default_group()
        current_group = self._normalize_group_name(s.value('quickbar/current_group', self._groups[0].get('name', self.DEFAULT_GROUP_NAME), str))
        if self._find_group_index(current_group) < 0:
            current_group = self._groups[0].get('name', self.DEFAULT_GROUP_NAME)
        self._active_group_name = current_group
        self._rebuild_group_selector(current_group)
        self._load_group_buttons(current_group)

    def _save_settings(self):
        self._ensure_default_group()
        self._sync_group_from_widgets()
        s = self._settings()
        s.remove('quickbar')
        s.setValue('quickbar/groups/count', len(self._groups))
        s.setValue('quickbar/current_group', self._active_group_name)
        for i, group in enumerate(self._groups):
            s.setValue(f'quickbar/groups/{i}/name', group.get('name', self.DEFAULT_GROUP_NAME))
            buttons = group.get('buttons', [])
            s.setValue(f'quickbar/groups/{i}/button_count', len(buttons))
            for j, cfg in enumerate(buttons):
                s.setValue(f'quickbar/groups/{i}/buttons/{j}/label', cfg.get('label', f'B{j+1}'))
                s.setValue(f'quickbar/groups/{i}/buttons/{j}/text', cfg.get('text', ''))
                s.setValue(f'quickbar/groups/{i}/buttons/{j}/is_hex', cfg.get('is_hex', False))
                s.setValue(f'quickbar/groups/{i}/buttons/{j}/append_newline', cfg.get('append_newline', True))
                s.setValue(f'quickbar/groups/{i}/buttons/{j}/color', cfg.get('color', 'Green'))
        s.sync()

    def has_any_buttons(self) -> bool:
        return any(group.get('buttons') for group in self._groups)

    # -- 按钮操作 --
    def _append_button(self, cfg):
        btn = QuickButton(cfg, self.container)
        btn.clicked.connect(lambda _=False, b=btn: self._on_click(b))
        btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        btn.customContextMenuRequested.connect(lambda pos, b=btn: self._on_button_menu(b, pos))
        # 在伸缩前插入
        self.h.insertWidget(self.h.count() - 1, btn)
        self._buttons.append(btn)
        self._update_height()
        return btn

    def add_button(self):
        dlg = MapButtonDialog(self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            cfg = dlg.get_values()
            self._append_button(cfg)
            self._sync_group_from_widgets()
            self._save_settings()

    def edit_button(self, btn: QuickButton):
        dlg = MapButtonDialog(self, btn.text(), btn.payload, btn.is_hex, btn.append_newline, btn.color)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            vals = dlg.get_values()
            btn.setText(vals['label'])
            btn.payload = vals['text']
            btn.is_hex = vals['is_hex']
            btn.append_newline = vals['append_newline']
            btn.color = vals['color']
            btn.update_style()
            self._sync_group_from_widgets()
            self._save_settings()

    def delete_button(self, btn: QuickButton):
        idx = self._buttons.index(btn)
        w = self.h.takeAt(idx)
        if w:
            w.widget().deleteLater()
        self._buttons.pop(idx)
        self._sync_group_from_widgets()
        self._save_settings()

    def move_left(self, btn: QuickButton):
        idx = self._buttons.index(btn)
        if idx <= 0:
            return
        self._buttons[idx-1], self._buttons[idx] = self._buttons[idx], self._buttons[idx-1]
        self._rebuild_layout()

    def move_right(self, btn: QuickButton):
        idx = self._buttons.index(btn)
        if idx >= len(self._buttons) - 1:
            return
        self._buttons[idx+1], self._buttons[idx] = self._buttons[idx], self._buttons[idx+1]
        self._rebuild_layout()

    def _rebuild_layout(self):
        # 清除伸缩以外的按钮项
        for i in reversed(range(self.h.count())):
            item = self.h.itemAt(i)
            if item and item.spacerItem():
                continue
            w = item.widget()
            if w:
                self.h.removeWidget(w)
        # 重新插入
        for b in self._buttons:
            self.h.insertWidget(self.h.count() - 1, b)
        self._update_height()
        self._sync_group_from_widgets()
        self._save_settings()

    def add_group(self):
        base_name = f"分组{len(self._groups) + 1}"
        name, ok = QtWidgets.QInputDialog.getText(self, "新建", "请输入分组名称：", text=base_name)
        if not ok:
            self._rebuild_group_selector(self._active_group_name)
            return False

        name = self._normalize_group_name(name)
        if not name:
            QtWidgets.QMessageBox.warning(self, "提示", "分组名称不能为空。")
            self._rebuild_group_selector(self._active_group_name)
            return False
        if self._find_group_index(name) >= 0:
            QtWidgets.QMessageBox.warning(self, "提示", f"分组“{name}”已存在。")
            self._rebuild_group_selector(self._active_group_name)
            return False

        self._sync_group_from_widgets()
        self._groups.append({
            'name': name,
            'buttons': []
        })
        self._active_group_name = name
        self._rebuild_group_selector(name)
        self._load_group_buttons(name)
        self._save_settings()
        return True

    def rename_current_group(self):
        current_name = self._active_group_name
        name, ok = QtWidgets.QInputDialog.getText(self, "重命名分组", "请输入新的分组名称：", text=current_name)
        if not ok:
            return

        name = self._normalize_group_name(name)
        if not name:
            QtWidgets.QMessageBox.warning(self, "提示", "分组名称不能为空。")
            return
        if name != current_name and self._find_group_index(name) >= 0:
            QtWidgets.QMessageBox.warning(self, "提示", f"分组“{name}”已存在。")
            return

        idx = self._find_group_index(current_name)
        if idx < 0:
            return
        self._groups[idx]['name'] = name
        self._active_group_name = name
        self._rebuild_group_selector(name)
        self._save_settings()

    def delete_current_group(self):
        if len(self._groups) <= 1:
            QtWidgets.QMessageBox.information(self, "提示", "至少保留一个分组。")
            return

        current_name = self._active_group_name
        reply = QtWidgets.QMessageBox.question(
            self,
            "删除分组",
            f"确定删除分组“{current_name}”吗？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        idx = self._find_group_index(current_name)
        if idx < 0:
            return

        self._sync_group_from_widgets()
        self._groups.pop(idx)
        next_idx = min(idx, len(self._groups) - 1)
        self._active_group_name = self._groups[next_idx].get('name', self.DEFAULT_GROUP_NAME)
        self._rebuild_group_selector(self._active_group_name)
        self._load_group_buttons(self._active_group_name)
        self._save_settings()

    # -- 发送逻辑 --
    def _on_click(self, btn: QuickButton):
        if self._sender:
            self._sender(btn.payload, btn.is_hex, btn.append_newline)
        else:
            self.send_requested.emit(btn.payload, btn.is_hex, btn.append_newline)

    def _update_height(self):
        """根据按钮的内容高度自适应整个栏位高度，避免额外占用空间"""
        base_h = 0
        for b in self._buttons:
            base_h = max(base_h, b.sizeHint().height())
        if base_h <= 0:
            base_h = 18
        m = self.h.contentsMargins()
        combo_h = self.group_combo.sizeHint().height() if hasattr(self, 'group_combo') else 0
        bar_h = max(base_h, combo_h) + m.top() + m.bottom()
        # 固定栏位与滚动区域高度，保证不多占空间
        self.scroll.setFixedHeight(bar_h)
        self.setFixedHeight(bar_h)

    # -- 菜单 --
    def _on_button_menu(self, btn: QuickButton, pos: QtCore.QPoint):
        menu = QtWidgets.QMenu(self)
        menu.addAction("编辑按钮...", lambda: self.edit_button(btn))
        menu.addAction("左移", lambda: self.move_left(btn))
        menu.addAction("右移", lambda: self.move_right(btn))
        menu.addSeparator()
        menu.addAction("删除按钮", lambda: self.delete_button(btn))
        menu.exec(QtGui.QCursor.pos())

    def _on_group_changed(self, index: int):
        if self._group_signal_blocked:
            return
        group_name = self.group_combo.itemData(index)
        if group_name == self.ADD_GROUP_SENTINEL:
            self.add_group()
            return
        if not group_name or group_name == self._active_group_name:
            return

        self._sync_group_from_widgets(self._active_group_name)
        self._active_group_name = group_name
        self._load_group_buttons(group_name)
        self._save_settings()

    def _on_group_combo_menu(self, pos: QtCore.QPoint):
        menu = QtWidgets.QMenu(self)
        menu.addAction("新建", self.add_group)
        menu.addAction("重命名当前分组...", self.rename_current_group)
        menu.addAction("删除当前分组", self.delete_current_group)
        menu.exec(self.group_combo.mapToGlobal(pos))

    def _on_bar_context_menu(self, pos: QtCore.QPoint):
        menu = QtWidgets.QMenu(self)
        menu.addAction("新建按钮...", self.add_button)
        menu.addSeparator()
        menu.addAction("新建", self.add_group)
        menu.addAction("重命名当前分组...", self.rename_current_group)
        menu.addAction("删除当前分组", self.delete_current_group)
        menu.exec(QtGui.QCursor.pos())
