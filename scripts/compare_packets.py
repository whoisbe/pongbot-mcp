#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Compare our Python drill packet byte-for-byte against what the olanga/smee JS produces
for an identical set of parameters.

Reference JS source:
  olanga/nova  js/bluetooth.js  packBall()
  smee/nova-s-custom-drills  src/script.js  createBall() + createDrill()

Run from repo root:
    uv run scripts/compare_packets.py
"""
from __future__ import annotations

import struct
import sys

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0] + "/src")
from pongbot_mcp.protocol import Ball, Drill, DrillMode

# ── Test parameters ──────────────────────────────────────────────────────────
SPEED = 3.0
SPIN  = 3.0
HEIGHT = 15.0
DROP_POINT = 0.0
FREQUENCY  = 60    # bpm (our abstraction) == 60/100+0.5 = 1.1 packet value
REPS       = 50

# ── JS reference calculation (hand-translated from JS source) ────────────────
# olanga packBall / smee createBall both produce identical layouts.
#
# us = top_rpm    (uint32 LE)
# ls = bot_rpm    (uint32 LE)
# bh = (h+50)/150*50 - 20   (float32 LE)
# dp = (dp+10)/20*44 - 22   (float32 LE)
# fr = freq/100 + 0.5        (float32 LE)   ← freq here is our bpm value
# rp = reps                  (uint32 LE)    ← confirmed setUint32 in both JS sources

us = round(970 + 630.5 * SPEED + 342 * SPIN)   # 3888
ls = round(970 + 630.5 * SPEED - 342 * SPIN)   # 1836
bh = (HEIGHT     + 50) / 150 * 50 - 20
dp = (DROP_POINT + 10) / 20  * 44 - 22
fr = FREQUENCY / 100 + 0.5
rp = REPS

js_ball = struct.pack("<IIfffI", us, ls, bh, dp, fr, rp)

# JS header (smee createDrill with combos=3, minutes=0, isRandom=False):
#   setUint8(0, 0x81)
#   setUint16(1, 4 + n_balls*24, LE)
#   setUint8(3, combos)
#   setUint16(4, 0 if combos else minutes, LE)
#   setUint8(6, isRandom)
def js_header(n_balls: int, combos: int = 3, minutes: int = 0, is_random: bool = False) -> bytes:
    b = bytearray(7)
    b[0] = 0x81
    struct.pack_into("<H", b, 1, 4 + n_balls * 24)
    b[3] = combos
    struct.pack_into("<H", b, 4, 0 if combos else minutes)
    b[6] = 1 if is_random else 0
    return bytes(b)

js_packet = js_header(1) + js_ball

# ── Our Python packet ────────────────────────────────────────────────────────
py_drill = Drill(
    balls=[Ball(speed=SPEED, spin=SPIN, height=HEIGHT,
                drop_point=DROP_POINT, frequency=FREQUENCY, reps=REPS)],
    mode=DrillMode.ENDLESS,
)
py_packet = py_drill.to_bytes()

# ── Pretty-print comparison ──────────────────────────────────────────────────
def annotate(data: bytes) -> list[str]:
    top, bot, bh_p, dp_p, fr_p, rp_p = struct.unpack("<IIfffI", data[7:])
    lines = [
        f"  [0]     command:       0x{data[0]:02x}",
        f"  [1-2]   pkt_length:    {struct.unpack_from('<H', data, 1)[0]}  (uint16 LE: {data[1]:02x} {data[2]:02x})",
        f"  [3]     combos/mode:   {data[3]}",
        f"  [4-5]   minutes:       {struct.unpack_from('<H', data, 4)[0]}  (uint16 LE: {data[4]:02x} {data[5]:02x})",
        f"  [6]     random:        {data[6]}",
        f"  [7-10]  top_rpm:       {top}  ({data[7:11].hex()})",
        f"  [11-14] bot_rpm:       {bot}  ({data[11:15].hex()})",
        f"  [15-18] height:        {bh_p:.6f}  ({data[15:19].hex()})",
        f"  [19-22] drop_point:    {dp_p:.6f}  ({data[19:23].hex()})",
        f"  [23-26] frequency:     {fr_p:.6f}  ({data[23:27].hex()})",
        f"  [27-30] reps:          {rp_p}  ({data[27:31].hex()})  ← uint32",
    ]
    return lines

print(f"Parameters: speed={SPEED}  spin={SPIN}  height={HEIGHT}  "
      f"drop_point={DROP_POINT}  frequency={FREQUENCY} bpm  reps={REPS}")
print()
print(f"JS  packet ({len(js_packet)} bytes): {js_packet.hex()}")
print(f"PY  packet ({len(py_packet)} bytes): {py_packet.hex()}")
print()

match = py_packet == js_packet
if match:
    print("✓ Packets are IDENTICAL")
else:
    print("✗ Packets DIFFER — byte diff:")
    for i, (a, b) in enumerate(zip(js_packet, py_packet)):
        if a != b:
            print(f"  byte [{i:2d}]: JS=0x{a:02x} ({a:3d})  PY=0x{b:02x} ({b:3d})")
    if len(js_packet) != len(py_packet):
        print(f"  length: JS={len(js_packet)}  PY={len(py_packet)}")
print()
print("Annotated JS packet:")
for line in annotate(js_packet):
    print(line)
print()
print("Annotated PY packet:")
for line in annotate(py_packet):
    print(line)
