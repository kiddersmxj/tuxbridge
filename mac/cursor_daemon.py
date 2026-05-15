"""Broadcast macOS cursor position over TCP.

Each connected client receives "x,y\n" lines at ~20 Hz. Replaces the
old SSH+cliclick polling loop so non-Tailscale clients (e.g. a Pi on
plain LAN) can also draw the live-cursor indicator.

Env vars:
  TUXBRIDGE_CURSOR_PORT   default 8767
  TUXBRIDGE_CURSOR_FPS    default 20
  TUXBRIDGE_BIND          override bind addr (else Tailscale IP, else 0.0.0.0)
"""
import os
import socket
import subprocess
import sys
import threading
import time

import Quartz

PORT = int(os.environ.get("TUXBRIDGE_CURSOR_PORT", "8767"))
FPS = float(os.environ.get("TUXBRIDGE_CURSOR_FPS", "60"))


def pick_bind_addr():
    override = os.environ.get("TUXBRIDGE_BIND", "")
    if override:
        return override
    try:
        out = subprocess.check_output(
            ["tailscale", "ip", "--4"], stderr=subprocess.DEVNULL, timeout=2,
        ).decode().strip().splitlines()
        if out and out[0]:
            return out[0]
    except Exception:
        pass
    print("WARNING: tailscale ip --4 unavailable; binding 0.0.0.0", file=sys.stderr)
    return "0.0.0.0"


def cursor_xy():
    e = Quartz.CGEventCreate(None)
    p = Quartz.CGEventGetLocation(e)
    return int(p.x), int(p.y)


def serve(client, addr):
    period = 1.0 / FPS
    print(f"cursor client: {addr}", file=sys.stderr, flush=True)
    try:
        while True:
            t0 = time.monotonic()
            x, y = cursor_xy()
            client.sendall(f"{x},{y}\n".encode())
            dt = period - (time.monotonic() - t0)
            if dt > 0:
                time.sleep(dt)
    except (BrokenPipeError, ConnectionResetError, OSError) as e:
        print(f"cursor pipe ended ({addr}): {e}", file=sys.stderr, flush=True)
    finally:
        try: client.close()
        except Exception: pass


def main():
    bind = pick_bind_addr()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((bind, PORT))
    s.listen(8)
    print(f"cursor listening on {bind}:{PORT} @ {FPS}fps", file=sys.stderr, flush=True)
    while True:
        client, addr = s.accept()
        threading.Thread(target=serve, args=(client, addr), daemon=True).start()


if __name__ == "__main__":
    main()
