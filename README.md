# Destiny 1 on shadPS4 (Windows) - local server glue

Windows glue for running Destiny 1 (CUSA00219, patch 01.29) on shadPS4 against the
[d1preservation](https://gitlab.com/aknumbers/d1preservation) server. As of 2026-10-10:
Director -> Tower launch, Guardian spawned with no memory pokes (all state served by the
activity host), daylight, and walking between all Tower areas.

As of 2026-10-12, all served, nothing written into the game's memory while playing:
- Tower, the Moon map and the first mission's world; a full Hunter (weapons with their real
  magazine sizes, abilities, weapon swap); enemies that fight.
- Character creation that counts: pick a class and look in the game's own creator and the server
  builds that Guardian - level 1, the class's starter armour, the Khvostov, the subclass's
  abilities (`tools\new_guardian.py`, `tools\creation_service.py`, `tools\talent_grid.py`).
- Equipping from the character screen (`tools\equip_service.py`): the login server pushes the
  changed character to the running game.
- "A Guardian Rises": objectives, Ghost lines, the Wall's power-up and gate, the rifle hand-over
  (you start unarmed), Fallen - played by `tools\mission_director.py`, partly on timers, partly
  on what the game reports. It logs every trigger the game fires with the player's position
  (`<run>\trigger-log.txt`).
- Item names and any other text straight from the package files (`tools\game_strings.py`).

Known wrong: see the "Open" / "NOT DONE" lines at the end of the last sections of
`NIGHT-NOTES.md`.

**Not included: the game.** You need your own disc + official 01.29 patch dump (eboot sha256
must match d1preservation's pin). Put it at `CUSA00219-129\` next to this file.

## Pieces
- `d1_launch.py` + `Launch Destiny (director).cmd` - start ShadNet, d1-responder, activity host and
  shadPS4 with the right environment. `tools\autopilot.py --director` drives it unattended.
- `patches\CUSA00219-windows.xml` - shadPS4 game patch (boot fix, no idle kick).
- `patches\d1server-served-spawn.diff` - changes to d1preservation (apply to a clone at
  `C:\d1server\d1preservation`, build with its `build-server.bat`).
- `patches\shadps4-*.diff` - shadPS4 fixes (apply to shadPS4 at `C:\d1server\shadPS4`).
- `capture\` - measured per-world data (Tower sensor slots).
- `tools\` - live debugging: memory reads (`d1guest_win.py`), hardware breakpoints
  (`hwwatch.py`), RenderDoc survey, input automation.
- `NIGHT-NOTES.md` - what was found and how, in order.

## Base versions the diffs apply to
- d1preservation `main` @ `59ffd07` (`git apply patches\d1server-served-spawn.diff`)
- shadPS4 @ `afde6318` (`git apply patches\shadps4-all-changes.diff`), built with Clang 19.1.7

Paths are currently hardcoded to `C:\d1server\...` and this folder.
`Launch Destiny*.cmd` installs a hosts-file redirect; `Undo unattended runs.cmd` removes it.
