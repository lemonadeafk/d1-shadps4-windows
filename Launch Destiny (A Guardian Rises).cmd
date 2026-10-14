@echo off
rem The first story mission, "A Guardian Rises" (act_cosmo_m0_highway), served with no memory
rem edits. In the game: Set Destination -> Earth -> PATROL THE COSMODROME -> Launch.
rem (The mission has no map node for an existing character; the game loads the world the server
rem names, so the Patrol node is used as the launch button. NIGHT-NOTES.md section 32.)
rem
rem You start on the highway. The way into the Wall: up the stairs at the Wall's foot right
rem behind the spawn, through the red-lit corridor, up and along inside. When you walk in, the
rem server follows you into that area and tools\mission_director.py plays the room: the Ghost
rem and its torch, the Ghost's lines, power up, the gate opens, the Fallen arrive.
rem NIGHT-NOTES.md sections 54-58.
cd /d "%~dp0"
rem You start UNARMED and are handed the Khvostov when you reach the rifle: the login server
rem pushes the changed loadout to the running game (tools\loadout_variant.py, section 63).
set VARIANTS=C:\d1server\d1preservation\capture-rig\variants
python "%~dp0tools\loadout_variant.py" unarmed --unarmed >nul
python "%~dp0tools\loadout_variant.py" khvostov --primary 3598 --special none --heavy none >nul
python "%~dp0tools\loadout_variant.py" khvostov_sniper --primary 3598 --special 3606 --heavy none >nul
del "%~dp0inject\loadout-swap.txt" 2>nul
rem The mission is played by the activity host itself (tools\mission_compile.py builds it,
rem NIGHT-NOTES section 84); mission_director.py only records triggers and the walked path.
python "%~dp0tools\mission_compile.py" --script mission --out "%~dp0inject\mission"
start "mission director" /min python "%~dp0tools\mission_director.py" --log-only
rem A Guardian made in the creator gets XP for its kills, and the completion of the mission is
rem recorded for it (Restoration opens): tools\xp_service.py, tools\progress.py, NIGHT-NOTES 89-97.
if exist "C:\d1server\d1preservation\capture-rig\guardians\current.txt" start "xp service" /min python "%~dp0tools\xp_service.py" --wait-new
python "%~dp0d1_launch.py" --inworld --director --world act_cosmo_m0_highway --checksum 0x8fe07299 --bubbles 22 --chosen 0-21 --env D1_AH_MISSION="%~dp0inject\mission\mission.txt" --env D1_AH_SENSOR_WORLD=0x80cb800d:14 --env D1_AH_ACTIVITY_INDEX=163 --env D1_AH_SENSOR_PLAYER_TEAM=-1 --env "D1_AH_SENSOR_KIND_VALUE=2:0x80800868:%~dp0capture\values\member_exists.bin,4:0x808007d9:%~dp0capture\values\object_exists.bin" --env D1_AH_SENSOR_KIND_RESEQ=4 --env D1_AH_SENSOR_KIND_SKIP=2@3 --env D1_AH_SENSOR_FOLLOW_MAX=3 --env D1_AH_SENSOR_REPEAT_MAX=3 --env "D1_ROSTER_DIR=%VARIANTS%\unarmed\roster" --env "D1_CHARACTER_FILE=%VARIANTS%\unarmed\char.bin" --env "D1_SWAP_TRIGGER=%~dp0inject\loadout-swap.txt" --name RISES %* --env D1_ORACLE_EXTRA_TAGS=0x8080279a --env D1_AH_SENSOR_SLOT_VALUE=fc0e45a3:5:808007d9:"%~dp0capture\values\gate_absent.bin",fc0e45a3:6:808007d9:"%~dp0capture\values\gate_absent.bin",fc0e45a3:95:80800868:"%~dp0capture\values\member_exists.bin",fc0e45a3:4:808007d9:"%~dp0capture\values\gate_closed.bin",fc0e45a3:1:808007d9:"%~dp0capture\values\gate_open.bin"
echo.
pause
