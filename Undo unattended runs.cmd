@echo off
rem Removes the persistent Destiny hostname redirect (and restores shadPS4 settings if a session
rem was cut short). PSN's web login works again afterwards.
cd /d "%~dp0"
python "%~dp0d1_launch.py" --restore
echo.
pause
