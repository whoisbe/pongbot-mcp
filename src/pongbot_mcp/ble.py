"""BLE connection layer for Pongbot Nova S Pro."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import struct
from collections import deque
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable

from bleak import BleakClient, BleakError, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice

from pongbot_mcp.protocol import Drill

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GATT UUIDs (discovered via scripts/discover.py against NOVA_O38240700268)
# ---------------------------------------------------------------------------
SERVICE_UUID       = "02f00000-0000-0000-0000-00000000fe00"
WRITE_CHAR_UUID    = "02f00000-0000-0000-0000-00000000ff01"  # write + write-without-response
NOTIFY_CHAR_UUID   = "02f00000-0000-0000-0000-00000000ff02"  # notify + read (CCCD 0x2902)
READ_CHAR_UUID_1   = "02f00000-0000-0000-0000-00000000ff00"  # read — possibly device info
READ_CHAR_UUID_2   = "02f00000-0000-0000-0000-00000000ff03"  # read — possibly firmware version

_PONGBOT_NAME_KEYWORDS = ("nova", "pongbot")

# ---------------------------------------------------------------------------
# Auth constants (from olanga/nova js/constants.js)
# ---------------------------------------------------------------------------
# SALT table used in the MD5 handshake; index with: ord(serial_char) % len(_AUTH_SALT)
_AUTH_SALT = "Mjgx1jAwXDBaMFcxCz3JBgNVBAYT4kJF7Rkw"  # 36 chars (0x24)

# Control commands (from smee/nova-s-custom-drills src/script.js)
_CMD_CHALLENGE  = bytes([0x07, 0x00, 0x00, 0x00])  # request serial + challenge code
_CMD_ACK1       = bytes([0x01, 0x00, 0x00])         # auth ack step 1/3
_CMD_ACK2       = bytes([0x02, 0x00, 0x00])         # auth ack step 2/3
_CMD_WAKEUP     = bytes([0x80, 0x01, 0x00, 0x00])   # wakeup — enter standby/ready
_CMD_STOP       = bytes([0x80, 0x01, 0x00, 0x01])   # stop running drill
_CMD_PAUSE      = bytes([0x80, 0x01, 0x00, 0x02])   # pause running drill
_CMD_RESUME     = bytes([0x80, 0x01, 0x00, 0x03])   # resume paused drill
_CMD_KEEPALIVE  = bytes([0x83, 0x06, 0x00])          # idle keepalive (every 10 s)

_KEEPALIVE_INTERVAL = 10.0  # seconds between keepalive writes

# Notification the robot sends when a drill sequence completes
_NOTIFY_DONE_HEX = "00020300050100"

# Stop-command response: leading 0x01 (vs 0x00) means robot was already stopped
_NOTIFY_ALREADY_STOPPED = bytes([0x01, 0x80, 0x00, 0x00])
_NOTIFY_KEEPALIVE_ACK   = bytes([0x00, 0x83, 0x00, 0x00])

# State machine notifications: 00 02 03 00 XX 01 00  (XX encodes state)
_NOTIFY_STATE_PREFIX = bytes([0x00, 0x02, 0x03, 0x00])
_STATE_STANDBY_1     = 0x02
_STATE_STANDBY_2     = 0x03
_STATE_ACTIVE        = 0x04
_STATE_DRILL_COMPLETE = 0x05
_STATE_PAUSED        = 0x06

# Drill progress notifications: 00 05 07 00 <total:u16><ball:u16><seq:u16><cycle:u8>
_NOTIFY_DRILL_STATUS_PREFIX = bytes([0x00, 0x05, 0x07, 0x00])

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class RobotState(IntEnum):
    UNKNOWN        = 0
    STANDBY        = 1
    ACTIVE         = 2
    PAUSED         = 3
    DRILL_COMPLETE = 4


@dataclass
class DrillProgress:
    total_shots: int
    ball_index: int
    sequence: int
    cycle: int


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _compute_auth_hash(challenge: bytes) -> str:
    """Derive the 32-char lowercase MD5 hex response from the robot's challenge notification.

    The notification payload layout:
      bytes  0-5  : unknown header
      bytes  6-17 : 12-char serial number (UTF-8)
      bytes 18+   : dynamic code (UTF-8)
    """
    if len(challenge) < 19:
        raise ConnectionError(
            f"Auth challenge too short: {len(challenge)} bytes (expected >18). "
            f"Raw: {challenge.hex()}"
        )
    serial = challenge[6:18].decode("utf-8")
    code   = challenge[18:].decode("utf-8")
    log.debug("Auth challenge — serial: %r  code: %r", serial, code)

    hashme = serial
    for ch in serial:
        hashme += _AUTH_SALT[ord(ch) % len(_AUTH_SALT)]
    hashme += code
    return hashlib.md5(hashme.encode()).hexdigest()


def _extract_firmware_version(payload: bytes) -> str | None:
    """Try to extract a firmware version string (e.g. 'V0130.0.5-30.0.6') from a notification."""
    try:
        s = payload.decode("ascii", errors="replace")
        idx = s.find("V")
        if idx >= 0:
            version = s[idx:].rstrip("\x00").strip()
            if len(version) >= 5 and "." in version:
                return version
    except Exception:
        pass
    return None


class PongbotConnection:
    """Manages a BLE connection to a single Pongbot Nova S Pro.

    connect() performs the full authentication handshake automatically before
    returning, so callers can send drills immediately after awaiting connect().

    Usage::

        conn = PongbotConnection()
        await conn.connect("5588619A-1F02-A72D-FA7E-547386BA00F0")
        await conn.send_drill(drill)
        await conn.stop_drill()
        await conn.disconnect()
    """

    def __init__(self) -> None:
        self._client: BleakClient | None = None
        self._notifications: deque[bytes] = deque(maxlen=64)
        self._on_notification: Callable[[bytes], None] | None = None
        self._last_address: str | None = None  # set on connect(); used by ensure_connected()

        # Used only during the auth handshake — cleared once auth is done.
        self._auth_queue: asyncio.Queue[bytes] | None = None
        self._in_auth: bool = False

        # Robot state tracking
        self._robot_state: RobotState = RobotState.UNKNOWN
        self._drill_progress: DrillProgress | None = None
        self._firmware_version: str | None = None
        self._is_drilling: bool = False

        # Keepalive background task
        self._keepalive_task: asyncio.Task | None = None  # type: ignore[type-arg]
        # Number of consecutive keepalives sent without receiving an ACK (00 83 00 00).
        # Reset to 0 on each ACK; if it reaches 3 the connection is declared dead.
        self._keepalive_missed: int = 0

        # One-shot queue for stop/control command ack detection
        self._cmd_response_queue: asyncio.Queue[bytes] | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @property
    def robot_state(self) -> RobotState:
        return self._robot_state

    @property
    def drill_progress(self) -> DrillProgress | None:
        return self._drill_progress

    @property
    def firmware_version(self) -> str | None:
        return self._firmware_version

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    @classmethod
    async def scan(
        cls,
        timeout: float = 10.0,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> list[dict]:
        """Scan for nearby Pongbot devices, retrying if none are found.

        The robot's BLE radio can be asleep after power-on; a second scan is
        often enough to wake it.  Retries up to *max_retries* times, waiting
        *retry_delay* seconds between each attempt.

        Returns a list of dicts with keys: name, address, rssi.
        """
        for attempt in range(1, max_retries + 1):
            log.info(
                "Scanning for Pongbot devices (%.1fs) — attempt %d/%d…",
                timeout, attempt, max_retries,
            )
            results: list[dict] = []
            seen: set[str] = set()

            def _callback(device: BLEDevice, adv) -> None:  # type: ignore[type-arg]
                name = (device.name or "").lower()
                if any(kw in name for kw in _PONGBOT_NAME_KEYWORDS):
                    if device.address not in seen:
                        seen.add(device.address)
                        log.debug("Found: %s  %s  rssi=%s", device.name, device.address, adv.rssi)
                        results.append({
                            "name": device.name or "",
                            "address": device.address,
                            "rssi": adv.rssi,
                        })

            async with BleakScanner(_callback):
                await asyncio.sleep(timeout)

            if results:
                log.info("Scan complete (attempt %d). Found %d Pongbot device(s).", attempt, len(results))
                return results

            if attempt < max_retries:
                log.warning(
                    "Scan attempt %d/%d found no Pongbot devices. Retrying in %.1fs…",
                    attempt, max_retries, retry_delay,
                )
                await asyncio.sleep(retry_delay)

        log.warning("All %d scan attempts found no Pongbot devices.", max_retries)
        return []

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(
        self,
        address: str,
        timeout: float = 15.0,
        max_retries: int = 3,
        backoff: float = 2.0,
    ) -> None:
        """Connect to the robot and complete the authentication handshake.

        Retries up to *max_retries* times on failure (BLE connections can be
        flaky on first attempt), waiting *backoff* seconds between each try.

        After this coroutine returns the robot is in standby and ready to
        receive drill commands.
        """
        if self.connected:
            log.warning("Already connected — call disconnect() first.")
            return

        self._last_address = address
        last_exc: Exception | None = None

        for attempt in range(1, max_retries + 1):
            log.info("Connecting to %s — attempt %d/%d…", address, attempt, max_retries)
            try:
                await self._connect_once(address, timeout)
                return  # success
            except ConnectionError as exc:
                last_exc = exc
                if attempt < max_retries:
                    log.warning(
                        "Connection attempt %d/%d failed: %s. Retrying in %.1fs…",
                        attempt, max_retries, exc, backoff,
                    )
                    await asyncio.sleep(backoff)
                else:
                    log.error("All %d connection attempts to %s failed.", max_retries, address)

        raise last_exc  # type: ignore[misc]

    async def _connect_once(self, address: str, timeout: float) -> None:
        """Single connection attempt — GATT connect, subscribe, authenticate, start keepalive."""
        self._client = BleakClient(
            address,
            timeout=timeout,
            disconnected_callback=self._on_disconnected,
        )

        try:
            await self._client.connect()
        except BleakError as exc:
            self._client = None
            raise ConnectionError(f"Failed to connect to {address}: {exc}") from exc

        log.info("Connected to %s (MTU %d).", address, self._client.mtu_size)

        try:
            await self._client.start_notify(NOTIFY_CHAR_UUID, self._handle_notification)
            log.info("Subscribed to notifications on %s.", NOTIFY_CHAR_UUID)
        except BleakError as exc:
            await self._client.disconnect()
            self._client = None
            raise ConnectionError(f"Failed to subscribe to notifications: {exc}") from exc

        await self._authenticate(timeout=timeout)
        self._keepalive_missed = 0
        self._start_keepalive()

    async def ensure_connected(self) -> None:
        """Verify the connection is live; reconnect to the last known address if not.

        Call this before any write that could follow a silent BLE disconnection.
        Raises RuntimeError if no address is known, or re-raises ConnectionError
        if reconnection fails.
        """
        if self.connected:
            return
        if not self._last_address:
            raise RuntimeError("Not connected and no previous address known — call connect() first.")
        log.warning(
            "Connection lost. Attempting to reconnect to %s…", self._last_address
        )
        await self.connect(self._last_address)

    async def disconnect(self) -> None:
        """Gracefully disconnect from the robot."""
        self._stop_keepalive()
        if not self._client:
            return
        try:
            await self._client.stop_notify(NOTIFY_CHAR_UUID)
        except BleakError:
            pass
        try:
            await self._client.disconnect()
            log.info("Disconnected.")
        except BleakError as exc:
            log.warning("Error during disconnect: %s", exc)
        finally:
            self._client = None
            self._in_auth = False
            self._auth_queue = None
            self._is_drilling = False
            self._robot_state = RobotState.UNKNOWN

    def _on_disconnected(self, client: BleakClient) -> None:  # noqa: ARG002
        log.warning("Robot disconnected unexpectedly.")
        self._stop_keepalive()
        self._client = None
        # Unblock any in-progress auth wait so it fails fast instead of timing out.
        if self._auth_queue is not None:
            self._auth_queue.put_nowait(b"")

    # ------------------------------------------------------------------
    # Authentication handshake
    # ------------------------------------------------------------------

    async def _authenticate(self, timeout: float = 10.0) -> None:
        """Execute the 7-step MD5 auth handshake.

        Sequence (from smee/nova-s-custom-drills src/script.js state machine):
          1. Write 07000000  → robot sends challenge notification (serial + code)
          2. Write 082000 + MD5(serial + SALT_chars + code) as 32 ASCII bytes
          3. Wait notification → write 010000
          4. Wait notification (AUTH_R3, contains firmware version) → write 020000
          5. Wait notification → write 80010000  (wakeup)
          6. Wait notification (standby transition 1/3 — no write)
          7. Wait notification (standby transition 2/3 — no write)
          Robot is ready for drills.

        IMPORTANT: Only 2 post-wakeup notifications arrive before the robot is
        ready. STANDBY 3/3 (state byte 0x04 = ACTIVE) arrives simultaneously
        with the first drill ACK — do NOT wait for a third notification here.
        """
        log.info("Starting authentication handshake…")
        self._in_auth = True
        self._auth_queue = asyncio.Queue()

        async def _wait(label: str) -> bytes:
            """Dequeue the next auth notification with a timeout."""
            try:
                payload = await asyncio.wait_for(self._auth_queue.get(), timeout)
            except asyncio.TimeoutError:
                raise ConnectionError(f"Auth timed out waiting for: {label}")
            if not self.connected:
                raise ConnectionError(f"Robot disconnected during auth at: {label}")
            return payload

        try:
            # Step 1 — request challenge
            log.debug("Auth 1/7: challenge request")
            await self._write_cmd(_CMD_CHALLENGE)
            challenge = await _wait("challenge notification")

            hash_hex = _compute_auth_hash(challenge)
            log.debug("Auth hash: %s", hash_hex)

            # Step 2 — send hash response (3-byte header + 32 ASCII hex chars = 35 bytes)
            log.debug("Auth 2/7: sending hash response")
            await self._write_cmd(bytes([0x08, 0x20, 0x00]) + hash_hex.encode())
            await _wait("auth_1 notification")

            # Step 3 — ack 1/3
            log.debug("Auth 3/7: ack 1")
            await self._write_cmd(_CMD_ACK1)
            await _wait("auth_2 notification")

            # Step 4 — ack 2/3; response (AUTH_R3) contains firmware version
            log.debug("Auth 4/7: ack 2")
            await self._write_cmd(_CMD_ACK2)
            auth_r3 = await _wait("auth_3 notification")
            version = _extract_firmware_version(auth_r3)
            if version:
                self._firmware_version = version
                log.info("Firmware version: %s", version)

            # Step 5 — wakeup
            log.debug("Auth 5/7: wakeup")
            await self._write_cmd(_CMD_WAKEUP)

            # Steps 6–7 — drain two post-wakeup standby-transition notifications.
            # Do NOT wait for a third: STANDBY 3/3 arrives with the first drill ACK.
            log.debug("Auth 6/7: draining standby transition 1/3")
            await _wait("standby transition 1/3")
            log.debug("Auth 7/7: draining standby transition 2/3")
            await _wait("standby transition 2/3")

            self._robot_state = RobotState.STANDBY
            log.info("Authentication complete — robot is in standby and ready.")

        finally:
            self._in_auth = False
            self._auth_queue = None

    # ------------------------------------------------------------------
    # Keepalive
    # ------------------------------------------------------------------

    def _start_keepalive(self) -> None:
        if self._keepalive_task is None or self._keepalive_task.done():
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            log.debug("Keepalive task started.")

    def _stop_keepalive(self) -> None:
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        self._keepalive_task = None

    async def _keepalive_loop(self) -> None:
        """Send 83 06 00 every 10 seconds while connected and not drilling.

        Tracks consecutive keepalives sent without receiving a 00 83 00 00 ACK.
        If 3 consecutive keepalives fail or go unACKed the connection is declared
        dead: the BLE client is forcibly closed and the loop exits so the next
        command triggers a fresh reconnect via ensure_connected().
        """
        try:
            while True:
                await asyncio.sleep(_KEEPALIVE_INTERVAL)
                if not self.connected:
                    log.warning("Keepalive loop: connection gone — exiting.")
                    break
                if self._is_drilling:
                    continue  # drill active — robot does not expect keepalives

                try:
                    await self._write_cmd(_CMD_KEEPALIVE)
                    self._keepalive_missed += 1
                    log.info(
                        "Keepalive sent (83 06 00). Waiting for ACK "
                        "[unacked=%d].", self._keepalive_missed,
                    )
                except IOError as exc:
                    self._keepalive_missed += 1
                    log.warning(
                        "Keepalive write failed (missed=%d): %s. "
                        "Attempting reconnect…",
                        self._keepalive_missed, exc,
                    )
                    try:
                        await self.ensure_connected()
                        log.info("Keepalive reconnect succeeded.")
                    except Exception as reconnect_exc:
                        log.error("Keepalive reconnect failed: %s", reconnect_exc)

                if self._keepalive_missed >= 3:
                    log.error(
                        "3 consecutive keepalives sent without ACK — "
                        "proactively marking connection dead so the next "
                        "command triggers a clean reconnect."
                    )
                    try:
                        if self._client:
                            await self._client.disconnect()
                    except Exception:
                        pass
                    self._client = None
                    break
        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------
    # Drill commands
    # ------------------------------------------------------------------

    async def send_drill(self, drill: Drill) -> None:
        """Encode *drill* and write it to the robot (write-with-response).

        Both olanga and smee use writeValue() = write-with-response for all
        writes including drill packets.
        """
        await self.ensure_connected()
        self._is_drilling = True
        data = drill.to_bytes()
        log.info(
            "Sending drill: %d ball(s), mode=%s, level=%d  [%d bytes]",
            len(drill.balls), drill.mode.name, drill.level, len(data),
        )
        log.debug("Drill bytes: %s", data.hex())
        await self._write_cmd(data)

    async def stop_drill(self) -> str:
        """Stop the currently running drill.

        Tries three escalating strategies and returns a status string describing
        which one succeeded (or that all failed).

        1. Sends the BLE stop command on the existing connection and checks the
           response notification.  Returns "already stopped" if the robot was
           already idle (01 80 00 00), "stopped via command" otherwise.

        2. If the connection has silently dropped, reconnects (full auth handshake)
           and retries the stop command.

        3. Last resort: disconnects from the robot entirely.

        After a "stopped by disconnecting" result you will need to call
        connect_robot() again before sending a new drill.
        """
        if not self.connected and not self._last_address:
            return "not connected — nothing to stop"

        self._is_drilling = False  # clear before write so keepalive can resume

        # Attempt 1 — send stop command on the existing connection.
        if self.connected:
            try:
                notif = await self._cmd_and_wait(_CMD_STOP, timeout=2.0)
                if notif is not None and notif[:4] == _NOTIFY_ALREADY_STOPPED:
                    log.info("Stop sent — robot was already stopped.")
                    return "already stopped"
                log.info("Drill stopped via stop command.")
                return "stopped via command"
            except IOError as exc:
                log.warning("Stop command failed (connection may have dropped): %s", exc)

        # Attempt 2 — reconnect (full auth handshake) then retry stop command.
        try:
            log.info("Attempting reconnect before retrying stop command…")
            await self.ensure_connected()
            notif = await self._cmd_and_wait(_CMD_STOP, timeout=2.0)
            if notif is not None and notif[:4] == _NOTIFY_ALREADY_STOPPED:
                return "already stopped (after reconnect)"
            log.info("Drill stopped via stop command after reconnect.")
            return "stopped via command (after reconnect)"
        except Exception as exc:
            log.warning("Stop command failed after reconnect attempt: %s", exc)

        # Attempt 3 (last resort) — disconnect; robot halts when BLE drops.
        log.warning("Falling back to disconnect to stop the drill.")
        try:
            await self.disconnect()
            log.info("Drill stopped by disconnecting.")
            return "stopped by disconnecting"
        except Exception as exc:
            log.error("Disconnect also failed: %s", exc)
            return "failed to stop — power cycle the robot"

    async def pause_drill(self) -> None:
        """Pause the currently running drill."""
        self._require_connected()
        log.info("Pausing drill.")
        await self._write_cmd(_CMD_PAUSE)

    async def resume_drill(self) -> None:
        """Resume a paused drill."""
        self._require_connected()
        log.info("Resuming drill.")
        await self._write_cmd(_CMD_RESUME)

    async def send_raw(self, data: bytes) -> None:
        """Write arbitrary bytes to the write characteristic (escape hatch)."""
        self._require_connected()
        log.info("send_raw: %d bytes → %s", len(data), data.hex())
        await self._write(data)

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def set_notification_callback(self, cb: Callable[[bytes], None]) -> None:
        """Register a callback invoked for every post-auth notification."""
        self._on_notification = cb

    def _handle_notification(
        self, characteristic: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        payload = bytes(data)

        # During auth the queue drives the handshake; don't forward to user callback.
        if self._in_auth and self._auth_queue is not None:
            log.debug(
                "Auth notification (%d bytes): %s", len(payload), payload.hex()
            )
            self._auth_queue.put_nowait(payload)
            return

        hex_str = payload.hex()
        log.info("Notification (%d bytes): %s", len(payload), hex_str)

        # Keepalive ACK: 00 83 00 00
        if payload == _NOTIFY_KEEPALIVE_ACK:
            self._keepalive_missed = 0
            log.info("Keepalive ACK received (00 83 00 00) — connection confirmed alive.")

        # State machine: 00 02 03 00 XX 01 00
        if payload[:4] == _NOTIFY_STATE_PREFIX and len(payload) >= 7:
            state_byte = payload[4]
            state_map = {
                _STATE_STANDBY_1:     RobotState.STANDBY,
                _STATE_STANDBY_2:     RobotState.STANDBY,
                _STATE_ACTIVE:        RobotState.ACTIVE,
                _STATE_DRILL_COMPLETE: RobotState.DRILL_COMPLETE,
                _STATE_PAUSED:        RobotState.PAUSED,
            }
            if state_byte in state_map:
                self._robot_state = state_map[state_byte]
                log.debug("Robot state → %s (byte 0x%02x)", self._robot_state.name, state_byte)
            if state_byte == _STATE_DRILL_COMPLETE:
                self._is_drilling = False
                log.info("Drill complete — robot returned to standby.")

        # Drill progress: 00 05 07 00 <total:u16><ball:u16><seq:u16><cycle:u8>
        elif payload[:4] == _NOTIFY_DRILL_STATUS_PREFIX and len(payload) >= 11:
            total_shots, ball_idx, seq = struct.unpack_from("<HHH", payload, 4)
            cycle = payload[10]
            self._drill_progress = DrillProgress(total_shots, ball_idx, seq, cycle)
            log.debug(
                "Drill progress: total=%d ball=%d seq=%d cycle=%d",
                total_shots, ball_idx, seq, cycle,
            )

        # Legacy drill-complete sentinel
        elif _NOTIFY_DONE_HEX in hex_str:
            self._is_drilling = False
            log.info("Drill-complete notification received.")

        self._notifications.append(payload)

        # Feed command-response queue (for stop/control ack detection).
        if self._cmd_response_queue is not None:
            self._cmd_response_queue.put_nowait(payload)

        if self._on_notification:
            try:
                self._on_notification(payload)
            except Exception:
                log.exception("Error in notification callback")

    @property
    def notifications(self) -> list[bytes]:
        """Snapshot of buffered post-auth notification payloads (oldest first)."""
        return list(self._notifications)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _cmd_and_wait(self, data: bytes, timeout: float = 2.0) -> bytes | None:
        """Write a command and return the first non-keepalive-ack notification within *timeout*."""
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._cmd_response_queue = queue
        try:
            await self._write_cmd(data)
            deadline = asyncio.get_event_loop().time() + timeout
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    return None
                try:
                    notif = await asyncio.wait_for(queue.get(), remaining)
                    if notif[:4] != _NOTIFY_KEEPALIVE_ACK:
                        return notif
                except asyncio.TimeoutError:
                    return None
        finally:
            self._cmd_response_queue = None

    async def _write(self, data: bytes) -> None:
        """Write-without-response — used for drill packets."""
        assert self._client is not None
        try:
            await self._client.write_gatt_char(WRITE_CHAR_UUID, data, response=False)
        except BleakError as exc:
            raise IOError(f"BLE write failed: {exc}") from exc

    async def _write_cmd(self, data: bytes) -> None:
        """Write-with-response — used for auth and control commands."""
        assert self._client is not None
        try:
            await self._client.write_gatt_char(WRITE_CHAR_UUID, data, response=True)
        except BleakError as exc:
            raise IOError(f"BLE command write failed: {exc}") from exc

    def _require_connected(self) -> None:
        if not self.connected:
            raise RuntimeError("Not connected — call connect() first.")
