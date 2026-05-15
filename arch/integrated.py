"""Integrated tuxbridge client: framebuffer (JPEG stream) + input capture.

VNC was the bottleneck: Apple Screen Sharing gates HID events while a VNC
client is connected, so clicks queued until the VNC channel closed. We now
get pixels from mac/capture_daemon.py (CoreGraphics -> JPEG over TCP) on a
separate port that has no effect on HID dispatch.

Env vars:
  TUXBRIDGE_HOST           Mac host for the input daemon (TCP 8765)  REQUIRED
  TUXBRIDGE_CAPTURE_HOST   Mac host for the JPEG stream (default = TUXBRIDGE_HOST)
  TUXBRIDGE_CAPTURE_PORT   default 8766
  TUXBRIDGE_REGION         "x,y,w,h" of iPhone window  default "auto" via SSH
  TUXBRIDGE_SCALE          window scale factor                       default 1.0
  TUXBRIDGE_NO_POLL=1      disable cliclick re-anchor polling
  TUXBRIDGE_NO_CAPTURE=1   disable JPEG framebuffer stream
"""
import io
import os
import queue
import socket
import struct
import subprocess
import sys
import threading
import time

import pygame
from PIL import Image

MAC_HOST = os.environ.get("TUXBRIDGE_HOST", "")
MAC_PORT = int(os.environ.get("TUXBRIDGE_PORT", "8765"))
CAPTURE_HOST = os.environ.get("TUXBRIDGE_CAPTURE_HOST", MAC_HOST)
CAPTURE_PORT = int(os.environ.get("TUXBRIDGE_CAPTURE_PORT", "8766"))

if not MAC_HOST:
    print("set TUXBRIDGE_HOST (Mac hostname/IP)", file=sys.stderr)
    sys.exit(2)


def _resolve_region():
    raw = os.environ.get("TUXBRIDGE_REGION", "auto")
    if raw == "auto":
        host = os.environ.get("TUXBRIDGE_SSH_HOST", MAC_HOST)
        out = subprocess.check_output(
            ["ssh", host, "~/tuxbridge/start-session.sh"],
            text=True, timeout=30,
        ).strip()
        print(f"start-session output:\n{out}", file=sys.stderr)
        raw = out.splitlines()[-1].strip()
    return tuple(int(v) for v in raw.split(","))


SCALE = float(os.environ.get("TUXBRIDGE_SCALE", "1.0"))

KEY_MAP = {
    pygame.K_RETURN: "enter", pygame.K_KP_ENTER: "enter",
    pygame.K_ESCAPE: "esc", pygame.K_BACKSPACE: "backspace",
    pygame.K_TAB: "tab", pygame.K_SPACE: "space", pygame.K_DELETE: "delete",
    pygame.K_UP: "up", pygame.K_DOWN: "down",
    pygame.K_LEFT: "left", pygame.K_RIGHT: "right",
    pygame.K_LSHIFT: "shift", pygame.K_RSHIFT: "shift",
    pygame.K_LCTRL: "ctrl", pygame.K_RCTRL: "ctrl",
    pygame.K_LALT: "alt", pygame.K_RALT: "alt",
    pygame.K_LMETA: "cmd", pygame.K_RMETA: "cmd",
    pygame.K_LSUPER: "cmd", pygame.K_RSUPER: "cmd",
    pygame.K_HOME: "home", pygame.K_END: "end",
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    KEY_MAP[getattr(pygame, f"K_{_c}")] = _c
for _d in "0123456789":
    KEY_MAP[getattr(pygame, f"K_{_d}")] = _d


class Link:
    """Persistent TCP control link with auto-reconnect."""
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.sock = None
        self.lock = threading.Lock()

    def _connect(self):
        s = socket.create_connection((self.host, self.port), timeout=3)
        s.settimeout(None)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock = s
        print(f"control: connected to {self.host}:{self.port}", file=sys.stderr)

    def send(self, line):
        data = (line + "\n").encode("utf-8", "ignore")
        with self.lock:
            for _ in range(2):
                try:
                    if self.sock is None:
                        self._connect()
                    self.sock.sendall(data)
                    return
                except Exception as e:
                    print(f"control send failed ({e}); reconnect", file=sys.stderr)
                    try:
                        self.sock and self.sock.close()
                    except Exception:
                        pass
                    self.sock = None
                    time.sleep(0.4)


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(min(65536, n - len(buf)))
        if not chunk:
            raise OSError("eof")
        buf += chunk
    return buf


def capture_loop(frame_queue, stop):
    backoff = 1.0
    while not stop.is_set():
        try:
            sock = socket.create_connection((CAPTURE_HOST, CAPTURE_PORT), timeout=5)
            sock.settimeout(None)
            print(f"capture: connected to {CAPTURE_HOST}:{CAPTURE_PORT}", file=sys.stderr)
            backoff = 1.0
            with sock:
                while not stop.is_set():
                    (length,) = struct.unpack(">I", _recv_exact(sock, 4))
                    if length == 0 or length > 16 * 1024 * 1024:
                        raise OSError(f"bogus frame length {length}")
                    jpeg = _recv_exact(sock, length)
                    try:
                        frame_queue.put_nowait(jpeg)
                    except queue.Full:
                        try: frame_queue.get_nowait()
                        except queue.Empty: pass
                        try: frame_queue.put_nowait(jpeg)
                        except queue.Full: pass
        except Exception as e:
            print(f"capture: error {e!r}; reconnect in {backoff:.1f}s", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, 10.0)


def main():
    REGION = _resolve_region()
    x, y, w, h = REGION
    print(f"iPhone region: {REGION}", file=sys.stderr)

    pygame.init()
    pygame.key.set_repeat(400, 40)
    win_w, win_h = int(w * SCALE), int(h * SCALE)
    screen = pygame.display.set_mode((win_w, win_h))
    pygame.display.set_caption(f"tuxbridge {w}x{h} @ {MAC_HOST}")
    font = pygame.font.SysFont(None, 18)

    # iPhone display has rounded corners (~12% of short edge). Build a mask
    # that punches a rounded-rect hole — blit it over the frame so the
    # corners outside the iPhone display look like real device bezel.
    corner_radius = int(os.environ.get(
        "TUXBRIDGE_CORNER_RADIUS",
        str(int(min(win_w, win_h) * 0.12))))
    corner_mask = pygame.Surface((win_w, win_h), pygame.SRCALPHA)
    corner_mask.fill((0, 0, 0, 255))
    pygame.draw.rect(corner_mask, (0, 0, 0, 0),
                     (0, 0, win_w, win_h), border_radius=corner_radius)

    link = Link(MAC_HOST, MAC_PORT)

    mac_model = [None, None]
    mac_lock = threading.Lock()
    mac_cursor = [None, None]
    stop_event = threading.Event()

    def send_delta_chunked(dx, dy, gap=0.0):
        # With pointer acceleration disabled (Mac side), no pacing needed
        # for normal motion — chunks map 1:1. move_to() passes a small gap
        # for its corrective bursts so accel residue can't compound.
        first = True
        while dx or dy:
            if gap and not first:
                time.sleep(gap)
            cx = max(-127, min(127, dx)); dx -= cx
            cy = max(-127, min(127, dy)); dy -= cy
            link.send(f"m {cx} {cy}")
            first = False

    def move_to(target_x, target_y, max_iters=20, threshold=3):
        # Closed-loop: read cursor, send small step toward target, repeat.
        # Step size kept small (<=40) so macOS pointer acceleration barely
        # engages. After each step we wait for cursor_daemon to publish the
        # new position, then re-aim based on reality. No accel model needed.
        deadline = time.monotonic() + 0.5
        while mac_cursor[0] is None and time.monotonic() < deadline:
            time.sleep(0.02)
        if mac_cursor[0] is None:
            return False
        def step(d):
            if d == 0: return 0
            s = max(-40, min(40, d // 2 if abs(d) > 4 else d))
            return s if s != 0 else (1 if d > 0 else -1)
        for _ in range(max_iters):
            cx, cy = mac_cursor[0], mac_cursor[1]
            dx = target_x - cx
            dy = target_y - cy
            if abs(dx) <= threshold and abs(dy) <= threshold:
                # Confirm cursor has actually stopped: poll once more after a
                # brief pause. If it shifts, the Pico still has a step queued —
                # loop and re-correct. Kills the "drift a few mm before click"
                # jitter.
                time.sleep(0.03)
                if (abs(target_x - mac_cursor[0]) <= threshold
                        and abs(target_y - mac_cursor[1]) <= threshold):
                    with mac_lock:
                        mac_model[0] = mac_cursor[0]
                        mac_model[1] = mac_cursor[1]
                    return True
                continue
            link.send(f"m {step(dx)} {step(dy)}")
            # 30ms: at 60Hz cursor_daemon ticks every 16ms, plus Pico margin.
            time.sleep(0.03)
        return False

    def _startup_warp():
        try:
            subprocess.run(
                ["ssh", os.environ.get("TUXBRIDGE_SSH_HOST", MAC_HOST),
                 "osascript -e 'tell application \"iPhone Mirroring\" to activate'"],
                timeout=5, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"activate failed: {e}", file=sys.stderr)
        target_x = x + w // 2
        target_y = y + h // 2
        ok = move_to(target_x, target_y)
        time.sleep(0.05)
        link.send("d l"); time.sleep(0.05); link.send("u l")
        # Re-converge after the click (focus shift may nudge nothing, but be safe).
        move_to(target_x, target_y)
        print(f"warp: cursor converged on {target_x},{target_y} (ok={ok}) "
              f"actual={mac_cursor[0]},{mac_cursor[1]}", file=sys.stderr)

    threading.Thread(target=_startup_warp, daemon=True).start()

    CURSOR_PORT = int(os.environ.get("TUXBRIDGE_CURSOR_PORT", "8767"))

    def _poll_mac_cursor():
        # Subscribe to mac/cursor_daemon.py over TCP. Cross-platform — Pi and
        # Arch both reach the Mac the same way.
        backoff = 1.0
        while not stop_event.is_set():
            try:
                sock = socket.create_connection((CAPTURE_HOST, CURSOR_PORT), timeout=5)
                sock.settimeout(None)
                print(f"cursor: connected to {CAPTURE_HOST}:{CURSOR_PORT}", file=sys.stderr)
                backoff = 1.0
                buf = b""
                with sock:
                    while not stop_event.is_set():
                        chunk = sock.recv(4096)
                        if not chunk:
                            raise OSError("eof")
                        buf += chunk
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            parts = line.decode("ascii", "ignore").strip().split(",")
                            if len(parts) != 2:
                                continue
                            try:
                                mx, my = int(parts[0]), int(parts[1])
                            except ValueError:
                                continue
                            mac_cursor[0] = mx; mac_cursor[1] = my
                            with mac_lock:
                                mac_model[0] = mx; mac_model[1] = my
            except Exception as e:
                print(f"cursor: error {e!r}; reconnect in {backoff:.1f}s", file=sys.stderr)
                time.sleep(backoff)
                backoff = min(backoff * 2, 10.0)

    if os.environ.get("TUXBRIDGE_NO_POLL") != "1":
        threading.Thread(target=_poll_mac_cursor, daemon=True).start()
    else:
        print("cliclick polling disabled (TUXBRIDGE_NO_POLL=1)", file=sys.stderr)

    frame_queue: "queue.Queue[bytes]" = queue.Queue(maxsize=2)
    if os.environ.get("TUXBRIDGE_NO_CAPTURE") == "1":
        print("capture disabled (TUXBRIDGE_NO_CAPTURE=1) — input only", file=sys.stderr)
    else:
        threading.Thread(target=capture_loop, args=(frame_queue, stop_event), daemon=True).start()

    TOUCH = os.environ.get("TUXBRIDGE_TOUCH") == "1"
    grabbed = TOUCH  # touchscreen: always "grabbed" — no toggle gesture exists
    def set_grab(on):
        nonlocal grabbed
        grabbed = on
        if not TOUCH:
            pygame.event.set_grab(on)
        pygame.mouse.set_visible(True)
    set_grab(grabbed)

    def pygame_to_mac(px, py):
        return REGION[0] + int(px / SCALE), REGION[1] + int(py / SCALE)

    def tap(px, py):
        """Atomic tap: warp under finger, click, release."""
        tx, ty = pygame_to_mac(px, py)
        move_to(tx, ty)
        link.send("d l")
        time.sleep(0.04)
        link.send("u l")

    def send_key(ev):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_g \
                and (ev.mod & pygame.KMOD_CTRL) and (ev.mod & pygame.KMOD_ALT):
            set_grab(not grabbed)
            return True
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_r and not grabbed:
            threading.Thread(target=_startup_warp, daemon=True).start()
            return True
        if ev.type == pygame.KEYDOWN:
            name = KEY_MAP.get(ev.key)
            if name and not (len(name) == 1 and name.isalnum()):
                link.send(f"kd {name}")
            return True
        if ev.type == pygame.KEYUP:
            name = KEY_MAP.get(ev.key)
            if name and not (len(name) == 1 and name.isalnum()):
                link.send(f"ku {name}")
            return True
        if ev.type == pygame.TEXTINPUT:
            text = ev.text.replace("\r", "").replace("\n", "")
            if text:
                link.send(f"t {text}")
            return True
        return False

    def handle_touch_events(events):
        # Touch mode: every MOUSEBUTTONDOWN is one atomic tap. Drop all
        # MOUSEMOTION / MOUSEBUTTONUP — they only cause drag/jitter.
        for ev in events:
            if ev.type == pygame.QUIT:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                return
            if send_key(ev):
                continue
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                tap(*ev.pos)

    def handle_trackpad_events(events):
        for ev in events:
            if ev.type == pygame.QUIT:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                return
            if send_key(ev):
                continue
            if ev.type == pygame.MOUSEBUTTONDOWN and not grabbed:
                set_grab(True); continue
            if not grabbed:
                continue
            if ev.type == pygame.MOUSEMOTION:
                tx, ty = pygame_to_mac(*ev.pos)
                with mac_lock:
                    if mac_model[0] is None:
                        continue
                    dx = tx - mac_model[0]; dy = ty - mac_model[1]
                    mac_model[0] = tx; mac_model[1] = ty
                if dx or dy:
                    send_delta_chunked(dx, dy)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                link.send("d l")
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                link.send("u l")
            elif ev.type == pygame.MOUSEWHEEL and ev.y:
                link.send(f"w {ev.y}")

    last_frame_surface = None
    clock = pygame.time.Clock()
    try:
        while True:
            try:
                jpeg = frame_queue.get_nowait()
                img = Image.open(io.BytesIO(jpeg)).convert("RGB")
                surf = pygame.image.frombuffer(img.tobytes(), img.size, "RGB")
                if surf.get_size() != (win_w, win_h):
                    surf = pygame.transform.smoothscale(surf.convert(), (win_w, win_h))
                else:
                    surf = surf.convert()
                last_frame_surface = surf
            except queue.Empty:
                pass
            except Exception as e:
                print(f"frame decode error: {e}", file=sys.stderr)

            if last_frame_surface is not None:
                screen.blit(last_frame_surface, (0, 0))
            else:
                screen.fill((10, 10, 16))
                screen.blit(font.render("waiting for frame…", True, (200, 200, 200)), (12, 12))

            with mac_lock:
                model_x, model_y = mac_model[0], mac_model[1]
            if model_x is not None:
                cx = int((model_x - REGION[0]) * SCALE)
                cy = int((model_y - REGION[1]) * SCALE)
                if 0 <= cx < win_w and 0 <= cy < win_h:
                    pygame.draw.line(screen, (255, 0, 0), (cx - 10, cy), (cx + 10, cy), 2)
                    pygame.draw.line(screen, (255, 0, 0), (cx, cy - 10), (cx, cy + 10), 2)
                else:
                    msg = font.render(f"Mac cursor off-region: {model_x},{model_y} — R to recenter",
                                       True, (255, 100, 100))
                    screen.blit(msg, (12, 12))
            if mac_cursor[0] is not None:
                gx = int((mac_cursor[0] - REGION[0]) * SCALE)
                gy = int((mac_cursor[1] - REGION[1]) * SCALE)
                if 0 <= gx < win_w and 0 <= gy < win_h:
                    pygame.draw.circle(screen, (0, 220, 0), (gx, gy), 3)

            if not grabbed:
                overlay = font.render("click to grab — Ctrl+Alt+G release — R recenter", True, (240, 240, 80))
                screen.blit(overlay, (12, win_h - 22))

            screen.blit(corner_mask, (0, 0))
            pygame.display.flip()

            events = pygame.event.get()
            if TOUCH:
                handle_touch_events(events)
            else:
                handle_trackpad_events(events)
            clock.tick(60)
    finally:
        stop_event.set()


if __name__ == "__main__":
    main()
