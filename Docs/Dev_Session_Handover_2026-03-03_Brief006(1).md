# Dev Session Handover -- March 3, 2026

**Project:** DM Puppeteer
**Session scope:** Dev Brief 006 -- Dice UX Enhancements
**Files delivered:** 6 files (all modified, no new files)

---

## What Was Accomplished

### Brief 006: All Five Features Implemented

Built all five dice UX enhancements specified in the brief: dice scale slider, per-player entry position, display mode dropdown, per-player pack selector, and advantage/disadvantage parser.

---

### Part A: Dice Scale Slider

**models.py** -- Added `dice_scale: float = 1.0` to AppState with save/load support. Backward-compatible default of 1.0.

**dice_effects.py** -- `DiceSprite.DIE_SIZE` renamed to `BASE_DIE_SIZE` (class constant). New `die_size` instance variable computed as `int(BASE_DIE_SIZE * scale)`. Constructor now accepts `scale: float = 1.0` parameter. All internal `self.DIE_SIZE` references updated to `self.die_size`. Paint method uses `self.die_size * self.scale` (global scale * animation scale).

**dice_overlay.py** -- Constants `CARD_WIDTH` / `CARD_HEIGHT` renamed to `BASE_CARD_WIDTH` / `BASE_CARD_HEIGHT`. New `card_width` and `card_height` properties that apply `state.dice_scale`. New `_dice_zone_height` property for the scaled 400px dice zone. New `_scaled_font()` helper that scales all QFont sizes proportionally (min size 6pt). `_apply_sizing()` now scales all window dimensions. `_card_rect()` uses scaled properties. `_random_landing_position()` uses scaled margin and zone height. `add_roll()` passes `scale` to DiceSprite constructor and uses scaled die size for advantage/disadvantage offset. Both `_paint_card()` and `_paint_card_body()` use `_scaled_font()` for all text and scale all layout offsets (padding, margins, rects). New `set_scale()` method.

**app_window.py** -- Scale slider (50-200 range, maps to 0.5x-2.0x) with live label update. Handler calls `dice_overlay.set_scale()` and saves state.

### Part B: Per-Player Entry Position

**dice_overlay.py** -- New `_get_entry_vector_for_character()` calculates the direction from the dice overlay center to the matched player's portrait position. Handles both strip mode (calculated from index * size + spacing) and individual mode (saved x/y positions). Returns (side, norm_x, norm_y). New `_vector_to_edge()` converts the direction vector to "left", "right", or "top" entry edge based on dominant axis. `add_roll()` calls both methods and passes the per-player side to `DiceRollCard(slide_from=...)` and entry edge to `DiceSprite(entry_edge=...)`. Falls back to global `_side` for unmatched characters (NPC/DM rolls).

### Part C: Display Mode Dropdown

**app_window.py** -- `dice_mode_combo` added to the layout options row alongside Slide From and Stack From. Three options: `dice_and_card`, `card_only`, `dice_only`. Handler calls existing `dice_overlay.set_display_mode()` and saves state.

### Part D: Per-Player Pack Selector

**widgets.py** -- `PCSlotEditor.__init__()` now accepts `dice_packs: list` and `dice_colors: list` parameters. New Row 6 with two dropdowns: dice pack (with "(default)" sentinel) and dice color (with "(auto)" sentinel). New `_on_dice_change()` handler writes to `slot.dice_pack` and `slot.dice_color`. Fixed height bumped from 158 to 184.

**app_window.py** -- `_add_pc_slot_editor()` now queries `dice_overlay.pack_loader.available_packs()` and `available_colors()` and passes them to the PCSlotEditor constructor.

### Part E: Advantage/Disadvantage Parser

**discord_bot.py** -- Four new class-level regex patterns on AvraeParser: `ADV_PATTERN`, `DIS_PATTERN`, `ADV_ALT_PATTERN`, `DIS_ALT_PATTERN`. Both `_parse_embed()` and `_parse_text()` now check the raw description/formula against all four patterns. When matched, sets `event.is_advantage` or `event.is_disadvantage`, overwrites `event.natural_roll` with the kept die, and sets `event.secondary_roll` with the dropped die. TODO comment added for D&D Beyond GameLog relay format verification.

Also added `event.die_type` assignment in `_parse_text()` (was previously unset, now populated from the parsed die type string).

---

### Bonus Fix

**dice_overlay.py line 860** (original) -- Replaced Unicode emoji `\U0001f3b2` and arrow `\u2192` with ASCII equivalents `[d20]` and `->` in the natural roll indicator. These were escape sequences (not corrupted bytes) but violated the ASCII-only string rule.

---

## Files Delivered

| File | Status | Lines | Key Changes |
|------|--------|-------|-------------|
| `models.py` | MODIFIED | 761 (was 758) | AppState +1 field (dice_scale), save/load |
| `dice_overlay.py` | MODIFIED | 1121 (was 972) | Scale properties, scaled fonts, per-player entry vector, set_scale(), _scaled_font(), _dice_zone_height, ASCII fix |
| `dice_effects.py` | MODIFIED | 842 (was 840) | DiceSprite scale parameter, BASE_DIE_SIZE rename, die_size instance variable |
| `app_window.py` | MODIFIED | 1793 (was 1747) | Display mode combo, scale slider + label, dice_packs/colors pass-through to PCSlotEditor |
| `widgets.py` | MODIFIED | 1067 (was 1029) | PCSlotEditor Row 6 dice pack/color dropdowns, _on_dice_change handler, height bump |
| `discord_bot.py` | MODIFIED | 821 (was 774) | 4 adv/disadv regex patterns, detection in _parse_embed + _parse_text, die_type assignment fix |

---

## What's NOT Done (Noted for Future)

- **D&D Beyond GameLog relay format** -- The parser handles standard Avrae command output (`2d20kh1`/`2d20kl1`). D&D Beyond relay may use a different format. TODO comment added. Capture samples via `avrae_debug.txt` during live sessions.

- **Scale persistence on overlay reopen** -- The scale is saved in state and applied when the slider is moved, but if the overlay is hidden and re-shown, scale is already persisted via the `card_width`/`card_height` properties reading from `state.dice_scale`. No issue expected.

- **Per-player landing zone** -- Brief 006 "Future Enhancements" item. Dice currently land at random positions; could land near the player's portrait area.

- **Entry animation trail** -- Brief 006 "Future Enhancements" item. Colored streak matching glow color as dice fly in.

---

## Architecture Notes for Next Dev

### Scale Flow

```
state.dice_scale (0.5 - 2.0)
  -> DiceRollOverlay.card_width / card_height (properties)
  -> DiceRollOverlay._dice_zone_height (property)
  -> DiceRollOverlay._scaled_font() (helper)
  -> DiceSprite(scale=...) -> self.die_size (instance var)
  -> _apply_sizing() -> window resize
  -> paintEvent -> all rects and fonts use scaled values
```

Changing the slider calls `set_scale()` which updates state and calls `_apply_sizing()`. All rendering reads scale from state on every paint, so it's instantly responsive.

### Per-Player Entry Flow

```
add_roll(event)
  -> _get_entry_vector_for_character(event.character_name)
     -> match name against pc_slots (player_name or character.name)
     -> calculate portrait center (strip mode: index-based, individual: saved pos)
     -> compute direction vector from portrait to dice overlay center
     -> return (side, norm_x, norm_y)
  -> _vector_to_edge(norm_x, norm_y) -> "left" / "right" / "top"
  -> DiceRollCard(slide_from=side)
  -> DiceSprite(entry_edge=edge)
```

Fallback: if no PC slot matches, returns `self._side` (global default). NPC/DM rolls and unknown names gracefully degrade.

### Advantage/Disadvantage Parser

Four regex variants for belt-and-suspenders matching:
- `ADV_PATTERN` / `DIS_PATTERN` -- tight match: `2d20kh1 (**15**, ~~8~~)`
- `ADV_ALT_PATTERN` / `DIS_ALT_PATTERN` -- loose match with `.*?` between `kh1`/`kl1` and the values

Both `_parse_embed()` and `_parse_text()` check all four. The kept die becomes `natural_roll`, the dropped die becomes `secondary_roll`. Rendering was already built in Brief 005 (dual dice with secondary dimming).

### Encoding

All 6 delivered files verified clean ASCII. No non-ASCII byte sequences. The Unicode emoji/arrow on the old line 860 was replaced with ASCII equivalents.

---

## Codebase Size (Post-Session)

Approx 11,400 lines across 17 Python modules (counting dice_assets.py at 464 from Brief 005). dice_overlay.py is now the largest file at 1,121 lines.

---

## Next Up

**Testing checklist from the brief (Step 8):**
1. Scale: Move slider 0.5x to 2.0x -- cards and dice resize
2. Entry position: Roll for different PCs -- dice enter from different edges
3. Fallback: Roll for unknown character -- uses default side
4. Display mode: Toggle all three modes -- overlay resizes
5. Pack selector: Assign different packs per PC slot
6. Color auto: Leave as "(auto)" -- matches glow color
7. Advantage: Trigger `2d20kh1` -- two dice, dropped one dimmed
8. Disadvantage: Trigger `2d20kl1` -- same visual
9. Combined: All features active simultaneously

**Future briefs:**
- Damage dice (d4/d6/d8/d10/d12) multi-die rendering
- Sound effects integration with dice bounce/land events
- Initiative Tracker phase (BG3 overlay, DM Combat tab, Avrae init commands)
