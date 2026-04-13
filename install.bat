@echo off
title VoiceApp Installer
color 0A
cls

echo.
echo  ==========================================
echo   VoiceApp - Voice to Text
echo   Installing... please wait
echo  ==========================================
echo.

:: Check Python
echo [1/6] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo     Python not found. Downloading Python 3.11...
    curl -L "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -o "%TEMP%\python_setup.exe"
    "%TEMP%\python_setup.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    del "%TEMP%\python_setup.exe"
) else (
    echo     OK - Python found
)

:: Create app folder
echo [2/6] Creating app folder...
set APPDIR=%USERPROFILE%\VoiceApp
if not exist "%APPDIR%" mkdir "%APPDIR%"
echo     OK - %APPDIR%

:: Download files from YOUR GitHub
echo [3/6] Downloading VoiceApp files from GitHub...
set GITHUB=https://raw.githubusercontent.com/ADIVEENA/voiceapp/main

curl -sL "%GITHUB%/tray_app.py"      -o "%APPDIR%\tray_app.py"
curl -sL "%GITHUB%/stt.py"           -o "%APPDIR%\stt.py"
curl -sL "%GITHUB%/nlp.py"           -o "%APPDIR%\nlp.py"
curl -sL "%GITHUB%/audio_capture.py" -o "%APPDIR%\audio_capture.py"
curl -sL "%GITHUB%/text_inject.py"   -o "%APPDIR%\text_inject.py"
curl -sL "%GITHUB%/cursor_mic.py"    -o "%APPDIR%\cursor_mic.py"
curl -sL "%GITHUB%/dictionary.json"  -o "%APPDIR%\dictionary.json"
curl -sL "%GITHUB%/snippets.json"    -o "%APPDIR%\snippets.json"
echo     OK - All files downloaded

:: Install Python packages
echo [4/6] Installing AI packages - please wait 5 minutes...
echo     Downloading Whisper AI model and tools...
echo.

pip install faster-whisper pyaudio pystray Pillow pywin32 keyboard spacy aiohttp --quiet
python -m spacy download en_core_web_sm --quiet
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu --quiet

echo     OK - All AI packages installed

:: Create desktop shortcut
echo [5/6] Creating desktop shortcut...

set LAUNCHER=%APPDIR%\launch.bat
echo @echo off > "%LAUNCHER%"
echo cd /d "%APPDIR%" >> "%LAUNCHER%"
echo start /b pythonw tray_app.py >> "%LAUNCHER%"

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%USERPROFILE%\Desktop\VoiceApp.lnk'); $sc.TargetPath = '%LAUNCHER%'; $sc.WorkingDirectory = '%APPDIR%'; $sc.Description = 'VoiceApp - Voice to Text'; $sc.Save()"

echo     OK - Desktop shortcut created

:: Add to Windows startup
echo [6/6] Setting up autostart...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "VoiceApp" /t REG_SZ /d "\"%LAUNCHER%\"" /f >nul 2>&1
echo     OK - VoiceApp starts with Windows

echo.
echo  ==========================================
echo   INSTALLATION COMPLETE!
echo  ==========================================
echo.
echo   HOW TO USE:
echo   1. Click where you want to type
echo   2. Press Ctrl+Space
echo   3. Speak your text
echo   4. Text appears automatically!
echo.
echo   Starting VoiceApp now...
echo.

cd /d "%APPDIR%"
start /b pythonw tray_app.py

timeout /t 3 /nobreak >nul
echo   VoiceApp is running in your system tray
echo   Look for mic icon bottom right of taskbar
echo.
pause
