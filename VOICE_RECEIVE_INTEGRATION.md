# Discord Voice Receive — Integration Guide

## Overview

This adds Discord voice speaking detection to PC portraits. When a player speaks in Discord voice, their portrait bounces/brightens using the existing animation system. The architecture is future-proofed for vowel detection — the signal carries `(slot_index, rms, vowel)` where `vowel` is `""` until that feature is added.

## Dependency Change

**IMPORTANT:** You need to switch from `discord.py` to `py-cord` for voice receive support. They're API-compatible for everything you're currently using.

```bash
pip uninstall discord.py
pip install py-cord[voice]
```

This installs py-cord (the fork with voice receive) plus PyNaCl for Opus decryption. All your existing `import discord` code works unchanged.

If you want to verify which library is installed:
```bash
python -c "import discord; print(discord.__title__, discord.__version__)"
```
- `discord.py 2.x` → Rapptz library (no voice receive)
- `Pycord 2.x` → py-cord (has voice receive) ✓

## New Files

### `dm_puppeteer/voice_receiver.py` — NEW
Drop this into the `dm_puppeteer/` package folder alongside `discord_bot.py`.

## Modified Files

### `dm_puppeteer/discord_bot.py` — REPLACED
Full replacement file provided. Changes from original:
- Added `voice_receiver` import
- `_DiscordBotRunner`: voice client tracking, command queue, join/leave/update methods
- `DiscordBridge`: `player_audio_update`, `voice_connected`, `voice_disconnected`, `voice_channels_updated` signals
- `DiscordBridge`: `join_voice()`, `leave_voice()`, `update_player_map()`, `request_voice_channels()` methods
- `_poll_events()`: handles new event types

### `dm_puppeteer/models.py` — MODIFIED
- `PCSlot`: added `discord_user_id: int = 0` field + serialization
- `AppState`: added `discord_voice_channel_id: int = 0` field + serialization

### `dm_puppeteer/pc_overlay.py` — MODIFIED
- `PCOverlayManager`: added `_voice_active` and `_voice_slots` tracking
- `update_audio_levels()`: now skips voice-active slots
- NEW `update_player_audio(slot_index, rms, vowel)`: Discord audio input
- NEW `set_voice_active(active, voice_slot_indices)`: toggle voice/OBS per slot

### `dm_puppeteer/app_window.py` — MODIFIED (manual edits below)

---

## app_window.py — Step-by-Step Modifications

### 1. Add imports (top of file, near existing imports)

After `from .discord_bot import DiscordBridge, DISCORD_AVAILABLE, DiceRollEvent, VoiceStateEvent`:

```python
from .voice_receiver import VOICE_RECEIVE_AVAILABLE
```

### 2. Connect new signals (in `__init__`, after existing discord signal connections)

After line ~78 (`self.discord.error_occurred.connect(self._on_discord_error)`), add:

```python
        # Voice receive signals
        self.discord.player_audio_update.connect(self._on_player_audio)
        self.discord.voice_connected.connect(self._on_voice_connected)
        self.discord.voice_disconnected.connect(self._on_voice_disconnected)
        self.discord.voice_channels_updated.connect(self._on_voice_channels_updated)
```

### 3. Add voice controls to the PC Portraits tab

In `_build_pc_tab()`, after the existing top_group settings and before the slot editors scroll area, add a new voice group. Find the line where `top_group.setLayout(top_vbox)` is called and add this BEFORE it:

```python
        # --- Voice Receive Controls ---
        voice_group = QGroupBox("Discord Voice Detection")
        voice_layout = QVBoxLayout()

        voice_row1 = QHBoxLayout()
        voice_row1.addWidget(QLabel("Voice Channel:"))
        self.voice_channel_combo = QComboBox()
        self.voice_channel_combo.setFixedWidth(250)
        self.voice_channel_combo.setPlaceholderText("Connect to Discord first...")
        voice_row1.addWidget(self.voice_channel_combo)

        self.voice_refresh_btn = QPushButton("🔄")
        self.voice_refresh_btn.setFixedWidth(32)
        self.voice_refresh_btn.setToolTip("Refresh voice channels")
        self.voice_refresh_btn.clicked.connect(self._refresh_voice_channels)
        voice_row1.addWidget(self.voice_refresh_btn)

        voice_row1.addStretch()

        self.voice_join_btn = QPushButton("🎙  Join Voice")
        self.voice_join_btn.setCheckable(True)
        self.voice_join_btn.setFixedWidth(130)
        self.voice_join_btn.clicked.connect(self._toggle_voice_receive)
        voice_row1.addWidget(self.voice_join_btn)

        self.voice_status_label = QLabel("")
        self.voice_status_label.setStyleSheet("color: #888; font-size: 11px;")
        voice_row1.addWidget(self.voice_status_label)

        voice_layout.addLayout(voice_row1)

        if not VOICE_RECEIVE_AVAILABLE:
            notice = QLabel(
                "💡 Voice detection requires py-cord[voice].\n"
                "Run: pip install py-cord[voice]")
            notice.setStyleSheet("color: #cc8800; padding: 4px;")
            notice.setWordWrap(True)
            voice_layout.addWidget(notice)

        voice_group.setLayout(voice_layout)
        top_vbox.addWidget(voice_group)
```

### 4. Add Discord User dropdown to PC slot editors

In your `PCSlotEditor` widget (defined in `widgets.py` or inline in `app_window.py`), add a Discord User dropdown. Find where each slot editor is built with the OBS audio source dropdown. After the existing audio source dropdown section, add:

```python
        # Discord user mapping
        discord_row = QHBoxLayout()
        discord_row.addWidget(QLabel("Discord User:"))
        self.discord_user_combo = QComboBox()
        self.discord_user_combo.setFixedWidth(180)
        self.discord_user_combo.addItem("(none)", 0)
        self.discord_user_combo.setPlaceholderText("Select Discord user...")
        self.discord_user_combo.currentIndexChanged.connect(
            self._on_discord_user_changed)
        discord_row.addWidget(self.discord_user_combo)
        discord_row.addStretch()
        # Add discord_row to the slot editor's layout
```

And the handler:
```python
    def _on_discord_user_changed(self, index):
        user_id = self.discord_user_combo.currentData() or 0
        self.slot.discord_user_id = user_id
```

Also add a method to populate it:
```python
    def populate_discord_users(self, members: list):
        """Populate the Discord user dropdown from voice channel members.
        
        Args:
            members: list of {"id": int, "name": str} dicts
        """
        current_id = self.slot.discord_user_id
        self.discord_user_combo.blockSignals(True)
        self.discord_user_combo.clear()
        self.discord_user_combo.addItem("(none)", 0)
        selected_index = 0
        for i, member in enumerate(members):
            self.discord_user_combo.addItem(member["name"], member["id"])
            if member["id"] == current_id:
                selected_index = i + 1
        self.discord_user_combo.setCurrentIndex(selected_index)
        self.discord_user_combo.blockSignals(False)
```

### 5. Add handler methods to AppWindow

Add these methods to the `AppWindow` class (near the existing Discord handlers around line ~1189):

```python
    # ------------------------------------------------------------------
    # Voice Receive Handlers
    # ------------------------------------------------------------------

    def _refresh_voice_channels(self):
        """Request voice channel list from Discord."""
        if not self.discord.is_connected:
            self.statusBar().showMessage("Connect to Discord first", 3000)
            return
        self.discord.request_voice_channels()

    def _on_voice_channels_updated(self, channels: list):
        """Voice channel list received from Discord."""
        self.voice_channel_combo.blockSignals(True)
        self.voice_channel_combo.clear()
        self._voice_channel_data = channels  # store for member lookups

        for ch in channels:
            label = f"{ch['name']} ({ch['guild']}) — {ch['member_count']} members"
            self.voice_channel_combo.addItem(label, ch["id"])

            # Auto-select saved channel
            if ch["id"] == self.state.discord_voice_channel_id:
                self.voice_channel_combo.setCurrentIndex(
                    self.voice_channel_combo.count() - 1)

        self.voice_channel_combo.blockSignals(False)

        # Update Discord user dropdowns in slot editors
        self._update_discord_user_dropdowns()

    def _update_discord_user_dropdowns(self):
        """Populate Discord user dropdowns from the selected voice channel."""
        idx = self.voice_channel_combo.currentIndex()
        if idx < 0 or not hasattr(self, '_voice_channel_data'):
            return

        channel_id = self.voice_channel_combo.currentData()
        members = []
        for ch in self._voice_channel_data:
            if ch["id"] == channel_id:
                members = ch.get("members", [])
                break

        for editor in self._pc_slot_editors:
            if hasattr(editor, 'populate_discord_users'):
                editor.populate_discord_users(members)

    def _toggle_voice_receive(self, checked):
        """Join or leave Discord voice channel."""
        if checked:
            # Join voice
            idx = self.voice_channel_combo.currentIndex()
            if idx < 0:
                self.statusBar().showMessage(
                    "Select a voice channel first", 3000)
                self.voice_join_btn.setChecked(False)
                return

            channel_id = self.voice_channel_combo.currentData()
            if not channel_id:
                self.voice_join_btn.setChecked(False)
                return

            # Build player map from slot editors
            player_map = {}
            voice_slots = []
            for i, slot in enumerate(self.state.pc_slots):
                if slot.discord_user_id > 0:
                    player_map[slot.discord_user_id] = i
                    voice_slots.append(i)

            if not player_map:
                self.statusBar().showMessage(
                    "Assign Discord users to PC slots first", 3000)
                self.voice_join_btn.setChecked(False)
                return

            # Save channel selection
            self.state.discord_voice_channel_id = channel_id
            self._save_state()

            # Join and start receiving
            self.discord.join_voice(channel_id, player_map)
            self.voice_join_btn.setText("⏹  Leave Voice")
            self.voice_status_label.setText("Joining...")
            self.voice_status_label.setStyleSheet("color: #cc8800;")
        else:
            # Leave voice
            self.discord.leave_voice()
            self.voice_join_btn.setText("🎙  Join Voice")

    def _on_voice_connected(self, info: dict):
        """Bot joined voice channel and is receiving audio."""
        self.pc_manager.set_voice_active(True)
        self.voice_join_btn.setChecked(True)
        self.voice_join_btn.setText("⏹  Leave Voice")

        player_count = info.get("player_count", 0)
        channel_name = info.get("channel_name", "?")
        self.voice_status_label.setText(
            f"🟢 Listening in #{channel_name} ({player_count} players mapped)")
        self.voice_status_label.setStyleSheet("color: #00cc66;")

        self.statusBar().showMessage(
            f"🎙 Voice receive active — {channel_name}", 3000)

    def _on_voice_disconnected(self):
        """Bot left the voice channel."""
        self.pc_manager.set_voice_active(False)
        self.voice_join_btn.setChecked(False)
        self.voice_join_btn.setText("🎙  Join Voice")
        self.voice_status_label.setText("")

        self.statusBar().showMessage("Voice receive stopped", 3000)

    def _on_player_audio(self, slot_index: int, rms: float, vowel: str):
        """Per-player audio received from Discord voice.
        
        Routes to the PC overlay manager, which uses RMS to set
        speaking state (and in the future, vowel for mouth shapes).
        """
        self.pc_manager.update_player_audio(slot_index, rms, vowel)
```

### 6. Auto-refresh voice channels on Discord connect

In the existing `_on_discord_connection()` method (around line ~1160), add a voice channel refresh when the bot connects:

```python
    def _on_discord_connection(self, connected, info):
        if connected:
            self.discord_status.setText(f"⬤  {info}")
            self.discord_status.setStyleSheet("color: #00cc66;")
            self.discord_connect_btn.setText("Disconnect")
            
            # Auto-refresh voice channels when bot connects
            QTimer.singleShot(1000, self._refresh_voice_channels)
        else:
            self.discord_status.setText(f"⬤  {info}")
            self.discord_status.setStyleSheet("color: #888;")
            self.discord_connect_btn.setText("Connect")
```

---

## Data Flow Summary

```
Discord Voice Channel (players talking)
    │
    ▼
py-cord VoiceClient (joins channel, receives Opus packets)
    │
    ▼
VoiceReceiveSink.write(data, user_id)       ← voice_receiver.py
    │  routes to correct PlayerAudioProcessor
    ▼
PlayerAudioProcessor.process_audio(pcm)     ← voice_receiver.py
    │  computes RMS (+ future vowel detection)
    │
    ▼
callback → event_queue.put(("player_audio", (slot, rms, vowel)))
    │
    ▼
DiscordBridge._poll_events()                 ← discord_bot.py (main thread)
    │  emits player_audio_update signal
    ▼
AppWindow._on_player_audio()                 ← app_window.py
    │
    ▼
PCOverlayManager.update_player_audio()       ← pc_overlay.py
    │  sets portrait.is_speaking = rms > threshold
    ▼
PCPortraitRenderer.update_state()            ← existing animation system
    │  bounce, pop-in, dim/brighten all react to is_speaking
    ▼
Portrait renders with speaking animation     ← existing paint system
```

## Testing Checklist

- [ ] `pip install py-cord[voice]` completes without error
- [ ] `python -c "import discord; print(discord.__title__)"` prints "Pycord"
- [ ] `python -c "import discord.sinks; print('Sinks available')"` works
- [ ] `python -c "import nacl; print('PyNaCl OK')"` works
- [ ] Bot connects to Discord (existing functionality unchanged)
- [ ] Dice rolls still parse and display (existing functionality unchanged)
- [ ] Voice channel dropdown populates after bot connects
- [ ] Discord user dropdowns show voice channel members
- [ ] "Join Voice" button connects bot to voice channel
- [ ] PC portraits animate when mapped players speak in Discord
- [ ] Portraits go idle when players stop speaking
- [ ] "Leave Voice" disconnects cleanly
- [ ] OBS audio still works for slots without Discord user mapping
- [ ] All state persists across restart (channel ID, user mappings)

## Graceful Degradation

| Condition | Behavior |
|-----------|----------|
| No py-cord | Info notice in UI, voice controls disabled, everything else works |
| No PyNaCl | Same as above (py-cord[voice] includes PyNaCl) |
| Discord not connected | "Connect to Discord first" on Join Voice click |
| No players in voice | Bot joins but no audio processed |
| Slot has no Discord user | Falls back to OBS audio meter for that slot |
| Voice disconnects unexpectedly | Portraits reset to idle, OBS fallback resumes |

## Future: Vowel Detection Upgrade Path

When ready to add vowel detection:

1. Create `vowel_detector.py` with `VowelDetector` class (FFT + formant analysis)
2. In `voice_receiver.py` → `PlayerAudioProcessor.__init__()`: instantiate `VowelDetector`
3. In `process_audio()`: the vowel detection call is already stubbed, just uncomment
4. The signal already carries `vowel` — `pc_overlay.py` just needs to use it for frame selection
5. No changes needed to `discord_bot.py`, `app_window.py`, or `models.py`

The entire voice receive pipeline, signal bridge, and threading model stay exactly the same.
