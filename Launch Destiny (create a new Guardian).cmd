@echo off
rem The game's real opening. Starts with NO character, so the game shows its own creator:
rem choose a class, race, gender and look, press FINISH. Then, by itself, the game plays the
rem intro film and goes into the first mission - no Director, no map (unlock flag 2837 is what
rem its "prologue" step asks for; the mission is activity 163). The server builds the Guardian
rem you chose (level 1, the class's starter armour, unarmed until you take the rifle) and
rem tools\mission_director.py plays the mission. Afterwards every launcher serves this Guardian;
rem "Use the default Hunter.cmd" goes back to the pre-built Hunter.
rem NIGHT-NOTES.md sections 66-72.
cd /d "%~dp0"
del "%~dp0inject\loadout-swap.txt" 2>nul
start "mission director" /min python "%~dp0tools\mission_director.py" --script mission
python "%~dp0d1_launch.py" --inworld --director --world act_cosmo_m0_highway --checksum 0x8fe07299 --bubbles 22 --chosen 0-21 --env D1_EMPTY_ROSTER=1 --env D1_UNLOCK_FLAGS=98,131,419,440,834,2479,2496,2497,2500,2501,2502,2503,2667,4917,4992,5015,5987,6018,2837 --env D1_AH_SENSOR_WORLD=0x80cb800d:14 --env D1_AH_ACTIVITY_INDEX=163 --env D1_AH_SENSOR_PLAYER_TEAM=-1 --env "D1_AH_SENSOR_KIND_VALUE=2:0x80800868:%~dp0capture\values\member_exists.bin,4:0x808007d9:%~dp0capture\values\object_exists.bin" --env D1_AH_SENSOR_KIND_RESEQ=4 --env D1_AH_SENSOR_KIND_SKIP=2@3 --env D1_AH_SENSOR_FOLLOW_MAX=3 --env D1_AH_SENSOR_REPEAT_MAX=3 --name OPENING %*
echo.
pause
