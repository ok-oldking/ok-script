setlocal enabledelayedexpansion
set "files="
for /f "delims=" %%i in ('dir /s /b *.py') do set "files=!files! %%~fi"
echo !files!
endlocal
pyside6-lupdate files -target-language zh_CN -no-obsolete -source-language en_US -ts zh_CN.ts