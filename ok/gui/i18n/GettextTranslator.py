import gettext
import os

from ok.util.path import ensure_dir_for_file, resource_path, get_path_relative_to_exe


def __get_root():
    return resource_path(os.path.join('i18n'))


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
    for root, dirs, files in os.walk(__get_root()):
        for file in files:
            # If the file is a .po file
            if file.endswith('.po'):
                # Get the full path of the .po file
                po_path = os.path.join(root, file)
                # Load the .po file
                po = polib.pofile(str(po_path))
                # Get the full path of the .mo file
                mo_path = os.path.splitext(po_path)[0] + '.mo'
                # Save as a .mo file
                po.save_as_mofile(mo_path)


def get_translations(language):
    gettext.textdomain('ok')
    dir_i18n = get_path_relative_to_exe('i18n')
    return gettext.translation('ok', dir_i18n, languages=[language])
