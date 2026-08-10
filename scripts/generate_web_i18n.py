"""Generate the browser translation catalog from Qt Linguist TS files."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QT_I18N_DIR = ROOT / "ok" / "ui" / "qt" / "i18n"
OUTPUT = ROOT / "web_src" / "src" / "i18n" / "catalogs.json"
CONTEXT = "WebUI"


def read_context(path: Path) -> tuple[str, dict[str, str]]:
    root = ET.parse(path).getroot()
    locale = root.get("language") or path.stem
    for context in root.findall("context"):
        if context.findtext("name") != CONTEXT:
            continue
        messages: dict[str, str] = {}
        for message in context.findall("message"):
            source = message.findtext("source")
            translation = message.find("translation")
            if not source or translation is None:
                continue
            if translation.get("type") == "unfinished" or translation.text is None:
                raise ValueError(f"Unfinished {CONTEXT} translation in {path.name}: {source}")
            messages[source] = translation.text
        return locale, messages
    raise ValueError(f"Missing {CONTEXT} context in {path.name}")


def generate() -> dict[str, dict[str, str]]:
    catalogs = dict(read_context(path) for path in sorted(QT_I18N_DIR.glob("*.ts")))
    if "en_US" not in catalogs:
        raise ValueError("The en_US web translation catalog is required")
    expected = set(catalogs["en_US"])
    for locale, messages in catalogs.items():
        missing = expected - set(messages)
        extra = set(messages) - expected
        if missing or extra:
            raise ValueError(
                f"Web catalog keys differ for {locale}; missing={sorted(missing)}, extra={sorted(extra)}"
            )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(catalogs, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return catalogs


if __name__ == "__main__":
    result = generate()
    print(f"Generated {OUTPUT.relative_to(ROOT)} for {len(result)} locales")
