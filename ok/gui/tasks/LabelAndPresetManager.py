from PySide6.QtWidgets import QWidget, QHBoxLayout, QCompleter
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QAction  # 使用 PySide6 原生 Action
from qfluentwidgets import LineEdit, ToolButton, PushButton, FluentIcon, RoundMenu  # 使用 RoundMenu

from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget


class LabelAndPresetManager(ConfigLabelAndWidget):
    def __init__(self, config_desc, config, key: str, task, linked_keys: list):
        super().__init__(config_desc, config, key)
        self.key = key
        self.task = task
        self.linked_keys = linked_keys
        self.suppress_guard = False

        self.default_presets = {
            "经典双爆方案": {
                '必须词条': ['暴击', '暴击伤害'],
                '可选词条': ['攻击百分比'],
                '可选词条数量 >=': 3,
                '前置检查': '在双爆出现前',
                '暴击数值 >=': '6.3%',
                '爆伤数值 >=': '12.6%',
                '双爆总计 >=': 13.8,
                'Pause after Success': True,
            }
        }

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
        self.container_layout.addStretch(1)  # 强制靠左紧凑排列

        self.add_widget(self.container, stretch=1)

        self.update_value()
        self._rebuild_menu_and_completer()

    def _show_presets_menu(self):
        """点击下拉箭头时，在按钮下方弹出方案菜单"""
        if hasattr(self, 'menu'):
            pos = self.menu_btn.mapToGlobal(QPoint(0, self.menu_btn.height()))
            self.menu.exec(pos)

    def _rebuild_menu_and_completer(self):
        """重新生成菜单和输入框过滤器项"""
        if hasattr(self, 'menu'):
            self.menu.deleteLater()

        self.menu = RoundMenu(parent=self) 
        presets = self.config.get('_presets_data', self.default_presets)

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
        """明确点选了某个方案：载入该方案数据并动态重绘全面板组件"""
        if not preset_name:
            return
        presets = self.config.get('_presets_data', self.default_presets)
        if preset_name in presets:
            preset_values = presets[preset_name]
            
            self.line_edit.setText(preset_name)
            self.update_config(preset_name)
            
            for key in self.linked_keys:
                if key in preset_values:
                    self.config[key] = preset_values[key]

            self._broadcast_ui_refresh()

    def _add_preset(self):
        """点击新增：获取当前面板的值并储存为非同名新方案"""
        name = self.line_edit.text().strip()
        if not name:
            name = "未命名方案"
        
        presets = dict(self.config.get('_presets_data', self.default_presets))
        
        while name in presets:
            name += "1"

        presets[name] = {}
        for key in self.linked_keys:
            presets[name][key] = self.config.get(key)

        self.config['_presets_data'] = presets
        self.line_edit.setText(name)
        self.update_config(name)
        self._rebuild_menu_and_completer()

    def _overwrite_preset(self):
        """点击覆盖：把当前面板更改后的数值，更新写入到当前输入的方案名中"""
        name = self.line_edit.text().strip()
        if not name:
            return
        
        presets = dict(self.config.get('_presets_data', self.default_presets))
        presets[name] = {}
        for key in self.linked_keys:
            presets[name][key] = self.config.get(key)
            
        self.config['_presets_data'] = presets
        self.update_config(name)
        self._rebuild_menu_and_completer()

    def _delete_preset(self):
        """点击删除：移除当前方案"""
        name = self.line_edit.text().strip()
        presets = dict(self.config.get('_presets_data', self.default_presets))
        
        if name in presets:
            del presets[name]
            self.config['_presets_data'] = presets
            self.line_edit.clear()
            self.update_config("")
            self._rebuild_menu_and_completer()

    def _broadcast_ui_refresh(self):
        """跨组件总控：向上溯源并遍历刷新其他关联配置项的 UI 显示"""
        curr_parent = self.parent()
        while curr_parent:
            children = curr_parent.findChildren(ConfigLabelAndWidget)
            if children:
                for child in children:
                    if child != self and hasattr(child, 'update_value') and child.key in self.linked_keys:
                        child.update_value()
                break
            curr_parent = curr_parent.parent()

    def update_value(self):
        """数据拉取刷新"""
        val = self.config.get(self.key, "")
        self.line_edit.setText(val)
