"""
TemplateFactory and TemplateInputDialog for the EditTaskTab.

This module provides:
- TemplateInputDialog: A dialog for inputting function parameters, each on a separate row.
- TemplateFactory: Reads function signatures and docs from ok/__init__.pyi and generates
  template code snippets for use in the code editor.
"""

import ast
import inspect
import os
import re
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout
from qfluentwidgets import LineEdit, MessageBoxBase, SubtitleLabel, BodyLabel


class TemplateInputDialog(MessageBoxBase):
    """A dialog for inputting function call parameters.

    Displays each parameter on a separate row with the parameter name as a label
    and its default value as placeholder text. If the user provides a value for a
    parameter, it will be included in the generated code; otherwise it is omitted.

    Args:
        title: The dialog title, typically the function/template name.
        params: A list of tuples (param_name, default_value_str).
                Each tuple represents one parameter row.
        doc: Optional documentation string to display below the title.
        parent: The parent widget.

    Example usage::

        dialog = TemplateInputDialog(
            title="click",
            params=[("x", "-1"), ("y", "-1"), ("after_sleep", "0")],
            doc="Performs a click action.",
            parent=self
        )
        if dialog.exec():
            values = dialog.get_values()
            # values = {"x": "0.5", "after_sleep": "1.0"}  (only filled params)
    """

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
        from qfluentwidgets import CaptionLabel
        for param_name, default_value, param_doc in params:
            row_layout = QHBoxLayout()
            
            label = BodyLabel(param_name, self)
            label.setFixedWidth(100)
            
            line_edit = LineEdit(self)
            placeholder = f"default: {default_value}" if default_value else "required"
            line_edit.setPlaceholderText(placeholder)
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
                from ok.gui.util.Alert import alert_error
                alert_error(self.tr(f"Parameter '{param_name}' is required!"))
                line_edit.setFocus()
                return False
        return True

    def get_values(self) -> Dict[str, str]:
        """Returns a dict of param_name -> user_value for only the params the user filled in.

        Returns:
            A dictionary mapping parameter names to user-provided values.
            Parameters left empty are excluded.
        """
        import ast
        result = {}
        for param_name, (line_edit, default_value) in self.inputs.items():
            text = line_edit.text().strip()
            if not text:
                continue
                
            is_quoted = (text.startswith("'") and text.endswith("'")) or \
                        (text.startswith('"') and text.endswith('"'))
            if not is_quoted:
                try:
                    parsed = ast.parse(text, mode='eval').body
                    if isinstance(parsed, ast.Name) and parsed.id not in ('True', 'False', 'None'):
                        text = f"'{text}'"
                except SyntaxError:
                    text = f"'{text}'"
                    
            result[param_name] = text
        return result


def _parse_pyi_functions(pyi_path: str) -> List[Dict]:
    """Parse the ok/__init__.pyi file and extract function signatures from BaseTask and its parents.

    Args:
        pyi_path: Absolute path to the .pyi file.

    Returns:
        A list of dicts, each with keys:
        - 'name': function name
        - 'template_name': display name for the template list
        - 'params': list of (param_name, default_value_str) tuples
        - 'doc': docstring
        - 'return_type': return annotation string
        - 'is_property': whether it's a property
        - 'class_name': the class it belongs to
    """
    if not os.path.exists(pyi_path):
        return []

    with open(pyi_path, 'r', encoding='utf-8') as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    def _get_category(name: str) -> str:
        name_lower = name.lower()
        if any(w in name_lower for w in ['run', 'scene', 'on_', 'tigger', '_config', 'set_', '_init', 'exit', 'check_interval', 'should_trigger', '_set_executor']):
            return "Skip"
        elif any(w in name_lower for w in ['click', 'scroll', 'mouse', 'swipe', 'move']):
            return "Mouse"
        elif any(w in name_lower for w in ['key', 'press', 'release', 'input', 'back']):
            return "Key"
        elif any(w in name_lower for w in ['sleep', 'reset_scene', 'next_frame', 'disable', 'wait_until', 'start','enable', 'unpause', 'pause', 'wait_scene']):
            return "Control"
        elif any(w in name_lower for w in ['ocr', 'text_fix']):
            return "OCR"
        elif any(w in name_lower for w in ['find', 'feature', 'match', 'exists']):
            return "Template Matching"
        elif any(w in name_lower for w in ['box', 'width', 'height']):
            return "Box"
        elif any(w in name_lower for w in ['window', 'ensure_in_front', 'hwnd']):
            return "Window"
        elif 'adb' in name_lower:
            return "ADB"
        elif any(w in name_lower for w in ['log', 'info_', 'screenshot']):
            return "Logging"
        return "Other"

    # Collect methods from target classes in inheritance order
    target_classes = ['ExecutorOperation', 'FindFeature', 'OCR', 'BaseTask']
    functions = []
    seen_names = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name in target_classes:
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    func_name = item.name
                    
                    # Skip private/dunder methods
                    if func_name.startswith('_'):
                        continue
                    # Skip if already seen from a parent class (child overrides)
                    if func_name in seen_names:
                        continue
                    seen_names.add(func_name)

                    # Check if property
                    is_property = any(
                        isinstance(d, ast.Name) and d.id == 'property'
                        for d in item.decorator_list
                    ) or any(
                        isinstance(d, ast.Attribute) and d.attr == 'property'
                        for d in item.decorator_list
                    )

                    # Skip properties - they don't make sense as templates
                    if is_property:
                        continue

                    # Skip static methods that don't use self
                    is_static = any(
                        isinstance(d, ast.Name) and d.id == 'staticmethod'
                        for d in item.decorator_list
                    )

                    # Parse docstring
                    doc = ast.get_docstring(item) or ""
                    # Take only first line of doc for display
                    doc_first_line = doc.split('\n')[0].strip() if doc else ""

                    param_docs_map = {}
                    for line in doc.split('\n'):
                        line = line.strip()
                        if line.startswith(':param '):
                            parts = line.split(':', 2)
                            if len(parts) >= 3:
                                pname = parts[1].replace('param ', '').strip()
                                pdoc = parts[2].strip()
                                param_docs_map[pname] = pdoc

                    # Parse params
                    params = []
                    args = item.args
                    # Compute defaults alignment
                    num_args = len(args.args)
                    num_defaults = len(args.defaults)
                    first_default_index = num_args - num_defaults

                    for i, arg in enumerate(args.args):
                        arg_name = arg.arg
                        if arg_name == 'self' or arg_name == 'cls':
                            continue
                        # Get default value
                        default_idx = i - first_default_index
                        if default_idx >= 0 and default_idx < len(args.defaults):
                            default_node = args.defaults[default_idx]
                            default_value = ast.unparse(default_node)
                        else:
                            default_value = ""
                        # Get parameter docstring
                        param_doc = param_docs_map.get(arg_name, "")
                        params.append((arg_name, default_value, param_doc))

                    # Return type
                    return_type = ""
                    if item.returns:
                        return_type = ast.unparse(item.returns)

                    sig_args = []
                    for arg, default, _ in params:
                        if default:
                            sig_args.append(f"{arg}={default}")
                        else:
                            sig_args.append(arg)
                            
                    if getattr(item.args, 'vararg', None):
                        sig_args.append(f"*{item.args.vararg.arg}")
                    if getattr(item.args, 'kwarg', None):
                        sig_args.append(f"**{item.args.kwarg.arg}")
                            
                    sig_str = f"{func_name}({', '.join(sig_args)})"
                    if return_type:
                        sig_str += f" -> {return_type}"
                        
                    full_doc = f"{sig_str}\n\n{doc}" if doc else sig_str

                    template_name = f"{func_name}"

                    category = _get_category(func_name)
                    if category == 'Skip':
                        continue

                    functions.append({
                        'name': func_name,
                        'template_name': template_name,
                        'params': params,
                        'doc': doc_first_line,
                        'full_doc': full_doc,
                        'return_type': return_type,
                        'is_property': is_property,
                        'class_name': node.name,
                        'category': category,
                        'is_static': is_static,
                    })

    return functions


# Cache parsed templates
_cached_templates = None
_cached_pyi_mtime = 0


def get_templates() -> List[Dict]:
    """Get all available templates, parsed from ok/__init__.pyi.

    Returns cached results if the file hasn't changed.

    Returns:
        List of template dicts with keys: name, template_name, params, doc, full_doc,
        return_type, is_property, class_name, is_static.
    """
    global _cached_templates, _cached_pyi_mtime

    pyi_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            '__init__.pyi')
    try:
        current_mtime = os.path.getmtime(pyi_path)
    except OSError:
        return _cached_templates or []

    if _cached_templates is None or current_mtime != _cached_pyi_mtime:
        _cached_templates = _parse_pyi_functions(pyi_path)
        _cached_pyi_mtime = current_mtime

    return _cached_templates


def filter_templates(templates: List[Dict], query: str) -> List[Dict]:
    """Filter templates by partial match on function name, template_name, or doc.

    Args:
        templates: List of template dicts.
        query: Search query string.

    Returns:
        Filtered list of templates matching the query.
    """
    if not query:
        return templates
    query_lower = query.lower()
    return [t for t in templates if (
            query_lower in t['name'].lower() or
            query_lower in t['template_name'].lower() or
            query_lower in t.get('doc', '').lower() or
            query_lower in t.get('full_doc', '').lower()
    )]


class TemplateFactory:
    """Factory for handling template selection and code generation.

    Reads function signatures from ok/__init__.pyi and generates
    properly formatted code snippets with user-provided parameter values.
    """

    @staticmethod
    def handle_template(template: Dict, parent_widget) -> Optional[str]:
        """Show a parameter input dialog for the selected template and generate code.

        Args:
            template: A template dict from get_templates().
            parent_widget: Parent widget for the dialog.

        Returns:
            Generated code string, or None if the user cancelled or provided no params.
        """
        func_name = template['name']
        params = template['params']
        doc = template.get('doc', '')
        is_static = template.get('is_static', False)

        if not params:
            # No params needed, generate simple call
            prefix = f"{template['class_name']}." if is_static else "self."
            return f"{prefix}{func_name}()"

        dialog = TemplateInputDialog(
            title=func_name,
            params=params,
            doc=doc,
            parent=parent_widget
        )

        if dialog.exec():
            values = dialog.get_values()
            if not values and all(default for _, default, _ in params):
                # User provided nothing but all params have defaults - use default call
                prefix = f"{template['class_name']}." if is_static else "self."
                return f"{prefix}{func_name}()"

            # Build the function call with only user-provided params
            prefix = f"{template['class_name']}." if is_static else "self."
            args_parts = []
            for param_name, default_value, _ in params:
                if param_name in values:
                    user_val = values[param_name]
                    # Check if this is a positional-only required param (no default)
                    if not default_value:
                        args_parts.append(user_val)
                    else:
                        args_parts.append(f"{param_name}={user_val}")

            args_str = ", ".join(args_parts)
            return f"{prefix}{func_name}({args_str})"

        return None
