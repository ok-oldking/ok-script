"""Qt parameter dialog for the shared core script-template catalog."""

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLineEdit, QScrollArea, QWidget

from ok.core.script_templates import get_script_templates, parse_script_templates
from ok.ui.qt.kit.dialogs import Dialog
from ok.ui.qt.kit.labels import Label


class TemplateInputDialog(Dialog):
    """Ask for a script template's parameters; required ones must be filled in."""

    def __init__(self, title: str, params: List[Tuple[str, str, str]], doc: str = "", parent=None):
        translated_title = parent.tr(title) if parent else title
        message = "\n\n".join(text for text in (translated_title if translated_title != title else "", doc) if text)
        from PySide6.QtCore import QCoreApplication
        translate = lambda text: QCoreApplication.translate('TemplateInputDialog', text)
        super().__init__(parent, title, message or None, ok_text=translate('Confirm'),
                         cancel_text=translate('Cancel'), width=560)
        self.titleLabel = self.title_label

        # Parameters scroll so long signatures keep the buttons on screen.
        form = QWidget()
        form.setObjectName("scrollContents")
        grid = QGridLayout(form)
        grid.setContentsMargins(0, 0, 8, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        self.inputs = {}
        for row, (param_name, default_value, param_doc) in enumerate(params):
            line_edit = QLineEdit(form)
            line_edit.setPlaceholderText(f"default: {default_value}" if default_value else "required")
            grid.addWidget(Label(param_name, "mono", form), row * 2, 0)
            grid.addWidget(line_edit, row * 2, 1)
            if param_doc:
                grid.addWidget(Label(param_doc, "caption", form, word_wrap=True), row * 2 + 1, 1)
            self.inputs[param_name] = (line_edit, default_value)
        scroll = QScrollArea(self.panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(form)
        available = max(160, self.parentWidget().height() - 300)
        scroll.setFixedHeight(min(form.sizeHint().height() + 4, available))
        self.body.addWidget(scroll)
        if self.inputs:
            first = next(iter(self.inputs.values()))[0]
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, first.setFocus)

    def validate(self) -> bool:
        for param_name, (line_edit, default_value) in self.inputs.items():
            if not default_value and not line_edit.text().strip():
                from ok.ui.qt.util.Alert import alert_error
                alert_error(self.tr("Parameter '{param_name}' is required!").format(param_name=param_name))
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
        try:
            if not dialog.exec():
                return None
            values = dialog.get_values()
        finally:
            dialog.deleteLater()
        if not values and all(default for _name, default, _doc in params):
            return f"{prefix}{func_name}()"
        arguments = [
            value if not default else f"{name}={value}"
            for name, default, _doc in params
            if (value := values.get(name)) is not None
        ]
        return f"{prefix}{func_name}({', '.join(arguments)})"
