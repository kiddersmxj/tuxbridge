"""TCP <-> Pico USB-serial pipe. Protocol-agnostic byte forwarder."""
import os
import select
import socket
import subprocess
import sys
import threading
import time

import serial
from serial.tools import list_ports

LISTEN_PORT = int(os.environ.get("TUXBRIDGE_PORT", "8765"))
SERIAL_OVERRIDE = os.environ.get("TUXBRIDGE_SERIAL", "")
SERIAL_BAUD = 115200


def pick_bind_addr():
    override = os.environ.get("TUXBRIDGE_BIND", "")
    if override:
        return override
    # Prefer Tailscale IP; fall back to all-interfaces with a loud warning.
    try:
        out = subprocess.check_output(
            ["tailscale", "ip", "--4"], stderr=subprocess.DEVNULL, timeout=2
        ).decode().strip().splitlines()
        if out and out[0]:
            return out[0]
    except Exception:
        pass
    print("WARNING: tailscale ip --4 unavailable; binding 0.0.0.0. Restrict at firewall.",
          file=sys.stderr)
    return "0.0.0.0"


def find_pico_data_port():
    if SERIAL_OVERRIDE:
        return SERIAL_OVERRIDE
    candidates = []
    for p in list_ports.comports():
        iface = (p.interface or "")
        desc = (p.description or "")
        # CircuitPython exposes two CDC interfaces when usb_cdc.enable(data=True).
        # The data channel's interface descriptor contains "CDC2" or "data".
        if "CDC2" in iface or iface.endswith("data") or "data" in desc.lower():
            candidates.append(p.device)
    if candidates:
        return candidates[0]
    # Last resort: any usbmodem device.
    for p in list_ports.comports():
        if "usbmodem" in p.device:
            candidates.append(p.device)
    if not candidates:
        raise RuntimeError("No Pico serial device found. Set TUXBRIDGE_SERIAL.")
    # On macOS the data channel typically sorts AFTER the REPL on the same VID/PID.
    candidates.sort()
    return candidates[-1]


def open_serial_blocking():
    """Open the Pico serial port, retrying until it appears."""
    last_err = None
    for attempt in range(0, 10**9):
        try:
            path = find_pico_data_port()
            s = serial.Serial(path, SERIAL_BAUD, timeout=0)
            print(f"opening serial: {path}", file=sys.stderr)
            return s
        except Exception as e:
            if str(e) != last_err:
                print(f"serial open failed: {e}; retrying", file=sys.stderr)
                last_err = str(e)
            time.sleep(1.0)


class SerialHolder:
    def __init__(self):
        self.ser = open_serial_blocking()

    def reopen(self):
        try:
            self.ser.close()
        except Exception:
            pass
        self.ser = open_serial_blocking()


def pipe(client, holder):
    client.setblocking(False)
    while True:
        ser = holder.ser
        try:
            r, _, _ = select.select([client, ser.fileno()], [], [], 1.0)
        except (OSError, ValueError):
            holder.reopen()
            continue
        if client in r:
            try:
                data = client.recv(4096)
            except BlockingIOError:
                continue  # spurious select wake; don't treat as EOF
            except ConnectionResetError:
                return
            if not data:
                return
            t0 = time.monotonic()
            try:
                ser.write(data)
                ser.flush()  # macOS tty layer otherwise buffers until close
            except (serial.SerialException, OSError) as e:
                print(f"serial write failed: {e}; reopening", file=sys.stderr)
                holder.reopen()
                continue
            dt = (time.monotonic() - t0) * 1000
            try:
                printable = data.decode("utf-8", "replace").rstrip("\n")
            except Exception:
                printable = repr(data)
            print(f"[{time.strftime('%H:%M:%S')}] -> pico ({dt:.1f}ms): {printable!r}",
                  file=sys.stderr, flush=True)
        if ser.fileno() in r:
            try:
                data = ser.read(4096)
            except (serial.SerialException, OSError) as e:
                print(f"serial read failed: {e}; reopening", file=sys.stderr)
                holder.reopen()
                continue
            if data:
                try:
                    client.sendall(data)
                except (BrokenPipeError, ConnectionResetError):
                    return


def main():
    holder = SerialHolder()
    bind = pick_bind_addr()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((bind, LISTEN_PORT))
    s.listen(1)
    print(f"listening on {bind}:{LISTEN_PORT}", file=sys.stderr)
    while True:
        client, addr = s.accept()
        print(f"client connected: {addr}", file=sys.stderr)
        try:
            pipe(client, holder)
        except Exception as e:
            print(f"pipe error: {e}", file=sys.stderr)
        finally:
            try:
                client.close()
            except Exception:
                pass
            print("client disconnected", file=sys.stderr)


if __name__ == "__main__":
    main()
