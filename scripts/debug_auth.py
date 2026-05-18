#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["bleak"]
# ///
"""
Debug script for the Pongbot BLE auth handshake.

Sequence:
  1. Scan + connect (raw Bleak — no PongbotConnection auth logic)
  2. Subscribe to ff02 notifications (print every notification with timestamp)
  3. Read ff00 and ff03 and print as hex
  4. Wait 2 s for unsolicited notifications
  5. Write 07 00 00 00 to ff01 with response=True; if that throws, retry with response=False
  6. Wait 10 s, print any notifications as they arrive
  7. Disconnect

Also prints the JS source behaviour for direct comparison.
"""
from __future__ import annotations

import asyncio
import sys
import time

from bleak import BleakClient, BleakError, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

# ── UUIDs ─────────────────────────────────────────────────────────────────────
SERVICE_UUID    = "02f00000-0000-0000-0000-00000000fe00"
WRITE_UUID      = "02f00000-0000-0000-0000-00000000ff01"
NOTIFY_UUID     = "02f00000-0000-0000-0000-00000000ff02"
READ_UUID_FF00  = "02f00000-0000-0000-0000-00000000ff00"
READ_UUID_FF03  = "02f00000-0000-0000-0000-00000000ff03"

CHALLENGE_BYTES = bytes([0x07, 0x00, 0x00, 0x00])

# ── JS behaviour reference ────────────────────────────────────────────────────
JS_REFERENCE = """
╔══════════════════════════════════════════════════════════════════════════════╗
║  olanga/nova  js/bluetooth.js  +  smee/nova-s-custom-drills  src/script.js  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  All writes go to ff01 only.  No writes ever to ff02 or ff03.               ║
║  No reads from any characteristic.                                           ║
║                                                                              ║
║  Connect sequence:                                                           ║
║    1. getPrimaryService(fe00)                                                ║
║    2. getCharacteristics()                                                   ║
║    3. startNotifications() on ff02  ← BEFORE any write                      ║
║    4. addEventListener('characteristicvaluechanged', handler) on ff02       ║
║    5. writeValue([07 00 00 00]) to ff01   ← writeValue = write-with-resp    ║
║                                                                              ║
║  Notification handler state machine:                                         ║
║    state "initial"         → parse serial[6:18] + code[18:]                 ║
║                              compute MD5 hash                                ║
║                              writeValue([08 20 00] + 32 ASCII hash bytes)   ║
║                              → state "connected 1/3"                        ║
║    state "connected 1/3"   → writeValue([01 00 00])                         ║
║                              → state "connected 2/3"                        ║
║    state "connected 2/3"   → writeValue([02 00 00])                         ║
║                              → state "connected 3/3"                        ║
║    state "connected 3/3"   → writeValue([80 01 00 00])  ← wakeup            ║
║                              → state "connected 3/3 1/3"                    ║
║    state "connected 3/3 1/3" → (no write)                                   ║
║                              → state "connected 3/3 2/3"                    ║
║    state "connected 3/3 2/3" → (no write)                                   ║
║                              → state "standby"  ← NOW READY FOR DRILLS      ║
║                                                                              ║
║  KEY: smee has 2 extra no-write notification steps after wakeup!            ║
║  Our ble.py was missing these — it declared auth done after writing wakeup. ║
║                                                                              ║
║  writeValue() is deprecated Web BT API = write-with-response equivalent.    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def ts() -> str:
    return f"[{time.strftime('%H:%M:%S')}]"


def notify_handler(char: BleakGATTCharacteristic, data: bytearray) -> None:
    payload = bytes(data)
    print(f"{ts()} NOTIFICATION  uuid={char.uuid}  len={len(payload)}  hex={payload.hex()}")
    if len(payload) >= 18:
        try:
            serial = payload[6:18].decode("utf-8")
            code   = payload[18:].decode("utf-8", errors="replace")
            print(f"        → decoded as challenge: serial={serial!r}  code={code!r}")
        except Exception:
            pass


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    print(JS_REFERENCE)

    # 1. Scan ──────────────────────────────────────────────────────────────────
    print(f"\n{ts()} ── Step 1: Scanning (10 s) ─────────────────────────────────")
    seen: dict[str, object] = {}

    def scan_cb(device, adv):
        name = (device.name or "").lower()
        if ("nova" in name or "pongbot" in name) and device.address not in seen:
            seen[device.address] = device
            print(f"{ts()}   Found: {device.name}  {device.address}  RSSI {adv.rssi}")

    async with BleakScanner(scan_cb):
        await asyncio.sleep(10)

    if not seen:
        print(f"{ts()} No Pongbot found. Power on the robot and try again.")
        return

    device = next(iter(seen.values()))
    print(f"{ts()}   Using: {device.name}  ({device.address})")

    # 2. Connect ───────────────────────────────────────────────────────────────
    print(f"\n{ts()} ── Step 2: Connecting ──────────────────────────────────────")
    client = BleakClient(device.address)
    try:
        await client.connect()
    except BleakError as exc:
        print(f"{ts()}   FAILED: {exc}")
        return
    print(f"{ts()}   Connected. MTU={client.mtu_size}")

    # 3. Subscribe to ff02 ─────────────────────────────────────────────────────
    print(f"\n{ts()} ── Step 3: Subscribing to notifications on ff02 ────────────")
    try:
        await client.start_notify(NOTIFY_UUID, notify_handler)
        print(f"{ts()}   start_notify OK on {NOTIFY_UUID}")
    except BleakError as exc:
        print(f"{ts()}   start_notify FAILED: {exc}")
        await client.disconnect()
        return

    # 4. Read ff00 and ff03 ────────────────────────────────────────────────────
    print(f"\n{ts()} ── Step 4: Reading ff00 and ff03 ───────────────────────────")
    for uuid, label in [(READ_UUID_FF00, "ff00"), (READ_UUID_FF03, "ff03")]:
        try:
            val = await client.read_gatt_char(uuid)
            raw = bytes(val)
            print(f"{ts()}   {label} = {raw.hex()}  ({len(raw)} bytes)")
            try:
                print(f"        → as UTF-8: {raw.decode('utf-8', errors='replace')!r}")
            except Exception:
                pass
        except BleakError as exc:
            print(f"{ts()}   {label} read FAILED: {exc}")

    # 5. Wait 2 s for unsolicited notifications ────────────────────────────────
    print(f"\n{ts()} ── Step 5: Waiting 2 s for unsolicited notifications ────────")
    await asyncio.sleep(2)
    print(f"{ts()}   (end of 2 s wait)")

    # 6. Write challenge with response=True ────────────────────────────────────
    print(f"\n{ts()} ── Step 6: Writing challenge [07 00 00 00] ─────────────────")

    write_ok = False
    for response in (True, False):
        label = "response=True" if response else "response=False"
        print(f"{ts()}   Trying write_gatt_char({WRITE_UUID}, 07000000, {label}) …")
        try:
            await client.write_gatt_char(WRITE_UUID, CHALLENGE_BYTES, response=response)
            print(f"{ts()}   Write SUCCEEDED with {label}")
            write_ok = True
            break
        except BleakError as exc:
            print(f"{ts()}   Write FAILED with {label}: {exc}")

    if not write_ok:
        print(f"{ts()}   Both write modes failed — cannot proceed.")
    else:
        # 7. Wait 10 s for challenge notification ──────────────────────────────
        print(f"\n{ts()} ── Step 7: Waiting 10 s for challenge notification ─────────")
        print(f"{ts()}   (Any notification will be printed above in real-time)")
        for remaining in range(10, 0, -1):
            print(f"{ts()}   {remaining}s remaining …", end="\r", flush=True)
            await asyncio.sleep(1)
        print(" " * 40, end="\r")
        print(f"{ts()}   Wait complete.")

    # 8. Disconnect ────────────────────────────────────────────────────────────
    print(f"\n{ts()} ── Step 8: Disconnecting ───────────────────────────────────")
    try:
        await client.stop_notify(NOTIFY_UUID)
    except BleakError:
        pass
    try:
        await client.disconnect()
        print(f"{ts()}   Disconnected.")
    except BleakError as exc:
        print(f"{ts()}   Disconnect error: {exc}")

    print(f"\n{ts()} ── Debug session complete ──────────────────────────────────\n")


if __name__ == "__main__":
    asyncio.run(main())
