"""Arch input-capture client: pygame window -> TCP -> Mac daemon -> Pico -> iPhone.

Trackpad-style relative pointer + keyboard.
Hotkey Ctrl+Alt+G toggles input grab (so you can escape the captured pointer).
"""
import os
import socket
import sys
import threading
import time

import pygame

MAC_HOST = os.environ.get("TUXBRIDGE_HOST", "")
MAC_PORT = int(os.environ.get("TUXBRIDGE_PORT", "8765"))
WIN_W = int(os.environ.get("TUXBRIDGE_W", "430"))
WIN_H = int(os.environ.get("TUXBRIDGE_H", "932"))

if not MAC_HOST:
    print("set TUXBRIDGE_HOST to the Mac's Tailscale IP / hostname", file=sys.stderr)
    sys.exit(2)


BUTTON_MAP = {1: "l", 2: "m", 3: "r"}

KEY_MAP = {
    pygame.K_RETURN: "enter", pygame.K_KP_ENTER: "enter",
    pygame.K_ESCAPE: "esc",
    pygame.K_BACKSPACE: "backspace",
    pygame.K_TAB: "tab",
    pygame.K_SPACE: "space",
    pygame.K_DELETE: "delete",
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
    """Persistent TCP sender with auto-reconnect."""
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.lock = threading.Lock()

    def _connect(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((self.host, self.port))
        s.settimeout(None)
        self.sock = s
        print(f"connected to {self.host}:{self.port}", file=sys.stderr)

    def send(self, line):
        data = (line + "\n").encode("utf-8", "ignore")
        with self.lock:
            for attempt in range(2):
                try:
                    if self.sock is None:
                        self._connect()
                    self.sock.sendall(data)
                    return
                except Exception as e:
                    print(f"send failed ({e}); reconnecting", file=sys.stderr)
                    try:
                        if self.sock:
                            self.sock.close()
                    except Exception:
                        pass
                    self.sock = None
                    time.sleep(0.5)


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("tuxbridge — input")
    font = pygame.font.SysFont(None, 22)

    link = Link(MAC_HOST, MAC_PORT)
    grabbed = False

    def set_grab(on):
        nonlocal grabbed
        grabbed = on
        pygame.event.set_grab(on)
        pygame.mouse.set_visible(not on)

    def render():
        screen.fill((20, 20, 28) if grabbed else (40, 40, 50))
        msg = "GRABBED — Ctrl+Alt+G to release" if grabbed else "click to grab"
        screen.blit(font.render(msg, True, (220, 220, 220)), (12, 12))
        screen.blit(font.render(f"-> {MAC_HOST}:{MAC_PORT}", True, (160, 160, 200)), (12, 36))
        pygame.display.flip()

    set_grab(False)
    render()
    clock = pygame.time.Clock()

    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_g and (ev.mod & pygame.KMOD_CTRL) and (ev.mod & pygame.KMOD_ALT):
                set_grab(not grabbed)
                render()
                continue
            if ev.type == pygame.MOUSEBUTTONDOWN and not grabbed:
                set_grab(True)
                render()
                continue
            if not grabbed:
                continue

            if ev.type == pygame.MOUSEMOTION:
                dx, dy = ev.rel
                if dx or dy:
                    link.send(f"m {dx} {dy}")
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button in BUTTON_MAP:
                link.send(f"d {BUTTON_MAP[ev.button]}")
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button in BUTTON_MAP:
                link.send(f"u {BUTTON_MAP[ev.button]}")
            elif ev.type == pygame.MOUSEWHEEL:
                if ev.y:
                    link.send(f"w {ev.y}")
            elif ev.type == pygame.KEYDOWN:
                name = KEY_MAP.get(ev.key)
                if name:
                    link.send(f"kd {name}")
            elif ev.type == pygame.KEYUP:
                name = KEY_MAP.get(ev.key)
                if name:
                    link.send(f"ku {name}")
            elif ev.type == pygame.TEXTINPUT:
                # printable text — let the Pico's layout.write handle it
                text = ev.text.replace("\r", "").replace("\n", "")
                if text:
                    link.send(f"t {text}")
        clock.tick(120)


if __name__ == "__main__":
    main()
