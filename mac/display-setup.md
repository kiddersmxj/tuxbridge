# Mac display & sharing setup (M3)

GUI-only, run on the Mac Mini. Order matters.

## 1. Headless display source

Either:
- **Dummy HDMI plug** in the HDMI port, or
- **BetterDummy**: `brew install --cask betterdummy` → launch → Create New Dummy → pick a phone-shaped resolution.

Target resolution: ~390×844 (iPhone 15) or 430×932 (iPhone 15 Pro Max). Slightly larger than the iPhone Mirroring window is fine.

If a real monitor is plugged in for setup, unplug it after — iPhone Mirroring follows the active display.

## 2. iPhone Mirroring

- Launch iPhone Mirroring.app, complete pairing if first run.
- Drag the window onto the dummy display.
- Resize so it fills the dummy display (or close to it).

## 3. Screen Sharing

System Settings → General → Sharing → enable **Screen Sharing**.

Note the address shown (`vnc://<host>.local` or the Tailscale IP).

## 4. Stay-up settings

- System Settings → Users & Groups → Automatically log in as: <user>.
- System Settings → Lock Screen → "Require password after…" → Never (or longest).
- System Settings → Energy → Prevent automatic sleeping when the display is off: ON. Computer sleep: Never.
- Bluetooth: ON (iPhone Mirroring requires it).

## 5. Verify

From Arch:
```bash
vncviewer <mac-tailscale-ip>
```
The window should show essentially the iPhone screen alone. If you see the macOS desktop with the iPhone Mirroring window inside, the dummy resolution is too large — shrink it in BetterDummy.
