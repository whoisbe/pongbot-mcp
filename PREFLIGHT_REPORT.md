# Pre-flight report — pongbot-mcp

Scan date: 2026-06-08. Scope: current working tree plus full git history (7 commits, `c581ec0`..`75c1189`, single `main` branch). Nothing has been changed or removed — this is a findings-only report. Remediation waits for your call.

## Summary

| # | Category | Severity | Found? | Recommendation |
|---|----------|----------|--------|----------------|
| 1 | Real secrets (keys/tokens/passwords) | — | None | No action |
| 2 | Device identifiers (serial, BLE address, firmware) | Low | Yes | Decide: keep or parameterize |
| 3 | Personal paths / username | None | Only placeholders | No action |
| 4 | `Co-Authored-By: Claude` / "Generated with" trailers | — | None (0 commits) | No action |
| 5 | Upstream license compatibility | Medium | Both unlicensed | Read before Task 4 |
| 6 | Existing attribution to olanga / smee | — | Yes, extensive | Build on it |

Bottom line: no secrets, no AI-attribution trailers, clean history. The only things that need a decision from you are (a) whether to keep the device identifiers in the public repo, and (b) the licensing nuance in finding 5, which affects your Task 4 license choice.

---

## 1. Real secrets — none found

Searched the tree and history for `sk-`, `api_key`, `api-key`, `secret`, `password`, `token`, `bearer`, `private_key`, and `.env` contents. No API keys, OAuth credentials, passwords, or tokens in either the working tree or any historical blob.

The one string that pattern-matched on "salt" is **not a secret**:

- `src/pongbot_mcp/ble.py:36` — `_AUTH_SALT = "Mjgx1jAwXDBaMFcxCz3JBgNVBAYT4kJF7Rkw"`

This is a fixed protocol constant lifted verbatim from the upstream reverse-engineering (olanga `js/constants.js`). It is the same value baked into every Nova S Pro client; it is not derived from your device and is not unique to you. It is part of the documented auth handshake the robot requires. **Recommendation: keep.** Removing it would break the handshake, and it is already public in two upstream repos.

No `.env` file exists, tracked or untracked.

---

## 2. Device-identifying values — present, low risk

These uniquely identify *your* robot. They are low-risk by nature — exploiting any of them requires being in physical Bluetooth range of your table tennis robot — but you asked to see every location so you can decide whether to parameterize them out going forward.

**Robot serial / device name (`O38240700268` / `NOVA_O38240700268`):**

- `CLAUDE.md:41` — in the GATT-discovery note
- `src/pongbot_mcp/ble.py:22` — comment: "discovered via scripts/discover.py against NOVA_O38240700268"
- `captures/btsnoop_hci.log.last` — appears in the raw BLE capture (binary), multiple times, alongside the live auth handshake

**BLE address / peripheral UUID (`5588619A-1F02-A72D-FA7E-547386BA00F0`):**

- `README.md:72` — used as a literal example in a "connect to ..." prompt
- `CLAUDE.md:41` — discovery note
- `src/pongbot_mcp/ble.py:139` — docstring example: `await conn.connect("5588619A-...")`
- `src/pongbot_mcp/server.py:135` — docstring example for the `connect_robot` tool

Note this is a macOS-assigned peripheral UUID, not a hardware MAC. It is specific to your Mac/robot pairing, not a globally routable identifier.

**Firmware version (`V0130.0.5`):**

- `captures/btsnoop_hci.log.last` — embedded in the captured AUTH_R3 notification

**The BLE captures are the most exposing artifact.** `captures/btsnoop_hci.log` and `captures/btsnoop_hci.log.last` are raw HCI traces of real sessions. They contain the device name, serial, firmware string, and the complete live auth exchange (the serial + code the robot issued and the MD5 response your client computed). The salt is static, so in principle the captured serial+code pair documents one real handshake — but it is a one-time challenge/response for a Bluetooth-range-only device, so the practical risk is negligible. They are genuinely useful for anyone reproducing the protocol work, which is presumably why they were committed.

**Recommendation: your call.** Options, in increasing effort:
- **Keep as-is.** Defensible — the risk is physical-proximity-only, and the captures have documentary value for the reverse-engineering story the repo tells.
- **Parameterize going forward.** Replace the hardcoded serial/address in `ble.py`/`server.py` docstrings and `README.md` with a generic placeholder (e.g. `NOVA_XXXXXXXXXXXX`), and read any real default from an env var or local config. This is a code change, so it is outside what I'll touch without your go-ahead. It only affects the *current* state; the values remain in history unless you also rewrite history.
- **Scrub from history.** Only worth it if you decide the serial/address matter, which I don't think they do. Requires `git filter-repo` + force-push.

I did **not** change any of these.

---

## 3. Personal paths / identifiers — only placeholders

No real home-directory paths revealing your username are committed. The only `/Users/...` occurrences are deliberate placeholders:

- `README.md:45,55` — `/Users/yourname/projects/pongbot-mcp`
- `claude_desktop_config_snippet.json:8` — `/Users/yourname/projects/pongbot-mcp`

History search (`git log -S "/Users/b"`) returned nothing. No real username leaks. **Recommendation: keep** (the placeholders are correct and intentional).

`.DS_Store` exists on disk but is **not tracked** (correctly gitignored), so it won't be published.

---

## 4. `Co-Authored-By: Claude` / "Generated with Claude Code" — none

Scanned every commit body across all refs. **Zero** commits contain `Co-Authored-By`, "Generated with Claude Code", or a 🤖 trailer. History is clean. No Task 5 cleanup is needed, and no history rewrite is required on this account.

---

## 5. Upstream license compatibility — both upstream repos are UNLICENSED

This is the finding that affects your Task 4 license choice, so read it before picking a license.

This project builds on two upstream repos (confirmed live, HTTP 200, checked via the GitHub API on 2026-06-08):

- **olanga/nova** — https://github.com/olanga/nova — `license: null`, no `LICENSE`/`COPYING` file in the repo root.
- **smee/nova-s-custom-drills** — https://github.com/smee/nova-s-custom-drills — `license: null`, no `LICENSE`/`COPYING` file in the repo root.

Neither declares a license. Under your task framing this is the "unstated" case, which you grouped with "permissive" as the green-light path for adding MIT. Two things worth knowing before you act on that:

1. **Strictly, "no license" is not "permissive."** Under default copyright, code with no license is "all rights reserved" — no one is granted permission to copy or adapt the *literal source*. So if this project had copy-pasted their JavaScript, that would be a real constraint.

2. **But this project did not copy their code — and what it does use is not copyrightable.** What was reused is *protocol facts*: byte layouts, the RPM formulas, the handshake sequence, the scaling transforms. Facts and functional interface specifications are not protected by copyright; only a specific creative expression of code is. This repo is a clean-room Python reimplementation (`protocol.py`, `ble.py`) informed by their findings, not a port of their JS. The one verbatim string is the auth salt (finding 1), which is itself a protocol constant, not creative authorship.

On that basis there is **no licensing obligation** that constrains your choice, and MIT for this repo is defensible. The honest caveat is that the upstream authors never granted explicit permission for *anything*, so the courtesy move — beyond crediting them prominently (Task 3) — would be to keep the attribution clear and link their repos directly, which the README will do.

**Recommendation:** Proceed with MIT as Task 4 allows for the "unstated" case, *with* the understanding above. I have **not** added the LICENSE yet — that's Task 4, after your review. If the "all rights reserved" nuance changes your mind, tell me and I'll hold.

---

## 6. Existing attribution — already extensive, in code comments

olanga and smee are already credited throughout the source comments (not just the README). This is good raw material; the README rewrite should consolidate and elevate it rather than duplicate it. Current locations:

- `README.md:207` — `BLE protocol reverse-engineered by [olanga/smee](https://github.com/olanga).` — **this is the weak spot.** It links a user profile, not the actual repos, and conflates the two people into one slug. The README rewrite should replace this with proper per-person links to `olanga/nova` and `smee/nova-s-custom-drills`.
- `CLAUDE.md:3,27,43,49` — protocol provenance attributed to "olanga/smee", with specific file references (`olanga/nova js/bluetooth.js`, `js/constants.js`, `smee/nova-s-custom-drills src/script.js`).
- `scripts/compare_packets.py:7,11–12,34,52` — credits both, names the exact upstream functions (`packBall`, `createBall`, `createDrill`).
- `scripts/debug_auth.py:41,69` — credits both for the auth state machine.
- `src/pongbot_mcp/protocol.py:20,28` — ball-field scaling attributed to olanga `packBall()`.
- `src/pongbot_mcp/ble.py:33,38,370,518` — auth constants from olanga `constants.js`, control commands from smee `script.js`.

**Confirmed upstream URLs for the README (real, verified):**
- olanga: https://github.com/olanga/nova (live web client at https://olanga.github.io/nova/)
- smee: https://github.com/smee/nova-s-custom-drills (live web client at https://smee.github.io/nova-s-custom-drills/)

No `TODO: confirm upstream URL` placeholders are needed — both URLs are confirmed.

---

## What needs your decision

1. **Device identifiers (finding 2):** keep as-is, or parameterize the current code (a code change I won't make without approval), or scrub history? My read: keep — the risk is proximity-only and the captures have documentary value. Your call.
2. **License (finding 5):** confirm you're comfortable with MIT given that upstream is technically unlicensed (all-rights-reserved) rather than affirmatively permissive. My read: MIT is fine because this repo reuses facts, not their code. Your call.

Everything else (no secrets, clean history, good existing attribution) needs no action. Once you tell me how to handle the two items above, I'll proceed to Task 3 (README), Task 4 (license), Task 6 (stage), and Task 7 (summary).
