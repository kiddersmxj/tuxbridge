import struct
import time
import usb_cdc
import usb_hid
from adafruit_hid.mouse import Mouse
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.keycode import Keycode

serial = usb_cdc.data
mouse = Mouse(usb_hid.devices)
keyboard = Keyboard(usb_hid.devices)
layout = KeyboardLayoutUS(keyboard)

# Wide-delta mouse: the last enabled device in boot.py. Its report is a
# single 5-byte payload (button byte + signed 16-bit X + signed 16-bit Y),
# letting us emit any screen-sized delta in one report. Buttons still go
# through the standard Mouse (different report ID, no interference).
rel16_dev = usb_hid.devices[-1]


def send_wide_delta(dx, dy):
    dx = max(-32768, min(32767, int(dx)))
    dy = max(-32768, min(32767, int(dy)))
    rel16_dev.send_report(struct.pack("<Bhh", 0, dx, dy))

BUTTONS = {
    "l": Mouse.LEFT_BUTTON,
    "r": Mouse.RIGHT_BUTTON,
    "m": Mouse.MIDDLE_BUTTON,
}

KEYS = {
    "enter": Keycode.ENTER, "esc": Keycode.ESCAPE,
    "backspace": Keycode.BACKSPACE, "tab": Keycode.TAB,
    "space": Keycode.SPACE, "delete": Keycode.DELETE,
    "up": Keycode.UP_ARROW, "down": Keycode.DOWN_ARROW,
    "left": Keycode.LEFT_ARROW, "right": Keycode.RIGHT_ARROW,
    "shift": Keycode.SHIFT, "ctrl": Keycode.CONTROL,
    "alt": Keycode.ALT, "cmd": Keycode.COMMAND,
    "home": Keycode.HOME, "end": Keycode.END,
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    KEYS[_c] = getattr(Keycode, _c.upper())
KEYS.update({
    "1": Keycode.ONE, "2": Keycode.TWO, "3": Keycode.THREE,
    "4": Keycode.FOUR, "5": Keycode.FIVE, "6": Keycode.SIX,
    "7": Keycode.SEVEN, "8": Keycode.EIGHT, "9": Keycode.NINE,
    "0": Keycode.ZERO,
})


MODIFIER_NAMES = ("shift", "ctrl", "alt", "cmd")
held_mods = set()  # keycodes of modifiers the host says are held


def handle(line):
    line = line.rstrip("\r\n")
    if not line:
        return
    if line.startswith("t "):
        text = line[2:]
        for ch in text:
            try:
                layout.write(ch)
            except Exception:
                pass
            time.sleep(0.012)
        for kc in held_mods:
            try:
                keyboard.press(kc)
            except Exception:
                pass
        return
    parts = line.split(" ")
    cmd = parts[0]
    try:
        if cmd == "m" and len(parts) >= 3:
            mouse.move(x=int(parts[1]), y=int(parts[2]))
        elif cmd == "M" and len(parts) >= 3:
            send_wide_delta(int(parts[1]), int(parts[2]))
        elif cmd == "w" and len(parts) >= 2:
            mouse.move(wheel=max(-127, min(127, int(parts[1]))))
        elif cmd == "d" and len(parts) >= 2 and parts[1] in BUTTONS:
            mouse.press(BUTTONS[parts[1]])
        elif cmd == "u" and len(parts) >= 2 and parts[1] in BUTTONS:
            mouse.release(BUTTONS[parts[1]])
        elif cmd == "kd" and len(parts) >= 2 and parts[1] in KEYS:
            keyboard.press(KEYS[parts[1]])
            if parts[1] in MODIFIER_NAMES:
                held_mods.add(KEYS[parts[1]])
        elif cmd == "ku" and len(parts) >= 2 and parts[1] in KEYS:
            keyboard.release(KEYS[parts[1]])
            if parts[1] in MODIFIER_NAMES:
                held_mods.discard(KEYS[parts[1]])
    except Exception:
        pass


buf = b""
while True:
    waiting = serial.in_waiting
    if waiting:
        buf += serial.read(waiting)
        while b"\n" in buf:
            idx = buf.index(b"\n")
            handle(buf[:idx].decode("utf-8", "ignore"))
            buf = buf[idx + 1:]
    else:
        time.sleep(0.002)
