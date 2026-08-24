@echo off
setlocal enabledelayedexpansion

:: Check if the user is launching Audio Mode (which requires Windows native drivers)
set "IS_AUDIO=0"
set "ARGS=%*"
if defined ARGS (
    echo !ARGS! | findstr /i "audio" >nul
    if !errorlevel! equ 0 set "IS_AUDIO=1"
)

:: Get the directory of this batch file
set "WIN_PATH=%~dp0"

if "!IS_AUDIO!"=="1" (
    echo [🎙️] Launching Jarvis in Windows Native Audio Mode (GPU & Mic)...
    cd /d "!WIN_PATH!"
    poetry run python main.py %*
    exit /b
)

:: Convert Windows backslashes to forward slashes for WSL
set "WIN_PATH=%WIN_PATH:\=/%"

:: Extract drive letter (first character) and lower-case it
set "DRIVE=%WIN_PATH:~0,1%"
for %%i in (a b c d e f g h i j k l m n o p q r s t u v w x y z) do (
    if /I "!DRIVE!"=="%%i" set "DRIVE_LOWER=%%i"
)

:: Reconstruct path in WSL style: /mnt/<drive_letter>/<rest_of_path>
set "REST_PATH=%WIN_PATH:~2%"
set "WSL_PATH=/mnt/!DRIVE_LOWER!!REST_PATH!"

:: Trim trailing slash if present
if "!WSL_PATH:~-1!"=="/" set "WSL_PATH=!WSL_PATH:~0,-1!"

:: Execute python main.py inside WSL 2, passing through all CLI arguments
wsl -e bash -c "export PATH=\"$HOME/.local/bin:$PATH\" && cd '!WSL_PATH!' && poetry run python main.py %*"
