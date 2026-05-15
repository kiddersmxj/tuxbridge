# Gotchas

The hard-won lessons. Read this before changing anything that touches HID,
TCC, the capture region, or the Pico firmware.

## The premise

macOS iPhone Mirroring accepts **real USB HID input** but **rejects
software-injected events** (CGEventPost, AppleScript clicks, accessibility
APIs). Verified by smoke test
(`/home/kidders/devel/bin-k/python/ios-remote-test/pico_code.py`). This is the
reason every component exists in the form it does — see
[architecture.md](architecture.md#the-core-constraint).

If a future macOS release opens up programmatic injection, much of tuxbridge
becomes unnecessary. Until then, the Pico stays.

## Screen Recording (TCC)

`capture_daemon.py` calls `CGWindowListCreateImage` on the iPhone Mirroring
window. iPhone Mirroring's contents are marked as protected by macOS — to
capture them, the calling process needs the **Screen Recording** TCC grant.

The trap: TCC is **per binary launching context**, not per executable path.
A grant given to "Terminal.app" applies to processes spawned from a Terminal
window. The same `python3 capture_daemon.py` invoked over SSH inherits the
SSH-session context, which has *no* grant, and silently captures the
underlying wallpaper instead.

Symptoms: client renders the Mac wallpaper inside the iPhone-shaped window
instead of the iPhone screen. No error is produced — `CGWindowListCreateImage`
just returns the public layer.

Workarounds tried:

- Adding `python3` itself to the Screen Recording list — doesn't help; TCC
  ignores the binary path when the launching context is non-GUI.
- Bundling a `.app` wrapper — works but adds complexity.

Current solution: **always launch capture_daemon from a Terminal window** that
has been granted Screen Recording permission. Do **not** put it in a
LaunchAgent unless you're prepared to package it as a `.app` and grant TCC
to the bundle. If you SSH in to kill and restart it, the restart loses the
grant and you'll see wallpaper.

`bridge_daemon` and `cursor_daemon` don't read screen contents, so they're
fine in LaunchAgents.

## Capture region and window chrome

The iPhone Mirroring window has a transparent chrome inset around the iPhone
display itself — roughly 13 px on left/right/bottom and 43 px on top. The
macOS wallpaper bleeds through that border. If you capture the full window
rect, the frame shows wallpaper around the edge of the iPhone display.

`mac/iphone-region.sh` trims the inset before reporting the rect:

```
TUXBRIDGE_INSET_TOP=43 RIGHT=13 BOTTOM=13 LEFT=13
```

These were measured against the current macOS version's iPhone Mirroring
chrome. A future macOS update may change them — if you suddenly see
wallpaper-colour borders, re-measure. The disconnect-state JPEG plus
`scipy.ndimage.uniform_filter` (texture analysis on the corners) gives
pixel-accurate insets.

The Linux client's `TUXBRIDGE_REGION` env var **must match** the daemon's
capture rect. Mismatches mean a tap at pygame coords (px, py) maps to the
wrong Mac coords, which can put the click outside the iPhone Mirroring
window entirely — see next gotcha.

## Edge taps backgrounded iPhone Mirroring

Clicking on the macOS desktop (outside the iPhone Mirroring window)
de-focuses iPhone Mirroring, hides the window, and breaks the session until
you reactivate it.

This used to happen when the capture region was off by ~24 px vertically —
a tap aimed at the bottom of the rendered iPhone display landed on the
title bar above the window, dismissing it.

Two defences in `integrated.py`:

1. `move_to()` actively contains the cursor inside `REGION` with a 2 px
   safety margin — any step that would land outside is replaced by a
   corrective step pulling back inside.
2. `tap()` re-checks the cursor's actual position before issuing `d l` / `u l`
   and **refuses to click** if the cursor is outside `REGION`. Logs the
   refused tap to stderr.

If the region itself is wrong, both defences trigger spuriously and nothing
clicks. The fix is to update `TUXBRIDGE_REGION` to match the current window
position — easiest by running `start-session.sh` and copying the rect it
prints.

## Pointer acceleration distorts open-loop deltas

macOS applies a non-linear acceleration curve to relative HID deltas. A
single `m 200 0` command does **not** move the cursor 200 px — it moves
much further. The curve is steep above ~40 px/event.

If you try to compute "how far to move" by tracking a software model and
sending one big delta, you'll overshoot wildly. The closed-loop convergence
in `move_to()` solves this:

- Steps capped at ±40 keep the curve in its near-linear region.
- After each step, re-read the actual cursor position from `cursor_daemon`
  and re-aim. Errors don't accumulate.
- Convergence threshold is 3 px; max 20 iterations (~1.2 s timeout).

This is slow (~500 ms per tap). Faster strategies that have been tried and
failed:

- Larger initial step, then converge — overshoots compound when the initial
  step lands outside the iPhone display rect (containment kicks in,
  corrective step is also large, oscillates).
- 30 ms settle instead of 60 ms — accuracy collapses; the cursor_daemon
  hasn't published the latest position yet.
- Disabling acceleration system-wide with `defaults write -g
  com.apple.mouse.scaling -1` — works partially but is global state we
  don't want to mutate.

If you find a way to halve tap latency without losing accuracy, that's a
real win.

## Typing mangled or spaces missing

Two distinct bugs, both fixed in `pico/code.py`:

### 1. `line.strip()` ate trailing spaces

```python
line = line.strip()       # OLD — wrong
```

`"t \n"` (typing a space) becomes `"t"` after strip — doesn't match
`startswith("t ")` — silently dropped. Fixed by:

```python
line = line.rstrip("\r\n")  # preserve all body whitespace
```

### 2. Back-to-back `layout.write()` coalesced HID reports

Typing "hello" issued five `layout.write("h")`, `("e")`, … calls in rapid
succession. Without pacing between them, the macOS HID subsystem coalesced
the reports — the iPhone Mirroring side-channel saw duplicated or dropped
characters. Fixed by emitting one char at a time with a 12 ms gap:

```python
for ch in text:
    layout.write(ch)
    time.sleep(0.012)
```

12 ms is empirical — 8 ms still showed occasional mangling, 12 ms has been
clean.

## `K_SPACE` double-spacing

On the Linux client, pygame fires both `KEYDOWN` (with `key == K_SPACE`) and
`TEXTINPUT` (with `text == " "`) for a space press. If `K_SPACE` is in
`KEY_MAP`, the client sends both `kd space` and `t ` — two spaces typed for
every one pressed. Fix: remove `K_SPACE` (and all alphanumeric keys) from
`KEY_MAP`; let `TEXTINPUT` handle them.

Same principle for any printable character: `send_key()` suppresses
single-character alphanumeric KEYDOWNs and lets `TEXTINPUT` send `t <ch>`.
Modifiers and named keys (arrows, enter, esc…) still go through `kd/ku`.

## Pico filesystem is read-only from CircuitPython

The Pico's `/` is read-only from MicroPython/CircuitPython code when USB MSC
is presenting the volume. `storage.remount('/', readonly=False)` fails with
"Cannot remount '/' when visible via USB."

This is fine for normal operation — you don't want the Pico writing to its
own filesystem.

For redeploying `code.py`, write to the CIRCUITPY volume from the Mac
filesystem (mount appears at `/Volumes/CIRCUITPY` or whatever the Pico's
disk is labelled — on this Mac it's `MXJKM_IN`). See
[development.md](development.md#deploying-pico-firmware).

## Pico not found or not typing

- The Pico exposes two CDC ports; `bridge_daemon` needs the **data** one
  (interface 2, higher-numbered `usbmodemXXX3`), not the REPL (interface 0,
  `usbmodemXXX1`).
- Auto-detection uses `pyserial.tools.list_ports` matching on
  `interface == "CircuitPython CDC2 data"` or descriptor text. If neither
  matches, it sorts `usbmodem*` ports and picks the last — usually right on
  macOS but not guaranteed. Override with `TUXBRIDGE_SERIAL=/dev/cu.usbmodem...`.
- After a Pico soft reboot the serial nodes are re-enumerated; the daemon
  reopens them on next write. A few cmds may be lost in the gap.

## Why one client at a time

The bridge, capture, and cursor daemons all `listen(1)` and accept one
client. Multiplexing would mean defining ownership semantics for the HID
state (whose held modifiers count?) which we've not needed. Don't change
this without a real use case.

## Tailscale binding

The daemons prefer the Tailscale IPv4 address when `tailscale ip --4`
succeeds, falling back to `0.0.0.0` with a loud warning. **Never expose port
8765 to the public internet** — it accepts arbitrary HID commands. Trust
boundary: the Tailscale tailnet.

If Tailscale is down, the fallback bind is to `0.0.0.0` so the daemon
remains useful on LAN. Restrict at the macOS firewall if you can't trust the
LAN.

## launchd bootstrap quirks

- `launchctl bootstrap gui/$(id -u) <plist>` is the modern equivalent of
  `launchctl load -w`. Use `bootout` to remove.
- After editing a plist, `bootout` then `bootstrap` to reload. `kickstart -k`
  just restarts the running process.
- LaunchAgent logs go to `StandardOutPath` / `StandardErrorPath` in the
  plist. If those paths are wrong, the daemon will fail silently — check
  the system log: `log show --predicate 'subsystem == "com.apple.xpc.launchd"' --last 5m`.
