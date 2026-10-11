@echo off
rem The first story mission, "A Guardian Rises" (act_cosmo_m0_highway), served with no memory
rem edits. In the game: Set Destination -> Earth -> PATROL THE COSMODROME -> Launch.
rem (The mission has no map node for an existing character; the game loads the world the server
rem names, so the Patrol node is used as the launch button. NIGHT-NOTES.md section 32.)
cd /d "%~dp0"
python "%~dp0d1_launch.py" --inworld --director --world act_cosmo_m0_highway --checksum 0x8fe07299 --bubbles 22 --chosen 0-21 --env D1_AH_SENSOR_WORLD=0x80cb800d:14 --env D1_AH_ACTIVITY_INDEX=165 --env D1_AH_SENSOR_PLAYER_TEAM=-1 --env "D1_AH_SENSOR_KIND_VALUE=2:0x80800868:%~dp0capturealues\member_exists.bin,4:0x808007d9:%~dp0capturealues\object_exists.bin" --env D1_AH_SENSOR_KIND_RESEQ=4 --name RISES %*
echo.
pause
