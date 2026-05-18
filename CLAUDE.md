Project: MCP server for controlling a Pongbot Nova S Pro table tennis robot over BLE.
Architecture: Three layers — protocol (byte packing), ble (bleak connection), server (MCP tools). No UI — Claude Desktop is the interface.
BLE Protocol (from reverse engineering by olanga/smee + BLE capture analysis):

Communication is via BLE GATT writes to the robot
NEW_DRILL packet = 7-byte header + N × 24-byte ball payloads
Header: [command(1), packet_length(1), level(1), mode(1), mode_value(1), mirror(1), random(1)]

command: 0x81 = new drill, 0x84 = modify running drill
packet_length: 4 + (ball_count × 24)  — NOTE: only for 0x81 NEW_DRILL
level: 0x00 = level 1, 0x02 = level 2 (1.2x RPM multiplier)
mode: 0x00 = timed (minutes), 0x01 = combo count, 0x03 = endless
mirror: 0x00 = normal, 0x01 = mirrored (left/right hand)
random: 0x00 = sequential, 0x01 = random

MODIFY_DRILL packet (0x84) uses a 3-byte header — confirmed from BLE capture:
  [0x84, n_balls * 24, 0x00]   (no level/mode/mode_value/mirror/random fields)
  packet_length = n_balls × 24 (NOT 4 + n_balls × 24)
  Total packet size = 3 + n_balls × 24 bytes

Ball payload (24 bytes): [top_motor_rpm(u32), bottom_motor_rpm(u32), height(f32), drop_point(f32), frequency(f32), reps(u32)]
All values are little-endian.
IMPORTANT: height, drop_point, and frequency are NOT raw user values — apply these transforms before packing:
  height_packet     = (height + 50) / 150 * 50 - 20     (user -50…100 → packet -20…30)
  drop_point_packet = (drop_point + 10) / 20 * 44 - 22  (user -10…10  → packet -22…22)
  frequency_packet  = frequency / 100 + 0.5              (user 30…90   → packet 0.8…1.4)
  reps_packet       = reps (packed as u32, confirmed by both olanga packBall and smee createBall)

RPM Formulas:

top_rpm = 970 + (630.5 × speed) + (342 × spin)
bottom_rpm = 970 + (630.5 × speed) - (342 × spin)
Topspin: top_rpm > bottom_rpm (use positive spin)
Backspin: top_rpm < bottom_rpm (use negative spin)
Speed range: 0–10 (step 0.5), Spin range: -10 to 10 (step 0.5)
Height range: -50 to 100 (step 1), Drop point: -10 to 10 (step 0.5)
Frequency: 30–90 bpm (step 1), Reps: 1–200 (step 1)

Speed/Spin dependency (max abs(spin) for given speed):
speed 0→max_spin 2, 0.5→3, 1→4, 1.5→5, 2→6, 2.5→7, 3→8, 3.5→9, 4→10, 4.5→10, 5→9, 5.5→8, 6→8, 6.5→7, 7→6, 7.5→5, 8→4, 8.5→3, 9→2, 9.5→1, 10→0
GATT UUIDs (discovered via scripts/discover.py against NOVA_O38240700268 / 5588619A-1F02-A72D-FA7E-547386BA00F0):
Service:  02f00000-0000-0000-0000-00000000fe00
ff01 (write + write-without-response) → drill commands — use response=True (writeValue in JS = write-with-response; both olanga and smee use this for all writes)
ff02 (notify + read, CCCD 0x2902)     → robot status/feedback; subscribe on connect to see responses
ff00 (read)                            → possibly device info
ff03 (read)                            → possibly firmware version

Authentication handshake (REQUIRED before sending any drill — robot disconnects if skipped):
  Source: olanga/nova js/bluetooth.js + js/constants.js, smee/nova-s-custom-drills src/script.js
  SALT = "Mjgx1jAwXDBaMFcxCz3JBgNVBAYT4kJF7Rkw"  (36 chars, index with ord(c) % 36)
  1. Write 07 00 00 00  → robot replies with notification: bytes[6:18]=serial, bytes[18:]=code
  2. Compute: hashme = serial + SALT[ord(c)%36 for c in serial] + code; hash = MD5(hashme).hexdigest()
     Write: 08 20 00 + hash (32 ASCII bytes) = 35 bytes total
  3. Wait notification → write 01 00 00
  4. Wait notification (AUTH_R3, 35 bytes, contains firmware version string) → write 02 00 00
  5. Wait notification → write 80 01 00 00  (wakeup)
  6. Wait notification → (no write — standby transition 1/3)
  7. Wait notification → (no write — standby transition 2/3)
  Robot is now in standby and ready for drills.

  IMPORTANT — post-wakeup notification count: BLE capture proves only 2 post-wakeup
  notifications arrive before the robot is ready. STANDBY 3/3 (state byte 0x04 = ACTIVE)
  arrives simultaneously with the first drill ACK. Do NOT wait for a 3rd notification after
  wakeup — it causes a 15-second timeout on every connect.

  Firmware version is embedded in the AUTH_R3 notification (after write 02 00 00), e.g.
  "V0130.0.5-30.0.6". Extracted by scanning for 'V' prefix in the ASCII-decoded payload.

  All writes (auth and drills) use write-with-response.

Control commands (post-auth):
  Stop:      80 01 00 01
  Pause:     80 01 00 02
  Resume:    80 01 00 03
  Keepalive: 83 06 00  (write-with-response every 10 s while idle — not drilling)

Stop-when-stopped: if the robot was already stopped when 80 01 00 01 is sent, it responds
  with 01 80 00 00 (leading byte 0x01) instead of the normal 00 80 00 00 (leading byte 0x00).
  The MCP server detects this and returns "already stopped" rather than "stopped via command".

Keepalive ACK: 00 83 00 00  (robot acknowledges the 83 06 00 keepalive)

Robot state machine — notification format: 00 02 03 00 XX 01 00
  XX = 0x02 → STANDBY_1   (first post-wakeup notification)
  XX = 0x03 → STANDBY_2   (second post-wakeup notification)
  XX = 0x04 → ACTIVE       (arrives with first drill ACK, not during auth)
  XX = 0x05 → DRILL_COMPLETE
  XX = 0x06 → PAUSED

Drill progress notification — format: 00 05 07 00 <total:u16le><ball_index:u16le><seq:u16le><cycle:u8>
  Total length: 11 bytes. Fields at offsets 4–10.

Drill-complete notification: robot sends bytes containing "00020300050100" when a drill finishes.
Error notification 01 81 00 00: drill rejected (wrong format or sent without auth).

BLE Retry Strategy (ble.py):
  scan(): retries up to 3 times with a 2s delay if no Pongbot is found (robot BLE can sleep on power-on).
  connect(): retries up to 3 times with a 2s backoff on BleakError; stores address in self._last_address.
  ensure_connected(): checks self.connected; if false and _last_address is set, calls connect() to recover
    from silent disconnections. Called by send_drill() and stop_drill() before every write.
  pause_drill() / resume_drill() / send_raw() still use _require_connected() (no auto-reconnect).
  All retries are logged at WARNING level so they are visible in Claude Desktop's tool output.

Testing: protocol.py must be fully unit tested without hardware. BLE tests are manual only.
Conventions: Python 3.11+, type hints everywhere, async for BLE operations, dataclasses for drill/ball models.
