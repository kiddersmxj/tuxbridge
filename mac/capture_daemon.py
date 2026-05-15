"""Capture iPhone Mirroring window region and stream JPEG frames over TCP.

Avoids Apple Screen Sharing (which gates HID input destined for iPhone
Mirroring while a VNC client is connected). Uses CoreGraphics directly.

Wire format: each frame is sent as a 4-byte big-endian length followed by
JPEG bytes. One frame per cycle, ~CAPTURE_FPS times per second.

Env vars:
  TUXBRIDGE_CAPTURE_PORT      TCP port to listen on              default 8766
  TUXBRIDGE_CAPTURE_FPS       target frames/sec                  default 15
  TUXBRIDGE_CAPTURE_QUALITY   JPEG quality 1-95                  default 70
  TUXBRIDGE_CAPTURE_REGION    "x,y,w,h" override (else auto from
                              iphone-region.sh)
"""
import io
import os
import socket
import struct
import subprocess
import sys
import time

import Quartz
from PIL import Image

CAPTURE_PORT = int(os.environ.get("TUXBRIDGE_CAPTURE_PORT", "8766"))
FPS = float(os.environ.get("TUXBRIDGE_CAPTURE_FPS", "15"))
JPEG_QUALITY = int(os.environ.get("TUXBRIDGE_CAPTURE_QUALITY", "70"))
REGION_SCRIPT = os.path.expanduser("~/tuxbridge/iphone-region.sh")


def resolve_region():
    raw = os.environ.get("TUXBRIDGE_CAPTURE_REGION", "auto")
    if raw != "auto":
        return tuple(int(v) for v in raw.split(","))
    out = subprocess.check_output([REGION_SCRIPT], text=True, timeout=10).strip()
    line = out.splitlines()[-1].strip()
    return tuple(int(v) for v in line.split(","))


def capture_jpeg(region, quality):
    x, y, w, h = region
    rect = Quartz.CGRectMake(x, y, w, h)
    image = Quartz.CGWindowListCreateImage(
        rect,
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID,
        Quartz.kCGWindowImageDefault,
    )
    if image is None:
        return None
    width = Quartz.CGImageGetWidth(image)
    height = Quartz.CGImageGetHeight(image)
    bpr = Quartz.CGImageGetBytesPerRow(image)
    raw = bytes(Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(image)))
    img = Image.frombuffer("RGBA", (width, height), raw, "raw", "BGRA", bpr, 1).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def serve(client, region):
    period = 1.0 / FPS
    last = 0.0
    while True:
        now = time.monotonic()
        wait = period - (now - last)
        if wait > 0:
            time.sleep(wait)
        last = time.monotonic()
        jpeg = capture_jpeg(region, JPEG_QUALITY)
        if jpeg is None:
            continue
        client.sendall(struct.pack(">I", len(jpeg)) + jpeg)


def pick_bind_addr():
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


def main():
    region = resolve_region()
    print(f"capture region: {region}", file=sys.stderr, flush=True)
    bind = pick_bind_addr()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((bind, CAPTURE_PORT))
    s.listen(1)
    print(f"capture listening on {bind}:{CAPTURE_PORT} @ {FPS}fps q{JPEG_QUALITY}",
          file=sys.stderr, flush=True)
    while True:
        client, addr = s.accept()
        print(f"capture client: {addr}", file=sys.stderr, flush=True)
        try:
            region = resolve_region()
            print(f"capture region: {region}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"region re-resolve failed: {e}", file=sys.stderr, flush=True)
        try:
            serve(client, region)
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"capture pipe ended: {e}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"capture error: {e!r}", file=sys.stderr, flush=True)
        finally:
            try:
                client.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
