import json
import zipfile

import cv2
import numpy as np

from ok.core.config_schema import build_config_fields
from ok.core.script_editing import merge_recorded_code
from ok.core.script_packager import import_script
from ok.core.template_store import CocoTemplateStore
from ok.util.windows_schedule import TriggerType, infer_trigger_type, normalize_trigger_type


def test_script_import_rejects_traversal_without_replacing_existing(tmp_path):
    imports = tmp_path / "imports"
    existing = imports / "demo"
    existing.mkdir(parents=True)
    (existing / "keep.txt").write_text("keep", encoding="utf-8")
    archive = tmp_path / "unsafe.okscript"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", json.dumps({"file_name": "demo"}))
        output.writestr("../escaped.txt", "bad")

    success, message, _folder = import_script(archive, import_base=imports)

    assert not success
    assert "Unsafe" in message
    assert (existing / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / "escaped.txt").exists()


def test_template_store_cleans_categories_clamps_boxes_and_saves_atomically(tmp_path):
    store = CocoTemplateStore(tmp_path / "templates")
    image_path = store.folder / "0.png"
    assert cv2.imwrite(str(image_path), np.zeros((50, 100, 3), dtype=np.uint8))

    result = store.replace_annotations("0.png", [{"category": "target", "bbox": [90, 45, 40, 30]}])
    assert result["annotations"][0]["bbox"] == [90.0, 45.0, 10.0, 5.0]

    store.replace_annotations("0.png", [])
    assert store.load()["categories"] == []
    assert not list(store.folder.glob(".coco-*.json"))


def test_recorded_code_merge_is_shared_and_supports_loops():
    source = """class Demo:\n    def __init__(self):\n        self.capture_config = {'old': True}\n\n    def run(self):\n        pass\n"""
    merged = merge_recorded_code(
        source, "self.capture_config = {'adb': {}}", "self.click(1, 2)", "count", 3)
    assert "'old'" not in merged
    assert "for _ in range(3):" in merged
    assert "            self.click(1, 2)" in merged


def test_config_schema_respects_explicit_widget_types_and_subconfigs():
    fields = build_config_fields(
        {"Mode": "A", "Path": "a.txt", "Notes": "short", "Only A": True},
        config_types={
            "Mode": {"options": ["A", "B"], "sub_configs": {"A": ["Only A"]}},
            "Path": {"type": "file_selector"},
            "Notes": {"type": "text_edit"},
        },
        defaults={"Mode": "A", "Path": "a.txt", "Notes": "short", "Only A": True},
    )
    assert {field["key"]: field["kind"] for field in fields} == {
        "Mode": "select", "Path": "file", "Notes": "multiline", "Only A": "boolean"}


def test_schedule_trigger_normalization_is_headless():
    assert normalize_trigger_type("2") is TriggerType.DAILY
    assert normalize_trigger_type("3") is TriggerType.WEEKLY
    assert infer_trigger_type("", "<ScheduleByMonth />") is TriggerType.MONTHLY
    assert infer_trigger_type("Daily", interval_hours=2) is TriggerType.CUSTOM
