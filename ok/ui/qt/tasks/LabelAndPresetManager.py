import json
import os
import re
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QCompleter, QLabel
from qfluentwidgets import LineEdit, ToolButton, PushButton, FluentIcon, RoundMenu

from ok.ui.qt.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget


class TierPopup(QWidget):
    """档位表浮层外壳：无框、类图片，按住左键任意位置可整体拖拽，双击可关闭。"""

    def __init__(self, parent):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._drag_offset = None
        # 双击关闭的回调由管理者注入（需要同步复位按钮文案）
        self.close_requested = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self.close_requested is not None:
            self.close_requested()
        super().mouseDoubleClickEvent(event)


class LabelAndPresetManager(ConfigLabelAndWidget):
    def __init__(self, config_desc, config, key: str, task, linked_keys: list):
        super().__init__(config_desc, config, key)
        self.key = key
        self.task = task
        self.linked_keys = linked_keys

        # 使用当前工作目录下的 configs
        self.presets_file_path = os.path.abspath(os.path.join("configs", "EnhanceEchoPresets.json"))

        self.default_preset_name = "经典双爆方案"
        self.default_preset_data = {
            '必须词条': ['暴击', '暴击伤害'],
            '可选词条': ['攻击百分比'],
            '可选词条数量 >=': 3,
            '前置检查': '在双爆出现前',
            '暴击数值 >=': '6.3%',
            '爆伤数值 >=': '12.6%',
            '双爆数值浮动策略': '仅同档位浮动',
            '整频器豁免': '关闭拼一把机制',
            'Pause after Success': True,
        }
        self.default_presets = {
            self.default_preset_name: self.default_preset_data
        }

        # ---------- 主容器（垂直布局） ----------
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        # ---- 第一行：方案管理按钮行 ----
        self.container = QWidget()
        self.container_layout = QHBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(8)

        self.line_edit = LineEdit()
        self.line_edit.setPlaceholderText("选择或输入新方案名")
        self.line_edit.setFixedWidth(180)

        self.menu_btn = ToolButton(FluentIcon.DOWN, self.container)
        self.menu_btn.setFixedWidth(32)
        self.menu_btn.clicked.connect(self._show_presets_menu)

        self.btn_add = PushButton("新增", self.container)
        self.btn_save = PushButton("覆盖", self.container)
        self.btn_del = PushButton("删除", self.container)

        self.btn_add.clicked.connect(self._add_preset)
        self.btn_save.clicked.connect(self._overwrite_preset)
        self.btn_del.clicked.connect(self._delete_preset)

        self.container_layout.addWidget(self.line_edit)
        self.container_layout.addWidget(self.menu_btn)
        self.container_layout.addWidget(self.btn_add)
        self.container_layout.addWidget(self.btn_save)
        self.container_layout.addWidget(self.btn_del)
        self.container_layout.addStretch(1)

        main_layout.addWidget(self.container)

        # ---- 第二行：档位表按钮（表格以固定宽度的类图片浮层弹出，可拖拽，不挤占面板布局） ----
        self.btn_toggle_tier = PushButton("查看 韩服声骸词条档位及概率（仅供参考）")
        self.btn_toggle_tier.clicked.connect(self._toggle_tier_table)
        main_layout.addWidget(self.btn_toggle_tier)

        self._tier_popup = None

        self.add_widget(main_widget, stretch=1)

        self.update_value()
        self._rebuild_menu_and_completer()

    # ---------- 数据持久化（不变） ----------
    def _get_presets(self):
        presets = self.config.get('_presets_data')
        if presets is not None:
            return presets
        data = self._read_file_data()
        return data.get('presets', self.default_presets.copy())

    def _ensure_presets_loaded(self):
        if '_presets_data' not in self.config or self.config['_presets_data'] is None:
            data = self._read_file_data()
            self.config['_presets_data'] = data.get('presets', self.default_presets.copy())

    def _read_file_data(self):
        if os.path.exists(self.presets_file_path):
            try:
                with open(self.presets_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        if "presets" not in data or not isinstance(data["presets"], dict):
                            data["presets"] = self.default_presets.copy()
                        if "__current__" not in data:
                            data["__current__"] = self.default_preset_name
                        return data
            except Exception as e:
                print(f"[LabelAndPresetManager] 读取预设 JSON 失败: {e}")
                try:
                    bak_path = self.presets_file_path + ".bak"
                    if os.path.exists(self.presets_file_path):
                        os.replace(self.presets_file_path, bak_path)
                except Exception as bak_err:
                    print(f"[LabelAndPresetManager] 创建备份失败: {bak_err}")

        default_data = {
            "__current__": self.default_preset_name,
            "presets": self.default_presets.copy()
        }
        self._write_file_data(default_data)
        return default_data

    def _write_file_data(self, data):
        try:
            os.makedirs(os.path.dirname(self.presets_file_path), exist_ok=True)
            temp_path = self.presets_file_path + ".tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            os.replace(temp_path, self.presets_file_path)
        except Exception as e:
            print(f"[LabelAndPresetManager] 写入预设文件失败: {e}")

    def _save_all_to_disk(self, current_name, presets_dict):
        payload = {
            "__current__": current_name,
            "presets": presets_dict
        }
        self._write_file_data(payload)

    def _show_presets_menu(self):
        if hasattr(self, 'menu'):
            pos = self.menu_btn.mapToGlobal(QPoint(0, self.menu_btn.height()))
            self.menu.popup(pos)

    def _rebuild_menu_and_completer(self):
        if hasattr(self, 'menu'):
            self.menu.deleteLater()

        self.menu = RoundMenu(parent=self)
        presets = self._get_presets()
        for name in presets.keys():
            action = QAction(name, self)
            action.triggered.connect(lambda checked=False, n=name: self._load_preset(n))
            self.menu.addAction(action)

        preset_names = list(presets.keys())
        self.completer = QCompleter(preset_names, self)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.activated.connect(self._load_preset)
        self.line_edit.setCompleter(self.completer)

    def _load_preset(self, preset_name):
        if not preset_name:
            return
        self._ensure_presets_loaded()
        presets = self.config['_presets_data']
        if preset_name in presets:
            self._save_all_to_disk(preset_name, presets)
            self.line_edit.setText(preset_name)
            self.update_config(preset_name)

            preset_values = presets[preset_name]
            for key in self.linked_keys:
                if key in preset_values:
                    self.config[key] = preset_values[key]

            # 恢复遍历父控件刷新（无外部依赖）
            self._broadcast_ui_refresh()

    def _broadcast_ui_refresh(self):
        """向上查找最顶层父控件，然后遍历所有 ConfigLabelAndWidget 子控件，调用其 update_value"""
        curr = self.parent()
        while curr and curr.parent():
            curr = curr.parent()
        if curr:
            for widget in curr.findChildren(ConfigLabelAndWidget):
                if widget is not self and hasattr(widget, 'update_value'):
                    widget.update_value()

    def _add_preset(self):
        name = self.line_edit.text().strip()
        if not name:
            name = "未命名方案"

        self._ensure_presets_loaded()
        presets = self.config['_presets_data']
        while name in presets:
            name = self._increment_name_suffix(name)

        presets[name] = {}
        for key in self.linked_keys:
            presets[name][key] = self.config.get(key)

        self._save_all_to_disk(name, presets)
        self.line_edit.setText(name)
        self.update_config(name)
        self._rebuild_menu_and_completer()

    def _overwrite_preset(self):
        name = self.line_edit.text().strip()
        if not name:
            return
        self._ensure_presets_loaded()
        presets = self.config['_presets_data']
        presets[name] = {}
        for key in self.linked_keys:
            presets[name][key] = self.config.get(key)
        self._save_all_to_disk(name, presets)
        self.update_config(name)
        self._rebuild_menu_and_completer()

    def _delete_preset(self):
        name = self.line_edit.text().strip()
        self._ensure_presets_loaded()
        presets = self.config['_presets_data']
        if name in presets:
            if len(presets) <= 1:
                self.config['_presets_data'] = self.default_presets.copy()
                self._save_all_to_disk(self.default_preset_name, self.default_presets)
                self._load_preset(self.default_preset_name)
            else:
                del presets[name]
                remaining_names = list(presets.keys())
                next_preset = remaining_names[0]
                self._save_all_to_disk(next_preset, presets)
                self._load_preset(next_preset)
        self._rebuild_menu_and_completer()

    def update_value(self):
        val = self.config.get(self.key, "")
        if not val:
            data = self._read_file_data()
            val = data.get("__current__", self.default_preset_name)
        if hasattr(self, 'line_edit') and self.line_edit.text() != str(val):
            self.line_edit.blockSignals(True)
            self.line_edit.setText(str(val))
            self.line_edit.blockSignals(False)

    @staticmethod
    def _increment_name_suffix(name):
        match = re.search(r'(\d+)$', name)
        if match:
            num = int(match.group(1))
            return name[:match.start()] + str(num + 1)
        return name + "1"

    # ---------- 档位表浮层（类图片：按内容固定宽度、可拖拽，按钮或双击浮层收回） ----------
    def _toggle_tier_table(self):
        popup = self._tier_popup
        if popup is not None and popup.isVisible():
            self._hide_tier_popup()
            return
        if popup is None:
            popup = self._build_tier_popup()
            self._tier_popup = popup
        popup.adjustSize()
        self._position_tier_popup(popup)
        popup.show()
        self.btn_toggle_tier.setText("折叠 韩服声骸词条档位及概率（仅供参考）")

    def _build_tier_popup(self):
        popup = TierPopup(self.window())
        popup.close_requested = self._hide_tier_popup
        popup.setObjectName("tierPopup")
        popup.setWindowTitle("韩服声骸词条档位及概率")
        popup.setStyleSheet("#tierPopup { background-color: #FFFFFF; border: 1px solid #9E9E9E; }")

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(8, 6, 8, 6)

        label = QLabel(TIER_TABLE_TEXT)
        label.setTextFormat(Qt.PlainText)
        label.setWordWrap(False)
        label.setFont(QFont("Consolas, Microsoft YaHei", 10))
        label.setStyleSheet("QLabel { background: transparent; border: none; color: #000000; }")
        # 文本区域对鼠标透明，让整个浮层表面都能按住拖拽
        label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(label)
        return popup

    def _position_tier_popup(self, popup):
        btn = self.btn_toggle_tier
        anchor = btn.mapToGlobal(QPoint(btn.width(), btn.height()))
        screen = btn.screen().availableGeometry()
        # 右缘对齐按钮右缘；放不下时才钳回屏幕内
        x = min(max(anchor.x() - popup.width(), screen.left() + 4), screen.right() - popup.width() - 4)
        y = min(max(anchor.y() + 4, screen.top() + 4), screen.bottom() - popup.height() - 4)
        popup.move(x, y)

    def _hide_tier_popup(self):
        if self._tier_popup is not None:
            self._tier_popup.hide()
        self.btn_toggle_tier.setText("查看 韩服声骸词条档位及概率（仅供参考）")

    def hideEvent(self, event):
        # 本控件随页面切换/销毁被隐藏时，浮层一并收回，避免残留
        if self._tier_popup is not None and self._tier_popup.isVisible():
            self._hide_tier_popup()
        super().hideEvent(event)


TIER_TABLE_TEXT = """ 暴击   暴伤     出率  4种伤害加成/攻/血/防%  小生命 共鸣效率    出率   小攻击  出率  小防御   出率
 6.3%  12.6%   23.33%               6.4%    320     6.8%    6.80%     30   6.80%   40   14.56%
 6.9%  13.8%   23.33%               7.1%    360     7.6%    7.77%     40  52.43%   50   44.66%
 7.5%  15.0%   23.33%               7.9%    390     8.4%   20.39%     50  37.86%   60   32.04%
 8.1%  16.2%    8.00%               8.6%    430     9.2%   24.27%     60   2.91%   70    8.74%
 8.7%  17.4%    8.00%               9.4%    470    10.0%   17.48%        
 9.3%  18.6%    8.00%              10.1%    510    10.8%   14.56%        
 9.9%  19.8%    3.00%              10.9%    540    11.6%    5.83%        
10.5%  21.0%    3.00%              11.6%    580    12.4%    2.91%"""