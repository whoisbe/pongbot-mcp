# pongbot-mcp

An [MCP](https://modelcontextprotocol.io) server that lets Claude control a **Pongbot Nova S Pro** table tennis robot over Bluetooth LE. Instead of tapping through the robot's official app to build a drill, you describe what you want to practise — "moderate topspin to my forehand, then alternate to my backhand every three balls" — and Claude translates it into the robot's wire protocol and sends it. The robot does not know the difference.

> **Status:** Working, actively developed. Known issue: the connection drops after ~13 minutes of idle time despite an implemented keepalive (see [Known issues](#known-issues)).

## What works, what doesn't

Honest accounting, because this is a live project and not a finished product.

**Works:**
- The full authenticated connection handshake (the robot disconnects if you skip it).
- Sending custom drills — speed, spin, height, placement, frequency, reps, mirroring, randomised order.
- Modifying a drill while it is running.
- Named presets (warm-ups, push drills, footwork patterns).
- Live telemetry — connection state, robot status notifications, drill progress.
- The actual point of the thing: running drills by talking to Claude instead of poking at an app between points.

**Doesn't, yet:**
- **The connection drops after roughly 13 minutes of idle time.** There is a keepalive (`83 06 00` every 10 seconds, ACKed by the robot), and it is demonstrably being sent and acknowledged — and the robot still hangs up after ~13 minutes of no drilling. The keepalive is necessary but not sufficient; something else times out. This is the current open problem and I have not solved it. If you pick up a drill within the window it is a non-issue; if you wander off to get water, you reconnect. Auto-reconnect on the next command papers over it but does not fix it.

## Credits

This project would not exist without two people who did the hard part first and published it. The Pongbot speaks an undocumented BLE protocol; figuring out the byte layouts, the RPM formulas, the parameter scaling, and — the genuinely nasty bit — the MD5 authentication handshake that the robot demands before it will accept a single command, was their work, not mine.

- **olanga** — [olanga/nova](https://github.com/olanga/nova) ([web client](https://olanga.github.io/nova/)). The drill packet format and the auth constants come from here.
- **smee** — [smee/nova-s-custom-drills](https://github.com/smee/nova-s-custom-drills) ([web client](https://smee.github.io/nova-s-custom-drills/)). The control commands and the post-wakeup state machine come from here.

What I added is a Python reimplementation, an MCP server around it, and a Claude-shaped natural-language layer on top. The protocol underneath is theirs. If you want to understand how the robot actually works, read their repos — they are the primary sources. Thank you both.

## Requirements

- macOS with Bluetooth (tested on macOS 14+; the BLE stack is `bleak`, which is cross-platform, but I have only run it on a Mac)
- [uv](https://docs.astral.sh/uv/) — Python package manager (Python 3.11+)
- [Claude Desktop](https://claude.ai/download)
- A Pongbot Nova S Pro, powered on and within Bluetooth range (~10 m)

## Install

```bash
git clone https://github.com/whoisbe/pongbot-mcp
cd pongbot-mcp
uv sync
```

`uv sync` creates the virtual environment and installs `bleak` and the MCP SDK.

## Connect it to Claude Desktop

Add this to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS), replacing the path with the actual location of this repo:

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

Restart Claude Desktop. The server starts on demand; there is nothing to run by hand.

## Use it

Talk to Claude. A few openers:

```
Connect to my Pongbot and warm me up with some easy balls.
```
```
Give me a forehand loop drill: moderate topspin to my forehand at a comfortable pace.
```
```
Build a 5-ball random-order drill across all three zones — backhand corner, middle,
forehand corner — at speed 5 with light topspin. Shuffle the order.
```
```
Mirror the current drill to my backhand side.
```
```
Stop the drill.
```

Claude works out the parameters from your description, sends the drill, and can adjust it mid-session.

### MCP tools

| Tool | What it does |
|------|-------------|
| `scan_robots()` | Scan for nearby Pongbot devices |
| `connect_robot(address?)` | Connect by address, or auto-connect to the first one found |
| `disconnect_robot()` | Close the BLE connection |
| `get_status()` | Connection state and recent robot notifications |
| `send_drill(...)` | Send a fully custom drill |
| `send_preset(name)` | Send a named preset |
| `list_presets()` | List available presets |
| `stop_drill()` | Stop the running drill |

Presets include `warmup_topspin`, `backhand_push`, `forehand_loop`, `alternating_bh_fh`, `progressive_speed`, and `random_placement`. Ask Claude to `list_presets` for the current set.

## Technical overview

Three layers, bottom to top:

```
Claude Desktop
     │  MCP (stdio)
     ▼
server.py     ← MCP tools, natural-language-friendly descriptions
presets.py    ← named drill definitions
protocol.py   ← Ball / Drill dataclasses, byte packing (fully unit-tested, no hardware needed)
ble.py        ← BleakClient connection, auth handshake, GATT writes, notifications, keepalive
     │  Bluetooth LE
     ▼
Pongbot Nova S Pro
```

The **protocol layer** packs drills into the robot's binary format and is covered by unit tests that run without a robot (`uv run pytest`). The **BLE layer** handles the connection lifecycle: the authentication handshake the robot requires, GATT characteristic writes, notification subscriptions for telemetry, and the keepalive. The **server layer** exposes the MCP tools that Claude calls.

I have not reproduced the protocol specification here on purpose — that would be re-deriving olanga's and smee's work badly. Their repos are the reference. This repo is the implementation.

## Known issues

- **Idle disconnect (~13 min).** Described above. Open. The keepalive is sent and ACKed; the robot disconnects anyway. Reproduce it with `uv run scripts/keepalive_test.py --duration 900`.

## Development

```bash
uv run pytest          # protocol/preset tests, no hardware
uv run scripts/discover.py   # scan and dump the GATT tree of a nearby robot
```

BLE behaviour can only be tested against a real robot, so those tests are manual.

## Contributing

This is a personal project I work on for fun, between actual table tennis. I may or may not get to issues and PRs promptly — treat it as a "no promises" repo rather than a maintained product. That said, if you have a fix for the idle-disconnect problem I would genuinely like to hear it. Fork freely.

## More

This repo accompanies an essay on my newsletter ([bharathk.dev](https://bharathk.dev)): [Read the essay](https://whoisb.substack.com/p/SLUG-TBD).

## License

MIT — see [LICENSE](LICENSE).
