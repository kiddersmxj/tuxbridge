# tuxbridge — Mac forwarding daemon

Bidirectional pipe between a TCP socket and the Pico's USB-serial data CDC.
Protocol-agnostic: just bytes. The client (Arch) and the Pico firmware agree
on the wire protocol; this daemon never parses it.

## Install (run on the Mac Mini)

```bash
mkdir -p ~/tuxbridge
# (copied via scp from Arch: bridge_daemon.py, com.tuxbridge.daemon.plist)
python3 -m pip install --user pyserial
```

## Run manually first

```bash
python3 ~/tuxbridge/bridge_daemon.py
```

Expected stderr:
```
opening serial: /dev/cu.usbmodemXXXX
listening on 100.x.y.z:8765      # Tailscale IP if available
```

If the wrong serial device is picked, override:
```bash
TUXBRIDGE_SERIAL=/dev/cu.usbmodem14201 python3 ~/tuxbridge/bridge_daemon.py
```

## Smoke test from Arch

```bash
printf 'm 80 0\n' | nc <mac-tailscale-ip> 8765    # pointer moves right
printf 't hello world\n' | nc <mac-tailscale-ip> 8765
```

## Install as a LaunchAgent

After manual run is happy:

```bash
sed "s|__HOME__|$HOME|g" ~/tuxbridge/com.tuxbridge.daemon.plist \
  > ~/Library/LaunchAgents/com.tuxbridge.daemon.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.tuxbridge.daemon.plist
launchctl enable gui/$(id -u)/com.tuxbridge.daemon
```

Logs: `~/tuxbridge/daemon.log`, `~/tuxbridge/daemon.err`.

Unload:
```bash
launchctl bootterminate gui/$(id -u)/com.tuxbridge.daemon
```

## Security

The daemon binds to the Tailscale IPv4 address when `tailscale ip --4` succeeds.
If Tailscale isn't installed/running it falls back to `0.0.0.0` with a warning —
in that case, restrict via macOS firewall to LAN only. Never expose to the open
internet: this daemon can drive the iPhone.
