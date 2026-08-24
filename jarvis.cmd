@echo off
setlocal enabledelayedexpansion

:: Get the directory of this batch file
set "WIN_PATH=%~dp0"

:: Check if the user is launching Audio Mode (case-insensitive check)
set "IS_AUDIO=0"
set "ARGS=%*"
if not "!ARGS!"=="!ARGS:audio=!" set "IS_AUDIO=1"

:: If Audio mode, run Windows native and exit
if "!IS_AUDIO!"=="1" goto run_windows

:: Otherwise, prepare WSL path and run WSL
set "WIN_PATH=%WIN_PATH:\=/%"
set "DRIVE=%WIN_PATH:~0,1%"
set "REST_PATH=%WIN_PATH:~2%"

:: Lower-case the drive letter safely
set "DRIVE_LOWER=!DRIVE!"
if /I "!DRIVE!"=="A" set "DRIVE_LOWER=a"
if /I "!DRIVE!"=="B" set "DRIVE_LOWER=b"
if /I "!DRIVE!"=="C" set "DRIVE_LOWER=c"
if /I "!DRIVE!"=="D" set "DRIVE_LOWER=d"
if /I "!DRIVE!"=="E" set "DRIVE_LOWER=e"
if /I "!DRIVE!"=="F" set "DRIVE_LOWER=f"
if /I "!DRIVE!"=="G" set "DRIVE_LOWER=g"
if /I "!DRIVE!"=="H" set "DRIVE_LOWER=h"
if /I "!DRIVE!"=="I" set "DRIVE_LOWER=i"
if /I "!DRIVE!"=="J" set "DRIVE_LOWER=j"
if /I "!DRIVE!"=="K" set "DRIVE_LOWER=k"
if /I "!DRIVE!"=="L" set "DRIVE_LOWER=l"
if /I "!DRIVE!"=="M" set "DRIVE_LOWER=m"
if /I "!DRIVE!"=="N" set "DRIVE_LOWER=n"
if /I "!DRIVE!"=="O" set "DRIVE_LOWER=o"
if /I "!DRIVE!"=="P" set "DRIVE_LOWER=p"
if /I "!DRIVE!"=="Q" set "DRIVE_LOWER=q"
if /I "!DRIVE!"=="R" set "DRIVE_LOWER=r"
if /I "!DRIVE!"=="S" set "DRIVE_LOWER=s"
if /I "!DRIVE!"=="T" set "DRIVE_LOWER=t"
if /I "!DRIVE!"=="U" set "DRIVE_LOWER=u"
if /I "!DRIVE!"=="V" set "DRIVE_LOWER=v"
if /I "!DRIVE!"=="W" set "DRIVE_LOWER=w"
if /I "!DRIVE!"=="X" set "DRIVE_LOWER=x"
if /I "!DRIVE!"=="Y" set "DRIVE_LOWER=y"
if /I "!DRIVE!"=="Z" set "DRIVE_LOWER=z"

set "WSL_PATH=/mnt/!DRIVE_LOWER!!REST_PATH!"
if "!WSL_PATH:~-1!"=="/" set "WSL_PATH=!WSL_PATH:~0,-1!"

:: Execute inside WSL 2
wsl -e bash -c "export PATH=\"$HOME/.local/bin:$PATH\" && cd '!WSL_PATH!' && poetry run python main.py %*"
exit /b

:run_windows
echo [🎙️] Launching Jarvis in Windows Native Audio Mode (GPU & Mic)...
cd /d "!WIN_PATH!"
poetry run python main.py %*
exit /b
