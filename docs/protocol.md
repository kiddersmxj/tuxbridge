# Wire protocol

All three TCP channels are simple. Two are byte streams from the Mac to the
client (capture, cursor); one is bidirectional but in practice only carries
commands client→Mac (bridge).

## Control channel (TCP 8765)

Client → daemon → Pico. Newline-delimited UTF-8. The Mac daemon is a dumb
forwarder — it never parses. The Pico parses; unknown lines are silently
ignored (forward compatibility).

| Line | Meaning |
|---|---|
| `m <dx> <dy>` | Relative pointer move. Each axis clamped to ±127 on the Pico. |
| `w <dy>` | Scroll wheel, ±127. |
| `d <l\|r\|m>` | Mouse button down (left / right / middle). |
| `u <l\|r\|m>` | Mouse button up. |
| `kd <name>` | Key down. See [Key names](#key-names). |
| `ku <name>` | Key up. |
| `t <text>` | Type literal text (US layout). `layout.write()` toggles shift internally for capitals and symbols. |

### Key names

`enter esc backspace tab space delete up down left right shift ctrl alt cmd home end`
plus `a..z` and `0..9`.

### Modifier stickiness

When `t <text>` types a capital letter, `adafruit_hid.KeyboardLayoutUS`
presses Shift, sends the key, releases Shift. If the host had also issued
`kd shift` (e.g. user holding shift on the Linux client), that release would
kill the held modifier. The Pico tracks `held_mods` and re-presses them
after every `layout.write()` to keep them sticky.

### Pacing

The Pico types one character per `layout.write()` call with a 12 ms sleep
between chars. Back-to-back `layout.write()` calls without spacing produce
mangled output on the host — HID reports get coalesced and the iPhone
side-channel sees duplicated or dropped chars. See
[gotchas.md](gotchas.md#typing-mangled-or-spaces-missing).

### `rstrip("\r\n")`, not `strip()`

`handle()` strips only line terminators, not all whitespace. Stripping all
whitespace would silently drop the trailing space in `"t "` (typing a
space), making `t` an unrecognised command.

## Capture channel (TCP 8766)

Daemon → client. Framed JPEG stream.

```
┌─────────────┬───────────────┐
│ uint32 BE   │ JPEG bytes    │
│ length      │ (length bytes)│
└─────────────┴───────────────┘
```

Repeats. Frame rate is whatever `TUXBRIDGE_CAPTURE_FPS` allows (default 15).
One client per daemon — a second connection blocks until the first closes.

## Cursor channel (TCP 8767)

Daemon → client. Plain text, line-delimited.

```
"<x>,<y>\n"
```

One line per tick at `TUXBRIDGE_CURSOR_FPS` (default 60). x and y are in Mac
global screen coordinates. Multiple clients OK.

The client (`integrated.py`) uses these as the ground truth for the Mac
cursor's position, and draws a small green dot on the iPhone display at that
location. The closed-loop tap relies on these readings being timely — at
60 Hz, `move_to` can sleep 60 ms between corrective steps and reliably
observe the result.
