#!/usr/bin/env bash
# From a fresh orbit screen: dismiss the arrival popups, steer the cursor to SET DESTINATION, open
# the Director and screenshot it.  usage: tools/open_director.sh <run-folder> [label]
R="$1"; L="${2:-director}"; cd "$(dirname "$0")/.."
for i in 1 2 3 4; do python tools/gamewin.py key n; sleep 3; done
python tools/gamewin.py hold 0.7 a; python tools/gamewin.py hold 0.35 s; sleep 1
python tools/gamewin.py key n; sleep 6
python tools/gamewin.py shot "$R/$L.png"
