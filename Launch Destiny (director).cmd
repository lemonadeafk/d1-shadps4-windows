@echo off
rem Director session: the Solar System map works, the Tower is selectable and LAUNCH starts the
rem real activity flow (it currently stops in matchmaking - see NIGHT-NOTES.md section 8).
rem Publishes the Tower's world like "Launch Destiny (tower).cmd".
cd /d "%~dp0"
python "%~dp0d1_launch.py" --inworld --director --world city_tower_default1 --checksum 0x7f0057be --bubbles 5 --chosen 0-4 --name DIRECTOR %*
echo.
pause
