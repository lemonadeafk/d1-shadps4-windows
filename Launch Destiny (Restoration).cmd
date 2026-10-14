@echo off
rem The second story mission, "Restoration" (act_cosmo_m1_dome_a), served with no memory edits.
rem In the game: Director -> Earth -> Patrol the Cosmodrome -> Launch (the server loads Restoration;
rem from the Tower node the world loads but the Guardian is never placed - black screen). You start inside Hive dome A at the foot of the Lunar Complex: up the steps
rem to the gate (HEAD TO SKYWATCH, then UNLOCK THE GATE - it rises a few seconds later), the
rem Hive inside, the wizard upstairs (KILL THE HIVE WIZARD); its death ends the mission with the
rem post-game screens of the game itself, then hold triangle for orbit. NIGHT-NOTES.md sections 86-88.
rem A Guardian made in the creator gets XP for its kills and the completion flag of the mission
rem (tools\xp_service.py, tools\progress.py - XP amounts are placeholders, section 89).
cd /d "%~dp0"
del "%~dp0inject\loadout-swap.txt" 2>nul
python "%~dp0tools\mission_compile.py" --script restoration --out "%~dp0inject\mission-restoration"
if exist "C:\d1server\d1preservation\capture-rig\guardians\current.txt" start "xp service" /min python "%~dp0tools\xp_service.py" --wait-new
python "%~dp0d1_launch.py" --inworld --director --world act_cosmo_m1_dome_a --checksum 0x42fe77a5 --bubbles 22 --chosen 0-21 --env D1_AH_MISSION="%~dp0inject\mission-restoration\mission.txt" --env D1_AH_SENSOR_WORLD=0x80cb804b:8 --env D1_AH_ACTIVITY_INDEX=165 --env D1_AH_SENSOR_PLAYER_TEAM=-1 --env "D1_AH_SENSOR_KIND_VALUE=2:0x80800868:%~dp0capture\values\member_exists.bin,4:0x808007d9:%~dp0capture\values\object_exists.bin" --env D1_AH_SENSOR_KIND_RESEQ=4 --env D1_AH_SENSOR_KIND_SKIP=2@8 --env D1_AH_SENSOR_FOLLOW_MAX=3 --env D1_AH_SENSOR_REPEAT_MAX=3 --name RESTORATION %*
echo.
pause
