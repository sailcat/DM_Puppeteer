@echo off
echo ============================================
echo  Building DM Puppeteer...
echo ============================================
echo.

REM Install dependencies
pip install -r requirements.txt

echo.
echo Building executable...

pyinstaller --onefile --windowed ^
    --name "DM Puppeteer" ^
    --add-data "dm_puppeteer;dm_puppeteer" ^
    --hidden-import "pynput.keyboard._win32" ^
    --hidden-import "pynput.mouse._win32" ^
    --hidden-import "StreamDeck" ^
    --hidden-import "hid" ^
    --hidden-import "obsws_python" ^
    run.py

echo.
echo ============================================
echo  Build complete!
echo.
echo  Your executable: dist\DM Puppeteer.exe
echo.
echo  To distribute, just give Raph:
echo    - DM Puppeteer.exe
echo    (The app creates its own data folder
echo     next to the exe automatically)
echo ============================================
pause
