@echo off
rem One admin prompt: leaves the Destiny hostname redirect in the hosts file so sessions can be
rem started without anyone clicking Yes. Undo with "Undo unattended runs.cmd".
cd /d "%~dp0"
python "%~dp0d1_launch.py" --hosts-persist
echo.
pause
