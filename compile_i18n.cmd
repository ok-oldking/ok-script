@echo off
echo Checking for unfinished translations...
findstr /C:"type=\"unfinished\"" ok\ui\qt\i18n\*.ts >nul
if %errorlevel% equ 0 (
    echo Error: Unfinished translations found! Please fix them before compiling.
    findstr /N /C:"type=\"unfinished\"" ok\ui\qt\i18n\*.ts
    exit /b 1
)

echo Compiling translations...
.venv\Scripts\pyside6-lrelease ok\ui\qt\i18n\zh_CN.ts
.venv\Scripts\pyside6-lrelease ok\ui\qt\i18n\zh_TW.ts
.venv\Scripts\pyside6-lrelease ok\ui\qt\i18n\ja_JP.ts
.venv\Scripts\pyside6-lrelease ok\ui\qt\i18n\ko_KR.ts
.venv\Scripts\pyside6-lrelease ok\ui\qt\i18n\es_ES.ts
.venv\Scripts\pyside6-lrelease ok\ui\qt\i18n\en_US.ts

echo Compiling resources...
.venv\Scripts\pyside6-rcc ok\ui\qt\qt.qrc -o ok\ui\qt\resources.py
echo Done!
