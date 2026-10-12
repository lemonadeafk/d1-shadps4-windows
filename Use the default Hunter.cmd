@echo off
rem After you make a Guardian in the game's creator, every launcher serves that Guardian.
rem This goes back to the pre-built level 40 Hunter (the created one stays on disk in
rem C:\d1server\d1preservation\capture-rig\guardians\created; "Create a new Guardian" replaces it).
del "C:\d1server\d1preservation\capture-rig\guardians\current.txt" 2>nul
echo The launchers now serve the default Hunter again.
pause
