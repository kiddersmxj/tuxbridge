#!/usr/bin/env bash
# Print iPhone Mirroring window region as "x,y,w,h". Launch it if not running.
set -e
osascript -e 'tell application "iPhone Mirroring" to activate' >/dev/null 2>&1
sleep 1
osascript <<'EOF'
tell application "System Events"
  tell process "iPhone Mirroring"
    set p to position of front window
    set s to size of front window
    return ((item 1 of p) as text) & "," & ((item 2 of p) as text) & "," & ((item 1 of s) as text) & "," & ((item 2 of s) as text)
  end tell
end tell
EOF
