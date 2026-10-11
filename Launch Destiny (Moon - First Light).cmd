@echo off
rem The Crucible map First Light (pvp_moonbase) as Elimination, served with no memory edits.
rem In the game: Set Destination -> Earth -> PATROL THE COSMODROME -> Launch (any node works:
rem the game loads the world the server names). NIGHT-NOTES.md section 34.
cd /d "%~dp0"
python "%~dp0d1_launch.py" --inworld --director --world pvp_moonbase --checksum 0x5966e491 --bubbles 1 --chosen 0 --env D1_AH_SENSOR_WORLD=0x80f08003 --env D1_AH_ACTIVITY_INDEX=407 --env D1_AH_SENSOR_PLAYER_TEAM=-1 --name MOON %*
echo.
pause
