import importlib
import os

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


def init_class_by_name(module_name, class_name, *args, **kwargs):
    module = importlib.import_module(module_name)
    class_ = getattr(module, class_name)
    return class_(*args, **kwargs)


def generate_label_enum(generate_label_enum_path, labels):
    if not generate_label_enum_path or not labels:
        return
    parts = generate_label_enum_path.split('.')
    class_name = parts[-1]
    if len(parts) > 1:
        # Check if the first part is a directory or just a module name
        # If it's something like "src.task.ABC", we might want to check the current directory structure
        # However, follow the user's logic or previous implementation
        folder_path = os.path.join(*parts[:-1])
        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)
    else:
        folder_path = "."

    file_path = os.path.join(folder_path, f"{class_name}.py")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("from enum import Enum\n\n\n")
        f.write(f"class {class_name}(str, Enum):\n")
        for label in sorted(labels):
            f.write(f"    {label} = '{label}'\n")
    logger.info(f"Generated label enum: {file_path}")
