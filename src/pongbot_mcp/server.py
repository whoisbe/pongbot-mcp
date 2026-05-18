"""MCP server — exposes Pongbot Nova S Pro controls as tools for Claude Desktop."""
from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from pongbot_mcp.ble import PongbotConnection
from pongbot_mcp.presets import get_preset, list_presets as _list_presets
from pongbot_mcp.protocol import Ball, Drill, DrillMode

log = logging.getLogger(__name__)

mcp = FastMCP("pongbot")

# Single connection instance shared across all tool calls.
_conn = PongbotConnection()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_mode(mode: str) -> DrillMode:
    m = mode.strip().lower()
    if m in ("time", "timed"):
        return DrillMode.TIME
    if m in ("combos", "combo"):
        return DrillMode.COMBOS
    if m in ("endless", "infinite", "loop", ""):
        return DrillMode.ENDLESS
    raise ValueError(f"Unknown mode '{mode}'. Use 'endless', 'time', or 'combos'.")


def _build_drill(
    balls: list[dict[str, Any]],
    mode: str,
    mode_value: int,
    mirror: bool,
    random: bool,
    level: int,
) -> Drill:
    ball_objects: list[Ball] = []
    for i, b in enumerate(balls):
        try:
            ball = Ball(
                speed=float(b["speed"]),
                spin=float(b["spin"]),
                height=float(b["height"]),
                drop_point=float(b["drop_point"]),
                frequency=float(b["frequency"]),
                reps=int(b["reps"]),
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Ball {i + 1}: missing or wrong-type field — {exc}") from exc
        ball.validate()   # raises ValueError with a clear message on bad ranges
        ball_objects.append(ball)

    return Drill(
        balls=ball_objects,
        mode=_parse_mode(mode),
        mode_value=mode_value,
        mirror=mirror,
        random=random,
        level=level,
    )


def _drill_summary(drill: Drill) -> str:
    lines = [
        f"Drill sent — {len(drill.balls)} ball(s) | "
        f"mode: {drill.mode.name.lower()} | "
        f"level: {drill.level} | "
        f"mirror: {'on' if drill.mirror else 'off'} | "
        f"random: {'on' if drill.random else 'off'}"
    ]
    for i, ball in enumerate(drill.balls):
        top, bot = ball._rpms()
        if ball.spin > 0:
            spin_label = f"topspin +{ball.spin}"
        elif ball.spin < 0:
            spin_label = f"backspin {ball.spin}"
        else:
            spin_label = "flat"

        if ball.drop_point > 0:
            side = f"forehand ({ball.drop_point:+})"
        elif ball.drop_point < 0:
            side = f"backhand ({ball.drop_point:+})"
        else:
            side = "middle"

        lines.append(
            f"  Ball {i + 1}: speed={ball.speed}  {spin_label}  "
            f"height={ball.height}  placement={side}  "
            f"{ball.frequency} bpm  {ball.reps} rep(s)  "
            f"[RPM top={top} bot={bot}]"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def scan_robots() -> str:
    """Scan the room for nearby Pongbot table tennis robots via Bluetooth.

    Performs a 10-second Bluetooth scan and returns every Pongbot device
    found — its display name, BLE address, and RSSI signal strength.
    RSSI closer to 0 is stronger (e.g. -50 dBm = excellent, -85 dBm = weak).

    Use this to discover the robot's address before calling connect_robot().
    The robot must be powered on and within roughly 10 metres.
    """
    devices = await PongbotConnection.scan(timeout=10.0)
    if not devices:
        return (
            "No Pongbot devices found. "
            "Make sure the robot is powered on and within Bluetooth range."
        )
    lines = [f"Found {len(devices)} Pongbot device(s):"]
    for d in devices:
        lines.append(f"  {d['name']}  |  address: {d['address']}  |  signal: {d['rssi']} dBm")
    lines.append("\nUse connect_robot(address) to connect.")
    return "\n".join(lines)


@mcp.tool()
async def connect_robot(address: str = "") -> str:
    """Connect to a Pongbot robot over Bluetooth so drills can be sent.

    If *address* is provided (e.g. "5588619A-1F02-A72D-FA7E-547386BA00F0"),
    connect directly to that robot. If *address* is omitted or blank, scan
    for 10 seconds and connect to the first Pongbot found automatically.

    The robot must be powered on before calling this. Call this before
    send_drill(), send_preset(), or stop_drill().
    """
    if _conn.connected:
        addr = _conn._client.address if _conn._client else "unknown"
        return f"Already connected to {addr}. Call disconnect_robot() first to switch robots."

    target = address.strip()
    if not target:
        devices = await PongbotConnection.scan(timeout=10.0)
        if not devices:
            return (
                "No Pongbot devices found during auto-scan. "
                "Power on the robot and try again, or provide the address directly."
            )
        target = devices[0]["address"]
        name = devices[0]["name"]
        log.info("Auto-selected %s (%s)", name, target)

    try:
        await _conn.connect(target)
    except ConnectionError as exc:
        return f"Connection failed: {exc}"

    return f"Connected to {target}. Ready to send drills."


@mcp.tool()
async def disconnect_robot() -> str:
    """Disconnect from the Pongbot robot.

    Closes the Bluetooth connection. The robot will continue playing its
    last drill until it finishes naturally or is powered off.
    Call this when you are done with a training session.
    """
    if not _conn.connected:
        return "Not currently connected to any robot."
    await _conn.disconnect()
    return "Disconnected from robot."


@mcp.tool()
async def get_status() -> str:
    """Return the current connection status and recent robot feedback.

    Shows whether a robot is connected and, if so, its BLE address, robot
    state, firmware version, drill progress, and the last few raw notification
    bytes received from the robot.
    """
    if not _conn.connected:
        return "Status: not connected."

    addr = _conn._client.address if _conn._client else "unknown"
    lines = [f"Status: connected to {addr}"]
    lines.append(f"Robot state: {_conn.robot_state.name}")

    if _conn.firmware_version:
        lines.append(f"Firmware: {_conn.firmware_version}")

    prog = _conn.drill_progress
    if prog:
        lines.append(
            f"Drill progress: {prog.total_shots} shots fired | "
            f"ball {prog.ball_index} | seq {prog.sequence} | cycle {prog.cycle}"
        )

    recent = _conn.notifications[-5:]
    if recent:
        lines.append(f"Last {len(recent)} notification(s) from robot (hex):")
        for n in recent:
            lines.append(f"  {n.hex()}")
    else:
        lines.append("No notifications received from robot yet.")
    return "\n".join(lines)


@mcp.tool()
async def send_drill(
    balls: list[dict],
    mode: str = "endless",
    mode_value: int = 0,
    mirror: bool = False,
    random: bool = False,
    level: int = 1,
) -> str:
    """Send a fully custom drill to the Pongbot robot.

    This is the main tool for a coach or player to design any ball sequence.
    Each entry in *balls* describes one shot type the robot will deliver.
    For multi-ball drills the robot cycles through them in order (or randomly).

    ── BALL FIELDS (each ball is a dict) ─────────────────────────────────────

    speed (float, 0–10, step 0.5)
        How fast the ball travels. 0 = very slow feeder pace, 5 = club-match
        pace, 10 = maximum. Note: at high speeds you cannot add much spin.

    spin (float, −10 to +10, step 0.5)
        Amount and direction of spin.
        POSITIVE → topspin: ball kicks forward after the bounce (loopy arc).
        NEGATIVE → backspin: ball kicks back / stays low after the bounce.
        ZERO → flat/no spin.
        The faster the ball, the less spin is possible — at speed 4–4.5 you
        can reach ±10; at speed 8+ the limit drops sharply; speed 10 = no spin.

    height (float, −50 to 100, step 1)
        Trajectory arc. Negative = flat, fast, driving trajectory.
        Zero = neutral mid-arc. Positive = high loopy arc (heavy topspin style
        or a lobbed backspin push). Typical range: −20 (fast drive) to 50 (lob).

    drop_point (float, −10 to +10, step 0.5)
        Where the ball lands left/right on the table, from the robot's perspective.
        NEGATIVE → robot's right = player's LEFT = backhand for a right-hander.
        POSITIVE → robot's left  = player's RIGHT = forehand for a right-hander.
        ZERO → middle of the table.
        Example: −4 = deep backhand corner, +4 = deep forehand corner.

    frequency (int, 30–90)
        Balls per minute. 30 = one ball every 2 s (beginner pace), 60 = one
        per second (intermediate), 90 = near-continuous (advanced). Start slow.

    reps (int, 1–200)
        How many times this ball fires before the sequence advances to the next
        ball. Use reps=1 for strict alternating, reps=10–30 to drill one shot
        type before moving on. In endless mode the whole sequence repeats forever.

    ── DRILL OPTIONS ─────────────────────────────────────────────────────────

    mode (str): "endless" — loop forever until stopped (default).
                "time"    — run for mode_value minutes then stop.
                "combos"  — repeat the full sequence mode_value times then stop.

    mode_value (int): Minutes for "time" mode, or repetition count for "combos".
                      Ignored for "endless".

    mirror (bool): Flip all drop_point values left↔right. Useful for left-handed
                   players, or to practise the same drill from the other wing.

    random (bool): Deliver balls in random order instead of sequentially.
                   Great for reaction training once the pattern is learned.

    level (int, 1 or 2): Level 2 applies a 1.2× RPM multiplier — slightly more
                         power for the same parameter values. Use 1 normally.

    ── EXAMPLES ──────────────────────────────────────────────────────────────
    Heavy topspin to forehand:
      {"speed": 5.5, "spin": 5.0, "height": 20, "drop_point": 4.0, "frequency": 50, "reps": 1}

    Short backspin push to backhand:
      {"speed": 3.0, "spin": -4.0, "height": 5, "drop_point": -3.0, "frequency": 45, "reps": 1}

    Fast flat crosscourt:
      {"speed": 7.0, "spin": 0.0, "height": -10, "drop_point": 4.0, "frequency": 55, "reps": 1}
    """
    if not _conn.connected:
        return "Not connected. Call connect_robot() first."

    try:
        drill = _build_drill(balls, mode, mode_value, mirror, random, level)
    except ValueError as exc:
        return f"Invalid drill parameters: {exc}"

    try:
        await _conn.send_drill(drill)
    except (IOError, RuntimeError) as exc:
        return f"Failed to send drill: {exc}"

    return _drill_summary(drill)


@mcp.tool()
async def send_preset(name: str) -> str:
    """Send a named preset drill to the robot.

    Presets are ready-made drills for common training scenarios.
    Call list_presets() to see what is available.

    Common presets:
      warmup_topspin    — gentle topspin to centre, good for loosening up
      backhand_push     — short backspin to the backhand, trains the push stroke
      forehand_loop     — moderate topspin to the forehand corner
      alternating_bh_fh — two-ball footwork: backhand then forehand
      progressive_speed — five balls that increase speed from 2 → 6
      random_placement  — three zones in random order, trains reading direction

    All presets run in endless mode — call stop_drill() to stop.
    The robot must be connected before calling this.
    """
    if not _conn.connected:
        return "Not connected. Call connect_robot() first."

    try:
        drill = get_preset(name.strip().lower())
    except KeyError as exc:
        available = ", ".join(p["name"] for p in _list_presets())
        return f"Unknown preset '{name}'. Available: {available}"

    try:
        await _conn.send_drill(drill)
    except (IOError, RuntimeError) as exc:
        return f"Failed to send preset: {exc}"

    # Find description from registry for the confirmation message
    meta_desc = next(
        (p["description"] for p in _list_presets() if p["name"] == name.strip().lower()),
        "",
    )
    return f"Sent preset '{name}'.\n{meta_desc}\n\n{_drill_summary(drill)}"


@mcp.tool()
async def list_presets() -> str:
    """List all available named preset drills with their descriptions.

    Returns the name and a plain-English description of each preset.
    Use send_preset(name) to start one on the connected robot.
    """
    presets = _list_presets()
    lines = [f"{len(presets)} preset(s) available:\n"]
    for p in presets:
        lines.append(f"  {p['name']}")
        lines.append(f"    {p['description']}")
    return "\n".join(lines)


@mcp.tool()
async def stop_drill() -> str:
    """Stop the drill currently running on the robot.

    Halts ball delivery immediately using a three-level fallback strategy:

    1. Sends the BLE stop command (80 01 00 01) on the existing connection.
       → Returns "stopped via command" if this succeeds.

    2. If the connection has silently dropped, reconnects (full auth handshake)
       and retries the stop command.
       → Returns "stopped via command (after reconnect)" if this succeeds.

    3. Last resort: disconnects from the robot entirely. The robot stops
       firing as soon as it loses its BLE connection.
       → Returns "stopped by disconnecting" if this succeeds.

    If all three fail, returns "failed to stop — power cycle the robot".

    After a "stopped by disconnecting" result you will need to call
    connect_robot() again before sending a new drill.
    """
    status = await _conn.stop_drill()
    return f"Stop result: {status}."
