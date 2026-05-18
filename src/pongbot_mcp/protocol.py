from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Literal

BallType = Literal["topspin", "backspin"]

# speed → max abs(spin) lookup table
_MAX_SPIN: dict[float, float] = {
    0.0: 2, 0.5: 3, 1.0: 4, 1.5: 5, 2.0: 6, 2.5: 7, 3.0: 8, 3.5: 9,
    4.0: 10, 4.5: 10, 5.0: 9, 5.5: 8, 6.0: 8, 6.5: 7, 7.0: 6, 7.5: 5,
    8.0: 4, 8.5: 3, 9.0: 2, 9.5: 1, 10.0: 0,
}

_BALL_STRUCT = struct.Struct("<IIfffI")  # top_rpm, bot_rpm, height, drop, freq, reps(u32)

# ---------------------------------------------------------------------------
# Ball field scaling (from olanga/nova js/bluetooth.js packBall())
# ---------------------------------------------------------------------------
# The robot's internal floats are NOT the raw user-facing values.
# These transforms convert user ranges → robot packet values.
#
#   height:     user -50…100  → packet (h+50)/150*50 - 20   → range [-20, 30]
#   drop_point: user -10…10   → packet (d+10)/20*44 - 22    → range [-22, 22]
#   frequency:  user 30…90 bpm→ packet f/100 + 0.5          → range [0.8, 1.4]
#   reps:       user int       → packed as uint32 (both olanga and smee use setUint32)

def _scale_height(h: float) -> float:
    return (h + 50) / 150 * 50 - 20

def _scale_drop_point(d: float) -> float:
    return (d + 10) / 20 * 44 - 22

def _scale_frequency(f: float) -> float:
    return f / 100 + 0.5


class DrillMode(IntEnum):
    TIME = 0x00
    COMBOS = 0x01
    ENDLESS = 0x03


@dataclass
class Ball:
    speed: float       # 0–10, step 0.5
    spin: float        # -10 to 10, step 0.5 (positive = topspin, negative = backspin)
    height: float      # -50 to 100, step 1
    drop_point: float  # -10 to 10, step 0.5
    frequency: float   # 30–90 bpm, step 1
    reps: int          # 1–200

    def validate(self) -> None:
        if self.speed not in _MAX_SPIN:
            raise ValueError(
                f"speed {self.speed} is out of range or not a 0.5 step (0–10)"
            )
        if not (-10 <= self.spin <= 10):
            raise ValueError(f"spin {self.spin} is out of range (-10 to 10)")
        max_spin = _MAX_SPIN[self.speed]
        if abs(self.spin) > max_spin:
            raise ValueError(
                f"spin magnitude {abs(self.spin)} exceeds max {max_spin} for speed {self.speed}"
            )
        if not (-50 <= self.height <= 100):
            raise ValueError(f"height {self.height} is out of range (-50 to 100)")
        if not (-10 <= self.drop_point <= 10):
            raise ValueError(f"drop_point {self.drop_point} is out of range (-10 to 10)")
        if not (30 <= self.frequency <= 90):
            raise ValueError(f"frequency {self.frequency} is out of range (30–90)")
        if not (1 <= self.reps <= 200):
            raise ValueError(f"reps {self.reps} is out of range (1–200)")

    def _rpms(self) -> tuple[int, int]:
        top = round(970 + 630.5 * self.speed + 342 * self.spin)
        bot = round(970 + 630.5 * self.speed - 342 * self.spin)
        return top, bot

    def to_bytes(self) -> bytes:
        self.validate()
        top, bot = self._rpms()
        return _BALL_STRUCT.pack(
            top, bot,
            _scale_height(self.height),
            _scale_drop_point(self.drop_point),
            _scale_frequency(self.frequency),
            self.reps,
        )


@dataclass
class Drill:
    balls: list[Ball]
    mode: DrillMode = DrillMode.ENDLESS
    mode_value: int = 0     # minutes for TIME, count for COMBOS, ignored for ENDLESS
    mirror: bool = False
    random: bool = False
    level: int = 1          # 1 or 2

    _COMMAND_NEW: int = 0x81
    _COMMAND_MODIFY: int = 0x84

    def _header(self, *, modify: bool = False) -> bytes:
        if modify:
            # MODIFY_DRILL uses a 3-byte header: [0x84, n_balls*24, 0x00]
            # No level/mode/mode_value/mirror/random fields — confirmed from BLE capture.
            return bytes([self._COMMAND_MODIFY, len(self.balls) * 24, 0x00])
        packet_length = 4 + len(self.balls) * 24
        level_byte = 0x02 if self.level == 2 else 0x00
        return bytes([
            self._COMMAND_NEW,
            packet_length,
            level_byte,
            int(self.mode),
            self.mode_value,
            0x01 if self.mirror else 0x00,
            0x01 if self.random else 0x00,
        ])

    def to_bytes(self, *, modify: bool = False) -> bytes:
        if not self.balls:
            raise ValueError("Drill must have at least one ball")
        header = self._header(modify=modify)
        payloads = b"".join(ball.to_bytes() for ball in self.balls)
        return header + payloads
