@echo off
rem "A Guardian Rises" started INSIDE THE WALL (bubble 3, its main combat area: 30 squads / 45
rem members spawn). In the game: Set Destination -> Earth -> PATROL THE COSMODROME -> Launch.
rem The room starts dark and empty; tools\mission_director.py then plays it out: Ghost lines,
rem power up, the gate opens, the Fallen arrive. NIGHT-NOTES.md sections 44 and 54.
cd /d "%~dp0"
rem You start UNARMED and are handed the Khvostov when you reach the rifle: the login server
rem pushes the changed loadout to the running game (tools\loadout_variant.py, section 63).
set VARIANTS=C:\d1server\d1preservation\capture-rig\variants
python "%~dp0tools\loadout_variant.py" unarmed --unarmed >nul
python "%~dp0tools\loadout_variant.py" khvostov --primary 3598 --special none --heavy none >nul
python "%~dp0tools\loadout_variant.py" khvostov_sniper --primary 3598 --special 3606 --heavy none >nul
del "%~dp0inject\loadout-swap.txt" 2>nul
rem The Ghost's dialogue is served once you are in the world (tools\mission_director.py).
start "mission director" /min python "%~dp0tools\mission_director.py"
python "%~dp0d1_launch.py" --inworld --director --world act_cosmo_m0_highway --checksum 0x8fe07299 --bubbles 22 --chosen 0-21 --env D1_AH_SENSOR_WORLD=0x80cb800d:3 --env D1_AH_ACTIVITY_INDEX=163 --env D1_AH_SENSOR_PLAYER_TEAM=-1 --env "D1_AH_SENSOR_KIND_VALUE=4:0x808007d9:%~dp0capture\values\object_exists.bin" --env D1_AH_SENSOR_KIND_RESEQ=4 --env D1_AH_SENSOR_REPEAT_MAX=3 --env "D1_ROSTER_DIR=%VARIANTS%\unarmed\roster" --env "D1_CHARACTER_FILE=%VARIANTS%\unarmed\char.bin" --env "D1_SWAP_TRIGGER=%~dp0inject\loadout-swap.txt" --name RISESWALL %* --env D1_ORACLE_EXTRA_TAGS=0x8080279a --env D1_AH_SENSOR_SLOT_VALUE=fc0e45a3:5:808007d9:"%~dp0capture\values\gate_open.bin",fc0e45a3:6:808007d9:"%~dp0capture\values\gate_open.bin",fc0e45a3:95:80800868:"%~dp0capture\values\member_exists.bin",fc0e45a3:4:808007d9:"%~dp0capture\values\gate_closed.bin",fc0e45a3:1:808007d9:"%~dp0capture\values\gate_open.bin"
echo.
pause
