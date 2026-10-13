r"""Give the game back what it last told the server about itself.

    python tools\client_state.py <profile.bin> [<state dir>]

Every so often the game uploads two blocks of its own state (investment messages 701 and 702);
the login server (D1_CLIENT_STATE_DIR) keeps the latest of each:

    702.bin  the CHARACTER's block, schema 0x8080193C, 2592 bytes - the same structure that sits
             at +0x2C40 of the character profile (0x80801743) the server sends at login
    701.bin  the ACCOUNT's block, schema 0x80801716, 1088 bytes - at +0x80 of the account object
             (0x808018C7); not applied here yet (that object is built inside the login server)

Without this the profile always carries an empty block, so the game starts every session as if
it had never shown the player anything. This decodes the saved 702 body with the game's own
codec and writes it into the profile file. NIGHT-NOTES section 81.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import finish_character as fc  # noqa: E402

STATE = os.path.join(fc.REPO, "capture-rig", "client-state")
PROFILE_TAG, PROFILE_AT, BLOCK_TAG, BLOCK_SIZE = "0x80801743", 0x2C40, "0x808016cf", 2592


def _run(*a):
    r = fc.run(fc.OBJFILE, *a)
    if r.returncode:
        raise SystemExit("object_file %s: %s%s" % (" ".join(a[:2]), r.stdout[-300:], r.stderr[-300:]))


def character_block(state=STATE):
    """The decoded 2592-byte block of the saved 702 upload, or None."""
    src = os.path.join(state, "702.bin")
    if not os.path.exists(src):
        return None
    tmp = tempfile.gettempdir()
    body, img = os.path.join(tmp, "d1_702.body"), os.path.join(tmp, "d1_702.img")
    with open(body, "wb") as f:
        f.write(open(src, "rb").read()[2:])          # after the u16 message id
    _run("decode", BLOCK_TAG, body, img)
    block = open(img, "rb").read()
    return block if len(block) == BLOCK_SIZE else None


def apply(profile, state=STATE):
    """Write the saved character block into `profile`; returns the number of bytes changed."""
    block = character_block(state)
    if block is None:
        return 0
    img = os.path.join(tempfile.gettempdir(), "d1_profile_state.img")
    _run("decode", PROFILE_TAG, profile, img)
    b = bytearray(open(img, "rb").read())
    changed = sum(1 for i in range(BLOCK_SIZE) if b[PROFILE_AT + i] != block[i])
    if not changed:
        return 0
    b[PROFILE_AT:PROFILE_AT + BLOCK_SIZE] = block
    open(img, "wb").write(b)
    backup = profile + ".bak-before-client-state"
    if not os.path.exists(backup):
        shutil.copyfile(profile, backup)
    _run("encode", PROFILE_TAG, img, profile)
    return changed


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    n = apply(sys.argv[1], *(sys.argv[2:3]))
    print("%d bytes of the character block changed in %s" % (n, sys.argv[1]))
