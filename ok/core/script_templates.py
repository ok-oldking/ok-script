"""Parse the headless script-helper palette shared by every UI."""

from __future__ import annotations

import ast
from pathlib import Path


_cached_templates = None
_cached_py_mtime = 0


def template_category(name):
    lowered = name.lower()
    if any(word in lowered for word in (
            'start', 'run', 'get_threshold', 'fix_texts', 'validate', 'ocr_fun',
            'get_box', 'fix_match_regex', 'onnx_ocr', 'paddle_ocr', 'duguang_ocr',
            'rapid_ocr', 'validate_key', 'scene', 'on_', 'tigger', '_config',
            'set_', '_init', 'exit', 'check_interval', 'should_trigger', '_set_executor')):
        return "Skip"
    categories = (
        ("Mouse", ('click', 'scroll', 'mouse', 'swipe', 'move')),
        ("Key", ('key', 'press', 'release', 'input', 'back')),
        ("Control", ('sleep', 'reset_scene', 'next_frame', 'disable', 'wait_until', 'start', 'enable', 'unpause', 'pause', 'wait_scene')),
        ("OCR", ('ocr', 'text_fix')),
        ("Template Matching", ('find', 'feature', 'match', 'exists')),
        ("Box", ('box', 'width', 'height')),
        ("Window", ('window', 'ensure_in_front', 'hwnd')),
        ("ADB", ('adb',)),
        ("Logging", ('log', 'info_', 'screenshot')),
    )
    return next((category for category, words in categories if any(word in lowered for word in words)), "Other")


def parse_script_templates(py_path):
    path = Path(py_path)
    if not path.is_file():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []

    target_classes = {'ExecutorOperation', 'FindFeature', 'OCR', 'BaseTask'}
    functions = []
    seen = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name not in target_classes:
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = item.name
            if name.startswith('_') or name in seen:
                continue
            seen.add(name)
            decorators = item.decorator_list
            is_property = any(
                (isinstance(value, ast.Name) and value.id == 'property')
                or (isinstance(value, ast.Attribute) and value.attr == 'property')
                for value in decorators
            )
            if is_property:
                continue
            category = template_category(name)
            if category == "Skip":
                continue
            is_static = any(isinstance(value, ast.Name) and value.id == 'staticmethod' for value in decorators)
            doc = ast.get_docstring(item) or ""
            param_docs = {}
            for line in doc.splitlines():
                line = line.strip()
                if line.startswith(':param '):
                    parts = line.split(':', 2)
                    if len(parts) >= 3:
                        param_docs[parts[1].replace('param ', '').strip()] = parts[2].strip()

            args = item.args
            first_default = len(args.args) - len(args.defaults)
            params = []
            for index, argument in enumerate(args.args):
                if argument.arg in {'self', 'cls'}:
                    continue
                default_index = index - first_default
                default = ast.unparse(args.defaults[default_index]) if 0 <= default_index < len(args.defaults) else ""
                params.append((argument.arg, default, param_docs.get(argument.arg, "")))

            signature_parts = [f"{param}={default}" if default else param for param, default, _doc in params]
            if args.vararg:
                signature_parts.append(f"*{args.vararg.arg}")
            if args.kwarg:
                signature_parts.append(f"**{args.kwarg.arg}")
            return_type = ast.unparse(item.returns) if item.returns else ""
            signature = f"{name}({', '.join(signature_parts)})"
            if return_type:
                signature += f" -> {return_type}"
            functions.append({
                "name": name,
                "template_name": name,
                "params": params,
                "doc": doc.splitlines()[0].strip() if doc else "",
                "full_doc": f"{signature}\n\n{doc}" if doc else signature,
                "return_type": return_type,
                "is_property": False,
                "class_name": node.name,
                "category": category,
                "is_static": is_static,
            })
    return functions


def get_script_templates(py_path=None):
    global _cached_templates, _cached_py_mtime
    path = Path(py_path) if py_path else Path(__file__).parents[1] / "task" / "task.py"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return _cached_templates or []
    if _cached_templates is None or mtime != _cached_py_mtime:
        _cached_templates = parse_script_templates(path)
        _cached_py_mtime = mtime
    return _cached_templates


def serialize_script_templates(templates=None):
    result = []
    for item in templates if templates is not None else get_script_templates():
        serialized = dict(item)
        serialized["params"] = [
            {"name": name, "default": default or None, "doc": doc}
            for name, default, doc in item.get("params", [])
        ]
        result.append(serialized)
    return result
