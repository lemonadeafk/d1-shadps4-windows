r"""Restoration (activity 165, world act_cosmo_m1_dome_a): the event script for the mission engine.

    python tools\mission_compile.py --script restoration --out inject\mission-restoration

Started inside Hive dome A (bubble 8, PRV64.64), at the foot of the Lunar Complex. The mission
really begins in the Steppes (public bubble 0), but public regions do not connect yet; the first
objective's own trigger is here in front of the complex anyway. Record names:
capture\values\record_names_restoration.json; NIGHT-NOTES sections 86-87.

What the game showed (run RES4): objective o1b is "UNLOCK THE GATE - Deploy Ghost to unseal the
gate to the Lunar Complex"; the gate (dg_cosmo_dome_a_door01) opens on state channel 2 = 1 and
the Hive behind it rushes out; a squad member's death is reported (cue "dead").

Steps are the ones tools\mission_compile.py knows: ("objective", sub, state, name),
("seq", group, sub, name), ("members", group, [subs], name), ("squad", group, [subs], name),
("countdown", seconds, name), ("phase", n, name), ("state", group, subs, channels,
name), ("fire", cue, name). Which Ghost line belongs to which moment is read from the names
(seq_d_o1_* = o1a, o2_* = o1b, o3_* = o1c) - the words are not known, the order is.
"""
WORLD = "0x80cb804b"            # act_cosmo_m1_dome_a:scenario_client
BUBBLE = 8                      # PRV64.64, inside Hive dome A
MISSION = "0xff4a0c1a"          # act_cosmo_m1_dome_a: objectives, their sequences and triggers
DIALOGUE = "0x8bd80dbe"         # the Ghost's lines and music cues
HIVE = "0x41d61614"             # dome A's Hive (bubble 8 only)

HIDDEN, ANNOUNCE, ACTIVE = 0, 1, 3
# objectives (kind 32) and their incoming / completion sequences (kind 5) in MISSION
O1A, O1B, O1C, O2 = 0, 3, 6, 9
INCOMING = {O1A: 1, O1B: 4, O1C: 7, O2: 10}
COMPLETION = {O1A: 2, O1B: 5, O1C: 8, O2: 11}
# Ghost lines (kind 5 in DIALOGUE)
D = dict(o1_s015=0, o1_s018=1, o1_s02=2, o2_s015=3, o2_s02=4, o2_s03=5, o2_s04=6, o3_s01=7,
         o3_s012=8, o3_s016=9, o3_s05=10, o3_s05_alt=11, m_intro=12, m_outro=13, m_cue1=14)
GATE = "0"                      # dg_cosmo_dome_a_door01 (kind 4); channel 2 = open
# squad members (kind 2 in HIVE); the other squads (upper front / rush / back, the t2 knight and
# troopers) have no member records in the content - section 87
SCARE01 = [8]
SCARE02 = [10, 12, 14, 16]
BASEMENT_THRALLS = [18, 19, 20, 21, 22, 23, 24]
BASEMENT_TROOPERS = [26, 27, 28]
WIZARD = 44
# squads WITHOUT member records, spawned at their designed size (compiler step "squad", sizes from
# capture\squad_sizes_80cb804b.json; NIGHT-NOTES 93-94). Which trigger brings which squad is read
# from the names: basement second wave (troopers02, t2 thrall02), the basement knight, the upper
# floor's front / back / t2 trooper, and the two rush waves.
BASEMENT_WAVE_2 = [29, 30]          # sq_hive_basement_troopers02, sq_t2_hive_basement_thrall02
KNIGHT = [31]                       # sq_t2_hive_basement_knight01
UPPER = [32, 33, 34, 35, 40, 41, 42]    # upper_front01-03, t2_upper_trooper01, upper_back01/02, t2_upper_back02
RUSH_1 = [36, 37]                   # upper_rush01, t2_upper_rush01
RUSH_2 = [38, 39]                   # upper_rush02, t2_upper_rush02
# ("dead" cues: a member's death report, see mission_compile.DEATH_BITS)


def line(delay, name):
    return (delay, "seq", DIALOGUE, D[name], "seq_d_" + name)


def objective_on(delay, sub, name, announce=False):
    steps = [(delay, "seq", MISSION, INCOMING[sub], name + " incoming")]
    if announce:
        steps += [(0, "objective", sub, ANNOUNCE, "NEW MISSION - Restoration"), (7, "objective", sub, ACTIVE, name)]
    else:
        steps += [(0, "objective", sub, ACTIVE, name)]
    return steps


def objective_done(delay, sub, name):
    return [(delay, "objective", sub, HIDDEN, name + " done"),
            (0, "seq", MISSION, COMPLETION[sub], name + " completion")]


def pt(group, sub):     # a player trigger
    return (group, 29, sub)


WAVE = (0, "seq", HIVE, 45, "seq_hive_wave_announce")

EVENT_SCRIPT = [
    # at the foot of the complex; the host's arrival frames (3 x 5 s) are over at SETTLE
    ("start", objective_on(0, O1A, "objective o1a", announce=True) + [
        (0, "seq", DIALOGUE, D["m_intro"], "seq_m_intro"),
        line(2, "o1_s015"),
    ]),
    # obj_m1_o1a._player_trigger: the way up to the gate (about -548,-601 in run RES4). The
    # Ghost unseals the gate while the player stands there: the gate rises and the first thrall
    # is behind it.
    (pt(MISSION, 13), objective_done(0, O1A, "objective o1a") + [
        line(0.5, "o1_s018"),
    ] + objective_on(2, O1B, "objective o1b: UNLOCK THE GATE") + [
        line(1, "o1_s02"),
        (8, "state", HIVE, GATE, (0.0, 0.0, 1.0), "the gate rises"),
        (0, "members", HIVE, SCARE01, "a thrall behind the gate (scare01)"),
    ] + objective_done(1, O1B, "objective o1b") + objective_on(2, O1C, "objective o1c") + [
        line(1, "o2_s015"),
    ]),
    (pt(HIVE, 48), [line(0, "o2_s02")]),               # pt_spawn_hive_intro01
    (pt(HIVE, 47), [                                    # pt_spawn_hive_scare02
        (0, "members", HIVE, SCARE02, "thralls rush in (scare02a-d)"),
    ]),
    # the basement: the frozen thralls and the troopers. _force is the same moment reached from
    # the other side.
    (pt(HIVE, 49), [                                    # pt_spawn_hive_intro02
        WAVE,
        (0, "members", HIVE, BASEMENT_TROOPERS, "troopers in the basement"),
        (0, "members", HIVE, BASEMENT_THRALLS, "the basement thralls"),
        (0, "squad", HIVE, BASEMENT_WAVE_2, "the basement's second wave"),
        line(1, "o2_s03"),
    ]),
    (pt(HIVE, 50), [(0, "fire", pt(HIVE, 49), "the basement (forced)")]),   # pt_spawn_hive_intro02_force
    (pt(HIVE, 52), [line(0, "o2_s04")]),               # pt_thrall_unfreeze
    (pt(HIVE, 53), [(0, "squad", HIVE, KNIGHT, "a knight (sq_t2_hive_basement_knight01)")]),  # pt_upper_knight_spawn
    (pt(HIVE, 54), [WAVE, (0, "squad", HIVE, RUSH_1, "the first rush")]),     # pt_upper_rush01_spawn
    (pt(HIVE, 55), [WAVE, (0, "squad", HIVE, RUSH_2, "the second rush")]),    # pt_upper_rush02_spawn
    # upstairs: the wizard
    (pt(HIVE, 51), [                                    # pt_upper_spawn01
        WAVE,
        (0, "seq", DIALOGUE, D["m_cue1"], "seq_m_cue1"),
        (0, "members", HIVE, [WIZARD], "the wizard (sq_hive_upper_wizard01)"),
        (0, "squad", HIVE, UPPER, "the upper floor's Hive"),
        line(3, "o3_s012"),
    ]),
    # o2 is "Kill the Hive Wizard" (user, Nav Mode): its death ends the mission - the outro line,
    # then lifetime phase 7, the game's own post-game screens (Advancement, Activity Rewards)
    ((HIVE, 2, WIZARD, "dead"), objective_done(1, O2, "objective o2") + [
        (0, "seq", DIALOGUE, D["m_outro"], "seq_m_outro"),
        # the game's own mission-end phase counts down, then its post-game screens (user: "mission
        # complete, then wait like 30 seconds, then the xp stats and activity rewards")
        (3, "countdown", 30, "MISSION END"),
        (1, "phase", 7, "the mission ends: post game"),
    ]),
    (pt(DIALOGUE, 15), [line(0, "o3_s016")]),          # pt_d_o3_s016_start
    (pt(MISSION, 14), objective_done(0, O1C, "objective o1c") + [   # obj_m1_o1c._player_trigger
        line(1, "o3_s05"),
    ] + objective_on(4, O2, "objective o2: KILL THE HIVE WIZARD") + [line(1, "o3_s01")]),
]
