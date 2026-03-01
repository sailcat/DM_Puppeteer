# Dev Session Handover -- February 27, 2026 (Session 2)

**Project:** DM Puppeteer
**Session scope:** Dev Brief 005 -- Graphical Dice Roll Effects
**Files delivered:** 5 files (1 new + 4 modified)

---

## What Was Accomplished

### Brief 005: Graphical Dice Roll Effects

Built the complete dice sprite animation engine, dice pack asset loader with placeholder generation, and integrated everything into the existing dice roll overlay. The system supports three display modes (dice_only, card_only, dice_and_card) with per-player dice pack and color customization.

**New file: `dice_assets.py` (464 lines)**

DicePackLoader class that discovers dice packs from `data/dice_packs/<name>/` folders, loads and caches sprites, applies hue shifting for color variants, and generates placeholder assets when no real packs exist.

Key features:
- Folder scanning with pack.json metadata parsing
- Landing frame loading with per-color hue shifting
- Tumble frame loading (pre-rendered tumble/ subfolder or shuffled landing frames as pseudo-tumble)
- Placeholder generator: 128x128 diamond-shaped sprites with face number, die type label, and color tinting. Placeholders auto-generate when no real pack folder exists, so the animation pipeline works immediately without art assets.
- Dual hue-shifting implementation: numpy fast path (approx 100x faster for large images) with QImage per-pixel fallback. numpy is already a required dependency, so the fast path is always available.
- Cache system: `"land:pack:die:face:color"` and `"tumble:pack:die:color"` keys. `clear_cache()` and `rescan()` for runtime pack changes.

**Modified: `dice_effects.py` (840 lines, was 499)**

Added DiceSprite class (approx 280 lines) -- the core animation engine.

Five animation phases:
1. **ENTER** -- Die appears from random edge (left/right/top), spinning with gravity arc
2. **BOUNCE** -- Hits ground, bounces 2-3 times with restitution decay, spin slowing
3. **SETTLE** -- Final bounce resolves to result face, scale pulse 1.0 -> 1.08 -> 1.0
4. **HOLD** -- Die sits at landing position with ground shadow, duration from display_time
5. **EXIT** -- Normal: fade out. NAT 20: `trigger_explode()` (rapid scale up + fade, particles handle visuals). NAT 1: `trigger_shatter()` (crack lines spread across die, then tumble-fall)

Physics: configurable gravity (1200 px/s^2), bounce restitution (0.45), friction (0.7x per bounce), spin decay (0.92x per bounce). Tumble frames cycle at randomized speed, decaying with each bounce.

Advantage/disadvantage support: `_is_secondary` flag dims the dropped die (50% opacity, 85% scale) during hold phase.

Also fixed: two encoding corruptions (triple-encoded em-dashes on lines 2 and 307 of original file).

**Modified: `dice_overlay.py` (972 lines, was 748)**

Major integration work:

- `DiceRollOverlay.__init__` now accepts optional `state` parameter for AppState access, creates `DicePackLoader`, maintains `dice_sprites` list alongside existing `cards` list.
- `_apply_sizing()` -- mode-aware window sizing: card_only (380+120 x 632), dice_only (500 x 400), dice_and_card (500 x 832). Called on init and when display mode changes.
- `_get_display_mode()` -- reads from state with "dice_and_card" fallback.
- `set_state()` -- links AppState for display mode and PC slot preferences.
- `add_roll()` rewritten: creates DiceSprite(s) and/or DiceRollCard(s) based on display mode. PC slot lookup for pack_name and dice_color preferences. Glow-to-dice-color auto-mapping. Card delay of 1.8s in dice_and_card mode. Advantage/disadvantage dual-die with secondary dimming. Trims to 6 max sprites and MAX_VISIBLE+2 cards.
- `_tick()` updated: dice sprite update loop with crit/fumble exit interception (when sprite transitions from hold -> exit, we override to explode/shatter and fire particle effects at the die's position).
- `paintEvent()` rewritten: paints dice sprites first (behind cards), then cards with mode-aware Y offset (400px dice zone above cards in dice_and_card mode), then effects on top.
- `_card_rect()` updated for dice zone offset in dice_and_card mode.
- `DiceRollCard._delay` support: cards wait for specified delay before entering. Effective age calculation offsets all time-based animations.
- `_random_landing_position()` -- randomized landing within the dice zone area.
- `_glow_to_dice_color()` -- maps hex glow color to nearest dice pack color by HSV hue distance.
- `set_display_mode()` -- changes mode and resizes overlay.

**Modified: `models.py` (758 lines, was 744)**

- `PCSlot`: added `dice_pack: str = ""` and `dice_color: str = ""` with to_dict/from_dict support. Backward-compatible (empty string defaults = use global).
- `AppState`: added `dice_display_mode: str = "dice_and_card"` and `dice_default_pack: str = "classic"` with save/load support. Backward-compatible defaults.

**Modified: `discord_bot.py` (774 lines, was 767)**

- `DiceRollEvent`: added `is_advantage: bool = False`, `is_disadvantage: bool = False`, `secondary_roll: int = 0`, `die_type: str = "d20"`. All default to disabled -- parser work deferred to Brief 005-B.
- Fixed pre-existing syntax error: docstring closing `"""` was on the same line as `AVRAE_BOT_ID` class variable, causing SyntaxError. Added newline to separate them.

---

## Files Delivered

| File | Status | Lines | Key Changes |
|------|--------|-------|-------------|
| `dice_assets.py` | NEW | 464 | DicePackLoader, placeholder generator, hue shifting (numpy + fallback) |
| `dice_effects.py` | MODIFIED | 840 (was 499) | DiceSprite class, encoding fixes (2 corrupted em-dashes) |
| `dice_overlay.py` | MODIFIED | 972 (was 748) | Display mode support, sprite integration, card delay, mode-aware sizing/painting |
| `models.py` | MODIFIED | 758 (was 744) | AppState +2 fields, PCSlot +2 fields |
| `discord_bot.py` | MODIFIED | 774 (was 767) | DiceRollEvent +4 fields, syntax fix |

---

## What's NOT Done (Noted for Future)

- **Advantage/disadvantage parser (Brief 005-B)** -- DiceRollEvent fields exist, dual-die rendering works, but the Avrae parser doesn't yet detect `2d20kh1`/`2d20kl1` patterns. Hardcoded to `is_advantage = False`. The parser work is isolated: just set the fields in `_parse_embed()` and `_parse_text()`.

- **app_window.py wiring** -- DiceRollOverlay constructor now accepts `state=` but app_window.py still creates it without state. One-liner change: `self.dice_overlay = DiceRollOverlay(state=self.state, x=..., y=...)`. Also needs: display mode dropdown/radio in the Discord tab settings, pack selector dropdown per PC slot.

- **Real dice assets** -- The Chequered Ink pack needs to be downloaded, organized into the `data/dice_packs/classic/d20/land_01.png` through `land_20.png` structure, and a `pack.json` created. The placeholder generator validates the entire pipeline until then.

- **Pack selector UI** -- Brief calls for a pack dropdown per PC slot. The data model supports it (PCSlot.dice_pack, PCSlot.dice_color), but the UI widgets aren't built yet.

- **Damage dice (d4, d6, d8, d10, d12)** -- Engine supports all die types via the `die_type` parameter. Needs Avrae parser work to distinguish damage rolls from to-hit rolls, and multiple simultaneous dice (e.g., 2d6 for greatsword).

- **Sound effects** -- Dice clatter on entry/bounce/land, crit fanfare, fumble sad trombone. Deferred to soundboard phase.

---

## Architecture Notes for Next Dev

### Display Mode Flow

```
state.dice_display_mode -> overlay._get_display_mode()
  -> add_roll(): creates sprites AND/OR cards
  -> _apply_sizing(): sets window dimensions
  -> paintEvent(): renders sprites AND/OR cards with correct offsets
```

Three modes: `"dice_only"` (just sprites), `"card_only"` (existing behavior), `"dice_and_card"` (sprites in upper 400px zone, cards below with 1.8s delay).

### Dice Pack Resolution

```
1. slot.dice_pack (per-player override)
2. state.dice_default_pack (global default)
3. First available pack from loader
4. DicePackLoader.PLACEHOLDER_PACK ("_placeholder") -- auto-generated
```

Placeholder sprites are 128x128 diamonds with numbers. Generated on demand, cached like real pack sprites.

### Crit/Fumble Interception Pattern

The DiceSprite's own `update()` transitions from `hold -> exit` when hold time expires. The overlay's `_tick()` watches for this transition and overrides:

```
was_holding = (sprite.phase == "hold")
sprite.update(dt, display_time)
if was_holding and sprite.phase == "exit":
    if NAT 20: sprite.trigger_explode() + particles
    if NAT 1:  sprite.trigger_shatter() + particles + screen_shake
```

This keeps the sprite self-contained (it doesn't need to know about the particle system) while the overlay orchestrates the visual coordination.

### Card Delay Mechanism

`DiceRollCard._delay` offsets all time calculations. Before the delay elapses, the card is "alive but not visible" (returns True from update, but opacity remains 0 and phase stays "enter"). After the delay, `effective_age = age - self._delay` drives all animation math. The hold phase start is also offset: `hold_start = self._delay + 0.4`.

### Pre-existing Bugs Fixed

1. `dice_effects.py` lines 2 and 307: triple-encoded em-dashes (`\xc3\xa2\xe2\x82\xac\xe2\x80\x9d`) replaced with ASCII `--`.
2. `discord_bot.py` line 95/101: docstring `"""` on same line as `AVRAE_BOT_ID` class variable caused SyntaxError. Added newline separator.

### Encoding Rule (Reminder)

ASCII only in Python string literals. All deliverables verified clean. Run `python ascii_guard.py` before committing.

---

## Codebase Size (Post-Session)

Approx 9,800 lines across 17 Python modules (16 existing + 1 new). dice_overlay.py is now 972 lines, dice_effects.py is 840 lines.

---

## Next Up

**Immediate (small tasks):**
- Wire `state=` into DiceRollOverlay construction in app_window.py (one-liner)
- Add display mode control to Discord tab settings (dropdown or radio buttons)
- Download and prep Chequered Ink d20 assets

**Brief 005-B:**
- Avrae parser for advantage/disadvantage detection (`2d20kh1`/`2d20kl1` patterns)
- Pack selector dropdown per PC slot in the UI

**Future briefs:**
- Damage dice (d4/d6/d8/d10/d12) with multi-die simultaneous rendering
- Sound effects integration with dice bounce/land events
- Initiative card shake when damage lands on a combatant
