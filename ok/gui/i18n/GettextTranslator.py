import gettext
import os
import re

from ok import ensure_dir_for_file, get_path_relative_to_exe, delete_if_exists, get_language_fallbacks


def __get_root():
    return get_path_relative_to_exe('i18n')


def update_po_file(strings, language_code):
    import polib
    # If the .po file exists, load it
    folder = __get_root()
    filename = str(os.path.join(folder, language_code, 'LC_MESSAGES', "ok.po"))
    if os.path.exists(filename):
        po = polib.pofile(filename)
        existing_ids = {entry.msgid: entry for entry in po}
    else:
        ensure_dir_for_file(filename)
        # Otherwise, create a new .po file
        po = polib.POFile()
        po.metadata = {
            'Project-Id-Version': '1.0',
            'Report-Msgid-Bugs-To': 'you@example.com',
            'Last-Translator': 'you@example.com',
            'Language-Team': 'English',
            'MIME-Version': '1.0',
            'Content-Type': 'text/plain; charset=UTF-8',
            'Content-Transfer-Encoding': '8bit',
        }
        existing_ids = {}

    # Add the new strings to the .po file
    for string in sorted(strings):
        if string not in existing_ids:
            entry = polib.POEntry(msgid=string, msgstr='')
            po.append(entry)

    # Remove obsolete keys
    # for msgid in list(existing_ids.keys()):
    #     if msgid not in strings:
    #         po.remove(existing_ids[msgid])

    # Save the .po file
    po.wrapwidth = 999999
    po.save(filename)
    return folder


def convert_to_mo_files():
    import polib
    dir = __get_root()
    for root, dirs, files in os.walk(dir):
        print(f'Converting {root} {dirs} {files}')
        for file in files:
            # If the file is a .po file
            if file.endswith('.po'):
                # Get the full path of the .po file
                po_path = os.path.join(root, file)
                if 'en' in po_path:
                    new_path = po_path.replace('.po', '.po2')
                    duplicate_spaced_msgids(po_path, new_path)
                    po_path = new_path

                # Load the .po file
                po = polib.pofile(str(po_path))
                # Get the full path of the .mo file
                mo_path = os.path.splitext(po_path)[0] + '.mo'
                # Save as a .mo file
                po.save_as_mofile(mo_path)

                if 'en' in po_path:
                    delete_if_exists(po_path)


def get_translations(language):
    fallback_list = get_language_fallbacks(language)
    gettext.textdomain('ok')
    dir_i18n = get_path_relative_to_exe('i18n')
    return gettext.translation('ok', dir_i18n, languages=fallback_list)


def get_ocr_translations(language):
    fallback_list = get_language_fallbacks(language)
    dir_i18n = get_path_relative_to_exe('i18n')
    return gettext.translation('ocr', dir_i18n, languages=fallback_list)


def duplicate_spaced_msgids(input_po_path, output_po_path):
    """
    Reads a PO file, duplicates it, and for each entry where
    msgid contains a space, adds a new entry with the space removed
    from msgid and the same msgstr.
    """
    try:
        with open(input_po_path, 'r', encoding='utf-8') as infile, \
                open(output_po_path, 'w', encoding='utf-8') as outfile:
            last_msgid_line = None
            last_msgid_value = None
            for line in infile:
                outfile.write(line)  # Write the original line first
                stripped_line = line.strip()
                # Use regex to capture msgid value
                msgid_match = re.match(r'^msgid\s+"(.*)"$', stripped_line)
                if msgid_match:
                    last_msgid_line = line
                    last_msgid_value = msgid_match.group(1)
                    # Reset msgstr state in case msgid appears without msgstr
                    continue  # Move to next line once msgid is found
                # Use regex to capture msgstr value, only if we just saw a msgid
                msgstr_match = re.match(r'^msgstr\s+"(.*)"$', stripped_line)
                if msgstr_match and last_msgid_value is not None:
                    current_msgstr_value = msgstr_match.group(1)
                    # Check if the *last seen* msgid value contained a space
                    if ' ' in last_msgid_value:
                        new_msgid_value = last_msgid_value.replace(' ', '')
                        # Write the new pair
                        outfile.write(f'msgid "{new_msgid_value}"\n')
                        outfile.write(f'msgstr "{current_msgstr_value}"\n')
                        # Optionally add a blank line for separation
                        outfile.write('\n')
                    # Reset state after processing msgstr for the last msgid
                    last_msgid_line = None
                    last_msgid_value = None
                # If line is not msgid or msgstr, reset state to avoid mismatches
                elif not stripped_line.startswith('#') and stripped_line != '':
                    last_msgid_line = None
                    last_msgid_value = None
    except FileNotFoundError:
        print(f"Error: Input file '{input_po_path}' not found.")
    except Exception as e:
        print(f"An error occurred: {e}")
