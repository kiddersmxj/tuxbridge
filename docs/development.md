# Development

## Modifying Pico firmware

Edit `pico/code.py` (or `pico/boot.py`) on the dev machine. To deploy:

### Easy path — CIRCUITPY mounted on the Mac

```bash
scp pico/code.py mac-host:/Volumes/CIRCUITPY/code.py
ssh mac-host 'sync'
```

(The volume name may differ — on this Mac it's `MXJKM_IN`. Check with
`ssh mac-host 'ls /Volumes/'`.)

CircuitPython auto-reloads on file save. The Pico re-enumerates its CDC
ports briefly; `bridge_daemon` handles the reopen.

### Fallback — REPL push over serial

If MSC is disabled or the volume isn't mounted, push via the REPL. Helper
script: `/tmp/pico_deploy.py` on the Mac (not committed — generated as
needed). It enters raw REPL on the lower-numbered usbmodem port, base64-encodes
the file, and writes it.

This only works if `storage.remount('/', readonly=False)` succeeds, which
requires MSC to be disabled. If MSC is presenting the volume, the remount
fails — use the easy path instead.

### Verifying a Pico change

After deploy:

```bash
# From the Linux client, talk directly to the bridge:
printf 't hello world\n' | nc <mac-tailscale-ip> 8765
# Check the iPhone screen for the typed text.
```

The bridge logs every chunk to `~/devel/tuxbridge/mac/bridge.err` (manual
run) or `~/tuxbridge/daemon.err` (LaunchAgent). If the typed text is right
on the wire but wrong on the iPhone, the bug is Pico-side.

## Modifying Mac daemons

Edit on the dev machine, rsync to the Mac, reload the LaunchAgent if
relevant:

```bash
rsync -av mac/ mac-host:~/devel/tuxbridge/mac/
ssh mac-host 'launchctl kickstart -k gui/$(id -u)/com.tuxbridge.daemon'
```

`capture_daemon` is launched from Terminal (see
[gotchas.md](gotchas.md#screen-recording-tcc)) — restart it by Ctrl-C in
that Terminal and rerun.

## Modifying the Linux client

`arch/integrated.py` is the only client of interest. Test cycle:

```bash
TUXBRIDGE_HOST=<mac> python3 arch/integrated.py
# Ctrl-C to quit; re-run.
```

Run with `TUXBRIDGE_NO_CAPTURE=1` to develop input handling without the
JPEG stream (faster iteration, no need for capture_daemon running).

## Debugging a tap

If a tap lands in the wrong place:

1. Check `mac/bridge.err` for the sequence of `m` deltas and the final
   `d l` / `u l`. The deltas should walk the cursor toward the target.
2. Check `integrated.py` stderr for `"tap blocked: cursor ..."` — means
   the cursor never converged into the region.
3. Check `TUXBRIDGE_REGION` matches the actual current iPhone display rect.
   Run `mac/start-session.sh` to re-emit it.
4. If the cursor *does* converge but the iPhone doesn't react, it's a
   focus issue — iPhone Mirroring window isn't frontmost. The startup
   warp's centre-click usually fixes this; if not, `osascript -e 'tell
   application "iPhone Mirroring" to activate'`.

## Tests

There are no automated tests. End-to-end verification is manual:

1. `bridge_daemon` listening; Pico plugged in.
2. `capture_daemon` running from Terminal with TCC grant.
3. `cursor_daemon` running.
4. Linux client connects; iPhone screen visible; green dot tracks Mac cursor.
5. Tap on a known target (e.g. the time in the status bar) — observe the
   tap lands inside the rendered region and iPhone reacts.
6. Type "hello world" — appears correctly on the iPhone.
7. Reboot Mac; LaunchAgents come back; client reconnects automatically.

## Git workflow

Single `main` branch, fast-forward commits. Save points after each verified
behaviour change (e.g. "tap accuracy restored", "typing pacing fix"). Each
commit message ends with a `Co-Authored-By: Claude Opus 4.7` trailer when
written via the assistant.
