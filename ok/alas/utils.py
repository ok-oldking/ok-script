import os
from typing import TypeVar

T = TypeVar("T")


def iter_folder(folder, is_dir=False, ext=None):
    """
    Args:
        folder (str):
        is_dir (bool): True to iter directories only
        ext (str): File extension, such as `.yaml`

    Yields:
        str: Absolute path of files
    """
    try:
        files = os.listdir(folder)
    except FileNotFoundError:
        return

    for file in files:
        sub = os.path.join(folder, file)
        if is_dir:
            if os.path.isdir(sub):
                yield sub
        elif ext is not None:
            if not os.path.isdir(sub):
                _, extension = os.path.splitext(file)
                if extension == ext:
                    yield os.path.join(folder, file)
        else:
            yield os.path.join(folder, file)
