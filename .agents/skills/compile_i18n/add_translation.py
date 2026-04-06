import xml.etree.ElementTree as ET
import argparse
import os

def update_translation(ts_path, context_name, source_text, translation_text=None):
    if not os.path.exists(ts_path):
        print(f"File not found: {ts_path}")
        return False

    tree = ET.parse(ts_path)
    root = tree.getroot()
    
    context = None
    for ctx in root.findall('context'):
        name = ctx.find('name')
        if name is not None and name.text == context_name:
            context = ctx
            break
            
    if context is None:
        context = ET.SubElement(root, 'context')
        name = ET.SubElement(context, 'name')
        name.text = context_name
        
    message = None
    for msg in context.findall('message'):
        src = msg.find('source')
        if src is not None and src.text == source_text:
            message = msg
            break
            
    if message is None:
        message = ET.SubElement(context, 'message')
        source = ET.SubElement(message, 'source')
        source.text = source_text
        
    translation = message.find('translation')
    if translation is None:
        translation = ET.SubElement(message, 'translation')
        
    if translation_text is not None:
        translation.text = translation_text
        if 'type' in translation.attrib:
            del translation.attrib['type']
    elif translation.text is None:
        translation.set('type', 'unfinished')
        
    if hasattr(ET, 'indent'):
        ET.indent(tree, space="    ", level=0)
        
    tree.write(ts_path, encoding='utf-8', xml_declaration=True)
    return True

def main():
    parser = argparse.ArgumentParser(description="Add or update a translation across .ts files.")
    parser.add_argument("--dir", default="ok/gui/i18n", help="Directory containing .ts files.")
    parser.add_argument("--context", required=True, help="The context name, e.g., 'MainWindow'")
    parser.add_argument("--source", required=True, help="The source string")
    parser.add_argument("--zh_cn", help="Translation for zh_CN.ts")
    parser.add_argument("--zh_tw", help="Translation for zh_TW.ts")
    parser.add_argument("--en_us", help="Translation for en_US.ts (defaults to source)")
    parser.add_argument("--ja_jp", help="Translation for ja_JP.ts")
    parser.add_argument("--ko_kr", help="Translation for ko_KR.ts")
    parser.add_argument("--es_es", help="Translation for es_ES.ts")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.dir):
        print(f"Directory {args.dir} not found. Please run from workspace root.")
        return

    translations = {
        'zh_CN.ts': args.zh_cn,
        'zh_TW.ts': args.zh_tw,
        'en_US.ts': args.en_us if args.en_us is not None else args.source,
        'ja_JP.ts': args.ja_jp,
        'ko_KR.ts': args.ko_kr,
        'es_ES.ts': args.es_es,
    }

    for filename in os.listdir(args.dir):
        if not filename.endswith('.ts'):
            continue
            
        filepath = os.path.join(args.dir, filename)
        translation_text = translations.get(filename)
        
        print(f"Updating {filename}...")
        update_translation(filepath, args.context, args.source, translation_text)
        
    print("Done. Use compile_i18n.cmd to compile to .qm files.")

if __name__ == "__main__":
    main()
