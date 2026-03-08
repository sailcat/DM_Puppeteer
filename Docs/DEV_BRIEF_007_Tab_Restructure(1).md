# DEV BRIEF 007 — Tab Restructure & Settings Gear

**From:** DM Puppeteer PMO
**Date:** March 7, 2026
**Priority:** Next up (after Sunday live test validation)
**Scope:** UI-only refactor. No new backend logic. No model changes.

---

## Context

DM Puppeteer currently has 5 tabs: Puppet, OBS Control, PC Portraits, Discord, DM Combat. This was organic growth — features landed where they fit at the time. Now that the core systems are built, we're reorganizing so every future feature has a clear home.

Key architectural context driving this restructure:
- **Stream Deck SDK plugin approach confirmed.** DM Puppeteer will register as a plugin inside the Elgato Stream Deck software (Phase 9), meaning Raph keeps his native OBS controls, media buttons, and existing deck layout. The built-in OBS operational controls (scene buttons, stream/record toggles, audio levels) are no longer needed.
- **Discord voice receive is the primary audio path** for player portraits, not OBS audio sources. The per-slot OBS audio dropdown is vestigial.
- **Voice preset buttons are vestigial** after Brief 002's adaptive thresholds. The tuning values stay in the model but the UI buttons add clutter without value.

---

## Target Layout

### Before (5 tabs)

```
[Puppet] [OBS Control] [PC Portraits] [Discord] [DM Combat]
```

### After (4 tabs + Settings Gear)

```
[Characters] [Portraits] [Dice] [Combat]  ⚙
```

**Left sidebar:** Character Library (unchanged — stays as a fixed 160px panel)

---

## Tab Specifications

### Tab 1: "Characters" (renamed from "Puppet")

**What stays:**
- Character editor group: Name input, Save/New buttons
- Sprite frame drop zones (idle, blink, talk, talk+blink)
- Lip sync frame drop zones (mouth_AH, mouth_EE, mouth_OO)
- Stream Deck grid (DeckGrid widget) with drag-to-assign, click-to-activate
- Stream Deck connection status + Connect button
- Stream Deck mode selector (Direct USB / Hotkey)
- Overlay show/hide toggle button

**What moves out:**
- Mic Sensitivity slider → Settings Gear
- Mic device selector → Settings Gear
- Audio level bar → Settings Gear

**Notes:** This tab is pre-session setup. Daniel comes here to configure characters and Stream Deck assignments before the game starts. Once the session is live, this tab is rarely visited.

---

### Tab 2: "Portraits" (name preserved — NOT "Players")

**What stays:**
- Portrait overlay controls: Mode dropdown (strip/individual), Show Portraits toggle
- Size, Spacing, Dim, Shade sliders
- Discord Voice Detection group: Voice channel dropdown, Refresh, Join Voice, status
- Player Slots (PCSlotEditor cards in scroll area)
- Add Player Slot button

**What's removed from PCSlotEditor (UI only — model fields preserved):**
- **Row 2: OBS audio source dropdown** — Remove the `audio_combo` and its "Audio:" label. The Sensitivity slider from this row moves to Row 3 (see below). The `obs_audio_source` field persists in PCSlot model and serialization for backward compat.
- **Row 5: Voice preset buttons** — Remove the entire row (Default/Responsive/Smooth/Dramatic). The `voice_attack_ms`, `voice_decay_ms`, `voice_smoothing`, and `voice_adaptive_multiplier` fields persist in model. If we ever want advanced per-player tuning, we'll add it to a future settings panel, not inline on the card.

**PCSlotEditor row layout after cleanup (6 rows → 4 rows):**

| Row | Contents |
|-----|----------|
| 1 | Name input, Character picker |
| 2 | Discord user dropdown, DM (use local mic) checkbox |
| 3 | Color picker, Intensity % slider, Sensitivity slider, level meter, X (remove) |
| 4 | Dice pack dropdown, Dice color dropdown |

**Relabeling:**
- Row 3 glow controls: "Color" picker + "Intensity %" slider (current labels are "Glow:" — make it clearer)
- Sensitivity slider: currently labeled "Sens:" in old Row 2 — relabel to "Sensitivity:" in new Row 3

**Other cleanup:**
- Update the info text at the bottom of the tab. Current text references OBS audio sources. New text should reference Discord voice detection as the audio path.
- `PCSlotEditor.setFixedHeight(184)` — reduce to fit the new 4-row layout (roughly 130-140px, tune visually)

---

### Tab 3: "Dice" (new — carved from Discord tab)

**Extracted from the Discord tab's "Dice Roll Overlay" group:**
- Show Dice Overlay toggle button
- Display Time slider + label
- Slide From dropdown (left/right)
- Stack From dropdown (top/bottom)
- Display Mode dropdown (dice_and_card / card_only / dice_only)
- Scale slider + label
- Recent Rolls log (scroll area)
- Send Test Roll button

**Layout:** Transplant the entire `dice_group` QGroupBox from `_build_discord_tab()` into a new `_build_dice_tab()` method. No rearrangement needed — the existing layout is clean.

**What does NOT come here:**
- Discord bot connection settings → Settings Gear
- Bot Setup Guide → Settings Gear (or remove entirely — it's a one-time setup reference)

---

### Tab 4: "Combat" (renamed from "DM Combat")

**No changes.** The CombatTab widget is already self-contained. Just rename the tab label from "DM Combat" to "Combat".

---

### Settings Gear (⚙ — persistent, always visible)

**Implementation:** A small gear icon button placed to the right of the tab bar (not inside it). Clicking it opens a dialog (QDialog) or a slide-out panel. A dialog is simpler and more Raph-proof — it's a familiar pattern.

**Contains three groups:**

#### Discord Bot Connection
- Bot Token input (password field)
- Roll Channel ID input
- Connect/Disconnect button
- Auto-connect checkbox
- Connection status label
- Bot Setup Guide text (condensed, or a "Show Guide" expandable)

#### OBS Connection
- Host input
- Port input
- Password input
- Connect/Disconnect button
- Auto-connect checkbox
- Connection status label

#### Microphone
- Mic device selector dropdown
- Mic sensitivity slider
- Audio level bar

**Notes:**
- All three groups use the same signal/slot connections as their current tab implementations. This is pure UI relocation — the backend wiring doesn't change.
- The OBS connection is needed for character-linked actions (auto scene switch, source show/hide). Only the operational controls (scene list, stream/record toggles) are removed.
- The Settings dialog should save-on-change (same pattern as the rest of the app — no "OK/Cancel" buttons needed).

---

## What Gets Removed Entirely

| Element | Current Location | Reason |
|---------|-----------------|--------|
| OBS scene buttons list | OBS Control tab | Raph uses native Stream Deck OBS plugin |
| Stream/Record toggle buttons | OBS Control tab | Same — native Stream Deck controls |
| OBS audio level meters | OBS Control tab | Voice receive replaced OBS audio path |
| Current Scene label | OBS Control tab | Not needed without scene list |
| Scene placeholder text | OBS Control tab | Tab is gone |
| Bot Setup Guide (full version) | Discord tab | Moves to Settings Gear (condensed) |

**Backend methods that lose their UI but remain functional:**
- `_on_obs_scenes_updated()` — still fires, but no scene buttons to rebuild. Can be left as a no-op or removed.
- `_on_obs_scene_switched()` — still needed for `_run_character_obs_actions()`. Remove the scene button highlighting logic.
- `_on_obs_audio_levels()` — still dispatches to `pc_manager.update_audio_levels()` for any residual OBS audio use. The PC slot editor level meters still work for Discord voice levels.
- `_on_obs_inputs_updated()` — was populating per-slot audio dropdowns. Can be simplified or removed since dropdowns are gone.
- `_rebuild_scene_buttons()`, `_clear_scene_buttons()` — remove entirely.
- `_obs_refresh_scenes()` — remove (no UI trigger).

---

## Implementation Steps

### Step 1: Create Settings Dialog

Build a new `SettingsDialog(QDialog)` class. Can live in `app_window.py` or in a new `settings_dialog.py` — Dev's choice.

Three QGroupBox sections: Discord, OBS, Microphone. Wire to the same state fields and handler methods. Add a gear icon button to the right of the tab bar in `_build_ui()`.

### Step 2: Build Dice Tab

Create `_build_dice_tab()` by extracting the dice group from `_build_discord_tab()`. All dice-related instance variables (`self.dice_show_btn`, `self.dice_time_slider`, `self.dice_side_combo`, etc.) stay as instance vars on AppWindow — just built in a different method.

### Step 3: Reorganize Characters Tab

Rename `_build_puppet_tab()` to `_build_characters_tab()`. Remove the Settings group (mic controls move to Settings Dialog). Keep everything else.

### Step 4: Clean Up Portraits Tab

In `_build_pc_tab()`:
- Update the info text at the bottom
- No structural changes to the tab itself — the PCSlotEditor changes handle the cleanup

### Step 5: Clean Up PCSlotEditor

In `widgets.py`:
- Remove Row 2 (OBS audio combo + label). Move Sensitivity slider to Row 3.
- Remove Row 5 (voice preset buttons + all preset logic).
- Relabel Row 3: "Color" picker, "Intensity %" slider, "Sensitivity" slider, level meter, X button.
- Reduce `setFixedHeight()` to ~135px (tune visually).
- Remove `populate_audio_sources()` method (no longer called).
- Keep `_apply_voice_preset()`, `_detect_current_preset()`, `_style_preset_buttons()` — actually, remove these too. They only served the preset buttons. The voice tuning values are preserved in the model and still applied by voice_receiver.py at runtime.

### Step 6: Remove OBS Tab

Delete `_build_obs_tab()` entirely. Remove the `self.tabs.addTab()` call for it.

Clean up orphaned methods:
- Remove `_rebuild_scene_buttons()`, `_clear_scene_buttons()`, `_obs_refresh_scenes()`
- Simplify `_on_obs_scene_switched()` — remove button highlighting, keep the state tracking if needed for character-linked actions
- Simplify `_on_obs_inputs_updated()` — remove PC slot dropdown population
- Keep `_on_obs_connection()` — still needed, but update it to set status in the Settings Dialog instead of the removed tab

### Step 7: Update Tab Construction

In `_build_ui()`, replace:
```python
self.tabs.addTab(self._build_puppet_tab(), "Puppet")
self.tabs.addTab(self._build_obs_tab(), "OBS Control")
self.tabs.addTab(self._build_pc_tab(), "PC Portraits")
self.tabs.addTab(self._build_discord_tab(), "Discord")
# ... combat tab ...
self.tabs.addTab(self.combat_tab, "DM Combat")
```

With:
```python
self.tabs.addTab(self._build_characters_tab(), "Characters")
self.tabs.addTab(self._build_pc_tab(), "Portraits")
self.tabs.addTab(self._build_dice_tab(), "Dice")
# ... combat tab ...
self.tabs.addTab(self.combat_tab, "Combat")
# Settings gear button added to the right of the tab bar
```

### Step 8: Status Bar Connection Indicators

Add persistent connection status to the app's status bar so Daniel/Raph can see at a glance whether services are connected without opening Settings.

**Format:** Small text indicators at the right end of the status bar:
- `OBS: ✓` (green) / `OBS: ✗` (dim) — updates via `_on_obs_connection()`
- `Discord: ✓` (green) / `Discord: ✗` (dim) — updates via `_on_discord_connection()`
- Current OBS scene name (e.g., `Scene: Gameplay`) — updates via `_on_obs_scene_switched()`. Shows `--` when disconnected.

This is lightweight — three QLabel widgets in the status bar, updated by existing signal handlers. Confirms that character-linked OBS actions are firing (scene name changes visibly) and that the Discord bot is alive (dice rolls will work).

### Step 9: Verify & Test

- All 4 tabs render without errors
- Settings Gear opens, shows all three groups, controls work
- Discord bot connects via Settings Gear
- OBS connects via Settings Gear
- Mic selector and sensitivity work from Settings Gear
- Dice overlay controls work from new Dice tab
- Test Roll button works
- PCSlotEditor displays cleanly with 4 rows
- Character-linked OBS actions still fire on character activation
- Portrait overlay works (voice detection, glow, dim/shade)
- Status bar shows OBS/Discord connection state and current scene
- All state persists across app restart

---

## Scope Boundaries

**IN scope:**
- Tab rename and reorganization
- OBS operational controls removal
- PCSlotEditor cleanup (rows 2 and 5)
- Settings Gear dialog
- Status bar connection indicators (OBS, Discord, current scene)
- Orphaned method cleanup

**OUT of scope (do not build):**
- Session bookmarking (next brief)
- Character library slide-out drawer (future UX enhancement)
- Stream Deck grid slide-out drawer (grid's long-term home is the plugin interface, not a drawer)
- Stream Deck SDK plugin migration (Phase 9)
- Any new features or backend logic
- Model changes

---

## Files Modified

| File | Changes |
|------|---------|
| `app_window.py` | Tab construction rewrite, Settings Dialog, OBS tab removal, method cleanup |
| `widgets.py` | PCSlotEditor row cleanup, preset removal, height adjustment |

**No changes to:** `models.py`, `combat_tab.py`, `dice_overlay.py`, `dice_effects.py`, `dice_assets.py`, `discord_bot.py`, `voice_receiver.py`, `pc_overlay.py`, `overlay.py`, `initiative_overlay.py`, `obs.py`, `audio.py`, `hotkeys.py`, `deck_hw.py`, `bestiary.py`, `srd_bestiary.py`, `ascii_guard.py`, `voice_diagnostics.py`

---

## Risk Notes

- **Backward compat:** PCSlot.obs_audio_source persists in JSON. Old save files load fine. The field just isn't exposed in the UI anymore.
- **Stream Deck grid on Characters tab:** The grid stays here for now. Its long-term home is the Stream Deck plugin interface (Phase 9), where button configuration happens inside Elgato's software via Property Inspector panels. The current DeckGrid widget will likely become a simple status readout or be removed entirely at that stage. No slide-out drawer or other grid relocation work is warranted before the plugin migration.
- **Row 3 density in PCSlotEditor:** The new Row 3 packs Color, Intensity, Sensitivity, level meter, and X button into one row. If it feels cramped at certain DPI settings, the level meter can drop to its own line. Tune visually.
