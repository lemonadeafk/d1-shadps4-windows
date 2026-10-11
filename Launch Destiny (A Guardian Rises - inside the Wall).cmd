@echo off
rem "A Guardian Rises" started INSIDE THE WALL (bubble 3, its main combat area: 30 squads / 45
rem members spawn). In the game: Set Destination -> Earth -> PATROL THE COSMODROME -> Launch.
rem It is pitch dark in there, as in the real mission. NIGHT-NOTES.md section 44.
cd /d "%~dp0"
python "%~dp0d1_launch.py" --inworld --director --world act_cosmo_m0_highway --checksum 0x8fe07299 --bubbles 22 --chosen 0-21 --env D1_AH_SENSOR_WORLD=0x80cb800d:3 --env D1_AH_ACTIVITY_INDEX=165 --env D1_AH_SENSOR_PLAYER_TEAM=-1 --name RISESWALL %*
echo.
pause
