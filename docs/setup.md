# First-time setup

Three machines: Mac Mini, Pico, Linux client. Order matters because each stage
verifies the previous one.

## Prerequisites

- Mac Mini with iPhone Mirroring set up and paired with the target iPhone.
- Raspberry Pi Pico (or Pico W) running CircuitPython 7.x or later, with
  `adafruit_hid` library in `/lib`.
- Linux client with `python3`, `pygame`, `Pillow`, and an SSH key authorised
  on the Mac.
- Tailscale on both Mac and client (recommended) — otherwise restrict the
  Mac daemons to your LAN at the firewall.

## 1. Pico firmware

```
pico/boot.py  → /boot.py on the Pico CIRCUITPY drive
pico/code.py  → /code.py
```

Then plug the Pico into the Mac. It should appear as two `/dev/cu.usbmodem*`
nodes. Verify with `ls /dev/cu.usbmodem*` — you should see two ports.

Smoke test from the Mac shell (find the higher-numbered port, the data CDC):

```bash
printf 'm 80 0\n' > /dev/cu.usbmodemXXX3
```

The Mac pointer should jump ~80 px right. If it doesn't, see
[gotchas.md](gotchas.md#pico-not-found-or-not-typing).

## 2. Mac display configuration

GUI-only steps — do these on the Mac Mini directly.

### Dummy display

Either:

- **Dummy HDMI plug** in the HDMI port, or
- **BetterDisplay** (`brew install --cask betterdisplay`) — `mac/start-session.sh`
  expects a `tuxbridge` virtual screen at 430×932 aspect with resolution modes
  `430x932,640x1388,860x1864`. The script will create it on first run.

The iPhone Mirroring window must live on a display that's invisible to humans
— otherwise the screen will sleep and HID input will stop reaching the iPhone.

### Stay-up settings

- System Settings → Users & Groups → enable auto-login.
- System Settings → Lock Screen → Require password after: Never.
- System Settings → Energy → Prevent automatic sleeping when the display is off: ON; Computer sleep: Never.
- Bluetooth: ON (iPhone Mirroring requires it).
- System Settings → General → Sharing → enable Remote Login (so the client can SSH in to run helper scripts).

### Screen Recording permission (TCC)

`capture_daemon.py` needs Screen Recording permission to see iPhone
Mirroring's protected window content. Grant it to **Terminal.app** (not
Python directly):

System Settings → Privacy & Security → Screen Recording → ✓ Terminal.

Then `capture_daemon` *must always be launched from a Terminal window*, never
over SSH. See [gotchas.md](gotchas.md#screen-recording-tcc) for why.

## 3. Mac daemons

Copy `mac/` to the Mac:

```bash
rsync -av ~/devel/tuxbridge/mac/ mac-host:~/devel/tuxbridge/mac/
ssh mac-host 'python3 -m pip install --user pyserial pillow pyobjc-framework-Quartz'
```

### `bridge_daemon` as a LaunchAgent

```bash
ssh mac-host
sed "s|__HOME__|$HOME|g" ~/devel/tuxbridge/mac/com.tuxbridge.daemon.plist \
  > ~/Library/LaunchAgents/com.tuxbridge.daemon.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.tuxbridge.daemon.plist
launchctl enable gui/$(id -u)/com.tuxbridge.daemon
```

(The launchd plist is named `com.tuxbridge.daemon` for historical reasons.
You may also have `com.tuxbridge.bridge` / `com.tuxbridge.cursor` — same
pattern.)

### `cursor_daemon` as a LaunchAgent

`cursor_daemon` doesn't need TCC, so it's safe to run from launchd. Use a
plist modelled on the bridge plist, calling `cursor_daemon.py` instead.

### `capture_daemon` — Terminal launch only

Do **not** put `capture_daemon` in a LaunchAgent. It needs Screen Recording
permission, which is tied to the launching binary's TCC context. Launch it
from a Terminal window:

```bash
cd ~/devel/tuxbridge && ./mac/run-capture.sh   # or run capture_daemon.py directly
```

Leave that Terminal window open. If the daemon dies, relaunch it from the same
Terminal.

### Smoke test from the Linux client

```bash
printf 'm 80 0\n' | nc <mac-tailscale-ip> 8765   # pointer moves right
printf 't hello\n' | nc <mac-tailscale-ip> 8765  # types "hello"
```

## 4. Linux client

```bash
python3 -m pip install pygame pillow
cd ~/devel/tuxbridge
TUXBRIDGE_HOST=<mac-tailscale-ip> python3 arch/integrated.py
```

`integrated.py` will SSH into the Mac to run `mac/start-session.sh`, which:

- Brings the dummy display up as a non-main extension to the right of main.
- Moves iPhone Mirroring onto it.
- Returns the iPhone display rect (`x,y,w,h`) for capture cropping.

To skip that and pin the region yourself, set `TUXBRIDGE_REGION="x,y,w,h"`.

## 5. Touchscreen client (Pi)

Same as the Arch client, with `TUXBRIDGE_TOUCH=1` so the input handler treats
every `MOUSEBUTTONDOWN` as an atomic tap (no drag, no motion events). See
[operations.md](operations.md#raspberry-pi-touchscreen-client).
