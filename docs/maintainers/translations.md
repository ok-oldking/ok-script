# Compile i18n

Repository-maintainer instructions for ok-script's bundled Qt translations. Consumer applications maintain their own translations separately.

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
   & $py .\docs\maintainers\scripts\add_translation.py --context "YourContext" --source "Your Source String" --zh_cn "Your Chinese String"
   ```
   **IMPORTANT WARNING: DO NOT use `pyside6-lupdate` as it corrupts and deletes existing translations. Always modify the XML nodes natively or use the python script!**
4. Check that the added translations are complete. You must replace `<translation type="unfinished" />` with `<translation>Your Translation</translation>`.
5. Compile the `.qm` files and the Qt resource module from `ok/ui/qt`. The project venv uses `ok-pyside-minimal`, which ships no Qt tools, so `lrelease` and `rcc` come from a separate tools venv with official PySide6-Essentials of the same version. Create it once from the repository root:

```powershell
python -m venv .venv-qt-tools
.\.venv-qt-tools\Scripts\python.exe -m pip install "PySide6-Essentials==$(.\.venv\Scripts\python.exe -c 'import PySide6; print(PySide6.__version__)')"
```

Then, from `ok/ui/qt`:

// turbo
```powershell
$bin = (Resolve-Path ..\..\..\.venv-qt-tools\Scripts).Path
Get-ChildItem i18n\*.ts | ForEach-Object { & "$bin\pyside6-lrelease.exe" $_.FullName -qm ($_.FullName -replace '\.ts$', '.qm') }
& "$bin\pyside6-rcc.exe" qt.qrc -o resources.py
```

Never install PySide6-Essentials into `.venv`: both packages own the `PySide6` folder.
