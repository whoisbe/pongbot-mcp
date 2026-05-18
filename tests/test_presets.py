from __future__ import annotations

import pytest

from pongbot_mcp.presets import get_preset, list_presets
from pongbot_mcp.protocol import Drill, DrillMode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_PRESET_NAMES = [
    "warmup_topspin",
    "backhand_push",
    "forehand_loop",
    "alternating_bh_fh",
    "progressive_speed",
    "random_placement",
]


# ---------------------------------------------------------------------------
# Registry / API
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_list_presets_returns_all(self):
        names = {p["name"] for p in list_presets()}
        assert set(ALL_PRESET_NAMES) == names

    def test_list_presets_have_descriptions(self):
        for preset in list_presets():
            assert preset["description"], f"Preset '{preset['name']}' has empty description"

    def test_get_preset_unknown_raises_key_error(self):
        with pytest.raises(KeyError, match="unknown_preset"):
            get_preset("unknown_preset")

    def test_get_preset_returns_drill(self):
        for name in ALL_PRESET_NAMES:
            assert isinstance(get_preset(name), Drill)

    def test_get_preset_returns_independent_instances(self):
        a = get_preset("warmup_topspin")
        b = get_preset("warmup_topspin")
        assert a is not b


# ---------------------------------------------------------------------------
# All presets: structural validity
# ---------------------------------------------------------------------------

class TestAllPresetsValid:
    @pytest.mark.parametrize("name", ALL_PRESET_NAMES)
    def test_has_at_least_one_ball(self, name: str):
        drill = get_preset(name)
        assert len(drill.balls) >= 1

    @pytest.mark.parametrize("name", ALL_PRESET_NAMES)
    def test_all_balls_pass_validate(self, name: str):
        drill = get_preset(name)
        for i, ball in enumerate(drill.balls):
            try:
                ball.validate()
            except ValueError as exc:
                pytest.fail(f"Preset '{name}' ball {i} failed validation: {exc}")

    @pytest.mark.parametrize("name", ALL_PRESET_NAMES)
    def test_to_bytes_succeeds(self, name: str):
        """Full encoding pipeline must not raise."""
        data = get_preset(name).to_bytes()
        expected_len = 7 + len(get_preset(name).balls) * 24
        assert len(data) == expected_len


# ---------------------------------------------------------------------------
# Per-preset content checks
# ---------------------------------------------------------------------------

class TestWarmupTopspin:
    def test_single_ball(self):
        assert len(get_preset("warmup_topspin").balls) == 1

    def test_speed_and_spin(self):
        ball = get_preset("warmup_topspin").balls[0]
        assert ball.speed == 3.0
        assert ball.spin == 3.0

    def test_centre_placement(self):
        ball = get_preset("warmup_topspin").balls[0]
        assert ball.drop_point == 0.0

    def test_topspin_direction(self):
        ball = get_preset("warmup_topspin").balls[0]
        top, bot = ball._rpms()
        assert top > bot


class TestBackhandPush:
    def test_backspin(self):
        ball = get_preset("backhand_push").balls[0]
        assert ball.spin < 0

    def test_backhand_placement(self):
        ball = get_preset("backhand_push").balls[0]
        assert ball.drop_point < 0

    def test_backspin_direction(self):
        ball = get_preset("backhand_push").balls[0]
        top, bot = ball._rpms()
        assert bot > top


class TestForehandLoop:
    def test_forehand_placement(self):
        ball = get_preset("forehand_loop").balls[0]
        assert ball.drop_point > 0

    def test_topspin(self):
        ball = get_preset("forehand_loop").balls[0]
        assert ball.spin > 0


class TestAlternatingBhFh:
    def test_two_balls(self):
        assert len(get_preset("alternating_bh_fh").balls) == 2

    def test_backhand_then_forehand(self):
        balls = get_preset("alternating_bh_fh").balls
        assert balls[0].drop_point < 0, "first ball should be backhand (negative drop_point)"
        assert balls[1].drop_point > 0, "second ball should be forehand (positive drop_point)"

    def test_one_rep_each(self):
        for ball in get_preset("alternating_bh_fh").balls:
            assert ball.reps == 1

    def test_same_frequency(self):
        balls = get_preset("alternating_bh_fh").balls
        assert balls[0].frequency == balls[1].frequency


class TestProgressiveSpeed:
    def test_five_balls(self):
        assert len(get_preset("progressive_speed").balls) == 5

    def test_speeds_strictly_increasing(self):
        speeds = [b.speed for b in get_preset("progressive_speed").balls]
        assert speeds == sorted(speeds) and len(set(speeds)) == len(speeds)

    def test_speed_range(self):
        speeds = [b.speed for b in get_preset("progressive_speed").balls]
        assert speeds[0] == 2.0
        assert speeds[-1] == 6.0

    def test_consistent_placement(self):
        drop_points = [b.drop_point for b in get_preset("progressive_speed").balls]
        assert len(set(drop_points)) == 1, "all balls should land in the same spot"


class TestRandomPlacement:
    def test_three_balls(self):
        assert len(get_preset("random_placement").balls) == 3

    def test_random_flag_set(self):
        assert get_preset("random_placement").random is True

    def test_three_distinct_drop_points(self):
        drop_points = [b.drop_point for b in get_preset("random_placement").balls]
        assert len(set(drop_points)) == 3, "each ball should have a different drop point"

    def test_covers_backhand_middle_forehand(self):
        drop_points = sorted(b.drop_point for b in get_preset("random_placement").balls)
        assert drop_points[0] < 0, "should have a backhand ball"
        assert drop_points[1] == 0.0, "should have a middle ball"
        assert drop_points[2] > 0, "should have a forehand ball"
