# Operations

## Starting a session

```bash
# Linux client
TUXBRIDGE_HOST=<mac-tailscale-ip> python3 arch/integrated.py
```

On startup the client:

1. SSHes into the Mac and runs `mac/start-session.sh` — brings up the dummy
   display, places the iPhone Mirroring window on it, and prints the iPhone
   display rect.
2. Opens TCP connections to `bridge_daemon` (8765), `capture_daemon` (8766),
   and `cursor_daemon` (8767).
3. Performs a "startup warp" — walks the Mac cursor to the centre of the
   iPhone display and clicks once (wakes Lock Screen / dismisses any
   blocking overlay).

## Ending a session

`integrated.py` doesn't quit iPhone Mirroring on its own — leave it running
or call `mac/end-session.sh` over SSH:

```bash
ssh <mac-host> ~/devel/tuxbridge/mac/end-session.sh
```

## Environment variables (Linux client)

| Variable | Default | Effect |
|---|---|---|
| `TUXBRIDGE_HOST` | (required) | Mac hostname/IP for control daemon. |
| `TUXBRIDGE_PORT` | 8765 | Control port. |
| `TUXBRIDGE_CAPTURE_HOST` | =`TUXBRIDGE_HOST` | Mac host for JPEG stream. |
| `TUXBRIDGE_CAPTURE_PORT` | 8766 | JPEG stream port. |
| `TUXBRIDGE_CURSOR_PORT` | 8767 | cursor_daemon port. |
| `TUXBRIDGE_REGION` | `auto` | `x,y,w,h` of the iPhone display. `auto` resolves via SSH. |
| `TUXBRIDGE_SSH_HOST` | =`TUXBRIDGE_HOST` | Override the SSH target if it differs from the daemon host. |
| `TUXBRIDGE_SCALE` | 1.0 | Window scale factor. |
| `TUXBRIDGE_CORNER_RADIUS` | `0.12 × min(w,h)` | Pixel radius for the rounded-corner mask. |
| `TUXBRIDGE_TOUCH` | unset | If `1`, touchscreen mode (taps only, no drag). |
| `TUXBRIDGE_NO_POLL` | unset | If `1`, skip cursor_daemon subscription. |
| `TUXBRIDGE_NO_CAPTURE` | unset | If `1`, skip JPEG stream (input-only). |

## Environment variables (Mac daemons)

| Variable | Default | Daemon | Effect |
|---|---|---|---|
| `TUXBRIDGE_BIND` | (auto) | all | Override bind address. Default: Tailscale IPv4 if available, else `0.0.0.0`. |
| `TUXBRIDGE_PORT` | 8765 | bridge | TCP listen port. |
| `TUXBRIDGE_SERIAL` | (auto) | bridge | Override Pico serial device path. |
| `TUXBRIDGE_CAPTURE_PORT` | 8766 | capture | Listen port. |
| `TUXBRIDGE_CAPTURE_FPS` | 15 | capture | Target frame rate. |
| `TUXBRIDGE_CAPTURE_QUALITY` | 70 | capture | JPEG quality 1–95. |
| `TUXBRIDGE_CAPTURE_REGION` | `auto` | capture | Override iPhone region. `auto` shells out to `iphone-region.sh`. |
| `TUXBRIDGE_CURSOR_PORT` | 8767 | cursor | Listen port. |
| `TUXBRIDGE_CURSOR_FPS` | 60 | cursor | Broadcast rate. |
| `TUXBRIDGE_INSET_{T,R,B,L}` | 43, 13, 13, 13 | iphone-region.sh | Crop inset trimming the iPhone Mirroring window chrome. |

## Logs

| Component | Path |
|---|---|
| `bridge_daemon` (LaunchAgent) | `~/tuxbridge/daemon.{log,err}` |
| `bridge_daemon` (manual) | stderr — also written to `~/devel/tuxbridge/mac/bridge.err` |
| `capture_daemon` | stderr of the Terminal window it was launched from |
| `cursor_daemon` | stderr of its LaunchAgent or Terminal |
| `integrated.py` | stderr |

The bridge log is the first thing to check when "tap did nothing" — every
chunk forwarded to the Pico is logged with timing, so you can see whether the
command made it onto the serial bus.

## Service control

```bash
# Start / stop the bridge daemon
launchctl kickstart -k gui/$(id -u)/com.tuxbridge.daemon
launchctl bootout   gui/$(id -u)/com.tuxbridge.daemon

# Reload after editing the plist
launchctl bootout    gui/$(id -u) ~/Library/LaunchAgents/com.tuxbridge.daemon.plist
launchctl bootstrap  gui/$(id -u) ~/Library/LaunchAgents/com.tuxbridge.daemon.plist
```

Capture must be relaunched by hand from Terminal (see [gotchas](gotchas.md#screen-recording-tcc)).

## Raspberry Pi touchscreen client

The Pi case typically runs `~/tuxbridge-run.sh` (Pi-local file, not in the
repo) which sets `TUXBRIDGE_TOUCH=1`, the cropped `TUXBRIDGE_REGION` matching
the current iPhone display rect, and launches `integrated.py` fullscreen.

When the Mac's iPhone Mirroring window is moved or the dummy resolution
changes, the cropped region drifts and the Pi's hardcoded `TUXBRIDGE_REGION`
needs updating. The smoothest fix is to let `integrated.py` auto-resolve
(remove `TUXBRIDGE_REGION` from the Pi script) so it always asks
`start-session.sh` for the current rect.

## Troubleshooting checklist

1. **No frames in client window** — capture_daemon dead or wrong TCC context.
   Relaunch from a Terminal window with Screen Recording permission. See
   [gotchas.md](gotchas.md#screen-recording-tcc).
2. **Frames show wallpaper, not iPhone screen** — same as above: TCC context
   is wrong. Confirm by `lsappinfo info` against the python process — it must
   inherit Terminal's context.
3. **Tap lands in wrong place** — `TUXBRIDGE_REGION` is stale. Re-run
   `start-session.sh` and copy the rect it prints.
4. **Tap dismisses iPhone Mirroring** — same as above (the click hit the
   macOS desktop because the region was off). The `move_to` containment
   check usually catches this and refuses to click; if it didn't, the rect
   is *very* wrong.
5. **Typed characters mangled** — should be fixed by the per-char pacing in
   Pico `handle()`. If it returns, see [gotchas.md](gotchas.md#typing-mangled-or-spaces-missing).
6. **Pointer drifts despite no input** — likely macOS pointer acceleration
   biting on a corrective step. The closed-loop convergence should self-heal
   on the next tick. If it doesn't, lower the step clamp in `move_to:step()`.
