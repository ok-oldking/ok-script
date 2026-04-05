---
name: Compile i18n
description: How to add i18n to all the ts files, and use the compile_i18n.cmd command to compile the ts files
---

# Compile i18n

When you are instructed to add or update internationalization (i18n) translations for this project, please follow these steps:

1. Identify the new strings that need to be translated.
2. Edit the `.ts` translation files located in the `ok/gui/i18n/` directory. Typically, these files include:
   - `zh_CN.ts` (Simplified Chinese)
   - `zh_TW.ts` (Traditional Chinese)
   - `ja_JP.ts` (Japanese)
   - `ko_KR.ts` (Korean)
   - `es_ES.ts` (Spanish)
   - `en_US.ts` (English)
3. Ensure that your new translations are correctly added under the appropriate `<context>` and `<message>` blocks in each XML file. If you are adding many translations, consider writing a temporary python script to automate the XML injection and prevent errors.
4. After updating the `.ts` files, compile them into `.qm` binary format by leveraging the provided script. Run the following command from the workspace root:

// turbo
```powershell
.\compile_i18n.cmd
```

This will run `pyside6-lrelease` on all language files and generate the corresponding `.qm` files used by the application, as well as compile updated resources if necessary.
