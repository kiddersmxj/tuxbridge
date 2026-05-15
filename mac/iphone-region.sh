#!/usr/bin/env bash
# Print iPhone Mirroring's *display* region (window minus chrome inset) as
# "x,y,w,h". Launch the app if not running. The inset trims the wallpaper
# visible inside the iPhone Mirroring window so we capture only the
# rounded iPhone display itself.
set -e
osascript -e 'tell application "iPhone Mirroring" to activate' >/dev/null 2>&1
sleep 1
read x y w h < <(osascript <<'EOF' | tr ',' ' '
tell application "System Events"
  tell process "iPhone Mirroring"
    set p to position of front window
    set s to size of front window
    return ((item 1 of p) as text) & "," & ((item 2 of p) as text) & "," & ((item 1 of s) as text) & "," & ((item 2 of s) as text)
  end tell
end tell
EOF
)
INSET_T="${TUXBRIDGE_INSET_TOP:-43}"
INSET_R="${TUXBRIDGE_INSET_RIGHT:-13}"
INSET_B="${TUXBRIDGE_INSET_BOTTOM:-13}"
INSET_L="${TUXBRIDGE_INSET_LEFT:-13}"
echo "$((x + INSET_L)),$((y + INSET_T)),$((w - INSET_L - INSET_R)),$((h - INSET_T - INSET_B))"
