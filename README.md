# pongbot-mcp

Control a **Pongbot Nova S Pro** table tennis robot using natural language via Claude Desktop.

This is an [MCP](https://modelcontextprotocol.io) server that bridges Claude Desktop to the robot over Bluetooth LE. Tell Claude what kind of drill you want — it figures out the parameters and sends them directly to the robot.

---

## Requirements

- macOS with Bluetooth (tested on macOS 14+)
- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Claude Desktop](https://claude.ai/download)
- Pongbot Nova S Pro (powered on, within ~10 m)

---

## Installation

```bash
git clone https://github.com/yourname/pongbot-mcp
cd pongbot-mcp
uv sync
```

That's it. `uv sync` creates a virtual environment and installs all dependencies.

---

## Claude Desktop configuration

Add the following to your Claude Desktop config file.

**Config file location:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "pongbot": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "/Users/yourname/projects/pongbot-mcp",
        "python",
        "-m",
        "pongbot_mcp"
      ]
    }
  }
}
```

Replace `/Users/yourname/projects/pongbot-mcp` with the actual path to this repo. Restart Claude Desktop after saving.

---

## Usage

Once configured, open Claude Desktop and start talking. The MCP server starts automatically in the background.

### Getting connected

```
Connect to my Pongbot.
```
```
Scan for nearby robots, then connect to the first one you find.
```
```
Connect to 5588619A-1F02-A72D-FA7E-547386BA00F0.
```

### Warm-up drills

```
Connect to my Pongbot and warm me up with some easy balls.
```
```
Send a gentle warmup — flat balls to the middle, nothing too fast.
```
```
Start the warmup_topspin preset.
```

### Custom drills

```
Give me a forehand loop drill: moderate topspin to my forehand at a comfortable pace.
```
```
Create a drill that alternates heavy topspin to my forehand with light backspin
pushes to my backhand, increasing speed every 3 balls.
```
```
I want to practise my backhand push. Short backspin balls to my backhand side,
slow frequency, 30 reps.
```
```
Set up a footwork drill: alternate between wide backhand and wide forehand,
flat balls, medium speed.
```

### Advanced drills

```
Build a 5-ball random-order drill covering all three zones — backhand corner,
middle, and forehand corner — at speed 5 with light topspin. Shuffle them
so I can't predict where the next ball is going.
```
```
Send a topspin drill to my forehand at speed 6, spin 5, 55 bpm. Then after
I've warmed up, increase speed to 7.
```
```
Mirror the current forehand drill to my backhand side.
```

### Stopping

```
Stop the drill.
```
```
Disconnect from the robot.
```

---

## Available tools

| Tool | What it does |
|------|-------------|
| `scan_robots()` | Scan for nearby Pongbot devices (10 s scan) |
| `connect_robot(address?)` | Connect by address, or auto-connect to first found |
| `disconnect_robot()` | Close the BLE connection |
| `get_status()` | Show connection state and recent robot notifications |
| `send_drill(balls, ...)` | Send a fully custom drill — see parameter details below |
| `send_preset(name)` | Send a named preset drill |
| `list_presets()` | List all available presets with descriptions |
| `stop_drill()` | Stop the running drill |

### `send_drill` parameters

| Parameter | Type | Range | Description |
|-----------|------|-------|-------------|
| `speed` | float | 0–10 (step 0.5) | Ball speed. 5 = club-match pace. |
| `spin` | float | −10 to +10 (step 0.5) | Positive = topspin, negative = backspin, 0 = flat. Max spin depends on speed. |
| `height` | float | −50 to 100 (step 1) | Arc height. Negative = flat drive, positive = loopy topspin or lob. |
| `drop_point` | float | −10 to +10 (step 0.5) | Left/right placement. **Negative = player's left (backhand), positive = player's right (forehand).** |
| `frequency` | int | 30–90 bpm | Balls per minute. 60 = one per second. |
| `reps` | int | 1–200 | Repetitions before cycling to next ball. |
| `mode` | str | endless/time/combos | Loop forever, run for N minutes, or repeat N times. |
| `mirror` | bool | — | Flip all left/right placement — useful for left-handers. |
| `random` | bool | — | Randomise ball order for reaction training. |
| `level` | int | 1 or 2 | Level 2 = 1.2× RPM multiplier for extra power. |

---

## Discovery script

If you're not sure of your robot's BLE address, run:

```bash
uv run scripts/discover.py
```

This scans for 10 seconds, lists all Pongbot devices found, and if one is found, connects and prints the full GATT service/characteristic tree.

---

## Running tests

```bash
uv run pytest
```

Protocol encoding tests run without any hardware. BLE tests are manual only.

---

## Architecture

```
Claude Desktop
     │  MCP (stdio)
     ▼
server.py       ← MCP tools, natural-language descriptions
     │
presets.py      ← named drill definitions
     │
protocol.py     ← Ball / Drill dataclasses, byte packing
     │
ble.py          ← BleakClient connection, GATT writes, notifications
     │  Bluetooth LE
     ▼
Pongbot Nova S Pro
```

**Known limitation:** The stop command is not yet reverse-engineered from the official app. `stop_drill()` currently works by disconnecting and reconnecting, which halts the robot. See `CLAUDE.md` for details.

---

## Credits

BLE protocol reverse-engineered by [olanga/smee](https://github.com/olanga).
