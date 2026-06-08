# Polish the Pongbot MCP Repo into a Public Artifact

## Context

I'm running you (Claude Code) inside my Pongbot MCP server project. This is a working project — an MCP server that lets Claude control a Pongbot Nova S Pro table tennis robot over Bluetooth, so I can run drills by talking to Claude instead of using the robot's official app.

The repo is **already public on GitHub.** Unlike a couple of other repos I recently archived, this one is an **active project**, not a shelved snapshot. I want to bring it up to the standard of a public artifact I'm proud to link from a newsletter essay: a clear README, proper attribution to the people whose reverse-engineering work this builds on, a license, and an honest status section that doesn't pretend the project is finished (it isn't — there's an unsolved connection-keepalive problem).

This project builds on prior open-source reverse-engineering of the Pongbot BLE protocol done by two people who published their work: **olanga** (a web client, the repo is roughly `nova`) and **smee** (earlier protocol reverse-engineering). Crediting them is a hard requirement of this task, not an optional nicety.

You will prepare everything locally. **Do not force-push and do not rewrite published git history without my explicit go-ahead.** Normal commits of the new README/LICENSE are fine to stage, but I'll decide when to push.

## Task 0 — Archive this prompt

Before anything else:

1. Create the directory `docs/prompts/` if it doesn't exist (`mkdir -p docs/prompts`).
2. Save the full text of this prompt to `docs/prompts/public-artifact-polish.md`.
3. Proceed with the remaining tasks.

## Operating principles

Read these once before starting.

- **Don't break the working code.** This is an active project that works (mostly). Do not refactor, rename, restructure, or "improve" the implementation. The only code changes permitted are removing genuinely sensitive content if I authorize it after the pre-flight. Everything else you do is documentation, attribution, and licensing.
- **Stop and ask if you find something sensitive.** If the pre-flight surfaces real secrets (tokens, keys, passwords) or anything I might not want public, stop and summarize what you found. Do not silently scrub. I make the keep/remove call.
- **No force-push, no history rewrite without explicit approval.** The repo is already public. Rewriting published history is disruptive and I want to decide whether it's worth it. Stage normal commits; leave pushing to me.
- **Voice.** Anywhere you write prose (README, status notes, commit messages), match the voice of my newsletter: direct, specific, honest, a little wry where the subject earns it. No marketing copy, no emoji, no exclamation points, no "amazing"/"powerful"/"seamless"/"leverage." Plain technical English.
- **Commits.** No `Co-Authored-By` trailers, no "Generated with Claude Code" lines, no attribution to Claude. Write commit messages as if I authored them. (This should be in my global `~/.claude/CLAUDE.md` already; restating for safety.)
- **Do not fabricate URLs.** When crediting olanga and smee, use the actual upstream repo URLs. They should be findable in this project's existing code comments, existing README, or git history. If you cannot find a real URL, leave a clearly-marked `TODO: confirm upstream URL` placeholder and tell me in your summary — do not invent a plausible-looking GitHub URL.

## Task 1 — Pre-flight check

Scan the repo (current working tree and full git history) and produce a report at `PREFLIGHT_REPORT.md`. Look specifically for:

1. **Real secrets:** API keys, tokens, passwords, OAuth credentials, anything matching `sk-`, `api_key`, `token`, `secret`, `password`, `.env` contents. Because the repo is already public, treat any real secret found in history as **already compromised** — flag it for rotation, not just removal.

2. **Device-identifying values:** my robot's BLE address/UUID, device serial number, and anything the MD5 auth salt is derived from. These are low-risk (a ping pong robot, requiring physical Bluetooth range) but I want them surfaced so I can decide whether to parameterize them out of the committed code (e.g., move to an env var or config file) going forward.

3. **Personal paths / identifiers:** home directory paths revealing my username (`/Users/...`, `/home/...`), and any personal references.

4. **`Co-Authored-By: Claude` or "Generated with Claude Code" trailers** anywhere in the commit history. List how many commits contain them.

5. **License compatibility:** check whether olanga's and/or smee's published work carries a license (look in this repo's existing references to them, and note if their license is unknown). If their work is copyleft (e.g., GPL) or otherwise imposes obligations on derivative work, flag it — my choice of license for this repo may be constrained by what I built on. If their licensing is permissive or unstated, note that too. I need to know before I pick a license in Task 4.

6. **Existing attribution:** does the current code or README already credit olanga and smee anywhere? Note what exists so we build on it rather than duplicating it.

Report each finding with file paths and line numbers (and commit SHAs for history findings), plus a recommendation: keep, parameterize, remove-from-current-state, or rewrite-history.

**Stop here and wait for my review before any remediation, scrubbing, or history rewriting.**

## Task 2 — Wait for my review

After I read `PREFLIGHT_REPORT.md`, I'll tell you what to remediate (if anything), or that the findings are acceptable as-is. Wait for explicit go-ahead before Task 3. If I authorize a history rewrite, create a backup branch first (`git branch backup-before-rewrite`) and use `git filter-repo`.

## Task 3 — Write the README

Write or substantially upgrade the top-level `README.md`. This is the single most important artifact a visitor sees. Structure:

**Opening (2–3 sentences):** What this is, factually. An MCP server that lets Claude control a Pongbot Nova S Pro table tennis robot over Bluetooth, so drills can be run through natural-language conversation instead of the robot's official app.

**Status note (prominent, near the top):** This is an active project, and it is honest about what works and what doesn't. State plainly:
- What works: authenticated connection, sending drills, modifying running drills, presets, telemetry, the natural-language control experience through Claude.
- What doesn't yet: the connection still drops after roughly 13 minutes of idle time despite an implemented keepalive. This is the current open problem. Do not soften this or imply it's nearly solved.
- Use a plain status line near the top, e.g.: `> **Status:** Working, actively developed. Known issue: connection drops after ~13 min idle (keepalive insufficient).`

**Credits / Acknowledgments (required, prominent — put this high, not buried at the bottom):** This project builds on prior open-source reverse-engineering of the Pongbot BLE protocol by **olanga** and **smee**. Credit them clearly, link their actual repos (real URLs only — see operating principles), and state plainly that the hard protocol work was theirs and this project stands on it. The tone should be genuine gratitude, not a legal footnote.

**What it does / how to use it:** Enough for someone to understand and run it. The MCP tools exposed, how it connects to Claude Desktop, the prerequisites (Python, the BLE library, the MCP SDK, a Pongbot Nova S Pro). Keep this practical.

**Technical overview (concise, not a teardown):** A short architecture description — protocol layer, BLE layer, MCP server — and the key facts someone needs to understand the codebase. Do NOT turn the README into a full protocol specification or a step-by-step "how to reverse-engineer your robot" guide. Point readers to olanga's and smee's work for the protocol details. The working code in the repo implements the protocol; the README documents the project, not a reproduction recipe.

**Newsletter link:** Link to the essay this accompanies. Newsletter is at `https://bharathk.dev`; the specific essay will be at `https://whoisb.substack.com/p/` followed by the essay slug (I'll provide the exact slug — leave a clearly-marked placeholder `https://whoisb.substack.com/p/SLUG-TBD` if I haven't given it to you yet).

**Contributing / maintenance expectations:** A brief, honest note. This is a personal project I work on for fun; I may or may not respond to issues and PRs. Set expectations without being unwelcoming.

## Task 4 — License

Based on the license-compatibility finding from the pre-flight:

- If olanga's/smee's work is permissive or unstated and there's no obligation, add an MIT `LICENSE`, copyright 2026, holder "Bharath Kumar."
- If their work is copyleft or imposes constraints, **stop and tell me** rather than picking a license that might conflict. I'll decide.

If a `LICENSE` already exists, confirm it's consistent with the above and flag any mismatch.

## Task 5 — Co-Authored-By cleanup (only if I approve in Task 2)

If the pre-flight found `Co-Authored-By: Claude` trailers in history and I approve cleaning them:
- Create a backup branch first.
- Use `git filter-repo` to strip the trailers from all commits.
- Verify with a `git log --all | grep` check afterward.
- Note that this requires a force-push, which I will do manually after reviewing.

If I don't approve, leave history as-is and just ensure no *new* commits add the trailer.

## Task 6 — Stage commits

Stage the new/updated README, LICENSE, PREFLIGHT_REPORT.md, and the archived prompt. Use a plain commit message such as:

```
docs: add public README, license, and attribution
```

Do not push. Leave that to me.

## Task 7 — Summary

Produce `PUBLIC_ARTIFACT_SUMMARY.md` at the repo root covering:
- What the pre-flight found (link to the report)
- What was remediated and how (with backup branch names if history was touched)
- The upstream URLs you used for attribution (and any you couldn't confirm)
- The license decision and its reasoning
- A ready-to-push checklist: the exact `git push` commands for me to run, including whether a force-push is needed (and why) if history was rewritten.

Do not run the push commands.

## What "done" looks like

When you're finished, I should be able to:
1. Read `PREFLIGHT_REPORT.md` and understand exactly what you found.
2. Read the new `README.md` and feel it represents the project honestly — including the unsolved keepalive — and credits olanga and smee properly with real links.
3. Read `PUBLIC_ARTIFACT_SUMMARY.md` and have a clean checklist for pushing.

If anything needs my judgment — an ambiguous license, an unconfirmable upstream URL, a device identifier I might want to parameterize — stop and ask. Don't guess.

Start with Task 0.
