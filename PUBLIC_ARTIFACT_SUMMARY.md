# Public artifact summary — pongbot-mcp

What was done to bring this repo to a public-artifact standard, and the checklist for pushing.

## Pre-flight findings

Full detail in [PREFLIGHT_REPORT.md](PREFLIGHT_REPORT.md). Headline results:

- **No real secrets** anywhere in the working tree or the 7-commit history. The `_AUTH_SALT` constant is a static upstream protocol value, not a personal secret.
- **No `Co-Authored-By: Claude` or "Generated with Claude Code" trailers** in any commit. History is clean; no rewrite was needed on that account.
- **No leaked username/paths.** The only `/Users/...` strings are intentional `yourname` placeholders. `.DS_Store` is untracked.
- **Device identifiers present, low risk:** robot serial `O38240700268`, BLE peripheral UUID `5588619A-1F02-A72D-FA7E-547386BA00F0`, firmware `V0130.0.5` — in docstrings, README, CLAUDE.md, and the raw `captures/btsnoop_hci.log*` traces. Exploiting any of it requires physical Bluetooth range of the robot.
- **Both upstream repos are unlicensed** (no declared license).

## Decisions and remediation

| Item | Decision | Action taken |
|------|----------|--------------|
| Device identifiers | **Keep as-is** | None. No code changed, no history touched. Risk is physical-proximity-only and the captures document the reverse-engineering work. |
| License | **MIT** | Added `LICENSE` (MIT, 2026, Bharath Kumar). |
| History rewrite | **Not needed** | No secrets and no AI trailers were found, so there was nothing to scrub. No backup branch created, no `git filter-repo` run. |

No remediation was required beyond adding documentation and the license. The implementation was not modified, refactored, or renamed.

## Attribution — upstream URLs used

Both confirmed live (HTTP 200, GitHub API checked 2026-06-08). No placeholders or unconfirmed URLs.

- **olanga** — https://github.com/olanga/nova (web client: https://olanga.github.io/nova/). Source of the drill packet format and auth constants.
- **smee** — https://github.com/smee/nova-s-custom-drills (web client: https://smee.github.io/nova-s-custom-drills/). Source of the control commands and post-wakeup state machine.

The old README credit (`BLE protocol reverse-engineered by [olanga/smee](https://github.com/olanga)`) linked a bare user profile and merged the two authors into one slug. The new README credits each separately with direct repo links, high up, with the protocol work attributed to them plainly.

## License decision and reasoning

**MIT**, copyright 2026, holder "Bharath Kumar".

Both upstream repos declare no license, which strictly means "all rights reserved" rather than affirmatively permissive. MIT is nonetheless appropriate here because this repo does not copy their source — it reuses *protocol facts* (byte layouts, RPM formulas, the handshake sequence, parameter scaling), which are functional and not protected by copyright. `protocol.py` and `ble.py` are a clean-room Python reimplementation, not a port of their JavaScript. The one verbatim borrowed string is the auth salt, itself a non-creative protocol constant. So there is no upstream licensing obligation constraining the choice. The courtesy owed to the upstream authors is prominent attribution, which the README provides. (This nuance was surfaced before the decision; you chose MIT with it in view.)

## Files added or changed

- `README.md` — rewritten. Honest status note (including the unsolved ~13-min idle disconnect), prominent credits with real links, practical setup/usage, concise architecture, newsletter link.
- `LICENSE` — new. MIT.
- `PREFLIGHT_REPORT.md` — new. The scan results.
- `PUBLIC_ARTIFACT_SUMMARY.md` — this file.
- `docs/prompts/public-artifact-polish.md` — new. The archived task prompt.

Note: `README.md` still contains a `https://whoisb.substack.com/p/SLUG-TBD` placeholder for the essay link. Replace `SLUG-TBD` with the real slug before or after pushing — it does not block anything.

## Ready-to-push checklist

History was **not** rewritten, so a normal push is all that's needed — **no force-push**.

1. Review the staged commit:
   ```bash
   git show --stat HEAD
   ```
2. (Optional) Replace the essay slug placeholder in `README.md`, then `git add README.md && git commit --amend --no-edit`.
3. Push:
   ```bash
   git push origin main
   ```

That's it. No `--force`, no `--force-with-lease`. The published history is untouched; this just adds the new commit on top.
