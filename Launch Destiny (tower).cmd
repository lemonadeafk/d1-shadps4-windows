@echo off
rem In-world session whose activity host publishes the Tower's world (city_tower_default1) under
rem activity 407, with the scenario facts measured live on 2026-10-10 (run 20261010-020143-WIN-TOWER,
rem two captures agreeing): record city_tower, tag 0x80c7a005, PRIVATE checksum 0x7f0057be,
rem 5 bubbles, all valid -> chosen 0-4. Reach orbit, then: python tools\d1_inworld.py
cd /d "%~dp0"
python "%~dp0d1_launch.py" --inworld --world city_tower_default1 --checksum 0x7f0057be --bubbles 5 --chosen 0-4 --name TOWER %*
echo.
pause
