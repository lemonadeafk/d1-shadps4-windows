@echo off
rem Same as "Launch Destiny.cmd", plus the activity host and the geared character fixture that
rem tools\d1_inworld.py needs. Reach orbit, then run:  python tools\d1_inworld.py
cd /d "%~dp0"
python "%~dp0d1_launch.py" --inworld --name INWORLD %*
echo.
pause
