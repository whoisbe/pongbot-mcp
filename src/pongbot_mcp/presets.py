"""Named preset drills for common table tennis training scenarios."""
from __future__ import annotations

from dataclasses import dataclass

from pongbot_mcp.protocol import Ball, Drill, DrillMode


@dataclass(frozen=True)
class PresetMeta:
    name: str
    description: str


def _b(
    speed: float,
    spin: float,
    height: float,
    drop_point: float,
    frequency: float,
    reps: int,
) -> Ball:
    ball = Ball(
        speed=speed,
        spin=spin,
        height=height,
        drop_point=drop_point,
        frequency=frequency,
        reps=reps,
    )
    ball.validate()
    return ball


# ---------------------------------------------------------------------------
# Preset registry
# ---------------------------------------------------------------------------
# Each entry: PresetMeta → callable that returns a fresh Drill instance.
# Callables are used (rather than module-level Drill objects) so each
# get_preset() call returns an independent, mutable object.

_REGISTRY: dict[str, tuple[PresetMeta, "DrillFactory"]] = {}
DrillFactory = type(lambda: None)  # just a type alias hint; real type below


def _register(meta: PresetMeta):
    """Decorator that registers a zero-arg factory under meta.name."""
    def decorator(fn: DrillFactory) -> DrillFactory:  # type: ignore[valid-type]
        _REGISTRY[meta.name] = (meta, fn)
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Preset definitions
# ---------------------------------------------------------------------------

@_register(PresetMeta(
    name="warmup_topspin",
    description=(
        "Gentle topspin balls to the centre of the table. "
        "Good for warming up forearms and finding your rhythm before harder drills."
    ),
))
def _warmup_topspin() -> Drill:
    return Drill(
        balls=[_b(speed=3.0, spin=3.0, height=15.0, drop_point=0.0, frequency=60, reps=50)],
        mode=DrillMode.ENDLESS,
    )


@_register(PresetMeta(
    name="backhand_push",
    description=(
        "Short backspin balls to the backhand side. "
        "Trains the push stroke — keep the ball low and return tight to the net."
    ),
))
def _backhand_push() -> Drill:
    return Drill(
        balls=[_b(speed=2.0, spin=-4.0, height=5.0, drop_point=-4.0, frequency=45, reps=30)],
        mode=DrillMode.ENDLESS,
    )


@_register(PresetMeta(
    name="forehand_loop",
    description=(
        "Moderate topspin to the forehand corner. "
        "Classic loop-training ball — focus on brushing the top of the ball."
    ),
))
def _forehand_loop() -> Drill:
    return Drill(
        balls=[_b(speed=5.0, spin=5.0, height=20.0, drop_point=4.0, frequency=50, reps=40)],
        mode=DrillMode.ENDLESS,
    )


@_register(PresetMeta(
    name="alternating_bh_fh",
    description=(
        "Two-ball footwork drill: one ball to the backhand, one to the forehand. "
        "Trains lateral movement and switching between wings."
    ),
))
def _alternating_bh_fh() -> Drill:
    return Drill(
        balls=[
            _b(speed=4.0, spin=0.0, height=10.0, drop_point=-4.0, frequency=55, reps=1),
            _b(speed=4.0, spin=0.0, height=10.0, drop_point=4.0,  frequency=55, reps=1),
        ],
        mode=DrillMode.ENDLESS,
    )


@_register(PresetMeta(
    name="progressive_speed",
    description=(
        "Five-ball sequence that ramps speed from slow (2) to medium-fast (6). "
        "Each ball is identical in placement but faster — trains timing adaptation."
    ),
))
def _progressive_speed() -> Drill:
    return Drill(
        balls=[
            _b(speed=2.0, spin=0.0, height=10.0, drop_point=0.0, frequency=52, reps=5),
            _b(speed=3.0, spin=0.0, height=10.0, drop_point=0.0, frequency=52, reps=5),
            _b(speed=4.0, spin=0.0, height=10.0, drop_point=0.0, frequency=52, reps=5),
            _b(speed=5.0, spin=0.0, height=10.0, drop_point=0.0, frequency=52, reps=5),
            _b(speed=6.0, spin=0.0, height=10.0, drop_point=0.0, frequency=52, reps=5),
        ],
        mode=DrillMode.ENDLESS,
    )


@_register(PresetMeta(
    name="random_placement",
    description=(
        "Three placement zones — backhand, middle, forehand — delivered in random order. "
        "Trains reading and reacting to ball direction without anticipating the pattern."
    ),
))
def _random_placement() -> Drill:
    return Drill(
        balls=[
            _b(speed=4.0, spin=1.0, height=12.0, drop_point=-4.0, frequency=50, reps=1),
            _b(speed=4.0, spin=1.0, height=12.0, drop_point=0.0,  frequency=50, reps=1),
            _b(speed=4.0, spin=1.0, height=12.0, drop_point=4.0,  frequency=50, reps=1),
        ],
        mode=DrillMode.ENDLESS,
        random=True,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_presets() -> list[dict[str, str]]:
    """Return a list of {name, description} dicts for all registered presets."""
    return [
        {"name": meta.name, "description": meta.description}
        for meta, _ in _REGISTRY.values()
    ]


def get_preset(name: str) -> Drill:
    """Return a freshly constructed Drill for the named preset.

    Raises KeyError if the name is not found.
    """
    entry = _REGISTRY.get(name)
    if entry is None:
        available = ", ".join(_REGISTRY.keys())
        raise KeyError(f"Unknown preset '{name}'. Available: {available}")
    _, factory = entry
    return factory()
