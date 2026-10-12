@echo off
rem Starts with NO character, so the game opens its own creator: choose a class, race, gender
rem and look, press FINISH. The server builds that Guardian (level 1, the class's starter
rem armour, the Khvostov) and pushes it to the game about 20 seconds later; from then on every
rem launcher serves it. "Use the default Hunter.cmd" goes back to the pre-built Hunter.
rem NIGHT-NOTES.md sections 66-69.
cd /d "%~dp0"
python "%~dp0d1_launch.py" --inworld --director --world city_tower_default1 --checksum 0x7f0057be --bubbles 5 --chosen 0-4 --env D1_EMPTY_ROSTER=1 --name CREATE %*
echo.
pause
