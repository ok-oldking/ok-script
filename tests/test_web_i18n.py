import json
from pathlib import Path

from scripts import generate_web_i18n


def test_web_catalog_is_generated_from_qt_webui_context(tmp_path, monkeypatch):
    output = tmp_path / "catalogs.json"
    monkeypatch.setattr(generate_web_i18n, "OUTPUT", output)

    catalogs = generate_web_i18n.generate()

    assert set(catalogs) == {"en_US", "es_ES", "ja_JP", "ko_KR", "zh_CN", "zh_TW"}
    assert all(set(catalog) == set(catalogs["en_US"]) for catalog in catalogs.values())
    assert catalogs["zh_CN"]["Automation control"] == "自动化控制"
    assert json.loads(output.read_text(encoding="utf-8")) == catalogs


def test_frontend_source_is_outside_python_package():
    root = Path(__file__).resolve().parents[1]

    assert (root / "package.json").exists()
    assert (root / "web_src" / "src" / "App.tsx").exists()
    assert not (root / "ok" / "ui" / "web" / "frontend").exists()
