import json
import os

from ok.util.path import ensure_dir_for_file


def read_json_file(file_path) -> dict | None:
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError:
        return None


def write_json_file(file_path, data):
    ensure_dir_for_file(file_path)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    return True
