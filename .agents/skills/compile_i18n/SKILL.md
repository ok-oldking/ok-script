---
name: Compile i18n
description: How to update Qt translations and generate the web i18n catalog
---

# Compile i18n

When you are instructed to add or update internationalization (i18n) translations for this project, please follow these steps:

1. Identify the new strings that need to be translated.
2. Edit the `.ts` translation files located in the `ok/ui/qt/i18n/` directory. Typically, these files include:
   - `zh_CN.ts` (Simplified Chinese)
   - `zh_TW.ts` (Traditional Chinese)
   - `ja_JP.ts` (Japanese)
   - `ko_KR.ts` (Korean)
   - `es_ES.ts` (Spanish)
   - `en_US.ts` (English)
3. Ensure that your new translations are correctly added under the appropriate `<context>` and `<message>` blocks in each XML file, without the `type="unfinished"` attribute. If you are adding many translations, or just want to minimize errors, use the provided `add_translation.py` script to automate the XML injection:
   ```powershell
   $py = if (Test-Path .\.venv\Scripts\python.exe) { ".\.venv\Scripts\python.exe" } else { "python" }
   & $py .\.agents\skills\compile_i18n\add_translation.py --context "YourContext" --source "Your Source String" --zh_cn "Your Chinese String"
   ```
   **IMPORTANT WARNING: DO NOT use `pyside6-lupdate` as it corrupts and deletes existing translations. Always modify the XML nodes natively or use the python script!**
4. Check that the translations added for the `WebUI` context are complete. You must replace `<translation type="unfinished" />` with `<translation>Your Translation</translation>`.
5. Generate the web catalog from the `WebUI` context by running this command from the workspace root:

// turbo
```powershell
npm run i18n
```

`npm run dev` and `npm run build` also run this generator automatically.
