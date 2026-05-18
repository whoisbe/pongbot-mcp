#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["bleak", "mcp[cli]"]
# ///
"""
Keepalive end-to-end test — connects to the robot, then sits idle for 5 minutes
printing every keepalive sent and every ACK received. Confirms keepalives are
actually flowing and the robot is staying connected without a drill running.

Usage:
    uv run scripts/keepalive_test.py
    uv run scripts/keepalive_test.py --duration 300   # 5 minutes (default)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0] + "/src")

from pongbot_mcp.ble import PongbotConnection, _NOTIFY_KEEPALIVE_ACK  # noqa: PLC2701

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)
log = logging.getLogger("keepalive_test")

# Counters updated by the notification callback
_sent = 0
_acked = 0
_start_time: float = 0.0


def _fmt_elapsed() -> str:
    elapsed = time.monotonic() - _start_time
    m, s = divmod(int(elapsed), 60)
    return f"{m:02d}:{s:02d}"


def _on_notification(data: bytes) -> None:
    global _acked
    if data == _NOTIFY_KEEPALIVE_ACK:
        _acked += 1
        print(f"  [{_fmt_elapsed()}]  ✓ ACK received (00 83 00 00)  "
              f"[sent={_sent}  acked={_acked}  missed={_sent - _acked}]")
    else:
        print(f"  [{_fmt_elapsed()}]  · other notification ({len(data)}b): {data.hex()}")


async def main(duration: int) -> None:
    global _sent, _start_time

    # ── Scan ────────────────────────────────────────────────────────────────
    print("\n── Scanning for Pongbot devices (10 s) ─────────────────────────")
    devices = await PongbotConnection.scan(timeout=10.0)
    if not devices:
        print("No Pongbot devices found. Is the robot powered on and nearby?")
        sys.exit(1)
    for d in devices:
        print(f"  {d['name']}  {d['address']}  RSSI {d['rssi']} dBm")
    target = devices[0]
    print(f"\n  Using: {target['name']}  ({target['address']})")

    # ── Connect ──────────────────────────────────────────────────────────────
    print("\n── Connecting + authenticating ─────────────────────────────────")
    conn = PongbotConnection()
    conn.set_notification_callback(_on_notification)
    try:
        await conn.connect(target["address"])
    except ConnectionError as exc:
        print(f"  Connection/auth failed: {exc}")
        sys.exit(1)
    print("  Connected and authenticated. Robot is in standby.")

    # Monkey-patch _keepalive_loop's write to count sends.
    # We do this by wrapping the notification callback instead (simpler):
    # the ACK counter is already handled above. For the "sent" count we hook
    # into the connection's keepalive task indirectly by watching the log.
    # Instead, patch _write_cmd to count keepalive writes.
    original_write_cmd = conn._write_cmd

    async def _counting_write_cmd(data: bytes) -> None:
        global _sent
        if data == b"\x83\x06\x00":
            _sent += 1
            print(f"  [{_fmt_elapsed()}]  → Keepalive sent (83 06 00)  "
                  f"[sent={_sent}  acked={_acked}  missed={_sent - _acked}]")
        await original_write_cmd(data)

    conn._write_cmd = _counting_write_cmd  # type: ignore[method-assign]

    # ── Idle loop ────────────────────────────────────────────────────────────
    print(f"\n── Idle for {duration}s — watching keepalives ───────────────────")
    print(f"  Keepalive interval: 10s  |  Dead-after: 3 missed ACKs")
    print(f"  Start time: {time.strftime('%H:%M:%S')}")
    print()

    _start_time = time.monotonic()
    deadline = _start_time + duration

    try:
        while time.monotonic() < deadline:
            remaining = int(deadline - time.monotonic())
            print(
                f"  [{_fmt_elapsed()}]  status: connected={conn.connected}  "
                f"sent={_sent}  acked={_acked}  "
                f"missed={_sent - _acked}  "
                f"remaining={remaining}s",
                end="\r",
                flush=True,
            )
            await asyncio.sleep(5.0)
            if not conn.connected:
                print(f"\n  [{_fmt_elapsed()}]  CONNECTION LOST (connected=False)")
                break
    except KeyboardInterrupt:
        print(f"\n  Interrupted at {_fmt_elapsed()}.")

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n\n── Summary ──────────────────────────────────────────────────────")
    print(f"  Duration:  {_fmt_elapsed()}")
    print(f"  Sent:      {_sent}")
    print(f"  ACKed:     {_acked}")
    print(f"  Missed:    {_sent - _acked}")
    print(f"  Connected: {conn.connected}")

    # ── Disconnect ───────────────────────────────────────────────────────────
    await conn.disconnect()
    print("  Disconnected cleanly.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Keepalive end-to-end test")
    parser.add_argument(
        "--duration", type=int, default=300,
        help="How many seconds to sit idle (default: 300 = 5 minutes)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.duration))
