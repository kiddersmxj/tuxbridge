#!/usr/bin/env bash
# Quit iPhone Mirroring.
osascript -e 'tell application "iPhone Mirroring" to quit' >/dev/null 2>&1 || true
echo "iPhone Mirroring quit."
