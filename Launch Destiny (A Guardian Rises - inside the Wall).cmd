@echo off
rem "A Guardian Rises" started INSIDE THE WALL (bubble 3, its main combat area: 30 squads / 45
rem members spawn). In the game: Set Destination -> Earth -> PATROL THE COSMODROME -> Launch.
rem The room starts dark and empty; tools\mission_director.py then plays it out: Ghost lines,
rem power up, the gate opens, the Fallen arrive. NIGHT-NOTES.md sections 44 and 54.
cd /d "%~dp0"
rem The Ghost's dialogue is served once you are in the world (tools\mission_director.py).
start "mission director" /min python "%~dp0tools\mission_director.py"
python "%~dp0d1_launch.py" --inworld --director --world act_cosmo_m0_highway --checksum 0x8fe07299 --bubbles 22 --chosen 0-21 --env D1_AH_SENSOR_WORLD=0x80cb800d:3 --env D1_AH_ACTIVITY_INDEX=165 --env D1_AH_SENSOR_PLAYER_TEAM=-1 --env "D1_AH_SENSOR_KIND_VALUE=4:0x808007d9:%~dp0capture\values\object_exists.bin" --env D1_AH_SENSOR_KIND_RESEQ=4 --env D1_AH_SENSOR_REPEAT_MAX=8 --name RISESWALL %*
echo.
pause
