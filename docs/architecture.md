# Architecture

## The core constraint

macOS iPhone Mirroring accepts USB HID input from a real device and **rejects
software-injected events** (CGEventPost, AppleScript clicks, accessibility
events). Verified empirically — see `/home/kidders/devel/bin-k/python/ios-remote-test/`.
Every design decision in tuxbridge falls out of this.

Consequences:

- Control cannot be a VNC keyboard/mouse channel. Apple Screen Sharing
  additionally *gates* HID events while a VNC client is connected, so events
  get queued and only fire after the VNC channel closes.
- A real USB HID device must sit on the Mac's USB bus. A Raspberry Pi Pico
  running CircuitPython does this for ~£4.
- The Linux client therefore has two completely separate jobs: (a) get
  pixels from the Mac, (b) get HID commands into the Pico. They share no
  transport.

## Data flow

```
Linux client                      Mac Mini                             Pico       iPhone
                                                                                  
 integrated.py                    bridge_daemon.py                    code.py     
   keyboard/touch  ──TCP 8765────► serial pipe        ──USB CDC────►  HID press/move ──HID──►
                                                                                  
   JPEG decode    ◄──TCP 8766─── capture_daemon.py                                  
   (CoreGraphics frames of                                                          
    the iPhone Mirroring window)                                                    
                                                                                  
   green dot      ◄──TCP 8767─── cursor_daemon.py                                  
   (Mac cursor xy @ 60 Hz)                                                          
```

## Components

### `pico/code.py` — HID firmware

Reads newline-delimited UTF-8 from the CircuitPython `usb_cdc.data` channel
and emits `adafruit_hid` mouse and keyboard events. Stateless except for
"held modifiers" tracking, which exists so that `layout.write()` calls (which
toggle shift around capital letters) don't kill a modifier the host says is
held externally. See [protocol.md](protocol.md) for the wire format.

### `pico/boot.py` — USB setup

Enables `usb_cdc.data` so the Pico exposes two CDC interfaces:

- Interface 0 (`/dev/cu.usbmodemXXX1` on macOS) — REPL console.
- Interface 2 (`/dev/cu.usbmodemXXX3`) — the data channel `bridge_daemon` writes to.

### `mac/bridge_daemon.py` — TCP ↔ serial pipe

Protocol-agnostic byte forwarder. Binds to the Tailscale IPv4 address when
available, falls back to `0.0.0.0` with a warning. Auto-detects the Pico's
data CDC node (`interface == "CircuitPython CDC2 data"`, or the highest-numbered
`usbmodem` device on tiebreak). Reopens the serial port if it disappears
(unplug, soft reboot).

Logs every chunk forwarded to `~/devel/tuxbridge/mac/bridge.err` (or
`~/tuxbridge/daemon.err` if installed as a LaunchAgent) — that's the first
place to look when "the click did nothing".

### `mac/capture_daemon.py` — JPEG framebuffer

Snapshots the iPhone Mirroring window via `CGWindowListCreateImage`, JPEG-encodes
it, frames it as `[uint32 big-endian length][jpeg bytes]`, and pushes ~15 fps
over TCP to one client.

The capture region is the iPhone Mirroring window **minus a chrome inset** so
we only capture the iPhone display itself, not the wallpaper visible inside
the window. The inset is set in `iphone-region.sh` (T:43, R:13, B:13, L:13 by
default) and was measured against a real window. See
[gotchas.md](gotchas.md#capture-region-and-window-chrome).

Critically: this daemon **must be launched from a Terminal that has been
granted Screen Recording permission**. macOS TCC is per-binary-context — if
you spawn `/usr/bin/python3 capture_daemon.py` over SSH, it inherits the
SSH session's TCC context, which has no Screen Recording grant, and you'll
get a stream of wallpaper instead of iPhone pixels. See
[gotchas.md](gotchas.md#screen-recording-tcc).

### `mac/cursor_daemon.py` — cursor position

Reads `CGEventGetLocation` at 60 Hz and broadcasts `"x,y\n"` lines to any
TCP subscriber. The client uses this to know where the Mac cursor actually
is — essential for the closed-loop convergence (see below). Runs fine over
SSH; no TCC permission needed.

### `arch/integrated.py` — single-window Linux client

One pygame window that:

1. Decodes JPEG frames from `capture_daemon` and blits them.
2. Reads the Mac cursor position from `cursor_daemon` and draws a green dot.
3. On a tap (touchscreen down, or mouse down in trackpad mode), runs a
   closed-loop convergence to walk the Mac cursor to the target point, then
   issues a click — but only if the cursor actually landed inside the iPhone
   display rect.
4. On `TEXTINPUT`, sends `t <char>` commands; on KEYDOWN/KEYUP for named keys
   (arrows, modifiers, enter…), sends `kd/ku` commands. Plain alphanumeric
   KEYDOWN is suppressed because TEXTINPUT covers it — sending both produces
   double-characters.

The window has a rounded-corner alpha mask so it visually matches the iPhone
display.

## The closed-loop tap

The core trick that makes tapping accurate. Naive: "send a 200×400 relative
mouse delta, then click". This fails because macOS applies a non-linear
acceleration curve to HID deltas — large deltas become *enormous* after the
curve, so the cursor overshoots wildly.

Instead `integrated.py:move_to()`:

1. Clamps the target inside the iPhone display rect (with a 2 px margin).
2. Reads the current Mac cursor xy from `cursor_daemon`.
3. Sends a step toward the target — `step = clamp(d/2, ±40)` if `|d| > 4`,
   else `±1`. Keeping steps small keeps the acceleration curve in its
   near-linear region.
4. Sleeps 60 ms (one cursor_daemon tick at 60 Hz, with margin) so the next
   read reflects the move.
5. Re-aims based on the new measured position. Repeats up to 20 times.
6. If the cursor wandered outside the iPhone display rect (rare, but possible
   if the user click-and-drags), the next step is a corrective pull back —
   the green dot is never allowed to sit on the macOS desktop, where a stray
   click would dismiss iPhone Mirroring.

After convergence (or its failure), `tap()` re-checks that the cursor really
is inside the rect and **refuses to click** if not.

This is slow (~500 ms per tap) but reliable. Reducing the latency without
losing accuracy is an open problem.

## Why not VNC?

Originally tuxbridge used a TigerVNC viewer for pixels. Apple Screen Sharing's
HID gating made clicks queue behind the VNC channel — taps registered only
after the viewer disconnected, which is useless. `capture_daemon` uses
CoreGraphics directly, with no Screen Sharing in the path, so HID dispatch is
untouched.
