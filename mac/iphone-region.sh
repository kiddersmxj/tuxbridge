#!/usr/bin/env bash
# Print iPhone Mirroring window region as "x,y,w,h". Launch it if not running
# and pin the window at a known main-display position so users on the Pi
# can't accidentally drag-launch it onto the dummy display.
set -e
TUXBRIDGE_PIN_X="${TUXBRIDGE_PIN_X:-600}"
TUXBRIDGE_PIN_Y="${TUXBRIDGE_PIN_Y:-100}"
osascript -e 'tell application "iPhone Mirroring" to activate' >/dev/null 2>&1
sleep 1
osascript <<EOF
tell application "System Events"
  tell process "iPhone Mirroring"
    try
      set position of front window to {${TUXBRIDGE_PIN_X}, ${TUXBRIDGE_PIN_Y}}
    end try
    set p to position of front window
    set s to size of front window
    return ((item 1 of p) as text) & "," & ((item 2 of p) as text) & "," & ((item 1 of s) as text) & "," & ((item 2 of s) as text)
  end tell
end tell
EOF
