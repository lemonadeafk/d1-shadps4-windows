@echo off
rem Starts a Destiny 1 session against the local server. Runs as a normal user; d1_launch.py asks
rem for administrator rights once, only for the small helper that edits the hosts file.
cd /d "%~dp0"
python "%~dp0d1_launch.py" %*
echo.
pause
