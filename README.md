# tuxbridge

Remote-control a paired iPhone from a Linux client (Arch desktop or a Raspberry
Pi touchscreen), driven through a Mac Mini running iPhone Mirroring. The
control path goes through a real Raspberry Pi Pico configured as a USB HID
device — because macOS iPhone Mirroring accepts real HID input but rejects
software-injected events.

```
Linux client                Mac Mini                          Pico            iPhone
 integrated.py  --TCP:8765--> bridge_daemon.py  --USB serial--> code.py  --HID-->
                <--TCP:8766-- capture_daemon.py (JPEG frames)
                <--TCP:8767-- cursor_daemon.py  (cursor xy)
```

The Linux client renders the iPhone's pixels in a single pygame window and
drives input by issuing tap/type commands. The "green dot" in the window is
the Mac cursor position published by `cursor_daemon`; the closed loop between
client and daemon is what makes taps accurate despite macOS pointer
acceleration.

## Documentation

- [docs/architecture.md](docs/architecture.md) — components, data flow, design rationale.
- [docs/setup.md](docs/setup.md) — first-time install on the Mac, Pico, and Linux client.
- [docs/operations.md](docs/operations.md) — starting/stopping a session, logs, services.
- [docs/protocol.md](docs/protocol.md) — wire protocol between client, daemon and Pico.
- [docs/development.md](docs/development.md) — modifying Pico firmware, deploying changes.
- [docs/gotchas.md](docs/gotchas.md) — non-obvious failure modes and the reasons behind them. **Read this before changing anything.**

## Quick start

Assuming a Mac, Pico, and Linux client have been set up per
[docs/setup.md](docs/setup.md):

```bash
# On the Linux client:
TUXBRIDGE_HOST=<mac-tailscale-ip> python3 arch/integrated.py
```

## Repository layout

```
pico/       CircuitPython firmware (boot.py + code.py).
mac/        Mac-side daemons (bridge, capture, cursor), launchd plists, helpers.
arch/       Linux client: integrated.py (one-window display + input).
docs/       Documentation — start with architecture.md.
```

## Known limits

- Relative HID pointing only — absolute HID would simplify taps but is harder to wire up.
- US keyboard layout only.
- One Linux client per Mac at a time (the daemons accept one TCP client each).
- Drag gestures: deferred. Tap and type work; drag-to-scroll on the iPhone does not yet.
