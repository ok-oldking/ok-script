"""Qt parameter dialog for the shared core script-template catalog."""

from typing import Dict, List, Optional, Tuple

from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import BodyLabel, CaptionLabel, LineEdit, MessageBoxBase, SubtitleLabel

from ok.core.script_templates import get_script_templates, parse_script_templates


class TemplateInputDialog(MessageBoxBase):
    def __init__(self, title: str, params: List[Tuple[str, str, str]], doc: str = "", parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title, self)
        self.viewLayout.addWidget(self.titleLabel)

        if parent:
            translated_title = parent.tr(title)
            if translated_title != title:
                translated_label = BodyLabel(translated_title, self)
                translated_label.setStyleSheet("color: gray;")
                self.viewLayout.addWidget(translated_label)

        if doc:
            doc_label = BodyLabel(doc, self)
            doc_label.setWordWrap(True)
            self.viewLayout.addWidget(doc_label)

        self.inputs = {}
        for param_name, default_value, param_doc in params:
            row_layout = QHBoxLayout()
            label = BodyLabel(param_name, self)
            label.setFixedWidth(100)
            line_edit = LineEdit(self)
            line_edit.setPlaceholderText(f"default: {default_value}" if default_value else "required")
            line_edit.setFixedWidth(180)
            row_layout.addWidget(label)
            row_layout.addWidget(line_edit)
            if param_doc:
                doc_label = CaptionLabel(param_doc, self)
                doc_label.setWordWrap(True)
                doc_label.setStyleSheet("color: gray;")
                row_layout.addWidget(doc_label, 1)
            else:
                row_layout.addStretch(1)
            self.viewLayout.addLayout(row_layout)
            self.inputs[param_name] = (line_edit, default_value)

        self.yesButton.setText(self.tr('Confirm'))
        self.cancelButton.setText(self.tr('Cancel'))
        self.widget.setMinimumWidth(480)

    def validate(self) -> bool:
        for param_name, (line_edit, default_value) in self.inputs.items():
            if not default_value and not line_edit.text().strip():
                from ok.ui.qt.util.Alert import alert_error
                alert_error(self.tr(f"Parameter '{param_name}' is required!"))
                line_edit.setFocus()
                return False
        return True

    def get_values(self) -> Dict[str, str]:
        import ast
        result = {}
        for param_name, (line_edit, _default_value) in self.inputs.items():
            text = line_edit.text().strip()
            if not text:
                continue
            is_quoted = ((text.startswith("'") and text.endswith("'"))
                         or (text.startswith('"') and text.endswith('"')))
            if not is_quoted:
                try:
                    parsed = ast.parse(text, mode='eval').body
                    if isinstance(parsed, ast.Name) and parsed.id not in ('True', 'False', 'None'):
                        text = repr(text)
                except SyntaxError:
                    text = repr(text)
            result[param_name] = text
        return result


def _parse_py_functions(py_path: str):
    """Compatibility wrapper for callers that parse a custom task source."""
    return parse_script_templates(py_path)


def get_templates():
    return get_script_templates()


def filter_templates(templates: List[Dict], query: str) -> List[Dict]:
    if not query:
        return templates
    query = query.lower()
    return [template for template in templates if any(
        query in str(template.get(field, "")).lower()
        for field in ("name", "template_name", "doc", "full_doc")
    )]


class TemplateFactory:
    @staticmethod
    def handle_template(template: Dict, parent_widget) -> Optional[str]:
        func_name = template["name"]
        params = template["params"]
        prefix = f"{template['class_name']}." if template.get("is_static") else "self."
        if not params:
            return f"{prefix}{func_name}()"
        dialog = TemplateInputDialog(
            title=func_name,
            params=params,
            doc=template.get("doc", ""),
            parent=parent_widget,
        )
        if not dialog.exec():
            return None
        values = dialog.get_values()
        if not values and all(default for _name, default, _doc in params):
            return f"{prefix}{func_name}()"
        arguments = [
            value if not default else f"{name}={value}"
            for name, default, _doc in params
            if (value := values.get(name)) is not None
        ]
        return f"{prefix}{func_name}({', '.join(arguments)})"
