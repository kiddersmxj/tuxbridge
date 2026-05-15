# tuxbridge

Remote-control a paired iPhone from an Arch Linux machine, via a Mac Mini
running iPhone Mirroring. Input travels through a Raspberry Pi Pico configured
as a real USB HID device — because macOS iPhone Mirroring accepts real HID
input even with a VNC session open, but rejects software-injected events.

```
Arch              Mac Mini                       Pico         iPhone
[client.py] --TCP--> [bridge_daemon.py] --USB--> [code.py] --HID-->
[vncviewer] <-VNC--- [Screen Sharing]
```

## Components

- `pico/` — CircuitPython firmware (boot.py + code.py). Serial -> HID bridge.
- `mac/` — Python forwarding daemon + launchd plist + setup docs.
- `arch/` — pygame input-capture client + launcher script.

## Wire protocol (newline-delimited UTF-8)

```
m <dx> <dy>     relative pointer move
w <dy>          scroll wheel
d|u <l|r|m>     button down/up
kd|ku <key>     key down/up (canonical names; see pico/code.py KEYS)
t <text>        type literal text (US layout)
```

Unknown lines are silently ignored (forward compatibility).

## Build order — verify each before moving on

1. **M1 — Pico firmware**
   - Copy `pico/boot.py` and `pico/code.py` to the Pico's CIRCUITPY mount.
   - Plug Pico into Mac. From Mac shell: `printf 'm 80 0\n' > /dev/cu.usbmodemXXXX` (the *data* CDC node, not the REPL). Mac pointer moves.

2. **M2 — Mac daemon** — see `mac/README.md`.
   - From Arch: `printf 'm 80 0\n' | nc <mac> 8765` moves the Mac pointer.

3. **M3 — Display & sharing** — see `mac/display-setup.md`.
   - From Arch: `vncviewer <mac>` shows essentially just the iPhone screen.

4. **M4 — Arch client**
   ```bash
   TUXBRIDGE_HOST=<mac-tailscale-ip> ./arch/run.sh
   ```
   - TigerVNC window: pixels. Pygame window: input. Click the pygame window to grab; Ctrl+Alt+G to release.

## Security

Everything is plain TCP. The Mac daemon binds to the Tailscale IP when
available (see `mac/bridge_daemon.py:pick_bind_addr`). Never expose port 8765
to the open internet — it can drive the iPhone.

## Known limits

- Relative pointing only (trackpad-style).
- US keyboard layout.
- One client at a time.

## Stretch (M5)

Render the VNC feed inside the pygame window for a true single-window
experience. Blocked on a Python VNC client that speaks Apple's ARD auth —
evaluate `asyncvnc` / `vncdotool` once M4 is solid.
