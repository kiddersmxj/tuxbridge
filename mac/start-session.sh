#!/usr/bin/env bash
# Prepare the Mac for a tuxbridge remote session:
#  - bring up the dummy display as a non-main extension to the right of main
#  - move iPhone Mirroring onto it
# Idempotent.
set -e
BD=/opt/homebrew/bin/betterdisplaycli
DUMMY=tuxbridge

# Recreate dummy if missing.
if ! "$BD" get --name="$DUMMY" --identifiers >/dev/null 2>&1; then
  "$BD" create --type=VirtualScreen --virtualScreenName="$DUMMY" \
    --aspectWidth=430 --aspectHeight=932 --useResolutionList=on \
    --resolutionList="430x932,640x1388,860x1864" >/dev/null
  sleep 1
fi

"$BD" set --name="$DUMMY" --connected=on >/dev/null
sleep 1
"$BD" set --name="$DUMMY" --displayModeNumber=0 >/dev/null   # 640x1388
sleep 0.5
"$BD" set --name="$DUMMY" --main=off >/dev/null 2>&1 || true
# Place to the right of the main display so Mac coords stay positive.
MAIN_RES=$("$BD" get --displayWithMainStatus --resolution)
MAIN_W=${MAIN_RES%x*}
"$BD" set --name="$DUMMY" --placement="${MAIN_W}x0" >/dev/null
sleep 1

# Launch iPhone Mirroring and move it onto the dummy.
osascript -e 'tell application "iPhone Mirroring" to activate' >/dev/null 2>&1
sleep 1
TARGET_X=$((MAIN_W + 10))
osascript <<EOF >/dev/null 2>&1 || true
tell application "System Events"
  tell process "iPhone Mirroring"
    set position of front window to {${TARGET_X}, 10}
  end tell
end tell
EOF

echo "dummy at ${MAIN_W}x0; iPhone Mirroring placed at ${TARGET_X},10"
"$(dirname "$0")/iphone-region.sh"
