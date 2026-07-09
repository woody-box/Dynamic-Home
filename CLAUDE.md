# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes, plus the operating
rules for the Dynamic Home integration. Merge with any task-specific instructions.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No *speculative* flexibility. But configurability that the user DID request is
  welcome — Dynamic Home is deliberately configurable; add the options asked for,
  just nothing speculative on top.
- No error handling for genuinely impossible scenarios — **but Home Assistant
  states like `unavailable` / `unknown` / `None`, restarts, and stale/aged sensor
  data are the normal case here and MUST be handled.**
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

## Dynamic Home — project rules

### Collaboration
- Communicate in **Spanish**: chat, `CHANGELOG.md` entries, PR bodies and release
  notes are Spanish. Code identifiers stay English; match a file's existing
  comment language.
- **One feature per PR / per release.** Keep scope tight; the user publishes each
  release with a `gh release create` command you provide.

### Architecture
- **Pure engines** (`ds_engine`, `dv_engine`, `dc_engine`, `weather_engine`,
  `energy_engine`) hold the decision logic with **no Home Assistant imports**:
  inputs in, decision out. Unit-test them directly.
- **Coordinators + platforms** (`coordinator_*.py` and the `fan`/`cover`/`climate`/
  `sensor`/`binary_sensor`/`switch`/`select`/`number`/`button` platforms) only
  translate HA state to/from the engines — keep logic out of them.
- Modules: **DV** (VMC/fan), **DS** (shutter/cover), **DC** (climate), **DW**
  (weather), **Zonas** (house hub: modes, presence, changeover), **Energía**,
  plus the auto-created **Dynamic Shutter · Común**.
- Cross-module coordination goes through the **SDHB bus** and `hass.data[DOMAIN]`
  blobs (`DATA_WEATHER`, `DATA_MODE`, `DATA_PRESENCE`, `DATA_CHANGEOVER`,
  `DATA_ENERGY`).
- `const.py` is the single source of truth for `DOMAIN`, `MODULE_*`,
  `PLATFORMS_*`, `CONF_*`, `DATA_*`, `SIGNAL_*`.

### Verify before every commit — keep all green
- `pytest tests/ -p no:randomly -q`
- `ruff check custom_components tests`
- **Translation parity:** `strings.json` and `en.json` must have identical key
  sets, and `es.json` must carry the same keys. Any new switch/number/select/
  option key goes into all three.

### Making a change (TDD)
1. Add/adjust a test that captures the desired behavior — engine test first when
   the logic lives in an engine.
2. Implement the minimum to pass it.
3. Bump `custom_components/dynamic_home/manifest.json` `version`.
4. Add a dated `CHANGELOG.md` entry (Spanish, Keep a Changelog: Added/Changed/Fixed).
5. Commit (Spanish, descriptive), open the PR, wait for CI (6 checks:
   lint / validate / dynamic-home-integration ×2), squash-merge, sync `main`.
6. Give the user the `gh release create vX.Y.Z --target main …` command with
   one-paragraph Spanish notes (full release, not prerelease).

Docs-only or meta changes (like this file) skip the version bump and the release.

### Home Assistant robustness (non-negotiable in this domain)
- Any sensor can read `None` (`unavailable`/`unknown`); never assume a value is present.
- The safe state of a home appliance is usually **not "off"** (e.g. the VMC
  failsafe holds V1, not 0). Fail safe and observable, never silent.
- Respect manual/user intent until a real transition (shutter manual hold,
  presence, changeover conflict → the zone rests, never a silent inversion).
- Restore state across restarts wherever the user expects continuity.
