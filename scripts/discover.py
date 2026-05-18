#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["bleak"]
# ///
"""Scan for BLE devices and enumerate GATT services on any Pongbot found."""
from __future__ import annotations

import asyncio

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

SCAN_SECONDS = 10
PONGBOT_NAMES = ("pongbot", "nova")  # case-insensitive substrings


def _is_pongbot(device: BLEDevice, adv: AdvertisementData) -> bool:
    name = (device.name or "").lower()
    return any(kw in name for kw in PONGBOT_NAMES)


async def scan() -> list[tuple[BLEDevice, AdvertisementData]]:
    print(f"Scanning for {SCAN_SECONDS}s …\n")
    discovered: list[tuple[BLEDevice, AdvertisementData]] = []

    def callback(device: BLEDevice, adv: AdvertisementData) -> None:
        discovered.append((device, adv))

    async with BleakScanner(callback) as scanner:  # noqa: F841
        await asyncio.sleep(SCAN_SECONDS)

    # Deduplicate by address, keeping last advertisement
    seen: dict[str, tuple[BLEDevice, AdvertisementData]] = {}
    for device, adv in discovered:
        seen[device.address] = (device, adv)

    return list(seen.values())


def print_scan_results(results: list[tuple[BLEDevice, AdvertisementData]]) -> list[BLEDevice]:
    pongbots: list[BLEDevice] = []
    print(f"{'ADDRESS':<20}  {'RSSI':>5}  NAME")
    print("-" * 60)
    for device, adv in sorted(results, key=lambda r: r[0].address):
        marker = " ★" if _is_pongbot(device, adv) else ""
        name = device.name or "(unknown)"
        print(f"{device.address:<20}  {adv.rssi or 0:>5}  {name}{marker}")
        if adv.service_uuids:
            for uuid in adv.service_uuids:
                print(f"  {'':20}         service: {uuid}")
        if _is_pongbot(device, adv):
            pongbots.append(device)
    print()
    return pongbots


async def enumerate_gatt(device: BLEDevice) -> None:
    print(f"Connecting to {device.name} ({device.address}) …")
    async with BleakClient(device) as client:
        print(f"Connected. MTU: {client.mtu_size}\n")
        for service in client.services:
            print(f"  SERVICE  {service.uuid}")
            if service.description and service.description != service.uuid:
                print(f"           {service.description}")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"    CHAR   {char.uuid}  [{props}]")
                if char.description and char.description != char.uuid:
                    print(f"             {char.description}")
                for desc in char.descriptors:
                    print(f"      DESC {desc.uuid}")
            print()


async def main() -> None:
    results = await scan()
    if not results:
        print("No BLE devices found.")
        return

    print(f"Found {len(results)} device(s):\n")
    pongbots = print_scan_results(results)

    if not pongbots:
        print("No Pongbot devices detected (looked for names containing: "
              + ", ".join(PONGBOT_NAMES) + ").")
        return

    for device in pongbots:
        print(f"\n{'='*60}")
        print(f"Pongbot found: {device.name}  {device.address}")
        print("=" * 60)
        await enumerate_gatt(device)


if __name__ == "__main__":
    asyncio.run(main())
