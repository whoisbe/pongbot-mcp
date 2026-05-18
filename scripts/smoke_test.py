#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["bleak", "mcp[cli]"]
# ///
"""Manual hardware smoke test — scan, connect, send warmup_topspin, wait, disconnect."""
from __future__ import annotations

import asyncio
import logging
import sys

# Allow running from repo root without installing the package
sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0] + "/src")

from pongbot_mcp.ble import PongbotConnection
from pongbot_mcp.presets import get_preset

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)
log = logging.getLogger("smoke_test")

WAIT_SECONDS = 10


def _on_notification(data: bytes) -> None:
    print(f"  [robot notification]  {len(data)} bytes: {data.hex()}")


async def main() -> None:
    conn = PongbotConnection()
    conn.set_notification_callback(_on_notification)

    # 1. Scan
    print("\n── Step 1: Scanning for Pongbot devices (10 s) ──────────────────")
    devices = await PongbotConnection.scan(timeout=10.0)
    if not devices:
        print("No Pongbot devices found. Is the robot powered on and nearby?")
        return
    for d in devices:
        print(f"  Found: {d['name']}  {d['address']}  RSSI {d['rssi']} dBm")

    target = devices[0]
    print(f"\n  Using: {target['name']}  ({target['address']})")

    # 2. Connect + authenticate (handshake is performed inside connect())
    print("\n── Step 2: Connecting + authenticating ──────────────────────────")
    print("  (5-step MD5 handshake: challenge → hash → ack1 → ack2 → wakeup)")
    try:
        await conn.connect(target["address"])
    except ConnectionError as exc:
        print(f"  Connection/auth failed: {exc}")
        return
    print(f"  Connected and authenticated. MTU: {conn._client.mtu_size if conn._client else '?'}")

    # 3. Send preset
    print("\n── Step 3: Sending 'warmup_topspin' preset ──────────────────────")
    drill = get_preset("warmup_topspin")
    print(f"  Drill: {len(drill.balls)} ball(s), mode={drill.mode.name}")
    for i, ball in enumerate(drill.balls):
        top, bot = ball._rpms()
        print(
            f"  Ball {i + 1}: speed={ball.speed}  spin={ball.spin}  "
            f"height={ball.height}  drop_point={ball.drop_point}  "
            f"freq={ball.frequency} bpm  reps={ball.reps}  "
            f"[top_rpm={top}  bot_rpm={bot}]"
        )
    try:
        await conn.send_drill(drill)
        print("  Drill sent successfully.")
    except IOError as exc:
        print(f"  Failed to send drill: {exc}")
        await conn.disconnect()
        return

    # 4. Wait — watch for notifications
    print(f"\n── Step 4: Waiting {WAIT_SECONDS} s (watching for robot notifications) ──")
    for remaining in range(WAIT_SECONDS, 0, -1):
        print(f"  {remaining}s remaining…", end="\r", flush=True)
        await asyncio.sleep(1)
    print(" " * 30, end="\r")  # clear the countdown line

    notifications = conn.notifications
    print(f"  Received {len(notifications)} notification(s) from robot during drill.")

    # 5. Stop drill + disconnect
    print("\n── Step 5: Stopping drill and disconnecting ─────────────────────")
    try:
        await conn.stop_drill()
        print("  Stop command sent (80 01 00 01).")
    except Exception as exc:
        print(f"  Stop failed: {exc}")
    await conn.disconnect()
    print("  Disconnected.")

    print("\n── Smoke test complete ──────────────────────────────────────────\n")


if __name__ == "__main__":
    asyncio.run(main())
