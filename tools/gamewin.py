"""The shadPS4 game window, for unattended runs: find it, screenshot it, send it keys.

    python tools\\gamewin.py shot out.png      # screenshot of the game window only
    python tools\\gamewin.py key n [n ...]      # bring it to the front and tap keys

shadPS4 keyboard map (AppData\\shadPS4\\input_config\\default.ini): cross = n (or keypad 2),
circle = b, square = v, triangle = c, options = enter, d-pad = arrow keys.
SDL only delivers input to the FOCUSED window (d1preservation status/shadps4.md), so key() focuses it first.
"""

import ctypes
import os
import struct
import subprocess
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import winproc  # noqa: E402

VK = {"n": 0x4E, "b": 0x42, "v": 0x56, "c": 0x43, "enter": 0x0D, "up": 0x26, "down": 0x28,
      "left": 0x25, "right": 0x27, "esc": 0x1B,
      "f12": 0x7B,
      # left stick = WASD, right stick (camera) = IJKL, L3 (sprint) = x  (input_config/default.ini)
      "w": 0x57, "a": 0x41, "s": 0x53, "d": 0x44, "i": 0x49, "j": 0x4A, "k": 0x4B, "l": 0x4C,
      "x": 0x58, "space": 0x20, "q": 0x51, "e": 0x45,
      # r2 (fire) = o, r1 = u, r3 = m, l1+r1 = f, l3 = lshift
      "o": 0x4F, "u": 0x55, "m": 0x4D, "f": 0x46, "lshift": 0xA0}   # shadPS4 hotkey_capture_frame. NOT f10: the fps hotkey crashed the client (d1preservation)

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def game_window():
    pids = set(winproc.emu_pids())
    found = []

    def cb(hwnd, _lp):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            if r.right - r.left > 300:
                found.append(hwnd)
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found[0] if found else None


def focus(hwnd):
    # Windows only lets a process take the foreground in some states; an ALT tap first is the
    # standard way to be allowed.
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    user32.ShowWindow(hwnd, 9)          # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)
    return user32.GetForegroundWindow() == hwnd


def tap(name, hold=0.12):
    vk = VK[name]
    scan = user32.MapVirtualKeyW(vk, 0)
    ext = 1 if name in ("up", "down", "left", "right") else 0
    user32.keybd_event(vk, scan, ext, 0)
    time.sleep(hold)
    user32.keybd_event(vk, scan, ext | 2, 0)


def hold(names, seconds):
    """Hold several keys together (e.g. ['w'] to walk forward) for `seconds`."""
    hwnd = game_window()
    if not hwnd:
        raise SystemExit("no shadPS4 window")
    focus(hwnd)
    vks = [(VK[n], user32.MapVirtualKeyW(VK[n], 0)) for n in names]
    for vk, sc in vks:
        user32.keybd_event(vk, sc, 0, 0)
    try:
        time.sleep(seconds)
    finally:
        for vk, sc in vks:
            user32.keybd_event(vk, sc, 2, 0)


def key(*names, gap=0.6):
    hwnd = game_window()
    if not hwnd:
        raise SystemExit("no shadPS4 window")
    if not focus(hwnd):
        print("warning: could not bring the game window to the front - SDL may ignore the keys")
    for n in names:
        tap(n)
        time.sleep(gap)


def shot(path):
    """Screenshot of the game window's screen rectangle (PowerShell + System.Drawing)."""
    hwnd = game_window()
    if not hwnd:
        raise SystemExit("no shadPS4 window")
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    ps = (
        "Add-Type -AssemblyName System.Drawing;"
        f"$b=New-Object System.Drawing.Bitmap({r.right - r.left},{r.bottom - r.top});"
        "$g=[System.Drawing.Graphics]::FromImage($b);"
        f"$g.CopyFromScreen({r.left},{r.top},0,0,$b.Size);"
        f"$b.Save('{os.path.abspath(path)}',[System.Drawing.Imaging.ImageFormat]::Png)"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True)
    return path


def shot_bg(path):
    """Screenshot via PrintWindow(PW_RENDERFULLCONTENT): works while other windows cover the game
    and does not take focus, so it does not disturb whoever is using the PC."""
    from PIL import Image
    gdi32 = ctypes.WinDLL("gdi32")
    hwnd = game_window()
    if not hwnd:
        raise SystemExit("no shadPS4 window")
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    w, h = r.right, r.bottom
    hdc = user32.GetDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 3)            # PW_CLIENTONLY | PW_RENDERFULLCONTENT
    buf = ctypes.create_string_buffer(w * h * 4)
    bmi = struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, bmi, 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1).convert("RGB").save(path)
    return path


if __name__ == "__main__":
    ctypes.windll.user32.SetProcessDPIAware()
    if sys.argv[1] == "shot":
        print(shot(sys.argv[2]))
    elif sys.argv[1] == "shotbg":
        print(shot_bg(sys.argv[2]))
    elif sys.argv[1] == "key":
        key(*sys.argv[2:])
    elif sys.argv[1] == "hold":                  # hold <seconds> <key> [key ...]
        hold(sys.argv[3:], float(sys.argv[2]))
