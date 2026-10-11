"""Destiny 1 (CUSA00219, 01.29) on shadPS4 for Windows, against the d1preservation local server.

Windows stand-in for d1preservation's Linux launcher (capture-rig/run-boot.sh ->
run-signon-experiment.sh). Linux isolates the game in a network namespace with a private
/etc/hosts; Windows has no per-process equivalent, so this script edits the SYSTEM hosts file for
the length of a session and puts it back afterwards. Only that edit needs administrator rights, so
only a small helper (--hosts-guard) is elevated; the servers and shadPS4 run as the normal user so
tools/d1guest_win.py can attach to the game.

One session:
  1. find this PC's LAN address (the game rejects 127.0.0.1 as a server address)
  2. add the Destiny hostname redirects to the hosts file, between marker lines
  3. point shadPS4 at the local ShadNet server (config.json + users.json, originals backed up)
  4. start shadnet-server and d1-responder, logging into runs/<timestamp>-WIN/
  5. run shadPS4 with patches/CUSA00219-windows.xml and wait for it to exit
  6. ALWAYS undo 2 and 3, stop the servers, and copy the logs into the run folder

    python d1_launch.py              run a session
    python d1_launch.py --restore    only undo a session that was killed before it could clean up
"""

import argparse
import ctypes
import datetime
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(r"C:\d1server\d1preservation")
RELEASE = REPO / "d1-server" / "target" / "release"
GAME = HERE / "CUSA00219-129" / "eboot.bin"
PATCH = HERE / "patches" / "CUSA00219-windows.xml"
MANIFEST = REPO / "capture-rig" / "manifests" / "full_en.bin"
# Prefer our own build: stock afde631 plus patches/shadps4-v_cmp_class.diff, without which the
# shader translator aborts (V_CMP_CLASS_F32 mask 0x2) while Destiny loads its first world.
SHADPS4_FIXED = Path(r"C:\d1server\shadPS4\build\shadps4.exe")
SHADPS4_STOCK = Path(os.environ["APPDATA"]) / "shadPS4QtLauncher" / "versions" / "Pre-release" / "shadPS4.exe"
SHADPS4 = SHADPS4_FIXED if SHADPS4_FIXED.exists() else SHADPS4_STOCK
SHAD_USER = Path(os.environ["APPDATA"]) / "shadPS4"
OPENSSL = Path(r"C:\Program Files\Git\usr\bin\openssl.exe")
RENDERDOC_CMD = Path(r"C:\d1server\renderdoc\RenderDoc_1.43_64\renderdoccmd.exe")
HOSTS = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"

BEGIN = "# >>> d1-local BEGIN (added by shadgames/d1_launch.py; removed when it exits)"
END = "# <<< d1-local END"
CONFIG_BACKUP_SUFFIX = ".d1-original"

# Same set as run-signon-experiment.sh. A scan of the 01.29 eboot on 2026-10-10 found no Destiny
# service host outside it (the rest are facebook/havok/SDK strings).
def redirect_names():
    names = []
    for d in ("deadorbit", "gravityshavings"):
        names += [f"signon.{d}.net", f"signon2.{d}.net", f"cdn.{d}.net", f"upload.{d}.net"]
        for i in range(1, 9):
            names += [f"www{i}.signon.{d}.net", f"stun{i}.signon.{d}.net"]
    names += [f"stun.{r}.demonware.net" for r in ("us", "eu", "jp", "au")]
    names += [
        "auth.api.np.ac.playstation.net",
        "auth.api.sp-int.playstation.net",
        "srv.shadps4.net",
        "dm-partnernet.upload.deadorbit.net",
        "help.bungie.net",
        "www.bungie.net",
    ]
    return names


def log(msg):
    print(f"[d1] {msg}", flush=True)


# ── hosts file ────────────────────────────────────────────────────────────────────────────────────

# A PERSISTENT block (--hosts-persist) stays across sessions so unattended runs need no admin
# prompt; sessions leave it alone and only --restore removes it.
PBEGIN = "# >>> d1-local PERSISTENT BEGIN (shadgames/d1_launch.py --hosts-persist; remove with --restore)"


def strip_block(text):
    for begin in (BEGIN, PBEGIN):
        text = re.sub(re.escape(begin) + r".*?" + re.escape(END) + r"\r?\n?", "", text, flags=re.S)
    return text


def hosts_add(ip, persistent=False):
    text = strip_block(HOSTS.read_text(encoding="utf-8", errors="replace"))
    if text and not text.endswith("\n"):
        text += "\n"
    block = [PBEGIN if persistent else BEGIN] + [f"{ip}\t{n}" for n in redirect_names()] + [END]
    HOSTS.write_text(text + "\n".join(block) + "\n", encoding="utf-8")
    subprocess.run(["ipconfig", "/flushdns"], capture_output=True)


def hosts_remove():
    text = HOSTS.read_text(encoding="utf-8", errors="replace")
    if BEGIN not in text and PBEGIN not in text:
        return False
    HOSTS.write_text(strip_block(text), encoding="utf-8")
    subprocess.run(["ipconfig", "/flushdns"], capture_output=True)
    return True


def hosts_present():
    text = HOSTS.read_text(encoding="utf-8", errors="replace")
    return BEGIN in text or PBEGIN in text


def persistent_ip():
    """The IP a persistent block redirects to, or None."""
    text = HOSTS.read_text(encoding="utf-8", errors="replace")
    i = text.find(PBEGIN)
    if i < 0:
        return None
    m = re.search(r"^(\S+)\tsignon\.deadorbit\.net$", text[i:], flags=re.M)
    return m.group(1) if m else None


def elevate_self(flag):
    """Re-run this script elevated with one flag, wait for it, return True if it ran."""
    import ctypes.wintypes as wt

    class SEI(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wt.HWND),
                    ("lpVerb", wt.LPCWSTR), ("lpFile", wt.LPCWSTR), ("lpParameters", wt.LPCWSTR),
                    ("lpDirectory", wt.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wt.HINSTANCE),
                    ("lpIDList", ctypes.c_void_p), ("lpClass", wt.LPCWSTR), ("hkeyClass", wt.HKEY),
                    ("dwHotKey", wt.DWORD), ("hIcon", wt.HANDLE), ("hProcess", wt.HANDLE)]
    sei = SEI(cbSize=ctypes.sizeof(SEI), fMask=0x40, lpVerb="runas", lpFile=sys.executable,
              lpParameters=f'"{Path(__file__).resolve()}" {flag}', nShow=0)
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
        return False
    ctypes.windll.kernel32.WaitForSingleObject(sei.hProcess, 120000)
    return True


# Only the hosts file needs administrator rights. Running the whole session elevated would make
# shadPS4 elevated too, and then nothing unelevated (tools/d1guest_win.py) can open its memory -
# OpenProcess fails with error 5. So a small elevated guard owns the hosts block instead: it adds
# it, then removes it when the launcher writes the stop file OR the launcher process disappears
# (a closed window still cleans up).
GUARD_LOG = Path(os.environ.get("TEMP", ".")) / "d1-hosts-guard.log"


def hosts_guard(parent_pid, ip, stop_file):
    try:
        hosts_add(ip)
        h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, parent_pid)   # SYNCHRONIZE
        while not Path(stop_file).exists():
            if not h or ctypes.windll.kernel32.WaitForSingleObject(h, 1000) == 0:   # parent exited
                break
    except Exception as e:   # noqa: BLE001 - this process has no console; leave a trace
        GUARD_LOG.write_text(f"{datetime.datetime.now().isoformat()} {e!r}\n", encoding="utf-8")
    finally:
        try:
            hosts_remove()
        finally:
            Path(stop_file).unlink(missing_ok=True)


def start_hosts_guard(ip, stop_file, timeout=90.0):
    """Ask for elevation once; returns True when the redirect block is in place."""
    if is_admin():
        hosts_add(ip)
        return True
    params = f'"{Path(__file__).resolve()}" --hosts-guard {os.getpid()} {ip} "{stop_file}"'
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 0)
    if rc <= 32:
        log("the administrator prompt was declined or failed - cannot redirect Destiny's hostnames")
        return False
    end = time.time() + timeout
    while time.time() < end:
        if hosts_present():
            return True
        time.sleep(0.3)
    log(f"the hosts guard never added the redirect (see {GUARD_LOG} if it exists)")
    return False


def stop_hosts_guard(stop_file, timeout=15.0):
    if is_admin():
        return hosts_remove()
    Path(stop_file).write_text("stop", encoding="utf-8")
    end = time.time() + timeout
    while time.time() < end and hosts_present():
        time.sleep(0.3)
    return not hosts_present()


# ── shadPS4 settings ─────────────────────────────────────────────────────────────────────────────

def backup_once(path):
    """Keep the user's own settings in <file>.d1-original until the session puts them back."""
    bak = path.with_name(path.name + CONFIG_BACKUP_SUFFIX)
    if not bak.exists():
        shutil.copy2(path, bak)


def restore_settings():
    restored = False
    for name in ("config.json", "users.json"):
        path = SHAD_USER / name
        bak = path.with_name(name + CONFIG_BACKUP_SUFFIX)
        if bak.exists():
            shutil.copy2(bak, path)
            bak.unlink()
            restored = True
    return restored


def parse_gpu_overrides(items):
    """['readbacks_mode=1', 'copy_gpu_buffers=true'] -> {'readbacks_mode': 1, ...}"""
    out = {}
    for item in items or []:
        key, _, raw = item.partition("=")
        val = {"true": True, "false": False}.get(raw.lower())
        if val is None:
            try:
                val = int(raw, 0)
            except ValueError:
                val = raw
        out[key] = val
    return out


def apply_settings(ip, gpu=None):
    cfg_path, users_path = SHAD_USER / "config.json", SHAD_USER / "users.json"
    backup_once(cfg_path)
    backup_once(users_path)

    # status/server.md "Client side must be configured to match". This shadPS4 keeps the network
    # keys in both "General" and "Network", so set both.
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    for section in ("General", "Network"):
        cfg.setdefault(section, {}).update({
            "connected_to_network": True,
            "shad_net_enabled": True,
            "shadnet_server": "127.0.0.1:31313",
            "shadnet_webapi_server": f"http://{ip}:31315",
        })
    for key, val in (gpu or {}).items():
        # Keys live in GPU or Vulkan (e.g. vkguest_markers); find the section that has it.
        section = next((s for s in ("GPU", "Vulkan") if key in cfg.get(s, {})), None)
        if section is None:
            raise SystemExit(f"unknown shadPS4 GPU/Vulkan setting: {key}")
        cfg[section][key] = val
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    users = json.loads(users_path.read_text(encoding="utf-8"))
    for u in users["Users"]["user"]:
        if u.get("user_id") == 1000:
            u.update(shadnet_enabled=True, shadnet_npid="D1Guardian", shadnet_password="d1-local")
    users_path.write_text(json.dumps(users, indent=2), encoding="utf-8")


# ── environment checks ───────────────────────────────────────────────────────────────────────────

def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def lan_ip():
    """IPv4 of the adapter that has a default gateway, skipping VPN/virtual adapters."""
    ps = (
        "Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } | "
        "ForEach-Object { '{0}|{1}' -f $_.InterfaceAlias, $_.IPv4Address.IPAddress }"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    skip = ("warp", "vpn", "vethernet", "virtualbox", "vmware", "loopback", "tailscale")
    for line in out.splitlines():
        alias, _, addr = line.partition("|")
        if addr and not any(s in alias.lower() for s in skip) and not addr.startswith(("127.", "169.254.")):
            return addr.strip()
    return None


def warp_connected():
    cli = shutil.which("warp-cli") or r"C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe"
    try:
        out = subprocess.run([cli, "status"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "Connected" in out and "Disconnected" not in out


def check_files():
    missing = [p for p in (GAME, PATCH, MANIFEST, SHADPS4, OPENSSL,
                           RELEASE / "d1-responder.exe", RELEASE / "shadnet-server.exe") if not p.exists()]
    for p in missing:
        log(f"MISSING: {p}")
    return not missing


def make_cert(run):
    # Self-signed, same names as the Linux launcher. shadPS4 stubs the cert callbacks, so the
    # client does not pin it (status/shadps4.md "Cert pinning is not enforced on this path").
    crt, key = run / "tls.crt", run / "tls.key"
    san = ",".join(f"DNS:{n}" for n in ("signon.deadorbit.net", "signon.gravityshavings.net",
                                         "www1.signon.deadorbit.net", "www1.signon.gravityshavings.net"))
    subprocess.run([str(OPENSSL), "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(key), "-out", str(crt), "-days", "2",
                    "-subj", "/CN=signon.deadorbit.net", "-addext", f"subjectAltName={san}"],
                   check=True, capture_output=True)
    return crt, key


def wait_port(host, port, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def wait_log(path, needle, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        if path.exists() and needle in path.read_text(encoding="utf-8", errors="replace"):
            return True
        time.sleep(0.2)
    return False


# ── session ──────────────────────────────────────────────────────────────────────────────────────

def summarize(run):
    emu = run / "emulator.log"
    if not emu.exists():
        return
    text = emu.read_text(encoding="utf-8", errors="replace")
    guest = run / "guest-stdout.log"
    if guest.exists():
        text += "\n" + guest.read_text(encoding="utf-8", errors="replace")
    states = re.findall(r"bootflow:[a-z_]+", text)
    seen = list(dict.fromkeys(states))
    log(f"boot-flow states reached: {' -> '.join(seen) if seen else '(none logged)'}")
    for pat in ("RELEASE_VHALT", "Unhandled Exception", "error\\.[a-z_]+"):
        hits = list(dict.fromkeys(re.findall(pat, text)))
        if hits:
            log(f"{pat}: {', '.join(hits[:8])}")
    crash = sorted((SHAD_USER / "temp" / "CUSA00219" / "temp" / "crash_folder" / "orbis").glob("crash_folder_*"))
    if crash and crash[-1].stat().st_mtime >= run.stat().st_ctime:
        shutil.copytree(crash[-1], run / "guest-crash-report", dirs_exist_ok=True)
        info = (crash[-1] / "crash_info.txt")
        if info.exists():
            m = re.search(r"halt information:\s*\n\s*(.+)", info.read_text(errors="replace"))
            log(f"game crash report: {m.group(1).strip() if m else info}")


def session(args):
    if not check_files():
        return 1
    if warp_connected():
        log("Cloudflare WARP is CONNECTED - disconnect it first, or the game's traffic may bypass the redirect.")
        if not args.allow_warp:
            return 1
    ip = args.ip or lan_ip()
    if not ip:
        log("could not find this PC's LAN address; pass --ip 192.168.x.y")
        return 1

    run = REPO / "runs" / (datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-WIN" + (f"-{args.name}" if args.name else ""))
    (run / "uploads").mkdir(parents=True)
    log(f"run folder: {run}")
    log(f"LAN address: {ip}")
    log(f"emulator: {SHADPS4}" + ("" if SHADPS4 == SHADPS4_FIXED else "  (STOCK - no V_CMP_CLASS fix)"))

    procs = []
    stop_file = run / "hosts-guard.stop"
    try:
        persistent = persistent_ip()
        if persistent == ip:
            log("hosts: using the persistent redirect (no admin prompt; remove with --restore)")
        else:
            if persistent:
                log(f"hosts: persistent redirect points at {persistent}, not {ip} - using a per-session one")
            log("asking Windows for permission to edit the hosts file (click Yes)")
            if not start_hosts_guard(ip, stop_file):
                return 1
        log(f"hosts: {len(redirect_names())} Destiny names -> {ip}")
        gpu = parse_gpu_overrides(args.gpu)
        apply_settings(ip, gpu)
        if gpu:
            log(f"shadPS4 GPU settings for this session: {gpu}")
        log("shadPS4: ShadNet -> 127.0.0.1:31313 as D1Guardian (your settings are backed up)")
        crt, key = make_cert(run)

        env = dict(os.environ,
                   D1_MANIFEST_FILE=str(MANIFEST), D1_UPLOAD_DIR=str(run / "uploads"),
                   D1_BAP_IP=ip, D1_CLIENT_IP=ip, D1_AH_IP=ip)
        # run-boot.sh's pinned account/character environment (lines 87-220). Without the push at
        # `echo`, families 4 then 3, investment_signin has nothing to satisfy it and the client
        # gives up with error.no_investment_connection ("chicken") - seen here on 2026-10-10.
        # Anything already set in the environment wins, as with run-boot.sh's ${VAR:-default}.
        for name, value in {
            "D1_503_SOID": "1",
            "D1_ACCOUNT_SOID": "0xD100000000000001",
            "D1_CHARACTER_SOID": "0xD100000000000101",
            "D1_PUSH_CHARACTER": "1",
            "D1_PUSH_AT": "echo",
            "D1_PUSH_FAMILY": "4,3",
            "D1_CHARACTER_LIFECYCLE": "1",
            "D1_PROFILE_FILE": str(REPO / "capture-rig" / "profiles" / "profile-old-russia.bin"),
            "D1_ACCOUNT_TRACE_OUT": str(run / "account-trace.bin"),
            "RUN_OUT": str(run),
        }.items():
            env.setdefault(name, value)
        if args.director:
            # The real Director flow (Set Destination -> Tower -> Launch), found 2026-10-10:
            #  - the investment clock is on by default in the responder (D1_INVESTMENT_TIME=now);
            #  - flags 308 and 3389 = "banned from social spaces" (Tower requirement set
            #    0x6291ABC8 is NOT 3389 / NOT 308), so they are dropped from the shipped ten;
            #  - flag 131 makes the Tower's Director entry available (status 4 instead of
            #    "Requirements Not Met"). tools\director_rules.py prints these rules live.
            # The in-world shortcut launches still need 308/3389, so this is opt-in.
            for name, value in {
                "D1_UNLOCK_FLAGS": "98,131,419,440,834,2667,5015,5987,6018",
                "D1_UNLOCKS": str(REPO / "capture-rig" / "unlocks" / "unlocks-200-campaign.bin"),
                "D1_FAMILY42": "1",
                # msg 43 f4.1 field 8 = big-party size. With the empty stub it is 0, a solo player
                # counts as a "big party", and setup:matchmaking loops on
                # 'big-party-count-exceeds-teams' (tools\hwwatch.py, 2026-10-10).
                "D1_MM_TUNING": "8=4",
                # Activity host serves the spawn state (2026-10-10, no pokes): one udt-5
                # sensor_auth_update carrying the initial state of the Tower's 99 authority sensor
                # slots (the client's post-pass waits for all of them), lifetime phase 3 on the
                # lifetime record {0x40aebf90, 0x10, 2}, and player slot sub 4 seated with our
                # profile SOID. Repeated every 5 s for 2 min so one copy lands after the world is
                # resident. NIGHT-NOTES section 14.
                "D1_AH_SENSOR_PHASE": "3",
                # The slot names are not measured any more: the activity host derives them from
                # the world record's packages (d1_oracle::world_sensors; 100/100 agreement with
                # the live measurement kept in capture	ower-sensor-init.txt). 0x80C7A005 is the
                # city_tower_default1 world record.
                "D1_AH_SENSOR_WORLD": "0x80c7a005",
                "D1_AH_SENSOR_PLAYER_SLOT": "auto",
                # NPCs: open the sensor-authority hand-over for peer 0 (generation 1, not yet
                # valid) so the client applies host values to squads, and tell every squad member
                # (kind 2) that it exists. The Tower's vendors and civilians spawn from this.
                "D1_AH_SENSOR_AUTHORITY": "0:1:0",
                # live experiment channel: tools\inject_sensor.py drops udt-5 frames here
                "D1_AH_SENSOR_INJECT_DIR": str(Path(__file__).resolve().parent / "inject"),
                "D1_AH_SENSOR_KIND_VALUE": "2:0x80800868:" + str(
                    Path(__file__).resolve().parent / "capture" / "values" / "member_exists.bin"),
                "D1_AH_SENSOR_REPEAT_S": "5",
                "D1_AH_SENSOR_REPEAT_MAX": "24",
                # the same lifetime value sets the world clock: late morning instead of midnight
                "D1_AH_SENSOR_TIME_OF_DAY": "0.45",
            }.items():
                env.setdefault(name, value)
                log(f"director mode: {name}={env[name]}")
        for item in args.env or []:
            name, _, value = item.partition("=")
            env[name] = value
            log(f"server setting {name}={value}")
        if args.inworld:
            # design/GUARDIAN-IN-WORLD.md §2 boot line, with the GEARED roster of the run the
            # operator played (140504-GEARED-RADV-11). The AH identity values must match
            # d1-activity-host or the failure is silent (run-boot.sh lines 193-210).
            for name, value in {
                "D1_ANSWER_FAMILIES": "0,2",
                "D1_ACTIVITY_HOST": "1",
                "D1_AH_BIND_PORT": "4110",
                "D1_AH_PORT": "4110",
                "D1_AH_HOST_TOKEN": "0xD1A0000000000001",
                "D1_AH_HOST_TEXT": "d1ah-d1a0000000000001",
                "D1_ROSTER_DIR": str(REPO / "capture-rig" / "rosters-f0-geared"),
            }.items():
                env.setdefault(name, value)
            # The WORLD the activity host publishes (global_activity_state+0x688) and its scenario
            # facts. Unmeasured worlds have no row in d1-activity-host's worlds.rs, so their
            # checksum/bubbles must be passed here once captured with tools/scenario_checksum_win.py.
            for opt, name in ((args.world, "D1_AH_ACTIVITY"), (args.checksum, "D1_AH_ACTIVITY_CHECKSUM"),
                              (args.bubbles, "D1_AH_BUBBLE_COUNT"), (args.chosen, "D1_AH_BUBBLE_CHOSEN")):
                if opt:
                    env[name] = opt
        flags = subprocess.CREATE_NO_WINDOW
        procs.append(subprocess.Popen([str(RELEASE / "shadnet-server.exe"), "--bind", "127.0.0.1:31313"],
                                      cwd=REPO, stdout=open(run / "shadnet.log", "wb"),
                                      stderr=subprocess.STDOUT, creationflags=flags))
        procs.append(subprocess.Popen([str(RELEASE / "d1-responder.exe"), "--bind", ip,
                                       "--cert", str(crt), "--key", str(key)],
                                      cwd=REPO, env=env, stdout=open(run / "responder.log", "wb"),
                                      stderr=subprocess.STDOUT, creationflags=flags))
        if args.inworld:
            # Stub Activity Host. Defaults: world pvp_moonbase, activity 407 (worlds.rs/state.rs).
            procs.append(subprocess.Popen([str(RELEASE / "d1-activity-host.exe"), "serve",
                                           "--bind", f"{ip}:4110"],
                                          cwd=REPO, env=env, stdout=open(run / "activity-host.log", "wb"),
                                          stderr=subprocess.STDOUT, creationflags=flags))
            if not wait_log(run / "activity-host.log", f"activity-host listening on {ip}:4110", timeout=30):
                log(f"d1-activity-host did not report its listener - see {run / 'activity-host.log'}")
                return 1
            log(f"activity host up on 4110 (world {env.get('D1_AH_ACTIVITY', 'pvp_moonbase')}, activity 407)")
        if not wait_port("127.0.0.1", 31313):
            log(f"shadnet-server did not come up on 127.0.0.1:31313 - see {run}")
            return 1
        # Never probe the responder by connecting to it: it numbers BAP connections, and the QueueZ
        # push that clears investment_signin only fires on connection #0. A probe connection took
        # #0 on 2026-10-10 and the run died with "chicken". Wait for its own `listening` lines.
        for line in (f"listening https://{ip}:443", f"listening tcp://{ip}:3075"):
            if not wait_log(run / "responder.log", line):
                log(f"d1-responder never logged '{line}' - see {run / 'responder.log'}")
                return 1
        log("servers up (ShadNet 31313, responder 443/32556/80/8080/31315/8788, BAP 3075)")
        (run / "RUN-INFO.txt").write_text(
            f"started: {datetime.datetime.now().isoformat()}\nplatform: windows\nlan ip: {ip}\n"
            f"game: {GAME}\npatch: {PATCH}\nmanifest: {MANIFEST}\nemulator: {SHADPS4}\n", encoding="utf-8")

        log("starting Destiny - close the game window to end the session")
        # The diagnostics patch routes the game's own `networking:`/bootflow log to stdout, which
        # is where gate names and halt reasons appear - keep it.
        emu_cmd = [str(SHADPS4), "-p", str(PATCH), "--game", str(GAME)]
        emu_env = None
        if args.renderdoc:
            # Portable RenderDoc's Vulkan layer is not registered (that needs admin), so hand the
            # loader its manifest for this process only and switch the layer on explicitly.
            emu_env = dict(os.environ, VK_ADD_LAYER_PATH=str(RENDERDOC_CMD.parent),
                           VK_INSTANCE_LAYERS="VK_LAYER_RENDERDOC_Capture",
                           ENABLE_VULKAN_RENDERDOC_CAPTURE="1")
            (SHAD_USER / "captures" / "CUSA00219").mkdir(parents=True, exist_ok=True)
            # Portable RenderDoc injects itself; shadPS4 then finds renderdoc.dll already loaded
            # (renderdoc.cpp GetModuleHandle) and its F12 hotkey triggers a capture.
            emu_cmd = [str(RENDERDOC_CMD), "capture", "-w", "-c", str(run / "capture"), *emu_cmd]
            log(f"RenderDoc injected; press F12 in the game window to capture into {run}")
        emu = subprocess.Popen(emu_cmd, cwd=SHADPS4.parent, env=emu_env,
                               stdout=open(run / "guest-stdout.log", "wb"), stderr=subprocess.STDOUT)
        emu.wait()
        log(f"shadPS4 exited with code {emu.returncode:#x}" if emu.returncode else "shadPS4 exited")
        return 0
    except KeyboardInterrupt:
        log("interrupted")
        return 130
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        if persistent_ip() == ip:
            clean = True        # the persistent block is meant to stay
        else:
            clean = stop_hosts_guard(stop_file) if hosts_present() else True
        restored = restore_settings()
        log(f"cleanup: hosts {'restored' if clean else 'STILL REDIRECTED - run python d1_launch.py --restore'}, "
            f"shadPS4 settings {'restored' if restored else 'unchanged'}")
        src = SHAD_USER / "log" / "shad_log.txt"
        if src.exists():
            shutil.copy2(src, run / "emulator.log")
        summarize(run)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--restore", action="store_true", help="only undo hosts/settings left by a killed session")
    ap.add_argument("--ip", help="override the LAN address the game is pointed at")
    ap.add_argument("--name", help="suffix for the run folder name")
    ap.add_argument("--inworld", action="store_true",
                    help="also run the activity host + geared roster (for tools/d1_inworld.py)")
    ap.add_argument("--world", help="with --inworld: world the activity host publishes (e.g. city_tower_default1)")
    ap.add_argument("--checksum", help="with --world: measured scenario +0x0C checksum (D1_AH_ACTIVITY_CHECKSUM)")
    ap.add_argument("--bubbles", help="with --world: measured bubble count (D1_AH_BUBBLE_COUNT)")
    ap.add_argument("--chosen", help="with --world: choosable bubbles, e.g. 0 or 0-4,9-14 (D1_AH_BUBBLE_CHOSEN)")
    ap.add_argument("--allow-warp", action="store_true", help="start even if Cloudflare WARP is connected")
    ap.add_argument("--gpu", action="append", metavar="KEY=VALUE",
                    help="shadPS4 GPU setting for this session only, e.g. readbacks_mode=1 (repeatable)")
    ap.add_argument("--director", action="store_true",
                    help="serve the account so the Director works: Tower selectable and launchable")
    ap.add_argument("--env", action="append", metavar="KEY=VALUE",
                    help="extra environment for the servers, e.g. D1_EMPTY_ROSTER=1 (repeatable)")
    ap.add_argument("--renderdoc", action="store_true",
                    help="launch shadPS4 under portable RenderDoc; F12 in the game captures a frame")
    ap.add_argument("--hosts-persist", action="store_true",
                    help="leave the hosts redirect in place across sessions (one admin prompt); undo with --restore")
    ap.add_argument("--hosts-guard", nargs=3, metavar=("PARENT_PID", "IP", "STOP_FILE"),
                    help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.hosts_guard:
        pid, ip, stop = args.hosts_guard
        hosts_guard(int(pid), ip, stop)
        return 0
    if args.hosts_persist:
        ip = args.ip or lan_ip()
        if not ip:
            log("could not find this PC's LAN address; pass --ip")
            return 1
        if is_admin():
            hosts_add(ip, persistent=True)
        else:
            log("asking Windows once for permission to leave the redirect in place (click Yes)")
            elevate_self(f"--hosts-persist --ip {ip}")
        ok = persistent_ip() == ip
        log(f"persistent redirect -> {ip}: {'IN PLACE' if ok else 'FAILED'}. "
            f"PSN's web login and srv.shadps4.net stay redirected until: python d1_launch.py --restore")
        return 0 if ok else 1
    if args.restore:
        settings = restore_settings()
        hosts = "already clean"
        if hosts_present():
            if is_admin():
                hosts_remove()
            else:
                elevate_self("--restore")
            hosts = "still redirected (admin prompt declined?)" if hosts_present() else "restored"
        log(f"hosts: {hosts}; settings: {'restored' if settings else 'nothing to restore'}")
        return 0
    if restore_settings():
        log("restored shadPS4 settings left by a previous session that did not exit normally")
    # A stale hosts block from a killed guard is harmless: the next guard's hosts_add replaces it.
    return session(args)


if __name__ == "__main__":
    sys.exit(main())
