@echo off
echo Compiling translations...
.venv\Scripts\pyside6-lrelease ok\gui\i18n\zh_CN.ts
.venv\Scripts\pyside6-lrelease ok\gui\i18n\zh_TW.ts
.venv\Scripts\pyside6-lrelease ok\gui\i18n\ja_JP.ts
.venv\Scripts\pyside6-lrelease ok\gui\i18n\ko_KR.ts
.venv\Scripts\pyside6-lrelease ok\gui\i18n\es_ES.ts
.venv\Scripts\pyside6-lrelease ok\gui\i18n\en_US.ts

echo Compiling resources...
.venv\Scripts\pyside6-rcc ok\gui\qt.qrc -o ok\gui\resources.py
echo Done!
