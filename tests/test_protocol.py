from __future__ import annotations

import struct

import pytest

from pongbot_mcp.protocol import (
    Ball, Drill, DrillMode, _MAX_SPIN,
    _scale_height, _scale_drop_point, _scale_frequency,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BALL_STRUCT = struct.Struct("<IIfffI")


def unpack_ball(data: bytes) -> tuple:
    """Return (top_rpm, bot_rpm, height_scaled, drop_point_scaled, freq_scaled, reps_u32)."""
    assert len(data) == 24
    return BALL_STRUCT.unpack(data)


def make_ball(**kwargs) -> Ball:
    defaults = dict(speed=3.0, spin=0.0, height=0.0, drop_point=0.0, frequency=60.0, reps=10)
    defaults.update(kwargs)
    return Ball(**defaults)


# ---------------------------------------------------------------------------
# RPM calculation
# ---------------------------------------------------------------------------

class TestRpmCalculation:
    def test_zero_spin_symmetric(self):
        ball = make_ball(speed=5.0, spin=0.0)
        top, bot = ball._rpms()
        assert top == bot

    def test_zero_speed_zero_spin(self):
        ball = make_ball(speed=0.0, spin=0.0)
        top, bot = ball._rpms()
        assert top == 970
        assert bot == 970

    def test_topspin_positive_spin(self):
        ball = make_ball(speed=3.0, spin=4.0)
        top, bot = ball._rpms()
        assert top > bot, "topspin: top_rpm should exceed bottom_rpm"

    def test_backspin_negative_spin(self):
        ball = make_ball(speed=3.0, spin=-4.0)
        top, bot = ball._rpms()
        assert bot > top, "backspin: bottom_rpm should exceed top_rpm"

    def test_rpm_formula_explicit(self):
        # speed=2.0, spin=3.0
        # top = 970 + 630.5*2 + 342*3 = 970 + 1261 + 1026 = 3257
        # bot = 970 + 1261 - 1026 = 1205
        ball = make_ball(speed=2.0, spin=3.0)
        top, bot = ball._rpms()
        assert top == 3257
        assert bot == 1205

    def test_rpm_symmetry_opposite_spin(self):
        ball_pos = make_ball(speed=4.0, spin=5.0)
        ball_neg = make_ball(speed=4.0, spin=-5.0)
        top_p, bot_p = ball_pos._rpms()
        top_n, bot_n = ball_neg._rpms()
        assert top_p == bot_n
        assert bot_p == top_n

    def test_max_speed_zero_spin(self):
        ball = make_ball(speed=10.0, spin=0.0)
        top, bot = ball._rpms()
        expected = round(970 + 630.5 * 10)
        assert top == expected
        assert bot == expected


# ---------------------------------------------------------------------------
# Ball byte packing
# ---------------------------------------------------------------------------

class TestBallBytes:
    def test_length_is_24(self):
        assert len(make_ball().to_bytes()) == 24

    def test_round_trip_fields_are_scaled(self):
        # Verify the packet contains scaled values, not raw user values.
        ball = make_ball(speed=3.0, spin=2.0, height=10.0, drop_point=1.5, frequency=45.0, reps=20)
        data = ball.to_bytes()
        top, bot, height_p, drop_p, freq_p, reps_p = unpack_ball(data)
        assert height_p == pytest.approx(_scale_height(10.0))
        assert drop_p   == pytest.approx(_scale_drop_point(1.5))
        assert freq_p   == pytest.approx(_scale_frequency(45.0))
        assert reps_p   == 20

    def test_rpm_values_in_bytes(self):
        ball = make_ball(speed=2.0, spin=3.0)
        top, bot, *_ = unpack_ball(ball.to_bytes())
        assert top == 3257
        assert bot == 1205

    def test_little_endian_u32(self):
        ball = make_ball(speed=0.0, spin=0.0)
        data = ball.to_bytes()
        # first 4 bytes = top_rpm = 970 = 0x000003CA, little-endian: CA 03 00 00
        assert data[0] == 0xCA
        assert data[1] == 0x03
        assert data[2] == 0x00
        assert data[3] == 0x00

    def test_height_min_scales_to_minus20(self):
        # height=-50 (min) → (0)/150*50 - 20 = -20.0
        ball = make_ball(height=-50.0)
        _, _, height_p, *_ = unpack_ball(ball.to_bytes())
        assert height_p == pytest.approx(-20.0)

    def test_height_max_scales_to_30(self):
        # height=100 (max) → (150)/150*50 - 20 = 30.0
        ball = make_ball(height=100.0)
        _, _, height_p, *_ = unpack_ball(ball.to_bytes())
        assert height_p == pytest.approx(30.0)

    def test_drop_point_centre_scales_to_zero(self):
        ball = make_ball(drop_point=0.0)
        _, _, _, drop_p, *_ = unpack_ball(ball.to_bytes())
        assert drop_p == pytest.approx(0.0)

    def test_frequency_scales_correctly(self):
        # freq=60 → 60/100 + 0.5 = 1.1
        ball = make_ball(frequency=60.0)
        _, _, _, _, freq_p, _ = unpack_ball(ball.to_bytes())
        assert freq_p == pytest.approx(1.1)


# ---------------------------------------------------------------------------
# Ball validation
# ---------------------------------------------------------------------------

class TestBallValidation:
    def test_speed_out_of_range(self):
        with pytest.raises(ValueError, match="speed"):
            make_ball(speed=11.0).validate()

    def test_speed_bad_step(self):
        with pytest.raises(ValueError, match="speed"):
            make_ball(speed=1.3).validate()

    def test_spin_exceeds_max_for_speed(self):
        # speed=0.0 → max_spin=2
        with pytest.raises(ValueError, match="spin magnitude"):
            make_ball(speed=0.0, spin=3.0).validate()

    def test_spin_at_max_ok(self):
        make_ball(speed=0.0, spin=2.0).validate()  # should not raise

    def test_max_speed_any_spin_rejected(self):
        # speed=10 → max_spin=0
        with pytest.raises(ValueError, match="spin magnitude"):
            make_ball(speed=10.0, spin=0.5).validate()

    def test_negative_spin_dependency(self):
        with pytest.raises(ValueError, match="spin magnitude"):
            make_ball(speed=0.0, spin=-3.0).validate()

    def test_height_out_of_range_low(self):
        with pytest.raises(ValueError, match="height"):
            make_ball(height=-51.0).validate()

    def test_frequency_out_of_range(self):
        with pytest.raises(ValueError, match="frequency"):
            make_ball(frequency=91.0).validate()

    def test_reps_zero_rejected(self):
        with pytest.raises(ValueError, match="reps"):
            make_ball(reps=0).validate()

    def test_reps_over_200_rejected(self):
        with pytest.raises(ValueError, match="reps"):
            make_ball(reps=201).validate()


# ---------------------------------------------------------------------------
# Drill header encoding
# ---------------------------------------------------------------------------

class TestDrillHeader:
    def _parse_header(self, data: bytes) -> dict:
        return {
            "command": data[0],
            "packet_length": data[1],
            "level": data[2],
            "mode": data[3],
            "mode_value": data[4],
            "mirror": data[5],
            "random": data[6],
        }

    def test_new_drill_command_byte(self):
        drill = Drill(balls=[make_ball()])
        h = self._parse_header(drill.to_bytes())
        assert h["command"] == 0x81

    def test_modify_drill_command_byte(self):
        drill = Drill(balls=[make_ball()])
        h = self._parse_header(drill.to_bytes(modify=True))
        assert h["command"] == 0x84

    def test_packet_length_one_ball(self):
        drill = Drill(balls=[make_ball()])
        h = self._parse_header(drill.to_bytes())
        assert h["packet_length"] == 4 + 1 * 24  # 28

    def test_packet_length_three_balls(self):
        drill = Drill(balls=[make_ball(), make_ball(), make_ball()])
        h = self._parse_header(drill.to_bytes())
        assert h["packet_length"] == 4 + 3 * 24  # 76

    def test_total_bytes_length(self):
        balls = [make_ball(), make_ball()]
        drill = Drill(balls=balls)
        assert len(drill.to_bytes()) == 7 + 2 * 24

    def test_mode_time(self):
        drill = Drill(balls=[make_ball()], mode=DrillMode.TIME, mode_value=5)
        h = self._parse_header(drill.to_bytes())
        assert h["mode"] == 0x00
        assert h["mode_value"] == 5

    def test_mode_combos(self):
        drill = Drill(balls=[make_ball()], mode=DrillMode.COMBOS, mode_value=3)
        h = self._parse_header(drill.to_bytes())
        assert h["mode"] == 0x01

    def test_mode_endless(self):
        drill = Drill(balls=[make_ball()], mode=DrillMode.ENDLESS)
        h = self._parse_header(drill.to_bytes())
        assert h["mode"] == 0x03

    def test_level_1_byte(self):
        drill = Drill(balls=[make_ball()], level=1)
        h = self._parse_header(drill.to_bytes())
        assert h["level"] == 0x00

    def test_level_2_byte(self):
        drill = Drill(balls=[make_ball()], level=2)
        h = self._parse_header(drill.to_bytes())
        assert h["level"] == 0x02

    def test_mirror_flag(self):
        drill = Drill(balls=[make_ball()], mirror=True)
        h = self._parse_header(drill.to_bytes())
        assert h["mirror"] == 0x01

    def test_random_flag(self):
        drill = Drill(balls=[make_ball()], random=True)
        h = self._parse_header(drill.to_bytes())
        assert h["random"] == 0x01

    def test_no_mirror_no_random(self):
        drill = Drill(balls=[make_ball()], mirror=False, random=False)
        h = self._parse_header(drill.to_bytes())
        assert h["mirror"] == 0x00
        assert h["random"] == 0x00

    def test_empty_balls_raises(self):
        drill = Drill(balls=[])
        with pytest.raises(ValueError, match="at least one ball"):
            drill.to_bytes()


# ---------------------------------------------------------------------------
# MODIFY_DRILL header (3-byte format confirmed from BLE capture)
# ---------------------------------------------------------------------------

class TestModifyDrillHeader:
    def test_command_byte(self):
        drill = Drill(balls=[make_ball()])
        assert drill.to_bytes(modify=True)[0] == 0x84

    def test_header_is_3_bytes(self):
        drill = Drill(balls=[make_ball()])
        # Ball payload starts at byte 3 — header must be exactly 3 bytes
        data = drill.to_bytes(modify=True)
        assert len(data) == 3 + 1 * 24

    def test_pktlen_no_plus4_offset_one_ball(self):
        # pktlen = n_balls * 24, NOT 4 + n_balls * 24
        drill = Drill(balls=[make_ball()])
        assert drill.to_bytes(modify=True)[1] == 1 * 24  # 24

    def test_pktlen_no_plus4_offset_two_balls(self):
        drill = Drill(balls=[make_ball(), make_ball()])
        assert drill.to_bytes(modify=True)[1] == 2 * 24  # 48

    def test_total_length_two_balls(self):
        drill = Drill(balls=[make_ball(), make_ball()])
        assert len(drill.to_bytes(modify=True)) == 3 + 2 * 24  # 51

    def test_reserved_byte_is_zero_regardless_of_level_and_mode(self):
        drill = Drill(balls=[make_ball()], level=2, mode=DrillMode.TIME, mode_value=5)
        assert drill.to_bytes(modify=True)[2] == 0x00

    def test_new_drill_header_still_7_bytes(self):
        drill = Drill(balls=[make_ball()])
        assert len(drill.to_bytes(modify=False)) == 7 + 1 * 24


# ---------------------------------------------------------------------------
# Speed/spin dependency table completeness
# ---------------------------------------------------------------------------

class TestSpinDependencyTable:
    def test_all_half_step_speeds_present(self):
        expected = {round(i * 0.5, 1) for i in range(21)}
        assert set(_MAX_SPIN.keys()) == expected

    def test_boundary_spin_values_valid(self):
        for speed, max_spin in _MAX_SPIN.items():
            ball = make_ball(speed=speed, spin=max_spin)
            ball.validate()  # should not raise
