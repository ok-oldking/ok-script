"""Merge newly added Qt Linguist <message> entries from a PR ref into HEAD's .ts files."""
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

LOCALES = ('en_US', 'es_ES', 'ja_JP', 'ko_KR', 'zh_CN', 'zh_TW')


def collect_messages(raw_xml: bytes) -> dict[tuple[str | None, str | None], tuple[str | None, dict[str, str]]]:
    root = ET.fromstring(raw_xml)
    messages = {}
    for ctx in root.findall('context'):
        cname = ctx.findtext('name')
        for msg in ctx.findall('message'):
            src = msg.findtext('source')
            tr_el = msg.find('translation')
            if tr_el is not None:
                messages[(cname, src)] = (tr_el.text, dict(tr_el.attrib))
    return messages


def main() -> int:
    if len(sys.argv) != 2:
        print('Usage: merge_ts.py <pr-ref>', file=sys.stderr)
        return 2
    pr_ref = sys.argv[1]
    base = subprocess.check_output(['git', 'merge-base', 'HEAD', pr_ref], text=True).strip()

    for loc in LOCALES:
        rel = f'ok/ui/qt/i18n/{loc}.ts'
        base_xml = subprocess.check_output(['git', 'show', f'{base}:{rel}'])
        pr_xml = subprocess.check_output(['git', 'show', f'{pr_ref}:{rel}'])
        base_map = collect_messages(base_xml)
        pr_map = collect_messages(pr_xml)
        added = {k: v for k, v in pr_map.items() if k not in base_map}

        path = Path(rel)
        tree = ET.parse(path)
        root = tree.getroot()
        ctx_by_name = {ctx.findtext('name'): ctx for ctx in root.findall('context')}
        inserted = 0
        for (cname, src), (tr, attrib) in added.items():
            ctx = ctx_by_name.get(cname)
            if ctx is None:
                ctx = ET.SubElement(root, 'context')
                name_el = ET.SubElement(ctx, 'name')
                name_el.text = cname
                ctx_by_name[cname] = ctx
            existing = {m.findtext('source') for m in ctx.findall('message')}
            if src in existing:
                continue
            msg = ET.SubElement(ctx, 'message')
            s = ET.SubElement(msg, 'source')
            s.text = src
            t = ET.SubElement(msg, 'translation', attrib)
            t.text = tr
            inserted += 1
        ET.indent(tree, space='    ')
        xml_bytes = (
            b'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n'
            + ET.tostring(root, encoding='utf-8')
            + b'\n'
        )
        path.write_bytes(xml_bytes)
        print(f'{loc}: inserted {inserted} messages (out of {len(added)} new in {pr_ref})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
