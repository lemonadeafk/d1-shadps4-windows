# Night notes - 2026-10-10

Running log of unattended work. Newest section at the bottom. Each entry says what was tried, what
happened, and what state things were left in.

## State at start (02:25)
- Tower reachable: `Launch Destiny (tower).cmd` -> orbit -> `python tools\d1_inworld.py`.
- Persistent hosts redirect is ON (`Undo unattended runs.cmd` removes it).
- Plan, in order: (1) autopilot for unattended sessions, (2) lighting, (3) the loading stall when
  walking between Tower areas, (4) character creation + a working director (Earth/Tower selectable).

## 1. Autopilot - DONE (02:40)
`python tools\autopilot.py` takes a session from nothing to standing in the Tower in ~2 min with no
input: launches, presses X at the title, skips the first-run settings screens by memory write
(profile_setup counter, d1preservation's own lever), runs the in-world script, screenshots each stage
into the run folder. `--no-spawn` stops in-world without the Guardian spawn (the spawn is what crashes
after 1-3 min). `--kill` ends a session cleanly. `--renderdoc` launches under portable RenderDoc.

## 2. Lighting - DIAGNOSED, NOT FIXED (03:52)
Captured a Tower frame with RenderDoc (tools\rdc_survey.py runs inside qrenderdoc) and walked the
pipeline. What is FINE: albedo, normals, depth, the sun shadow mask (correct sun/shade split), the
local-light buffers (orange/blue lamps). What is WRONG: there is almost no sun or sky light.
The cause is in the GAME's own per-frame lighting constants, not in shadPS4's copy of them:
- composite pass (eid 42729) constants at +512/+528/+544 read (0.347, 1.87e-13 x3), (1.63, 60.59 x3),
  (0.392, 7.87e-12 x3) - colour terms ~1e-13 = no light.
- the same values are in GUEST memory (found by search, e.g. 0x2c0d0bbd0), so the game computed them.
- the sun is up: c_sun_manager reads (-81.08, 48.67) - elevation ~49 degrees, i.e. daytime.
=> the sun is positioned right but its light is crushed by ~1e-13 - looks like atmospheric
   transmittance exp(-huge). Leading suspect: atmosphere/lighting parameters from content (the sun
   manager references content tag 0x80ca0ded) or a server-fed value (activity host never sends udt 2
   world_globals_state, whose +0x520 is a world time base).
Ruled out: shadPS4 readbacks (relaxed and precise), the colour-LUT texture bug (fixed anyway - big
texture-cache cleanup), GPU accuracy options (copy_gpu_buffers CRASHES shadPS4 - don't use).
Kept in shadPS4: 3D-texture-slice render target fix (patches\shadps4-*.diff), file-triggered RenderDoc
capture (touch AppData\Roaming\shadPS4\capture.trigger), a texture diagnostic log line (D1DIAG).

## 3. Loading stall between Tower areas - NOT REPRODUCED (04:00)
Walking works unattended (`python tools\gamewin.py hold 8 w`; WASD move, IJKL camera, x sprint).
Walked from the courtyard to a plaza: no stall, and the client sent the activity host nothing but
keepalives (udt 15) and a stats report (udt 47 high_water). Dark areas are just the broken lighting.
Best guess for your 10 s stall: first-time shader compilation (shader cache is now ON, so repeat
visits should be faster). Unconfirmed - the log has no timestamps.

## 4. Character creation - CLASS SELECT REACHED (04:02)
`python tools\autopilot.py --stop-at signin --env D1_EMPTY_ROSTER=1` boots straight to
"CHOOSE YOUR CLASS" (Titan / Hunter / Warlock) - screenshot in
runs\20261010-040107-WIN-CREATE\shot-040202-signin.png. Next: pick class/race/gender/face with keys
(✕ = n, ◯ = b, d-pad = arrows), press Finish, and see whether the server's 501 reply leads to orbit
with a real character - and whether that character gets more than Earth on the map.

## State left (04:03)
Nothing running. Persistent hosts redirect still ON - run "Undo unattended runs.cmd" when done.
All shadPS4 source changes: patches\shadps4-all-changes.diff.

## 5. Character creation - WORKS END TO END (10:30, run 20261010-102521-WIN-CREATE2)
`python tools\autopilot.py --stop-at signin --env D1_EMPTY_ROSTER=1`, then in the creator: cursor
(left stick = WASD; it is a free cursor that "sticks" to buttons) onto TITAN -> n (✕) -> appearance
screen -> cursor onto FINISH -> n. Result:
- game sent investment 501 (class 0 / race 0 / gender 0, online id D1Guardian); server minted SOID
  0xD100000000000101, wrote create-character-*.txt, account now reports 1 character
- character:signin -> prologue -> cleanup -> setup:orbit; popups "Crucible unlocked", "Armsday"
- orbit card: D1Guardian, level 40, Light 385 (the served profile)
- Director: STILL only Earth, not selectable; corner icons inert. Creation alone does not fix it.
Note: the appearance preview is black (same lighting bug).

## 6. Director - ACTIVITIES SHOW, TOWER LAUNCH BLOCKED (12:30, run 20261010-104527-WIN-DIR-UNLOCKS)
Started with `--env D1_UNLOCKS=capture-rig\unlocks\unlocks-200-campaign.bin --env D1_FAMILY42=1`.
- Why the Director was empty: `cui::c_director_data_component_v2 +0x8C` (the destination the
  Director wants to show) is 0x575b7710, which is not one of the 9 destination books
  (Earth 0xA15E9435, Tower book 0x1C36C0EE, 7 gated ones). So the selected index +0x163 stays -1
  and the panel builds 0 nodes. 0x575b7710 also sits in the director cui_screen_widget +0x248, so
  it looks like the screen's own parameter leaking in. Root source not yet found.
- `python tools\director_fix.py [earth|tower]` (Director open) writes a real book hash and forces
  a rebuild: Earth shows its story/patrol nodes, Tower shows TOWER with its nodes. Screenshot without
  stealing focus: `python tools\gamewin.py shotbg out.png`.
- Pressing X on the Tower: "ACTIVITY BANNED - This account is permanently banned from social
  spaces." No server traffic at all on the press (only 701/702 stats), so it is a client check.
  Ruled out: activity status bytes in the family 4/type 4 table (all set to 2, still banned),
  c_banhammer_controller_monitor (it is the idle timer), entitlement (base game owned).
- Advice received (from the user, quoting what looks like d1preservation's author): "you need to
  have the investment clock running. you need to author unlocks and entitlements ... almost
  certainly missing parts of queuez/families". The investment clock lives at
  `[0x26A3888+8]` +0x408/+0x410 (written by the simulation-queue element
  `investment_local_time_update`, applier 0x586850). It does advance here, but its base looks like
  nonsense - a ban window compared against a bad clock is the leading suspect.

## 7. Investment clock - FIXED ON THE SERVER; Director now works without pokes (12:15)
- The investment clock is family-5 object 5/5 (`0x80801941`, served inside BAP 503/205), field [1]:
  a u64 right after the family-5 root (registry element `+0x008`), Unix seconds. Client clock
  (`0x584CB0`) = that base + elapsed cycles / frequency (runtime state `[0x26A3888+8]`, `+0x58`
  = current investment time). Dawn's family5 codec names the same field `time`.
- Our server sent that field PRESENT with value 0, so the client's investment time was 1970 + uptime.
  (The repo's 0x80801941 field map omits this field; its later offsets are struct-relative and fine.)
- Fix in `d1-server/crates/d1-responder/src/main.rs`: `served_503_body()` / `served_205_body()`
  splice the current time into bit 230 / bit 70 (position found with the client's own codec via
  `d1-oracle message --tag 0x80801827 --msgid 205 --obj`; the no-time encode reproduces the shipped
  205 byte-for-byte). Knob `D1_INVESTMENT_TIME` (default `now`; `0`/`off` = old behaviour; or a
  number). Startup guard prints `investment time on the wire: <t>`; 205/503 agreement and the
  controls/test compare with the time slot masked. `cargo test -p d1-responder`: 13/13 pass.
- Verified run 20261010-120850-WIN-CLOCK: element +8 = current time; with NO memory edits the
  Director opens on the real SOLAR SYSTEM page (Tower, Earth, Crucible), Earth opens the full
  Cosmodrome map (missions, patrol, Felwinter Peak). `tools\director_fix.py` is no longer needed.
- Still open: X on the Tower = "ACTIVITY BANNED - permanently banned from social spaces"
  (hover card: "Requirements Not Met"). Ruled out: unlock flags (cleared all -> "Trial mode
  unavailable" instead, set all -> still banned), unlock values, family-5 +0x2DC gate bit,
  activity status bytes, signon flags, PSN privileges (no such calls). Untested: whether a
  non-social Earth activity launches.

## 8. Tower from the Director - SELECTABLE, LAUNCH STARTS; stops in matchmaking (13:00)
Run 20261010-125424-WIN-TOWER131, no memory edits anywhere.
- The "ACTIVITY BANNED - permanently banned from social spaces" dialog was OUR flags. The click
  handler (node widget, 0x9DD300) calls the launch validator 0x546B30(ctx, activity); it walks the
  activity's requirement sets (global table keyed by hash, two expression lists each) and returns
  the failure reason of the first false expression. Tower = sets 0x6291ABC8 {NOT FLAG 3389,
  NOT FLAG 308} and 0xC6CD9E47 {419 OR 440, 2667 OR 440}. The repo's shipped ten flags include
  308 and 3389 -> banned. (Two independent culprits, which is why flag bisection never found one.)
- "Requirements Not Met" was a different table: each Director entry has status rules, tried from
  the highest index down, first true wins (0 hidden, 2 not met, 3/4 selectable). Tower entry 0:
  status 4 if FLAG 131, status 4 if FLAG 3136, else 2. `python tools\director_rules.py 12` prints
  the rules for any destination with the live flag values (10 = Earth).
- Server: new responder knob `D1_UNLOCK_FLAGS` (comma list, all granted at value 2; default = the
  shipped ten). `d1_launch.py --director` / "Launch Destiny (director).cmd" serves
  98,131,419,440,834,2667,5015,5987,6018 + D1_UNLOCKS + D1_FAMILY42. The in-world shortcut launches
  keep the old ten (they need 308/3389 for the PvP activity gate).
- Result: Director -> Tower hover card is clean -> X -> orbit shows "TOWER, The Last City, Earth
  // Social" with a green LAUNCH -> X on LAUNCH -> world_controller leaves orbit:
  setup:activity_session_creation -> setup:matchmaking -> "Composition check failed with
  'big-party-count-exceeds-teams'" -> cleanup -> orbit_loading -> orbit -> repeats forever
  (screen: dimmed orbit + spinner). NEXT GATE: matchmaking configuration for a social activity
  (party of 1 vs 0 teams; client_config social_matchmaking_id is 0; BAP 42/43 kind 4 stub).
- Tools added: tools\hwwatch.py (attach as debugger; hardware data watch or --exec breakpoint
  with register/memory capture; this is how the validator and the expression were found -
  ALWAYS pass host address = current base + vaddr, the base changes per run),
  tools\open_director.py (clears popups, opens Director, hovers Tower),
  tools\director_rules.py. hwwatch crashed the game once on detach (fixed: drain before detach).

## 9. Matchmaking gate - SOLVED; Tower reached from the Director (13:15)
Run 20261010-130920-WIN-MM2.
- The loop was `0xB0A720` returning 12 (`big-party-count-exceeds-teams`): big-party count
  (`state+0x14`, counted at `0xB09FEA` as parties with size >= `props+0xB0`) > `props+0xC4`
  (0 for the Tower). `props+0xB0` was 0, so a solo player was a "big party".
- `props+0xB0` comes from the server: BAP msg 43 field 4 (matchmaking_configuration, 0x420 B,
  memcpy'd to `matchmaking_iface+0x38` by `0x599F80`), submessage f4.1 "tuning" (descriptor
  0x15B48B0, 11 fields). `0x5990B0` copies them into every properties struct:
  f1->+0x08 f2->+0x98 f3->+0x58 f4->+0xB8 f5(u8)->+0x64 f6->+0x5C f7->+0x60 **f8->+0xB0**
  f9->+0xB4 f10(f32)->+0x130 f11(f32)->+0x40. The responder sent an empty f4.1 (`22 02 0A 00`).
  This answers the repo's open "[U] who consumes the 0x420 configuration blob".
- New responder knob `D1_MM_TUNING` (e.g. `8=4`: big party = 4+ players). Tests 13/13.
  `d1_launch.py --director` now sets it. Only f8 is set; the other ten are still 0 (unknown meaning).
- With it: "Ready to start criteria met" -> "Teams have been picked" -> setup:activity_host_setup
  (activity client connects to our AH, startup for activity HASH 0xDF283AFB index 1 = the Tower,
  join accepted) -> prologue_intro_loading -> orbit_outro -> activity_world_transition ->
  activity:initial_slice_set_loading, where it waits ("Timeout entering the prologue-filler").
- From there `python tools\d1_inworld.py --skip-launch` (new flag: no launch poke) finds the done
  mask already 0x1FF, applies the two hooks + mask 0x7FF, and the game goes physics_join ->
  activity:in_world in 7 s. Spawn word + fade clear -> Guardian on screen in the Tower plaza, HUD up,
  walks with W. `python tools\autopilot.py --director` chains all of it (not yet run end to end).
- STILL BROKEN: crash ~2.5 min after the spawn, access violation at eboot 0xBBDEDE - the SAME
  address as the old launch-poke route, so it is not caused by the launch method. Lighting unchanged.
- Remaining pokes on this route: the two hooks (0x10C500 lifetime-state getter, 0x411E16 reject),
  done mask 0x7FF, spawn word, fade block. Everything before in_world is now served, not poked.

## 10. The in-world crash - EXPLAINED AND AVOIDED (14:30)
- What killed every in-world session after 1-3 min was NOT the spawn itself: the game logs
  `Prerequisite 'ENUM(1)' failed for reason 'error.inactivity_timed_out'` and tears the world down
  (the normal idle kick, 0x792210: idle STICK time > 5/15/60 min by activity kind, counted from
  the last stick move - which in unattended runs was in orbit). The teardown then crashed on
  hand-made state: hooked biped -> 0xBBDEDE; hand-linked slot -> 0x119321 (slot pool already
  unloaded). Caught with tools\crashwatch.py (stays attached, prints the fatal AV + registers).
- Optional patch added to patches\CUSA00219-windows.xml: "never kick for inactivity"
  (0x792302 `ja` -> 2 NOPs). With it an untouched session ran 8+ min and was still controllable.
- Why the repo's two code hooks were needed, answered (its open "[U] which other leg refused"):
  the spawn gate 0x414730 -> 0x1192A0 needs the player's "player array" element (0x2670940,
  20 x 0x1C0) to carry a definition tag at +0x50. It is set by 0x1195E0 (setter 0x3011F0), which
  scans the world's 30 kind-12 objects (schema 0x80802236 = one slot per possible player) for the
  one whose owner id (slot+0x258) equals the player's id, then writes the player handle to
  slot+0x1F0 (0x1293D0). All 30 owners are 0: our activity host never assigns a slot.
  The gate also needs slot+0x221 != 0 (block at slot+0x218) and lifetime phase in {3,6}.
- NO-HOOK ROUTE (code segment untouched except the XML patches):
  `tools\nohook_inworld.py` (phase byte = 3 via the getter's own pointer, done mask 0x7FF) then
  `tools\link_player_slot.py` (slot+0x1F0 = handle, slot+0x220 = 01 01, element+0x50 = slot tag,
  spawn word, fade). The REAL gate passes, the Guardian spawns, "Team voice channel now
  available" appears. `python tools\autopilot.py --director` does boot -> Director -> LAUNCH ->
  this, in ~2 m 50 s (run 20261010-142459-WIN-ONECMD).
- Still pokes, to be served by the activity host instead: lifetime phase (repo has
  D1_AH_SENSOR_PHASE / udt 5 for it, untested here; name hash + gen are per-world), the player
  slot (same sensor mechanism: the slot record has setters bound at +0x28/+0x48/+0x88/+0xA8/
  +0x1B0/+0x1D0), done-mask tasks 9/10, spawn word, fade.
- Director scripts are now closed-loop: tools\cursor.py finds the free cursor (closed ring r=26,
  dark inside) and steers it via the empty middle band; open_director.py / launch_tower.py use it.
- Gotcha that cost an hour: a timed-out command kept running in the background and later ran the
  same pokes a second time (double spawn -> instant 0xBBDEDE). One driver per session.

## 11. Lighting - MAIN CAUSE FOUND: it was night. Ambient-in-shadow still missing (14:45)
- c_time_of_day_game_system (object eboot 0x2943E40, state at [+8]): +0 fraction of day,
  +4 day length (7200 s in the Tower), +8 game seconds at last tick, +0xC paused. Each tick adds
  elapsed/length (0x8B47C0). Nothing ever sets it for us, so the day starts at 0.0 = MIDNIGHT when
  the activity starts; every session so far was looked at during the first ~10 minutes = deep
  night. That is what the section-2 diagnosis measured (sun/sky terms ~1e-13): correct for night.
- `python tools\time_of_day.py 0.5` -> blue sky, sunlit paving, correct sun shadows
  (runs\20261010-142459-WIN-ONECMD\tod050.png). link_player_slot.py now sets 0.45 on arrival
  (`--keep-night` to skip). Write ONLY the fraction: also writing +8 makes the next tick subtract
  the difference back out (cost one wrong "no effect" conclusion).
- How the real game sets it: the lifetime-record setter 0x11DE30 (the udt-5 sensor value that
  also carries the lifetime phase) calls 0x8B46C0(record+0x680) when record+0x67C != 0. So the
  activity host should send time of day in the same frame as the phase. global_activity_state
  +0x520 ("time base") is NOT it: poking it changed nothing.
- STILL WRONG at noon: anything in shadow is pure black (no sky/bounce light) and there is colour
  banding (day3.png). Sun-lit surfaces are right. Separate problem - renderer-side or a missing
  ambient input; needs a RenderDoc capture taken at noon (`autopilot.py --director --renderdoc`,
  then time_of_day.py 0.5, then touch capture.trigger).

## 12. Shadows - one real renderer bug fixed (shadPS4), more remains (15:25)
- Return-to-orbit crash (user, "hold triangle"): same 0x119321 teardown crash. Fixed by
  tools\slot_guard.py (started by link_player_slot.py): unlinks player element+0x50 the instant
  the game leaves activity:in_world. Verified: Ghost -> hold triangle -> clean return to orbit.
- Time-of-day sweep (tools\time_of_day.py, 20 steps): brightest at 0.45-0.55; even at noon ~40%
  of the frame near-black. So it is not "wrong time" any more.
- RenderDoc noon frame (runs\20261010-144838-WIN-SHADOW\noon.rdc): the light accumulation
  buffers (7311/7313) are exactly 0 in shade - the game's own lighting adds no sky/ambient there.
- SEPARATE REAL BUG found and fixed: the final colour-grading 3D LUT (32x32x32, built as four
  copies of 8 slices) had slices 0-7 all zero, so every dark colour graded to black. shadPS4's
  SanitizeCopyLayers FORCED a 2D->3D copy's layer count up to the full volume depth (8 -> 32),
  an invalid copy that dropped the first batch. Now only clamps down. Patch:
  patches\shadps4-lut-partial-volume-copy.diff (also in shadps4-all-changes.diff). Rebuilt.
  Same view at noon: near-black 41% -> 34%, shadows show detail.
- Still to do: why the ambient term is 0 in shade. Candidates: the probe/irradiance volumes (many
  32x32x32 / 32x32x16 3D textures in the frame - same family of 2D/3D handling as the LUT), or
  content the server should drive. Next step: dump those volumes from the capture and check for
  empty slices like the LUT had.

## 13. Black shadows - root cause narrowed to ONE render pass (16:10)
Capture runs\20261010-144838-WIN-SHADOW\noon.rdc (noon, pre-LUT-fix build). Tools added to
tools\rdc_survey.py, driven by `python tools\rdc_run.py <rdc> <out> '<json job>'`:
pick (pixel values, any slice), history (pixel history), bufwatch, apievents, shader
(disassembly + blend/depth state), debugpixel.
- Light accumulation (7311/7313) is a normal deferred sun + local lights buffer: 0 in shade is right.
- Ambient/sky light is applied in the composite (eid 13876, shader 3975) and multiplied by
  `1 + s*(mask*k - 1)` with mask = lerp(A, 1, R) of render target 7287 (R8G8B8A8, 1920x1080).
  mask = 0 -> ambient factor ~0 -> shadows black. 7287.R and .A are 0 EVERYWHERE in the frame.
- 7287 history at any pixel: eid 5384 clears it to (1,1,1,1) [= fully visible]; eid 5421 (shader
  1719: 9-tap PCF against the 1536x1536 depth map 7282, constants k=16797, slope 1) leaves it at
  (0,0,0,0) = "fully shadowed"; later passes (8977, write mask G|B) only rewrite G/B (AO).
  RenderDoc flags the 5421 fragments as depth-test-failed yet the value changes, and its shader
  debugger cannot trace them - so the PCF/visibility pass is where it goes wrong, inside shadPS4
  (depth compare / shadow-map depth convention / volume depth test), not in game data.
- The "1e-13 sky constants" from section 2 are NOT the problem: they are height-fog density at the
  Tower's altitude, computed by the game's material-constant VM (0x827680, table 7 inputs at
  eboot 0x26D5780; fog writer 0x841240: density *= exp(min(64, falloff*(h-base)*-0.001)),
  falloff 42, base height -627). Correct values.
- Next: get the scene depth vs box depth at one pixel for eid 5421 and the 7282 shadow-map depth
  the PCF reads, to see which comparison shadPS4 gets backwards.

## 14. Lifetime phase now SERVED by the activity host - no poke (17:00)
The lead's advice was "stop poking your character in". First poke removed: the lifetime phase (record+0x1AC).
- The udt-5 sensor_auth_update was already decoded and applied (gen 0 matched world+0x1D, the
  name-ref resolved to the Tower's lifetime slot, and the slot was marked dirty at 0x2D05C0). But the
  setter post-pass never ran: `0x2D0B70` (called at 0x2D062A) returns 0 while ANY replicated sensor
  slot still awaits its initial state (slot+0x15 != 0) and is local-owned or unowned
  (owner == local, or > 0x7F; only remote-peer-owned slots are skipped).
- The Tower has 99 such slots: 64 in group 0x8d3f1166 (owner 0) and 35 in groups 0x40aebf90 /
  0xf2d88bd0 (owner -1), including the 30 kind-12 PLAYER SLOTS (0x40aebf90, i8 12, sub 4..33, value
  schema 0x808022a5). Names and slot indices are identical across boots.
- Fix, in the server: d1-oracle `SensorPhaseUpdate.init` + AH knob `D1_AH_SENSOR_INIT=<file>`.
  The udt-5 frame carries one entry per slot with fresh=1 (the client default-inits it) and
  presence=0 (the change-mask bit "nothing changed", read at 0x2C91BA), plus a 0 bit for a second
  part. No values are invented. Manifest: `capture\tower-sensor-init.txt` (99 lines). Frame:
  1182 bytes.
- Result (run 20261010-165533-WIN-SENSORINIT2): phase byte 0xFF -> 03 via the game's own setter,
  dirty slots 0, with no hooks or pokes. `d1-oracle sensor controls`: 11/11 still byte-exact.
- Still poked: the rung-34 done mask is naturally 0x1FF, and task 9 waits on leg A = the player-slot
  assignment (0x1192A0), the same as the spawn gate. Join counter is naturally 0. Next to serve:
  the player-slot value (schema 0x808022a5, sub 4 = first slot) over the same udt-5 channel.
- Build: `C:\d1server\d1preservation\build-server.bat -p d1-activity-host` (needs C:\Program
  Files\CMake\bin on PATH for unicorn-engine-sys; the script sets it).

## 15. GUARDIAN IN THE TOWER WITH ZERO POKES - all served by the activity host (17:25)
Run 20261010-172236-WIN-FULLSERVED: `python tools\autopilot.py --director` boots, opens the
Director, launches the Tower, and the game spawns the Guardian at 10.8 h daylight. No memory
writes or hooks at all. Remaining code patches: only the XML (boot heartbeat NOP, idle-kick NOP).
"Team voice channel now available" now appears too.
What the AH sends (one udt-5 frame, repeated every 5 s for 2 min; d1_launch.py --director sets it):
- the initial state of the 99 sensor slots (section 14);
- lifetime phase 3, plus time of day (value field [10] +0x4D0 = 1, [11] +0x4D4 = 0.45; the setter
  0x11DE30 calls the c_time_of_day setter) - knob D1_AH_SENSOR_TIME_OF_DAY;
- player slot sub 4 (= kind-12 slot 0) seated: value schema 0x808022a5 with owner (+0x40, kind
  0x23 = full 64-bit id) = profile SOID 0xD100000000000201, +0x08/+0x09 = 1, +0x38 = 0. The
  client's linker then fills slot+0x1F0 / element+0x50 itself. +0x38 must equal the client's
  (i8)players[i]+0x738 (0), or the client never sets its own ready flag slot+0x299 (0x408D30) and
  the spawn gate (0x1192A0 -> slot+0x290 block) refuses forever - knob D1_AH_SENSOR_PLAYER_SLOT.
- d1-oracle needed kind 0x23 support: crate::runtime_ids seeds the two BSS id-schema tag records
  (0x808004AC compact / 0x80801932 full, derived statically) and the client's id-mode flag object
  (live client: full ids). All oracle/AH controls still pass (sensor 11/11, AH 112).
Done mask reaches 0x7FF and the fade lifts naturally. Untested: returning to orbit (the slot_guard
poke is no longer started; the state is real now, so the old teardown crash may be gone).

## 16. Walking between Tower bubbles works (18:15)
Stall was "Region 'PRV24.24' is ready for switch, but we do not yet have valid host-tabulated data
for it. Waiting." + "player was held ... [matchmaking IN-PROGRESS]".
- The client reports its pending transition to the AH in udt 21 client_authoritative_data_update
  (+0x158 = pending region, 10 bits; +0x1F8 = token), byte-identical to sstm+0x138 / +0x1D0.
  The AH now decodes udt 21 seeded (it is a replicated delta) and follows it.
- But an answer sent after the client asks is too late: FUN_007775B0 scans the PAH array once per
  transition, and again only when the membership's member count (+0x00, read via ac+0xE70)
  changes. The client held {0x18, 2} in ac+0x3CB8 and still waited.
- Fix: the AH tabulates ahead (ReplicateMembership::set_pah_table). It publishes the current
  {region, token} plus every bubble region (bubble*8) with token+1, and re-publishes when udt 21
  reports a new token. Verified by the user, run 20261010-180828-WIN-BUBBLES2: PRV24 / PRV16
  crossings load through, and the matchmaking hold cleared with it. AH controls 112/112.

## 17. The sensor slots are CONTENT - the server derives them itself (19:15)
No more measured Tower inputs. `d1_oracle::world_sensors::derive(world_tag, bubble)`:
- world record (city_tower_default1 = tag 0x80C7A005, class 0x8106216F): +0x0C = the activity
  checksum (0x7F0057BE), +0x70 bubble count, +0x80 bubble table {region hash, 1, off} stride 0x18,
  body at entry+off+0x50 = {region hash, bubble content tag}. Region hashes are the ones in the
  log (f28fc859 = PRV00, 61974e44 = PRV16, 1ad5e415 = PRV24).
- bubble content (class 0x808008F0) -> bubble definition -> group tags (class 0x8080076E).
  Bubble 0's definition lists exactly the five groups the client loads (FUN_00345250 ->
  FUN_00106D60 copies hash = [group+0xC] into the world's group table).
- group entry: +0x0C hash, u16 +0x10 replicated count, +0x50 member count, members @+0x60
  stride 0x10 {kind,...}; the tail holds the member NAMES.
  40aebf90 = scoreboard, lifetime_timer, lifetime, new_user_experience, players x30.
  8d3f1166 = obj_patrol_lower/upper, sq_boulevard_vendor_*, sq_boulevard_civ_* ... (kind 3 =
  objective, 1 = squad, 2 = squad member, 40 = ?).
- record entries (class 0x80800861, in the world package and the packages the groups reference):
  own name-ref {group hash, kind u8, 0, sub i16}, then +0x14 part-2 tag, +0x18 value tag.
- Result for the Tower: 100 slots, 100/100 identical to the live measurement, ~8 s.
- AH knob D1_AH_SENSOR_WORLD=0x80c7a005 (+ D1_AH_SENSOR_PLAYER_SLOT=auto) replaces
  D1_AH_SENSOR_INIT and the three NAME knobs; d1_launch.py --director uses it. Verified run
  20261010-191107-WIN-DERIVED: spawned, phase 3, 10.8 h. AH controls 112/112.
- LEAD for the "empty world": the 64 slots of group 8d3f1166 are the Tower's objectives and NPC
  squads, and the AH is their authority. Vendors/civilians are probably spawned by the host sending
  values on those slots (schemas: kind 1 0x8080071E/0x80800357, kind 2 0x80800868/0x808005D9,
  kind 3 0x808004FA/0x80800830, kind 40 0x80800556).
- Other bubbles add their own group (PRV16 19d43443 + 2318ee6c, PRV24 8cc31436); their slots are
  not initialised by us yet - harmless so far, relevant once those squads matter.

## 18. NPC squads - what is known, what is not (19:40)
- The udt-5 frame's optional "sensor block" is the sensor AUTHORITY table: schema 0x80800CF7
  (*[0x1902280], struct 0x310) = {u32, 65 x {8-byte peer id, u16 generation, bool valid}}, stored
  at world+0xA88 and indexed by PEER (the owner index at slot+0x60), not by bubble. FUN_002A1210
  reads 65 "changed" bits + the table; FUN_002A1080 arms a changed entry whose generation differs
  and, if valid, fires the authority-change callbacks (FUN_002408B0) with that index.
  Served now: D1_AH_SENSOR_AUTHORITY=<peer>[:<gen>] (opt-in). Accepted live (entry 0 = gen 1,
  valid, world+0xD98 = 1), repeat frames do not re-fire. Run 20261010-192710-WIN-SQUADS.
- It does NOT spawn anyone. c_squad_sensor_authority_change_observer (vtable 0x18EE5C0, slot 0
  FUN_00106090) only walks EXISTING actors and reconciles them with their squad record
  (FUN_00105D70) or deletes orphans - the hand-over path when authority moves between peers.
- Squad record classes: squad 0x808007BC (setter FUN_00104990), member 0x80800810, objective
  0x80800560, kind 40 0x808003C0. All 40 replication setters are listed by scanning the binding
  tables for sig 0x4D7DDECB (scratchpad setters.json).
- Squad value (0x8080071E, 0x7C bytes) as the setter reads it: +0x10..+0x28 -> rec+0x3BC..;
  +0x2C count / +0x30 i16[] = per-member alive counts ("alive count auth", FUN_00103320 watchdog);
  +0x40..+0x43 three state enums pushed onto existing members (FUN_00104D30 -> FUN_00BDA0E0);
  +0x60 -> FUN_001046B0 on change; +0x64 -> rec+0x1B4, re-evaluates members; +0x78 a hash.
  Every handler read so far acts on actors that already exist.
- OPEN: who CREATES squad actors. Not the squad setter and not the authority observer. Next:
  find the actor-creation call for a squad member (simulation entity create,
  c_simulation_squad_entity_definition) and walk back to its trigger - a script command on the
  authority, or a member-record (class 0x80800810, setter in the 0x40xxxx group) field.

## 19. NPCs SPAWN in the Tower (19:50) - run 20261010-194617-WIN-MEMBERS3
26/26 squad members got actors; vendor marker + friendly radar dots visible (Desktop\tower-npcs.png).
- Creation trigger = the squad MEMBER's host value (kind 2, schema 0x80800868, 0x908 bytes), not
  the squad's. Setter FUN_001BE5F0: FUN_001BE9B0 spawns (-> FUN_001BDFB0) when value+6 (bool) is
  set, value+5 (3-bit state) is 0 or 2, and the member has no actor (rec+0x218 == -1).
  FUN_001BE870: a changed value+0 (id) with value+4 == 0 destroys the old actor.
- Squad/member setters are gated by FUN_00108360 -> FUN_002A1050(world, owner): the owner's bit
  must be SET in world+0xA70 and CLEAR in world+0xA7C = the authority hand-over window.
  A table entry with a new generation sets both bits (FUN_002A1080); the per-tick check
  (@0x2A0B62, using FUN_002D0B70) clears +0xA7C once that peer's slots have initial state; a
  VALID entry fires the callbacks and clears both (window closed). On a normal load both are 0.
  So: authority entry {gen 1, valid 0} + member values in the repeated frame. With valid=1 in the
  same frame (first attempt) the window closed before the values were dispatched -> nothing.
- Knobs (now defaults of d1_launch.py --director): D1_AH_SENSOR_AUTHORITY=0:1:0 and
  D1_AH_SENSOR_KIND_VALUE=2:0x80800868:capture\values\member_exists.bin (default member image read
  from a live slot buffer, +0 = 1, +5 = 0, +6 = 1). capture\values\default_kind{1,2,3,40}.bin are
  the measured defaults. The AH now takes ~30 s to arm (autopilot wait raised to 90 s).
- Not done: closing the hand-over (valid=1 after the values), squad values (alive counts, states),
  objectives, the other bubbles' groups, whether vendors are interactable. The member default
  image is measured, not derived (the harness default-init returns zeros).

## 20. NPCs in every Tower bubble (20:40) - run 20261010-203737-WIN-BUBNPC5, user-verified plaza
- One udt-5 frame per bubble is built at startup (derive_cached per bubble; region = bubble*8) and
  armed when the client reports being IN that region: udt 21 +0xB8 = CURRENT region, +0x158 =
  PENDING. Pending goes back to 0 with the same token when a transition completes, so a pending
  change only counts when the token advances.
- The sensor authority table is indexed by BUBBLE, not peer: a bubble's own slots carry owner
  index = bubble index (slot+0x60 / record+0x48: 0 at the start, 3 in the plaza), and the setter
  gate tests that bit. Each bubble frame opens entry <bubble> {generation 1, valid 0}.
  (Section 18's "indexed by peer" was wrong; peer 0 == bubble 0 was a coincidence.)
- Three failed attempts on the way: frame sent at transition REQUEST (expired before the switch),
  frame for region 0 sent on completion (pending misread), entry 0 opened for the plaza.
- Frame build: ~0.6 s each (one name oracle, identical values encoded once).
- Kind 40 = "performance sensors" (vendor_performance_sensor_avatar/_nm, npc_kneeler, ...), each
  linked to its squad member; left at default. Vendors show NO interact prompt. The records and
  packages hold no performance names -> set at runtime by script. Open.
- Also open: revisiting a bubble (same generation again), closing the hand-over, the served
  character (Titan body + Warlock super, L3 = super, no sprint).

## 21. Character and vendor prompts - findings, no fix (20:55)
Character:
- The served inventory's subclass is Striker (Titan, hash 0x925CDEEA) - `d1-oracle inventory
  rebuild --dry-run` (needs capture-rig\item-content-index.tsv: `d1-oracle item-index write`).
- Yet L3 fires STORMTRANCE (Warlock Stormcaller) on the Titan body (screenshot l3_1.png), and
  there is no sprint. shadPS4's input_config\default.ini is clean (l3 = l3). Supers should not
  work in a social space at all. Cause unknown: not key bindings, not the staged subclass item.
Vendors:
- In the plaza Rahool has a nameplate and a "[] Approach" prompt; holding square does nothing and
  sends nothing to the server (701/702 are periodic sync; "drought" lines are status dumps).
- Performance sensor (kind 40, value 0x80800556, setter FUN_00128B30) just stores 0x30 bytes at
  rec+0x1AC. The per-actor update FUN_0013B460 reads it via FUN_00128F60: if value+0 != FNV basis
  and value+8 (sequence) > actor+0xABC, it starts the performance {hash A = value+0, hash B =
  value+4} through FUN_00137920. So value = {performance name hash, second hash, sequence, list}.
- The valid performance NAMES are not in the sensor records, the groups, or as text in the Tower
  packages ("approach" only matches an enemy animation list, entry 3309 of the ambient package).
  Next: dig the per-NPC performance table out of the running game (inside FUN_00137920's lookup)
  and reverse the hashes, or find the script that sets them.

## 22. Vendor trace: the valid performance hashes (21:10)
- Per-actor update FUN_0013B460: sensor value {hash A @+0, hash B @+4, sequence @+8}; if A is set
  and sequence > actor+0xABC, FUN_00150900 looks A up in the actor DEFINITION and FUN_00BDAC20
  plays it (B is passed along); then actor+0xABC = sequence.
- Lookup table (FUN_00150900): definition D = resolve(actor+0x1C); count [D+0x38]; entries at
  D+0x40+[D+0x40], stride 0x20, type key at +0x1C (must equal *[0x25BEBD0] = 0xAFB11A12), then
  count at +0x20 and a relative pointer at +0x28 to u32 name hashes (+0x10).
- Every plaza NPC definition (class 0x808013F3, e.g. tag 0x80C889CC) carries the same 71 hashes
  under that key - dumped to capture\tower-plaza-performance-hashes.json. The definition names
  three sequence files: vendors\sequences\{vendor_mode, ledge_sit_mode,
  rail_lean_backwards_mode}.sequence.tft.
- The names do NOT reverse: not in the eboot corpus, and no match against 352,873 strings from
  the two Tower activity packages (whole strings or any token sub-sequence, FNV-1, either case).
  Several hashes differ only in the low byte by '1'/'2'/'3' (numbered variants).
- Not established: that a performance is what the "Approach" prompt / vendor menu waits for.
- Next: a way to inject a udt-5 frame into a running session, then try performances one at a
  time on Rahool's sensor and watch the prompt.

## 23. Injection tool, performance sweep, sense messages (22:05)
- INJECTION: D1_AH_SENSOR_INJECT_DIR (launcher default: shadgames\inject). The AH sends every
  *.udt5 file dropped there on its next tick and renames it .sent. `tools\inject_sensor.py
  <bubble> <group>:<sub>[:<value hex>]` builds the frame with d1-oracle's `sensor_frame` example
  (kind / value tag / part 2 from derived content). Verified: value lands in the sensor record
  within ~1 s, no memory writes. `tools\perf_sweep_all.py` steps all candidates with screenshots.
- Performance play path: FUN_0013B460 -> FUN_00150900 (name lookup) -> thunk 0xBDAC20 ->
  FUN_00428FB0 -> FUN_0042B520 (already active? else FUN_00427160 fetch + thunk 0xBDA030 ->
  FUN_00474AD0). FUN_00474AD0 returns true only if the performance has flag bit 0 and the value's
  hash B is in its variant list (count @+0x20, 4 hashes @+0x24, flag @+0x34 of 0x38-byte
  entries). In the plaza definition only index 63 has the flag and no entry has variants, so the
  call returns false every tick and actor+0xABC never takes the sequence. Whether the pose still
  plays is NOT established (Xur's nameplate did move between steps of the sweep).
- Sweep at Xur (bubble 0, all 21 kind-40 sensors, 64 names): the prompt stayed "Approach"
  throughout. Performances alone do not gate the vendor prompt/menu.
- "Approach" exists once in memory as UTF-16 UI text (next to "Patches 99-40", the sweeper bot's
  name); it is written once and never rewritten when the prompt toggles (20 toggles, 0 writes).
  The UI element beside it carries 0x07862BF8 - not a corpus hash, not in the eboot, not in the
  Tower packages. Text is not stored plainly in the _en_ packages searched.
- udt 6 sensor_sense_update (client -> AH), now logged every time: gen(8), 3 bits, the same
  55-bit name-ref, then a body. All decoded ones name SQUADS (kind 1) of group 8d3f1166
  (sq_boulevard_vendor_black_market = Xur's squad, vendor_avatar, vendor_nm, civ_*, the_mask,
  vendor_playtest) or the two objectives - the client's own squad state (part 2). Approaching Xur
  and holding square produced no message naming his performance sensor or member.
- content_grep is slow by construction (the game's Oodle under Unicorn, every entry, no index):
  fine for a few-MB package, hopeless for ps4_ui_social (590 MB).

## 24. Character: the inventory was never being served (22:35)
- Three "fixes" (talent grid on the subclass, node states on) changed nothing because none
  reached the client. Check that should have come first: search guest memory for the subclass
  SOID 0xD100000000000301 - 3 hits, all the 64-byte EQUIPPED list entries {soid, content index
  710}; no 184-byte item element anywhere.
- Cause: d1-responder serves family 4/3 only `if let Ok(spec) = std::env::var("D1_INVENTORY")`.
  Its startup table prints `capture-rig/inventory [default]` whether or not it is set, and the
  Windows launcher never set it. d1_launch.py now sets D1_INVENTORY. Run 20261010-222959-WIN-INV:
  responder logs 13 inventory items; guest memory has the full Striker element (level 40,
  grid 132, 36 node states = 1).
- Talent grid facts (all from content / code, valid regardless): element +0x58 = grid index,
  +0x5A = 36 node-state bytes (0 = off, N = active at step N; FUN_002824C0). A subclass
  definition names its grid as the u32 before tag 0x80801A06: Bladedancer 130, Gunslinger 131,
  Striker 132, Defender 133, Sunsinger 134, Voidwalker 135, Nightstalker 888, Sunbreaker 889,
  Stormcaller 890. `d1-oracle inventory rebuild` now writes it for the Subclass bucket
  (--subclass-node-state N sets all nodes; an experiment, not a real build).
- Lesson: verify the data ARRIVED (read it back from the guest) before judging its effect.
- Rebuilding the whole inventory on this PC drops helmet fields (no art-arrangement table here);
  only 00-Subclass.bin was replaced. Backup: capture-rig\inventory.bak-no-grid.

## 25. FOUNDATION FIX: the Tower was running as ELIMINATION (23:25)
- The host published activity INDEX 407 (its default, kept from the first pvp_moonbase runs).
  activity-modes.tsv: 407 = 0x6D714C3A "Elimination" (3v3 Crucible). The client itself requests
  `activity HASH(0xdf283afb) (activity_index=1)` when the Tower is launched (activity_manager line
  in guest-stdout). Row 1 = 0xDF283AFB. Row 0 = 0x8AE8DA69 "Tower" (unmet prerequisites).
- d1_launch.py --director now sets D1_AH_ACTIVITY_INDEX=1. Run 20261010-232301-WIN-ACT1 reaches
  in_world, no team-mode warning.
- Likely explains: super usable in the Tower; possibly the wrong super / no sprint / dead vendors
  (social-space behaviour comes from the activity). To be re-tested on activity 1.
- Process lesson (user's words): stop fixing step 10 while steps 1-9 are wrong. Check that the
  inputs the server publishes match what the client asked for BEFORE chasing symptoms.
- hwwatch is unsafe while the user plays: breakpoints survived detach twice (0x80000004 crashes
  on the subclass screen). No debugger attaches during a play session.
- Later: derive the index from the client's BAP 6 startup request instead of a launcher constant.

## 26. VENDORS WORK (23:35) - run 20261010-232301-WIN-ACT1, user-verified
- First session with activity index 1 (the Tower's own activity) instead of 407 (Elimination).
  Vendor menus open. Most likely cause: the activity (social space). Not fully separated from the
  geared character + inventory, which started being served two runs earlier with no vendor test in
  between. Discriminator if ever needed: geared set + D1_AH_ACTIVITY_INDEX=407.
- So the performance-sensor and sense-message hunts (sections 22-23) were chasing a symptom of the
  wrong activity. Supers still fire on L3 and there is still no sprint on activity 1.
- Keyboard: shadPS4 input_config\default.ini now also has l3 = lshift, l1 = f, r1 = f
  (backup default.ini.bak-before-shift-f).

## 27. Sprint / super: a character-data gap the whole project has (00:05)
- Button layout is fine: in-game Settings shows Default (L3 Sprint, L1+R1 Super). Re-selecting
  Jumper then Default changes nothing - L3 still casts the super, L1+R1 does nothing.
- shadPS4 is fine: SDL left-stick click / l3 keys -> OrbisPad L3 = 0x2, L1 0x400, R1 0x800.
- So the "sprint" action slot holds a super. Abilities are separate action classes
  (c_action_impl_sprint_ability, slam (Fist of Havoc), radiance, void_bow, ward_of_dawn,
  dynamic_binding_ability, ...).
- Character object (0x80801954) C+0x78 = 5 x 68 B {u8, 16 x u32} ("talent-grid-ish" in the
  repo's notes) is ALL ZERO in every character fixture in the repo (8 files), and every fixture
  has identity {race 0, gender 0, class 1}. The repo's own playable run also fired a Warlock super.
  => an open problem for the project, not a Windows-port issue.
- Hunter consistency test (Gunslinger in inventory + character equipped list + profile list,
  run 20261010-234142-WIN-HUNTER): no sprint. Class/subclass mismatch alone is not the cause.
- Tools: d1-oracle example object_file (decode/encode big objects via files, refuses non-round-trip).
- Next: find the reader of C+0x78 (not an imul 0x44 site; try the investment character-state
  component's methods) and what fills it on a real server - likely the subclass talent grid's
  active nodes / ability perks resolved server-side.

## 28. Consistent Hunter (00:25)
- Class byte 1 = Hunter (Bungie class_type; the loadout's Hunter subclass is class_type 1).
- capture-rig/inventory-hunter-full = loadouts/y1-hunter-vault-of-glass.json (Bladedancer grid 130,
  The Last Word, Praedyth's Revenge, Corrective Measure, Prime Zealot set, Shattered Vault Cloak)
  + the class-neutral Ghost/Artifact/Vehicle/Horn. char-hunter.bin / profile-hunter.bin built by
  `d1-oracle character build` / `profile build --inventory <dir> --identity 0,0,1 --all-content`.
  Launcher default now.
- `--all-content` (+0x6E4C/+0x6E4D = 1) is what unlocked every Director destination in the old
  geared profile.
- `d1-oracle art-arrangement write --inventory <dir>` -> capture-rig/item-art-arrangement.tsv; with
  it the character's equipment entries carry art indices (armour 713-721, weapons 1220/1384/1379)
  instead of 0xFFFF = no model.
- Equipping an item sends investment 403 inventory_equip_item; the generic reply dropped BAP and
  crashed the game. Responder now answers it with the {u4,u32} composite (same as 701).
- Activities: the old geared profile also had ONE progression entry, character_level (ordinal 117)
  = 400000 XP (level 40). Without it the Director treats the character as level 1. Now
  `profile build ... --all-content --progression 117:400000`; byte-identical to the geared
  profile outside the item fields.
- Appearance: in-world look comes from the family-0 peer view (D1_ROSTER_DIR), which was still
  the old rosters-f0-geared. Now capture-rig/rosters-f0-hunter (character build-peer from the
  Hunter inventory). Untested.

## 29. Head fixed: wear-helmet (00:55) - user-verified, Desktop\tower-hunter-helmet.png
- Customization block 0x8080181A (36 B at +0x0C of character, profile AND peer view) was all
  zeros. +0x20 (2-bit bool) behaves as DestinyCharacterCustomization.wearHelmet: setting it to 1 in
  all three made the Prime Zealot helm render; with 0 the head was empty (face fields all zero ->
  nothing to draw). Field naming was [U] in the repo; this run is the evidence for that one field.
- Rebuild recipe for the served Hunter set (generated files are NOT in git):
    d1-oracle item-index write
    stage loadouts/y1-hunter-vault-of-glass.json -> capture-rig/inventory-hunter-full (legacy
      elements, see section 28) + Ghost/Artifacts/Vehicle/Horn from capture-rig/inventory
    d1-oracle inventory rebuild --dir capture-rig/inventory-hunter-full
    d1-oracle art-arrangement write --inventory capture-rig/inventory-hunter-full
    d1-oracle inventory rebuild --dir capture-rig/inventory-hunter-full   (picks up art/curves)
    d1-oracle character build --inventory <dir> --identity 0,0,1 --out capture-rig/characters/char-hunter.bin
    d1-oracle profile build --inventory <dir> --identity 0,0,1 --all-content --progression 117:400000 --out capture-rig/profiles/profile-hunter.bin
    d1-oracle character build-peer --inventory <dir> --identity 0,0,1 --with-family2 --out-dir capture-rig/rosters-f0-hunter
    then +0x2C = 1 (wear helmet) in all three via the object_file example.
- Still open: a translucent blue orb at the chest/neck (has always been there); sprint/super
  (empty ability block C+0x78); Dreadnaught (probably TTK DLC ownership).

## 30. Sprint: the sprint action never runs (01:05) - run 20261011-003611-WIN-ABILCAP
- Character object (C+0x78 block) and peer view (+0x40 block): no code reads either during the
  Tower load or while pressing L3 (hardware read-watch, 150 s and 14 s). Not the runtime source.
- Exec breakpoints on c_action_impl_sprint_ability's vtable (0x391940, 0x391C00, 0x391DB0): zero
  hits while pressing L3 (key x). The sprint action is not being started at all - most likely the
  biped has no sprint action in its ability set. Next: find where a player biped's action/ability
  set is built (class/subclass content -> c_action_impl_* instances) and what selects Stormtrance.
- (01:15, run 20261011-005645-WIN-GRIDCAP2) The talent-grid lookup FUN_0025B960 (vtbl+0x4E0) is
  NOT called during the Tower load (exec bp @0x25B9A9, 150 s, launch -> in_world). Only the
  subclass screen uses it. So the in-world ability set is NOT assembled from the subclass item's
  grid/node states at load; setting nodes will not restore sprint. Source of the player's ability
  set (and of Stormtrance) still unknown.

## 31. Action types (01:30) - run 20261011-011316-WIN-ACTCAP
- FUN_003B5740(type) = action type -> class, table 0x191D880 (u64 per type, pointing at
  typeinfo+0x18). Full list recovered (scratchpad acttab/rtti), e.g. 4-10 sequence/radiance/blink
  supers, 13-15 grenade, 16 void_bow, 17 ward_of_dawn, 18 slam, 24-25 evade/dodge, 57-61 melee,
  63 jetpack, 64 double_jump, 65 glide, 66 SPRINT, 73 jump, 80-83 locomotion.
- Logged every lookup from Tower load to in_world (44,675): only 2 resurrect, 53/54 weapon
  switch/ready, 80/82/83 locomotion. Idle vs pressing L3 (uncharged super): identical sets.
  Sprint (66) is never requested.
- So input L3 is not routed to the sprint action at all. Next: the player's input -> action
  binding, probably biped/class content selected by identity, or a character/profile field that
  picks the ability set. Look at who calls 0x3B5740 with a computed type (callers 0x36BE00..).
- (01:40, run 20261011-012826-WIN-ACTLIST) The 16 callers of FUN_003B5740 all read the type from a
  byte of an EXISTING action record (dispatchers, not creation). The player's record (type 80,
  physics_driven_locomotion) sits in a 7-slot per-actor action table (array of 7 x {.., .., u8
  type, ..}, element 0x808027F2): slot 0 = 80, slots 1-6 = 0xFF. NPCs use 82. Sprint would be
  STARTED by the locomotion action's update (type 80 class c_action_impl_physics_driven_locomotion,
  vtable via table entry 80) on L3 - that start condition is the next thing to read.

## 32. Overnight 2026-10-11: beyond the Tower - A GUARDIAN RISES LOADS AND SPAWNS (03:25)
Screenshots: Desktop\guardian-rises-1.png (first spawn), -2-navmode.png, -3-weapons-unlocked.png;
all intermediate shots in shadgames\overnight\.
- World names: `python tools\world_names.py [filter]` rebuilds the activity-symbol list from the
  packages' own symbol tables (header +0xEC count, +0xF0 offset, 0x44-byte records) ->
  capture\world-namespace.tsv (untracked). `<activity>` (type 0x808008BA) is a 72-byte entry
  {name hash +8, [..] scenario_client tag @+0x40}; `<activity>:scenario_client` is the world
  record. Tags are per package VERSION; newest wins (cosmo_patrols_1 only exists in _0).
- The client loads whatever world the AH names: launching Patrol (index 92) with the AH on the
  Tower loaded the Tower. So any world is reachable from any Director node.
- Director automation: tools\launch_patrol.py (Set Destination -> Earth -> Patrol -> LAUNCH,
  open-loop cursor from the bottom clamp); tools\autopilot.py --destination
  {tower,cosmo_patrol,guardian_rises}. Measured from the Director: Patrol the Cosmodrome =
  activity 92 (hash 0x09fa9d74), Restoration = 165 (0xb9fccac3).
- Cosmodrome worlds (22 bubbles, all valid): patrol_deltas_com01 = 0x80cb87eb checksum
  0x6a556a7f; act_cosmo_m0_highway (A Guardian Rises) = 0x80cb800d checksum 0x8fe07299.
  world_sensors now follows a bubble definition into another package (content +0x1C).
  Per-bubble derive is ~25 s cold: warm with `examples/world_sensors <tag> <bubble> cache`.
- PATROL IS BLOCKED on public regions: "Region 'PUB00.00' is PUBLIC but not yet connected".
  FUN_0077F6B0 needs transition+0x13C(public)==1 -> +0x141 (session state) == 2; state setter
  FUN_0077B3B0 ("session state being changed from..to..due to"), 2 = connected set in
  FUN_0077CA20. Protocol in the strings: PAH tabulated data includes us -> PAH assigns
  AMBASSADORSHIP -> we spin up a public activity session -> PAH broadcasts the advertised public
  session / activity host -> session-lock tokens. Not attempted yet.
- A mission starts in PRIVATE regions. Three things were missing:
  1. the START REGION: FUN_0077E440 reads global_activity_state+0x54 (blob accessor
     FUN_002A1F50). 0 = bubble 0. The mission record ends with an ordered phase list
     (0x8080073F, 7 entries); bubbles with table flag 2 carry a per-phase content variant;
     the FIRST phase (00bc0bb1) is on bubble 14 -> region 112 ("PRV112.1").
     D1_AH_SENSOR_WORLD=<tag>:<bubble> sets it.
  2. the TEAM: spawn gate 0x414730 failed at `cmp byte [rax+9],0` (client ready flag
     slot+0x299), set only when slot+0x250 (our value +0x38) == slot+0x2C8 =
     (i8)players[i]+0x738. Tower: 0. Story mission: -1. D1_AH_SENSOR_PLAYER_TEAM=-1.
  3. (found after spawning) the WEAPON SLOTS, below.
  tools\spawn_state.py prints the whole spawn chain read-only.
- In the mission: first person, Cosmodrome wall at sunset, movement and camera work, the
  touchpad opens Nav Mode ("COSMODROME", Go to Orbit). The mission's Ghost squad member exists.

## 33. THE "ORB" / NO SPRINT / NO WEAPONS = LOCKED WEAPON SLOTS (03:50)
- Character screen in the mission: armour equipped, all three weapon slots + artifact = padlocks.
  The biped spawns unarmed, so the summoned Ghost (a "pocket weapon") is permanently out:
  no firing, no sprint, and in the Tower's third person it is the blue orb at the chest.
- ddmin over the client's unlock-flag plane (diagnostic poke, reopen the screen, read pixels):
  FLAG 2502 = primary slot (+ the character PREVIEW), 2503 = special, 2501 = heavy.
  Launcher now grants them (D1_UNLOCK_FLAGS). Subclass/artifact flags: see section 34.

## 34. More worlds, lifetime phases, item grids (04:40)
- Subclass + artifact flags (same ddmin): 2479, 4917, 4992. Launcher grants all six.
  With the flags SERVED (no poke) the character screen shows the three weapons, the lit
  subclass, the artifact slot and the character PREVIEW (silhouette = lighting, model is right).
- CRUCIBLE MAP SERVED, ZERO POKES: `autopilot.py --director --destination pvp_moonbase`
  (First Light, world 0x80f08003, checksum 0x5966e491, 1 private bubble, activity 407).
  Needed: (a) records with NO first part (value tag -1, part2 only - kind 14): the walk skips
  fresh/presence for them (@0x2D03E5); unserved they stay pending+unowned and hold the post-pass.
  SensorInitEntry.no_value_part; world_sensors cache is now v2. (b) team -1 here too (client
  players[i]+0x738 = -1 everywhere except the Tower).
- LIFETIME PHASES are real activity states, changed live with tools\inject_sensor.py +
  SENSOR_FRAME_PHASE (read back at record+0x1AC each time): 3 = play (spawn allowed),
  4 = black screen, 5 = looks like 3, 6 = "MISSION COMPLETE - ELIMINATION - Mission end:
  seconds remaining" (Desktop\moon-mission-complete-from-server.png), 7 = like 3.
  Spawn gate allows only 3 and 6 (masks 0x48 vs 0x3B7 @0x4147DB).
- ITEM TALENT GRIDS: the grid index is the u32 AFTER tag 0x808017BD in the item definition
  (Last Word 295, Praedyth 319, Corrective Measure 314, armour 151-155, Ghost 897, vehicle 278,
  Bladedancer 130). `d1-oracle inventory rebuild` now sets it for every item. Result: the
  tooltip shows Rate of Fire/Impact/Range/Stability/Reload/Magazine + perks + "Details", and
  the Details screen shows the whole perk tree (Desktop\the-last-word-*.png).
- STILL OPEN - the in-world Guardian holds the summoned Ghost (first person: hand + Ghost +
  dial; third person in the Tower: the "orb" at the chest) instead of a weapon, in every world.
  No firing, no sprint, L1+R1 nothing. NOT the cause: weapon-slot flags, item grids, lifetime
  phase, mission script, touchpad state (touchpad toggles the Nav Mode text only).
  Action lookups in the mission: only 80 (player locomotion) and 84 (floating_locomotion = the
  Ghost). One type-8 object is parented to the biped (def 0x80aae367, ps4_globals).

## 35. Subclass nodes decoded and served (05:20)
- Talent grid table: investment-globals root [0x2639AF8] +0x468 = table tag; resolve(tag)+8 =
  {i32 count (1285), +8 self-rel}, entries at T+0x18+[T+8], stride 0x18, +0x10 = grid def tag.
  Grid def G: +0x10 node count, nodes at G+0x18+[G+0x18]+0x10, stride 0x40: +0x00 node hash,
  +0x18 step count, +0x20 self-rel steps (0x90 each), +0x38 exclusive-set hash (FNV-1;
  0x811C9DC5 = none), +0x3C flags. (scratchpad griddef.py reads it live.)
- Bladedancer (grid 130, def 0x80a6467c): 30 nodes x 1 step. Sets: {0} {1,15,16} {2,11,22}
  {3,17,18} {4,5,6} {7,8,9} {10} {13,14,21} {19} {23,28,29} {24,26,27}; set-less (flag 1):
  12, 20, 25.
- Node state byte (item element +0x5A+i) = steps bought (0 = off). FUN_00285E00 evaluates a
  node against its set partner (FUN_00284970) and indexes steps[state-1]: an inconsistent set
  walks off the array -> the crashes seen with "node 0 only" and "all 36 on" (0xc0000005 at
  eboot 0x286194).
- VALID SET = one node per exclusive set + the set-less ones:
  `d1-oracle inventory rebuild --dir capture-rig/inventory-hunter-full
     --subclass-nodes 0,1,2,3,4,7,10,12,13,19,20,23,24,25`
  Served result: subclass tooltip shows Armor/Agility bars, the grid shows the active nodes
  (Desktop\bladedancer-nodes-active.png). No crash.
- hwwatch leftover breakpoints AGAIN: an exec bp left on 0x269180 killed the game
  (0x80000004) the moment the subclass screen was dismissed - that function runs there. This is
  also the likely cause of the earlier "circle on the subclass screen crashes".
- Gear caches (init 0x63DF20; registry header +0x28 = count): player gear [0x26A5DE8] = 6,
  WEAPON gear [0x26A5DF0] = 3, ship [0x26A5DF8] = 1, ghost [0x26A5E00] = 0, vehicle
  [0x26A5E08] = 0. So the three weapons ARE loaded as gear; they are just not in hand.
- In-world after all of this (Moon): still the Ghost in the open hand
  (Desktop\moon-ghost-in-hand.png), jump works (z +1.39), no double jump measured, no firing.

## 36. Why the Ghost is in hand: there are NO weapon objects (05:35)
- Object type table (d1preservation design/player-in-world.md): 8 interactive, 9 biped,
  11 WEAPON, 12 vehicle, 19 gear, 21/22/23 hop_on_gear_{biped,weapon,ship}, 24 system.
  Census in every world we reach (Tower, mission, Moon): types {1,2,3,4,8,9,12,14,24} only -
  not one type-11 weapon, no gear, no hop_on_gear. The biped's children (linked at +0x44/+0x48,
  first child at biped+0x4C) are 2 x interactive + 1 x system (def 0x80ad27b2, ids 11/23/18)
  and one interactive (def 0x80aae367).
- So weapon_switch/weapon_ready (actions 53/54) run at spawn with nothing to ready, the
  first-person view falls back to the open hand + Ghost, fire/sprint/L1+R1 do nothing, and in
  third person (Tower) it is the "orb". d1preservation records the same symptom as open
  ("The Ghost persists and won't dismiss", GUARDIAN-IN-WORLD.md).
- Ruled out as the cause, each by serving it and reading it back: weapon-slot unlock flags
  (2501-2503), item talent grids, subclass node set, lifetime phase, team, touchpad state,
  mission scripting (same on the Moon). The weapon GEAR cache has 3 entries, the client never
  sends allocate_entity_indices (udt 19) and frees most of its entity indices (udt 20).
- Next leads, in order: (1) c_investment_equip_inventory_item_component (RTTI) - what applies
  an equipped item to the unit and what it waits for; (2) s_player_resurrection_payload - what
  the spawn carries (c_simulation_queue_player_resurrection_definition); (3) the kind-12 player
  slot value arrays we leave empty: +0x10 {u3 count, 4 x {hash, float}} and +0x4C {u4 count,
  8 x hash} (schema 0x808022A5) - 4 and 8 are suspiciously "abilities" and "gear" shaped, and
  the AH is the authority for that value.

## 37. Return to orbit and relaunch - WORKS (05:50, run 20261011-045928-WIN-ORBITBACK)
- In "A Guardian Rises": touchpad (Nav Mode) -> hold triangle "Go to Orbit" ->
  `cleanup (return_fireteam_to_orbit)` -> `setup:orbit_loading` -> `setup:orbit`. No crash.
- From that orbit, Director -> Earth -> Patrol -> Launch again -> `activity:in_world`, biped
  spawned again (team -1/-1, ready flag set). The activity host serves a second instance in the
  same session with no restart.

## 38. Spare items and equipping (06:15, run 20261011-050821-WIN-EQUIP)
- A spare item = one more element file in the inventory dir (key = base SOID + file index, so
  `13-Primary Weapons.bin` must carry SOID ...030E). Staged as a legacy element (+0x18 item
  hash, see d1-responder stage_loadout) then `inventory rebuild` + `art-arrangement write` +
  rebuild. character/profile builders now treat the FIRST item of an equipped ordinal as
  equipped and later ones as backpack spares (profile slot = bucket first slot + n).
- Result: Fatebringer shows in the PRIMARY WEAPONS panel next to the equipped Last Word
  (Desktop\inventory-spare-fatebringer.png).
- Pressing X on it sends investment 403 inventory_equip_item; the responder's composite reply
  (5 B: 1800000000) is accepted - no BAP drop, no crash (the old 2-byte reply dropped BAP).
  The screen does NOT swap: the real server follows with updated objects (profile 4/1
  equipment list, character 3/1, peer view 0/1). NEXT: on 403, decode the item SOID
  (request schema 0x80801942, one u64), swap it into the equipment list, re-push those objects.

## 39. Final check and the sharpest form of the weapon problem (06:25)
- Default Tower launch still works with tonight's files (run 20261011-051050-WIN-FINALTOWER:
  in_world, team 0/0, ready flag set, fade lifted).
- Tower census: 28 bipeds, 20 type-11 WEAPON objects. Walking each biped's child list
  (first child at +0x4C, next sibling at +0x48): NPC bipeds carry 1-2 weapons each; the
  PLAYER biped (index 0) carries only one `interactive` and one `system` object. So weapon
  objects can be created in our worlds - from an NPC's definition - but the player's loadout
  is never applied to its biped. That is the whole "Ghost in hand / orb / no sprint / no
  firing" problem, and it is the next thing to solve (leads in section 36).

## 40. Weapons, day 2 (2026-10-11 11:00-12:10) - CORRECTION to section 36/39
A hint from the d1preservation side (paraphrased): the spawned biped is not complete - the
spawn-in has many steps that must all be handled, in order, in time and correctly, with no pokes
or hooks left. Pokes: none at runtime; boot XML patches = heartbeat workaround, two
log patches, unsigned manifest, optional idle-kick NOP (none touch spawning).
- Ruled out by experiment (each read back): lifetime phases served IN ORDER 1 -> 2 -> 3 (AH held
  at D1_AH_SENSOR_PHASE=1, later phases injected; spawn happens at 3, still unarmed);
  udt 2 world_globals_state (now encodable: descriptor *0x1902388, schema 0x80800dc1 =
  {bool, float}, applier FUN_002A2270 -> world_globals+0x14, received byte +0x10) sent before
  spawn - no change; the inject dir now takes `<name>.udtN` (struct image) for any AH message.
- Lifetime setter 0x11DE30 notifies on change: vtbl+0xD0(old,new) for the phase, vtbl+0xC8 when
  value+4 (u32, we send NONE) changes, vtbl+0xF0 with value+2.
- Object creation: FUN_0032D180 (79 callers). Player spawn = FUN_00411830; spawn-point search
  via 0x4141A0; biped at 0x412D18; an optional pre-object at 0x412BDF.
- THE PLAYER'S WEAPONS DO EXIST. FUN_006676B0 (per unit, slots 0..2) reads the player's weapon
  descriptions and creates one object per slot through FUN_00666130 - a GENERIC object (fixed
  descriptor globals 0x1902DA8/0x1902D88, parent = unit), i.e. sobject type 8/24, not type 11
  (type 11 = tag-defined NPC weapons). unit+0x1E8.. = 3 x {handle, n, 0x10d2}. So "no weapon
  objects" (sections 36/39) was a wrong reading of the type census.
- Player record (players[i], stride 0x2AF0, [0x2725700]+8): +0x1660 character representation
  (tag, hash, 3 floats = level; 5 armour entries at +0x17E0), weapon descriptions at +0x19C8 /
  +0x1CE8 / +0x2008 (stride 0x320): +0 tag (0x80a7e218 for ALL three), +0xC / +0x10 hashes =
  UNSET (0x811C9DC5), +0x18 item SOID, +0x20 gear count, +0x24.. gear model tags (these match
  the weapon gear cache). 0x80a7e218 is a value in the live {tag, hash} asset table (10053
  entries at 0x382fb2404, sorted by hash) under many keys - a shared asset, probably fine.
- "Weapons disabled" switch in 0x6676B0: object named hash [0x25BE630] = 0xe0f3e461 via
  FUN_00118860, bool at +8 -> strips weapons. On our runs the lookup returns NULL (= not
  disabled).
- OPEN: why the three weapon objects stay inactive (first person = open hand + Ghost). Suspects:
  the two unset hashes at desc+0xC/+0x10 (0x668100 is handed desc+0xC), and the per-equipment
  fields the peer view leaves empty (0x8080183C +0x0A u16, +0x20 {hash,u32}, +0x28 list).

## 41. Fully slotted character (12:30) - Desktop\character-page1-full.png / -page2-full.png
- Every item definition states its BUCKET id at def+0x88 and (via the art table) its equipped
  ordinal. Read over all 7,544 items: ordinal 9 = Ships (bucket 0x0C), 12 = Emblems (0x19),
  13 = Emotes (0x1B), 14 = Shaders (0x1C), 15 = Sparrow Horn (0x1E), 16 = Artifacts (0x24).
  d1-oracle's BUCKET_IDS now has all five "undetermined" buckets, so those items get backpack
  slots (210 / 220 / 230 / 240 / 280) - without one the character screen shows a spinner.
- Slot padlocks on page 2: FLAG 2500 (left 1st = vehicle), 2497 (left 3rd = ship),
  2496 (right 1st = shader). Launcher grants them. Slot-flag family so far: 2496, 2497,
  2500, 2501 heavy, 2502 primary, 2503 special, 2479 subclass, 4917 + 4992 artifact.
- inventory-hunter-full now has 18 elements: subclass (valid node set), 3 weapons + spare
  Fatebringer, Ghost (Competitive Shell), 5 armour, artifact, sparrow (Arecibo Answer), horn,
  ship (ci 1853), emote (ci 1800), shader (ci 4481), emblem (ci 1512, SOID ...0312).
  The emblem element is refused by `character build` / `build-peer` (they set the emblem via
  --emblem), so: build character + peer WITHOUT 17-Emblems.bin, then add it and run
  `inventory rebuild` + `profile build`. Then wear-helmet (+0x2C = 1) in all three as before.
- Result: all 12 slots on page 1 and all 6 on page 2 show an item with icon; tooltips are
  complete (Ghost shell perks, sparrow speed/boost/durability). Tower launch re-checked.
- Not done: face/customization (0x8080181A; FUN_0054DC10 reads +0x00 u16 as an arrangement
  index, +0x1C hash, +0x20 wear-helmet and an option-byte array) - hidden by the helmet;
  Intellect/Discipline/Strength read 0 (items carry no stats); Grimoire 0.

## 42. WEAPONS WORK (2026-10-11 12:55) - Desktop\WEAPON-*.png
- Chain: players[i] config (0x90F530) -> rep buffer 0x1098 B (FUN_009105B0) -> set
  (0x73C3E0 -> 0x73C230) -> spawn. Weapon descriptions (rep+0x368 / +0x688 / +0x9A8) are built
  by FUN_0090EFD0(ordinal, equipment entry, ...):
    desc+0x18 = entry+0x00 (SOID), desc+0x20 = ordinal,
    row = FUN_0054B730(u16 entry+0x0A)          <- PATTERN TABLE, investment-globals root
          (tag 0x80a58000) +0x350 -> 0x80a5ffa9: 192 rows x 0x20 {asset key, hash1, type
          hash, hash3, n, .., off},
    desc+0x0C = row+4, desc+0x10 = row+8, desc+0x00 = asset table lookup of row+0 (the
    weapon's gameplay bundle); then 16 x u16 from the per-weapon perk tables (root +0x360,
    0x10-stride, via 0x54B930) -> desc+0x2D8, and the per-weapon stat table -> 20 floats.
- We shipped 0 at entry+0x0A for every item = pattern row 0 = {key 79257f0a -> 0x80a7e218,
  hashes unset}: a weapon object exists per slot but has no behaviour (open hand + Ghost).
- THE VALUE IS CONTENT: u32 at gear record +0x60 of the item definition (the gear record is
  the `gear @+0x...` art-arrangement already walks): The Last Word 32, Praedyth's Revenge 13,
  Corrective Measure 14. (def+0x7C is the weapon TYPE hash = the row's type hash; rows where
  hash1 == type are the type's base pattern: hand cannon 12, sniper 13, MG 14, rocket 15.)
- `python tools\finish_character.py` (after the three builders) sets entry+0x0A for ordinals
  6/7/8 in the character (+0x250) and the peer view (+0x218) and the wear-helmet byte.
- Result on the Moon map, zero pokes: first person with The Last Word in hand, crosshair,
  weapon HUD with ammo; firing consumes ammo (3 -> 1); triangle swaps to Praedyth's Revenge;
  hold triangle -> Corrective Measure with "NO HEAVY AMMO". The Ghost is gone.
- STILL OPEN: sprint (peak speed 5.6 u/s walking, L3 click and L3 held identical) and no
  grenade/melee/super HUD icons = ABILITIES. Same builder: FUN_0090F1B0 -> rep+0x180,
  0x90F440 -> rep+0x320, 0x90E560 / 0x90E6F0 / 0x90EA60 -> rep+0x324 / +0x330 / +0x358,
  fed by the appearance block's 5 x {u8, 16 hashes} (+0x10) and 32 hashes (+0x164) that we
  serve as zeros.

## 43. ABILITIES WORK (2026-10-11 13:10) - Desktop\FULL-HUD-*.png, GRENADE-thrown.png
- Appearance block +0x10: 5 x {u8 row, 16 x u32 option hash} (68 B each), +0x768: 32 x u16
  perk indices. FUN_0090E000 resolves row in the ability table (root +0x340 -> 38 rows x
  0x28, key hash -> bundle), then applies the 16 hashes and the block's 32 hashes
  (FUN_0061F620). Zeros = row 0 in all five slots (what every build shipped: no sprint, no
  grenade/melee, "lightning on L3"). 0xFF in all five asserts at spawn (0xc0000096 @0xC66BA6).
- The values are in the subclass TALENT GRID definition: each node record holds 0x808018E8
  elements {u32 option hash, u8 target row @+4, u8 ability row @+0xB, u32 slot @+0xC} and a
  0x80804628 list of u16 perk indices (0x80801787 = stat modifiers). For the active node set:
  Bladedancer slots [26, 12, 8, 3, 13]; options row 12: 9d0fa163 d2b26ec9; row 8: 62239b90
  d2b26ec9 d4d0f628; perks 208 88 89 84 76 77 78 79. (scratchpad grid3.py)
- tools\finish_character.py writes them (character + peer view) with the weapon patterns.
- Measured on the Moon map, zero pokes: HUD shows grenade + melee icons, super bar, 3 weapons;
  grenade throws (arc grenade, icon goes on cooldown); double jump 3.8 vs 1.0; sprint 8.3 u/s
  with L3 HELD (walk 5.6; a quick L3 click did not latch in my input timing).

## 44. Enemies spawn in the mission (2026-10-11 13:30, run 20261011-132448-WIN-ENEMY1)
- Mission bubbles with squads (world_sensors cache): bubble 3 = 30 squads / 45 members
  (+16 kind-40 performance sensors), 12 = 12 / 6, 1 = 6 / 0, 13 = 8 / 0, 16 = 5 / 0,
  5 = 3 / 0, start bubble 14 = 1 / 1 (the Ghost).
- `autopilot.py --director --destination guardian_rises_b3` (D1_AH_SENSOR_WORLD=0x80cb800d:3):
  the same "member exists = 1" value that spawns Tower NPCs spawns the mission's squads:
  44 bipeds and 69 type-11 weapon objects. The player (biped #843) starts inside the Wall
  (dark, flashlight cone, the mission Ghost's blue light), full HUD.
- The radar shows hostile contacts (red sector; inner ring red when a biped is ~5 m away behind
  a wall). In 8 s only 1 of 44 bipeds moved: they are idle - nothing wakes them (squad values
  and objectives are still schema defaults; mission script not emulated).
- Player facing = player array element +0x120 (fx, fy); position +0x90. Turn rate with the
  right stick held ~104 deg/s.
- Not yet seen on screen (dark); not yet tested: walking in from the start bubble 14 (the
  client did start a `normal_z_leg` transition to PRV112.1 on its own here), whether enemies
  react to gunfire, damage, kills.
- USER-VERIFIED (13:50): walked to a Dreg inside the Wall and shot it - it died. A nearby Dreg
  behind a broken window was trying to melee/shoot. So enemy AI, damage and death all work;
  what is missing is the mission's direction (lights, squad wake-up, objectives, phases).

## 45. Scripted objects (kind 4) - why the Wall is dark (2026-10-11 14:40)
- Record names are in the content (D1_WS_DUMP=<dir> on the world_sensors example writes every
  record entry; the name strings are at the end). Bubble 3 kind 4, subs 0-19: o_breach_control,
  o_breach_doors_lights, o_breach_doors_exit, o_breach_cables, o_breach_gating_lights
  ("m0_power_up"), o_breach_gating_back, o_breach_nut_back, o_chest_primary_weapon,
  o_device_invis_light ("breach_light_fall"), o_floor_grate_1a/1b/2a/2b, o_fallen_tripwire_1-7.
  Others: kind 1 sq_fallen_*, kind 3 obj_breach_fallen01, kind 6 *_cinematic, kind 24
  ho_ghostlight, kind 28 pm_* , kind 30 tg_m0_gating, kind 33 of_ghostlight, kind 40 actors
  (nux_ghost, dropper1, crawler1-8, runner1-4, shank1-2).
- Setter -> schema map for all 40 replication setters: each starts `lea rax,[g]; mov rax,[rax];
  mov esi,[rax]` = the value tag. Kind 4 (0x808007D9, 0xF0 B) = FUN_001238D0; kind 5 0x40BE80,
  6 0x402550, 12 0x408740, 15 0x11DAC0, 16 0x11DE30, 17 0x11EF80, 24 0x122C60, 28 0x129EE0,
  29 0x12A780, 30 0x12C900, 33 0x126C10, 34 0x10BC20, 39 0x406E20, 40 0x128B30.
- Kind-4 live record: value image at rec+0x1B0 (default {0, -1, bool 0, null name ref, ...}),
  object handle at rec+0x390 = -1 on all 21 loaded records: NO scripted object exists (read in
  the user's live session, no writes). FUN_001238D0: with rec+0xA4 == 0, value+8 (bool) set and
  no object -> FUN_00124A10 + FUN_00124DF0 create it; value+0 is a sequence number (rec+0x2A0).
- Next run: `autopilot.py --director --destination guardian_rises_b3_objects` serves
  capture\values\object_exists.bin (default image with +8 = 1) to every kind-4 slot.

## 46. All scripted objects created from served state; lights need object STATE flags (14:20)
- Run LIGHTS2 (object_exists.bin to every kind-4 slot): 7 of 21 objects created on arrival
  (grates, nut_back, gating_back, the m0 weapon); the other 14 (lights, doors, cables, control,
  chest, tripwires = the ones whose object definition has a dependency tag at +0x98) failed on
  the first apply. A frame with a CHANGED value (seq value+0 = 1, injected) created them at once.
  The client re-applies a slot only when its value changes; identical repeats are ignored.
- AH bug found + fixed (listener.rs): on_tick only ran when the socket was idle for `poll`; in a
  mission the client streams udt-6 sense updates, so repeats AND injected frames stopped after
  ~4 min. The tick now runs whenever `poll` has elapsed.
- AH: D1_AH_SENSOR_KIND_RESEQ=<kinds>: an alternate frame with those kinds' value+0 = 1 is built
  per bubble; every other repeat sends it. Run LIGHTS3 (autopilot destination
  guardian_rises_b3_objects): all 21 kind-4 objects exist, zero pokes, no injection.
- Still dark: the setter's applier FUN_00125250 walks the object's state components and calls each
  one's handler (FUN_003529F0, virtual) with value+0x20 = {2-bit mode, +0x10: struct 0x80804153
  whose +0x40 is a kind-0x22 DYNAMIC FLAGS bitset}. Light on/off is almost certainly a flag there.
  Any non-zero mode makes the oracle encoder fault (READ_UNMAPPED calling 0x2C8FF0, RIP 0x105B74A)
  - the known harness limitation (activity_host.rs FIELD_KIND_DYNAMIC_FLAGS: the game's dynamic
  flags pool is not set up in the static image). NEXT: give the encoder harness a dynamic-flags
  pool so object states (and probably objective/script states) can be served.
- Encoder work toward object states (14:50): d1-oracle `make_object` now accepts images longer
  than the struct (out-of-line storage) with self-relative pointers (`0xD1D1D1 << 40 | offset`),
  and D1_HARNESS_TRACE=1 appends the last 24 RIPs + registers to a unicorn fault. With mode = 1
  and a valid bitset pointer the encode still faults: the field walker (FUN_0105B410 loop,
  dispatch `call [0x18FAB40 + 0x150 + kind*8]` @0x105B74A) reads field kind 0xC8 (rax =
  0xffffffc8) while walking 0x80804117/0x80804153 - the descriptor it walks there is not the
  one `d1-eboot descriptors` prints (likely a runtime-built descriptor for the flags type).
  NEXT: dump the descriptor bytes the walker is reading (rdi/r14 at the fault) and compare with
  the static 0x80804153 record; then the flag meanings (light on) from the object's state
  component handler (FUN_003529F0 virtual).

## 47. The "flags" field, sequences (Ghost speaks), cinematics (2026-10-11 15:00-16:00, run SEQ1)
- Field kind 0x22 is NOT a flags bitset: FUN_010695C0 encodes a TYPED body {u32 type tag @+0,
  body @+0x10}: the tag through schema *[0x197DEB0] (BSS 0x28C2380 = 0x80800046, a 4-byte
  tag-ref struct; static record 0x13C4078 has its descriptor at +0x08), then the body with that
  tag. The oracle could not encode it: the BSS tag was unseeded and 0x80800046 was outside the
  registry closure (the walker ran on code bytes, kind 0xC8). Fixed in d1-oracle
  (runtime_ids::seed + registry::build extra roots, D1_ORACLE_EXTRA_TAGS for body schemas):
  kind-4 values with mode 1 now encode (86-byte frame). Scripted-object state bodies: still to
  identify (objects with a +0x98 state definition, class 0x808005eb, list component classes
  0x808028ef / 0x808006f9 / 0x8080279b ...).
- KIND 5 = SEQUENCES (setter FUN_0040BE80, value 0x808029a1 32 B {i32 start, u8 counter, ...,
  name ref}; default {-1, 0xFF}). Names: seq_d_o1_10 ... (Ghost dialogue per objective),
  seq_m_cue1/2 (music), seq_fallen_*, seq_ambush_*, seq_drone_*, objective
  _incoming/_completion_sequence (empty: def+0x68 = -1). A changed counter plays it:
  injecting {start 0, counter 1} into 3c2f5ed5 sub 3 (seq_d_o1_10) put the GHOST speaker
  indicator on the HUD (overnight\seq-sheet.png). Zero pokes.
- KIND 6 = CINEMATICS (value 0x8080254d: +4 play id, +8 play, +9 ?, +0x14 player (-1 = any),
  lists of participant ids). Only one is in the Wall: 992bb471 sub 10 = pf_104a_pwr (the
  POWER cinematic - the lights). The value applies and FUN_004027A0 runs, but FUN_004E2F50
  finds no cinematic with that hash: [[0x2697280]+0x1350] (registered cinematics) = 0.
  Registration = FUN_004E28F0(id), called from a method of record class 0x8080228f
  (binding 0x1982140, registered in FUN_00BF2B00) with the id at object+0x2C.
- Kind 32 = player objectives (obj_investigate_wall, obj_get_weapon, ...), kind 29 = player
  triggers, kind 28 pm_*, kind 30 tg_m0_gating, kind 24/33 ghost light.
- Registration trace (runs CINE1/CINE2, exec bp on FUN_004E28F0): 28 registrations during the
  boot -> orbit -> launch path, from object creation (0x32D51E -> 0x30D630 -> 0x30E64F ->
  FUN_004E6C50, a vtable method of an RTTI-less cinematic object type, vtable ~0x1981CB8, whose
  sibling FUN_004E6570 unregisters). In-world the list is empty again in both the Wall and the
  start bubble: the mission's own cinematic objects (pf_104a_pwr) are never created. NEXT: what
  creates them - a host-spawned simulation object (like squad actors) named by the kind-6
  value's participant lists (kind-0x23 ids), or a phase/precache record.

## 48. What creates cinematic objects (2026-10-11 16:00-17:00, runs CINE3/CINE4)
- The 28 objects that register cinematics during a load are content entities of class 0x80800861
  (globals_cinematic, orbit, globals_com01) carrying a cinematic component (runtime type
  0x808028A1, registered in FUN_00BFADD0). Its init (FUN_004E6C50) calls FUN_004E28F0 = register.
- They are created by the SIMULATION QUEUE: element types registered in FUN_00762DF0 -
  0x3A c_simulation_queue_cinematic_batch_request (handler FUN_00763F80 -> activity loader
  [0x267AF08] load/unload of cinematic batch slots), 0x39 start_stop, 0x37 cinematic_object
  (FUN_00764120 -> FUN_004E45D0), 0x38 cache_gear. Posted with FUN_002FF7C0(type, tag, data)
  only by world-controller states (prologue_intro_loading, initial_slice_set_loading filler,
  setup_orbit, physics_join).
- Batch requests seen on a mission load (exec bp on FUN_00763F80, request bytes: +0 type,
  +1 activity name, +0x29 load mask, +0x2A unload mask): type 1 act_cosmo_m0_highway load 3;
  load 4 unload 1; then unload 6 (physics_join). Nothing stays loaded in-world.
- The mission's power cinematic: kind-6 record def+0x68 = 0x0B975B3D = FNV-1("104a_pwr").
  FUN_004E2F50 compares it with each registered entry's virtual name hash (FUN_003537E0).
  The scene entity named 104a_pwr has not been found in content yet (no literal hash/name in
  cinematic_trv_activities 021f or cosmo packages). NEXT: read a registered entry's hash in an
  orbit session to learn how names are stored; find which batch/slot carries mission scenes.

## 49. The Ghost in the Wall (2026-10-11 17:30, run GHOST1)
- The music cue plays for the user; the Ghost's lines do not (no voice, no Ghost visible).
- The Ghost is squad member sq_nux_ghost__ghost (fc0e45a3 kind 2 sub 95) driven by
  ho_ghostlight (kind 24, value 0x8080065C {bool, u32 counter, name ref, typed body}, setter
  FUN_00122C60 stores it at rec+0x1B0 and acts when the counter rises), of_ghostlight (kind 33),
  pm_nux_ghost_light_up_fly_to_gun (kind 28 {name ref, u32}) and triggers
  pt_nux_ghost_light_up_start/continue (kind 29).
- Served {1, 1, null} to ho_ghostlight: applied, no visible change. Kind 28 values are NOT
  applied (the client reports kind 28 in its own udt-6 sense updates - client side).
- Normal start (bubble 14, autopilot destination guardian_rises_objects, run GHOST3): the start
  area has its own Ghost: group ecf574b5 = sq_ghost / sq_ghost__ghost (member has an actor,
  0x4ef58000), perf_ghost (kind 40), guide objects o_ghost_ab/_int, o_ghost_bc/_int,
  o_ghost_c/_int (kind 4) and triggers pt_bubble, pt_ab, pt_ab_1, pt_ab_2 (kind 29): the Ghost
  leads the player A -> B -> C. The 992bb471 group also names pf_104a_pwr._player_trigger
  (kind 29 sub 37) - the trigger that should start the power cinematic.
- The camera was in THIRD PERSON on the highway in this run (overnight\g3-now.png) - unexplained.

## 50. Black shadows, continued (2026-10-11 18:30, capture runs\20261010-144838-WIN-SHADOW\noon.rdc)
- New rdc_survey jobs: {"postvs":[eid]} (vertex-shader outputs + indices), {"raster":[eids]}
  (depth bias, depth clamp, viewport depth range, depth func).
- Ruled out: viewport depth mapping. Shadow-map draws (eid 4301-5380, ortho, w=1) write
  z_ndc unchanged (clip-space z 0.948 -> stored 0.948; viewport min/max -1..1 + negativeOneToOne,
  depth clamp on, func LessEqual, map cleared to 1). Scene draws write reverse-Z 0.15/w
  (func GreaterEqual), and the mask pass linearises it correctly (6.6666*d = 1/w).
- Depth bias in the shadow draws: constant 10-20, slope 4-8 (Vulkan units) - small, not the cause.
- Hand recomputation of eid 5421 (shader 1719) for three pixels with the captured constants
  (ssbo +112..+175 = view->light matrix, +240 map size 1536, +272 k 16797): receiver light-space
  z = 0.988-0.997, but the map is a smooth ground plane at 0.928-0.956 (8x8 grid) -> every
  receiver is "behind" the map by ~0.05 -> R = 0 everywhere. The matrix puts the CAMERA at
  shadow ndc (-0.03, -1.01, 1.0002): the bottom edge and the far plane of the light frustum,
  which is not where cascade 0 should sit. Also the uv mapping uses attr0 = (1,1,-1,-1) from
  the box VS, which flips both axes relative to how the map was rasterised.
- Leading hypotheses: (a) the receiver-side light matrix in buffer 213 is stale or from another
  cascade (shadPS4 buffer cache / upload timing), (b) attr0 (cascade scale/bias from the box
  vertex shader) is wrong in shadPS4. NEXT: dump the box VS (eid 5421 vertex stage) and its
  inputs to see where attr0 = (1,1,-1,-1) comes from; compare the light matrix the shadow-map
  draws used (their VS constants) with the receiver matrix.

## 51. Shadow cascade fitting FIXED in shadPS4 (2026-10-11 18:45, capture runs\20261011-184251-WIN-RDCFIX\fix.rdc)
- Chain (old capture eids): 4199 fills 7259 (120x270) with 2.0; 4207 scatters the visible scene
  into it with MIN blending; 4217..4289 reduce 7259 -> 7262 -> ... -> 7278 (1x1 RGBA32F) =
  the cascade scale/offset the mask pass's vertex shader fetches as attr0. Everything was the
  sentinel 2.0 -> 7278 = (1,1,-1,-1) -> wrong uv + the shadow map fitted to nothing.
- Cause: the 4207 vertex shader (vs_0x7a6d711fdad781fc) builds its full-screen triangles from
  the vertex index with EXEC-masked code: `s_and_b64 exec, s, vcc` / two masked v_mov /
  `s_andn2_b64 exec, s, exec` / v_cmp_eq 1.0, v0. shadPS4's CFG::SplitDivergenceScopes only
  opened a scope on S_AND_SAVEEXEC / S_ANDN2 / cmpx, so the masked v_mov ran for every lane and
  the compare became `1.0 == -1.0`: all vertices x = -1, zero-area triangles, nothing drawn.
- Fix: S_AND_B64 with dst EXEC also opens a scope (control_flow_graph.cpp;
  patches\shadps4-exec-and-scope.diff, included in shadps4-all-changes.diff). shadPS4 was also
  merged up to upstream 2026-10-11. The shader cache must be cleared after such a fix
  (%APPDATA%\shadPS4\cache\CUSA00219; old one kept as CUSA00219.bak-before-execfix).
- After: 7259-equivalent holds real data, the 1x1 texture holds real per-cascade values, and the
  mask (tex 3215) is a correct picture - lit ground white, cars in the Wall's shadow dark.
- STILL BLACK on screen: shadowed pixels and surfaces facing away from the sun get no ambient
  at all. The mask is now right, so the remaining fault is the ambient/sky term itself in the
  composite. NEXT: in fix.rdc find the composite pass and which input is zero.

## 52. BLACK SHADOWS FIXED (2026-10-11 19:25) - Desktop\SHADOWS-before.png / SHADOWS-FIXED-after.png
- tools\rdc_eval.py: evaluates one pixel of a fragment shader from the RenderDoc disassembly with
  the pass's real buffers, vertex outputs and texels (RenderDoc cannot debug these shaders).
  Reproduced the composite (eid 29789) to 1%: a shadowed pixel gets sky light ~1/25 of a sunlit
  one - the lighting was fine. Then the tone-map pass (eid 32179): its 32^3 colour-grading LUT
  returned (0,0,0,0) - slices 0-6 of the LUT were empty, so any colour with a dark blue channel
  became pure black. (rdc_survey apievents now prints numeric arguments.)
- Cause (shadPS4 texture cache, FindImage/ResolveOverlap): for each LUT slice the render target
  (2D array, layers = slice+1) correctly resolved to the cached 3D image, but the loop then
  called ResolveOverlap again with that volume as the request: against ITSELF (equal size + 3D
  -> ExpandImage = a new 3D image and a full copy per slice: 57 LUT images per frame) and
  against the stale 8-layer array from before the volume existed (ExpandImage again = its
  empty layers copied over slices 0-7).
- Fix: a resolved volume returns itself when it meets itself, and drops (does not copy from)
  the stale slice array. patches\shadps4-volume-self-overlap.diff (in shadps4-all-changes.diff).
- Result at the mission start: near-black pixels 31% -> 0%; cars, the Wall, the gun and the
  hands are all visible in shade.
- USER-VERIFIED (2026-10-11 evening): the highway start "looks way better, actually beautiful",
  nothing looks wrong. Inside the Wall the flashlight and geometry are visible. The user's
  memory of the real mission for that room: dark until the lights come on, Fallen seen in the
  distance, and the gate to the rifle (Khvostov) is one you normally walk through - here it is
  shut with a Dreg behind it. = the room is in its unscripted initial state (section 45/49).
