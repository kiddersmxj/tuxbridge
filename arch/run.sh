#!/usr/bin/env bash
# Launch TigerVNC viewer (pixels) and the pygame input client (control) side-by-side.
set -euo pipefail

: "${TUXBRIDGE_HOST:?set TUXBRIDGE_HOST to the Mac Tailscale IP / hostname}"
: "${TUXBRIDGE_PORT:=8765}"

VNC_HOST="${TUXBRIDGE_VNC_HOST:-$TUXBRIDGE_HOST}"
VNC_DISPLAY="${TUXBRIDGE_VNC_DISPLAY:-:0}"

vncviewer -DotWhenNoCursor=1 -AcceptClipboard=1 -SendClipboard=1 "${VNC_HOST}${VNC_DISPLAY}" &
VNC_PID=$!

cd "$(dirname "$0")"
python client.py
kill "$VNC_PID" 2>/dev/null || true
