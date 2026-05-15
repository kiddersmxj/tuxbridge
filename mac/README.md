# Mac-side components

The Mac runs three daemons: `bridge_daemon.py` (control), `capture_daemon.py`
(JPEG frames), `cursor_daemon.py` (cursor position). Helper scripts
`start-session.sh`, `end-session.sh`, and `iphone-region.sh` manage the
dummy display and emit the iPhone display rect.

Documentation has moved to `../docs/`:

- Architecture and rationale: [../docs/architecture.md](../docs/architecture.md)
- First-time setup (Mac side): [../docs/setup.md](../docs/setup.md)
- Day-to-day operation, logs, services: [../docs/operations.md](../docs/operations.md)
- Non-obvious failure modes (TCC, capture insets, pointer accel): [../docs/gotchas.md](../docs/gotchas.md)
