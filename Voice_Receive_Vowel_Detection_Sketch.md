# Voice Receive & Per-Player Vowel Detection — Architecture Sketch

## Overview

The Discord bot joins the voice channel and receives per-user decoded PCM audio.
Each player gets their own `VowelDetector` instance with independent smoothing buffers.
Audio data is bridged from the asyncio Discord thread to the Qt main thread via signals.

---

## Data Flow

```
Discord Voice Channel
    │
    ▼
discord.py VoiceClient (joins channel, receives Opus packets)
    │
    ▼
PyNaCl decrypts → Opus decodes → raw PCM (48kHz, 16-bit, stereo)
    │
    ▼
VoiceReceiver (custom Sink subclass)
    │  Receives per-user audio keyed by discord user ID
    │  Downmixes stereo → mono, resamples 48kHz → 44.1kHz (or keep 48k)
    │
    ▼
PlayerAudioProcessor (one per PC slot)
    │  Owns: VowelDetector instance + smoothing buffer
    │  Computes: RMS level + vowel shape per chunk
    │  Emits: (slot_index, rms, vowel_shape) via thread-safe queue
    │
    ▼
Qt Signal Bridge (existing pattern from discord_bot.py)
    │  player_audio_update = pyqtSignal(int, float, str)
    │                        slot_idx, rms, vowel ("AH"/"EE"/"OO"/None)
    │
    ▼
pc_overlay.py → updates portrait frame based on (rms, vowel)
```

---

## New Dependency

```
PyNaCl    — Required by discord.py for voice receive (Opus decryption)
           pip install PyNaCl
           Already an optional dep of discord.py, just not installed yet
```

Note: scipy (for VowelDetector) was already proposed. Total new deps: PyNaCl + scipy.

---

## Module: voice_receiver.py (NEW)

```python
"""
Per-player voice audio receiver and vowel detection processor.

Receives decoded PCM audio from Discord voice channel via discord.py's
AudioSink system. Each connected player gets an independent audio
processing pipeline with its own VowelDetector instance.

Threading: This runs inside the Discord bot's asyncio thread.
All Qt communication goes through the thread-safe event queue.
"""

import numpy as np
from typing import Dict, Optional, Callable
from dataclasses import dataclass, field

# discord.py voice receive imports
import discord

from dm_puppeteer.vowel_detector import VowelDetector


# ──────────────────────────────────────────────
# Per-Player Processor
# ──────────────────────────────────────────────

@dataclass
class PlayerAudioProcessor:
    """
    Independent audio processing pipeline for one player.
    
    Each player gets their own VowelDetector + smoothing buffer
    so Player A's "AHHH" doesn't bleed into Player B's animation.
    """
    discord_user_id: int
    slot_index: int                     # Which PC slot this maps to
    detector: VowelDetector = field(default_factory=VowelDetector)
    
    # Smoothing: hold vowel for N consecutive detections before switching
    _vowel_buffer: list = field(default_factory=list)
    _buffer_size: int = 3               # Frames before vowel change commits
    _current_vowel: Optional[str] = None
    
    def process_chunk(self, pcm_data: bytes) -> tuple[float, Optional[str]]:
        """
        Process a chunk of PCM audio for this player.
        
        Args:
            pcm_data: Raw PCM bytes from discord.py (48kHz, 16-bit signed, stereo)
            
        Returns:
            (rms_level, vowel_shape) where vowel is 'AH', 'EE', 'OO', or None
        """
        # Convert bytes → numpy float array
        # discord.py voice receive: 48kHz, 16-bit signed LE, stereo
        samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32)
        
        # Stereo → mono (average channels)
        if len(samples) % 2 == 0:
            samples = samples.reshape(-1, 2).mean(axis=1)
        
        # Normalize to [-1.0, 1.0]
        samples = samples / 32768.0
        
        # RMS level for speaking detection
        rms = float(np.sqrt(np.mean(samples ** 2)))
        
        # Vowel detection (VowelDetector handles its own silence threshold)
        raw_vowel = self.detector.analyze_chunk(samples)
        
        # Smooth vowel changes to prevent flicker
        vowel = self._smooth_vowel(raw_vowel)
        
        return rms, vowel
    
    def _smooth_vowel(self, raw_vowel: Optional[str]) -> Optional[str]:
        """
        Prevent flickering by requiring N consecutive same-vowel detections.
        
        Logic:
        - If silent (None), clear buffer and return None immediately
        - If new vowel matches current, keep current (no change)
        - If new vowel differs, buffer it. Only switch after N consistent readings.
        """
        if raw_vowel is None:
            self._vowel_buffer.clear()
            self._current_vowel = None
            return None
        
        # Same as current — stable, just keep it
        if raw_vowel == self._current_vowel:
            self._vowel_buffer.clear()
            return self._current_vowel
        
        # Different vowel — buffer it
        self._vowel_buffer.append(raw_vowel)
        
        # Count how many of the last N readings are this new vowel
        if len(self._vowel_buffer) > self._buffer_size:
            self._vowel_buffer.pop(0)
        
        # Only switch if the new vowel dominates the buffer
        if self._vowel_buffer.count(raw_vowel) >= self._buffer_size:
            self._current_vowel = raw_vowel
            self._vowel_buffer.clear()
            return self._current_vowel
        
        # Not enough evidence yet — hold previous vowel
        return self._current_vowel
    
    def reset(self):
        """Clear state when player disconnects or audio stops."""
        self._vowel_buffer.clear()
        self._current_vowel = None


# ──────────────────────────────────────────────
# Discord Audio Sink (receives per-user audio)
# ──────────────────────────────────────────────

class VoiceReceiveSink(discord.sinks.Sink):
    """
    Custom discord.py Sink that routes per-user audio to PlayerAudioProcessors.
    
    discord.py voice receive calls write() with (data, user_id) for each
    audio frame received from the voice channel. We look up the matching
    PlayerAudioProcessor and feed it the PCM data.
    
    IMPORTANT: This runs in the Discord asyncio thread.
    Results must be pushed to the Qt thread via the callback, never
    directly to Qt widgets.
    """
    
    def __init__(self, on_audio_processed: Callable):
        """
        Args:
            on_audio_processed: Callback receiving (slot_index, rms, vowel).
                                Must be thread-safe (pushes to event queue).
        """
        super().__init__()
        self.processors: Dict[int, PlayerAudioProcessor] = {}
        self._on_audio_processed = on_audio_processed
    
    def register_player(self, discord_user_id: int, slot_index: int,
                        sample_rate: int = 48000):
        """
        Register a Discord user → PC slot mapping.
        
        Called during setup when we know which Discord users map to which
        PC portrait slots. This is configured in the PC Portraits tab GUI.
        """
        detector = VowelDetector(sample_rate=sample_rate, frame_size=2048)
        self.processors[discord_user_id] = PlayerAudioProcessor(
            discord_user_id=discord_user_id,
            slot_index=slot_index,
            detector=detector,
        )
    
    def unregister_player(self, discord_user_id: int):
        """Remove a player's processor (left voice channel, etc.)."""
        processor = self.processors.pop(discord_user_id, None)
        if processor:
            processor.reset()
    
    def write(self, data: bytes, user: int):
        """
        Called by discord.py for each audio frame received.
        
        Args:
            data: Raw PCM audio bytes (48kHz, 16-bit, stereo)
            user: Discord user ID who produced this audio
        """
        processor = self.processors.get(user)
        if processor is None:
            return  # Unknown user, not a registered player — skip
        
        rms, vowel = processor.process_chunk(data)
        
        # Push to Qt thread via thread-safe callback
        self._on_audio_processed(processor.slot_index, rms, vowel)
    
    def cleanup(self):
        """Called when voice connection ends."""
        for proc in self.processors.values():
            proc.reset()
        self.processors.clear()


# ──────────────────────────────────────────────
# Sample Rate Note
# ──────────────────────────────────────────────
#
# discord.py voice receive outputs 48kHz PCM (Discord's native rate).
# The VowelDetector was originally designed for 44.1kHz.
# Two options:
#   A) Resample 48k → 44.1k before analysis (adds latency + complexity)
#   B) Just tell VowelDetector the sample rate is 48000 (preferred)
#      The formant frequency ranges are absolute Hz values, not relative
#      to sample rate, so FFT bin mapping just adjusts automatically.
#
# Going with Option B. The VowelDetector accepts sample_rate as a
# constructor param and uses it for rfftfreq(). No resampling needed.
```

---

## Changes to: discord_bot.py (MODIFY EXISTING)

```python
# ── New imports ──
from dm_puppeteer.voice_receiver import VoiceReceiveSink

# ── New signal on the DiscordBridge (the Qt signal emitter) ──
class DiscordBridge(QObject):
    # ... existing signals ...
    roll_received = pyqtSignal(dict)          # existing
    voice_state_changed = pyqtSignal(dict)    # existing
    
    # NEW: Per-player audio analysis results
    player_audio_update = pyqtSignal(int, float, str)
    #                                 │    │     └─ vowel: "AH"/"EE"/"OO"/""
    #                                 │    └─ rms level (0.0-1.0)  
    #                                 └─ slot_index


# ── New methods on the Discord bot class ──

class DMPuppeteerBot(discord.Client):
    
    def __init__(self, bridge: DiscordBridge, ...):
        super().__init__(...)
        self.bridge = bridge
        self.voice_sink: Optional[VoiceReceiveSink] = None
        self._voice_client: Optional[discord.VoiceClient] = None
        
        # Player mapping: discord_user_id → pc_slot_index
        # Populated from PC Portraits tab config
        self._player_map: Dict[int, int] = {}
    
    def set_player_map(self, mapping: Dict[int, int]):
        """
        Update Discord user → PC slot mapping.
        
        Called from Qt thread when user configures PC portrait slots.
        Thread-safe: just a dict assignment.
        
        Args:
            mapping: {discord_user_id: slot_index, ...}
        """
        self._player_map = mapping
        
        # Update sink registrations if already connected
        if self.voice_sink:
            self.voice_sink.processors.clear()
            for user_id, slot_idx in mapping.items():
                self.voice_sink.register_player(user_id, slot_idx)
    
    async def join_voice_channel(self, channel_id: int):
        """
        Join a voice channel and start receiving per-user audio.
        
        Called when user clicks "Enable Lip Sync" in PC Portraits tab.
        """
        channel = self.get_channel(channel_id)
        if channel is None or not isinstance(channel, discord.VoiceChannel):
            return
        
        # Create the sink with a thread-safe callback
        def on_audio_processed(slot_index: int, rms: float, vowel: Optional[str]):
            # This is called from the Discord thread.
            # Emit Qt signal via the bridge (which is thread-safe via QMetaObject).
            self.bridge.player_audio_update.emit(
                slot_index, rms, vowel or ""
            )
        
        self.voice_sink = VoiceReceiveSink(on_audio_processed)
        
        # Register known players
        for user_id, slot_idx in self._player_map.items():
            self.voice_sink.register_player(user_id, slot_idx)
        
        # Join channel and start receiving
        self._voice_client = await channel.connect()
        self._voice_client.start_recording(self.voice_sink)
    
    async def leave_voice_channel(self):
        """Disconnect from voice and stop receiving audio."""
        if self._voice_client:
            self._voice_client.stop_recording()
            await self._voice_client.disconnect()
            self._voice_client = None
        if self.voice_sink:
            self.voice_sink.cleanup()
            self.voice_sink = None
```

---

## Changes to: pc_overlay.py (MODIFY EXISTING)

```python
# The PC overlay currently receives audio levels from OBS InputVolumeMeters.
# With voice receive enabled, it receives (slot_index, rms, vowel) from Discord instead.
# Both paths coexist — OBS audio is the fallback when lip sync is disabled.

class PCPortraitOverlay(QWidget):
    
    def __init__(self, ...):
        # ... existing init ...
        
        # NEW: Lip sync state per slot
        self._lip_sync_enabled = False
    
    def enable_lip_sync(self, bridge: DiscordBridge):
        """
        Connect Discord voice audio signals to portrait animation.
        
        When enabled, Discord voice receive drives the portraits instead of
        OBS audio meters. OBS meters are still available as fallback.
        """
        self._lip_sync_enabled = True
        bridge.player_audio_update.connect(self._on_player_audio)
    
    def disable_lip_sync(self, bridge: DiscordBridge):
        """Revert to OBS audio meter-driven portraits."""
        self._lip_sync_enabled = False
        bridge.player_audio_update.disconnect(self._on_player_audio)
    
    def _on_player_audio(self, slot_index: int, rms: float, vowel: str):
        """
        Handle per-player audio update from Discord voice receive.
        
        This replaces OBS audio meter updates when lip sync is active.
        Called on the Qt main thread (signal connection ensures this).
        """
        if slot_index >= len(self.pc_slots):
            return
        
        slot = self.pc_slots[slot_index]
        is_speaking = rms > slot.threshold
        
        if is_speaking:
            if vowel and f'mouth_{vowel}' in slot.frames:
                frame_key = f'mouth_{vowel}'
            else:
                frame_key = 'talk'
            
            # Blink overlay during speech
            if self._should_blink(slot):
                blink_key = f'{frame_key}_blink'
                frame_key = blink_key if blink_key in slot.frames else frame_key
            
            self._set_frame(slot_index, frame_key)
            self._set_speaking_glow(slot_index, True)
        else:
            frame_key = 'blink' if self._should_blink(slot) else 'idle'
            self._set_frame(slot_index, frame_key)
            self._set_speaking_glow(slot_index, False)
```

---

## Changes to: models.py (MODIFY EXISTING)

```python
@dataclass
class PCSlot:
    character_name: str = ""
    obs_audio_source: str = ""          # existing — OBS fallback
    glow_color: str = "#00ff00"         # existing
    glow_intensity: float = 1.0         # existing
    threshold: float = 0.05             # existing
    
    # NEW: Discord voice receive mapping
    discord_user_id: Optional[int] = None   # Maps this slot to a Discord user
    lip_sync_enabled: bool = False          # Per-slot toggle
```

---

## UI: PC Portraits Tab — New Controls

```
Per-Slot Settings (expanded when lip sync is available):
┌──────────────────────────────────────────────┐
│ 🎭 Alaric                           [Remove] │
│ OBS Audio Source: [Discord - Alaric    ▼]     │  ← existing
│ Glow Color: [■ green]  Intensity: [====]      │  ← existing
│ Threshold: [====]                             │  ← existing
│                                               │
│ ── Lip Sync ──────────────────────────────    │  ← NEW section
│ Discord User: [Jareth#1234             ▼]     │  ← dropdown of voice channel members
│ ☑ Enable Vowel Detection                      │  ← per-slot toggle
│ Sensitivity: [========]                       │  ← maps to VowelDetector.min_speaking_level
└──────────────────────────────────────────────┘

Global Controls:
┌──────────────────────────────────────────────┐
│ Voice Channel: [Okora Voice Chat       ▼]    │  ← which channel to join
│ [🎙️ Join Voice & Enable Lip Sync]            │  ← single button, joins + starts
│ Status: 🟢 Receiving audio (4 players)       │
└──────────────────────────────────────────────┘
```

The Discord User dropdown auto-populates from voice channel members.
When the bot joins voice, it cross-references discord_user_id on each PCSlot
to register the correct PlayerAudioProcessor instances.

---

## DM (Raph) Lip Sync — Separate Path

Raph's NPC puppet already uses local mic via sounddevice in audio.py.
For DM lip sync, we just add a VowelDetector to the existing mic pipeline:

```python
# In audio.py — existing mic monitoring callback

class AudioMonitor:
    def __init__(self):
        # ... existing ...
        self.vowel_detector = VowelDetector(sample_rate=44100, frame_size=2048)
        self._vowel_buffer = []
    
    def _audio_callback(self, indata, frames, time, status):
        """Existing sounddevice callback — just extend it."""
        mono = indata[:, 0]
        rms = float(np.sqrt(np.mean(mono ** 2)))
        
        # NEW: Vowel detection on the same audio data
        vowel = self.vowel_detector.analyze_chunk(mono)
        
        # Emit both values (existing RMS + new vowel)
        # The overlay picks up whichever it needs
        self.audio_update.emit(rms, vowel or "")
```

This is the "easy win" — no new audio pipeline, just a smarter analysis
on data we're already capturing.

---

## Startup Sequence

1. User opens PC Portraits tab
2. User assigns characters to slots (existing)
3. User selects Discord users from dropdown for each slot (NEW)
4. User checks "Enable Vowel Detection" per slot (NEW)  
5. User selects voice channel from dropdown (NEW)
6. User clicks "Join Voice & Enable Lip Sync" (NEW)
7. Bot joins voice channel → VoiceReceiveSink created
8. For each slot with lip_sync_enabled + discord_user_id:
   → PlayerAudioProcessor created with independent VowelDetector
9. Audio flows: Discord → Sink → Processors → Qt signals → Portrait frames
10. Portraits now show vowel-matched mouth shapes for dramatic moments

Graceful degradation:
- No Discord? → OBS audio meters drive portraits (existing behavior)
- No vowel frames for a character? → Falls back to talk.png
- Discord connected but lip sync disabled? → OBS audio meters still work
- Player not in voice? → Portrait stays idle, no crash

---

## New Dependencies Summary

| Dependency | Purpose | Size | Required? |
|-----------|---------|------|-----------|
| `PyNaCl` | Discord voice decryption | ~2MB | Only if lip sync enabled |
| `scipy` | `find_peaks` for formant detection | ~30MB | Only if lip sync enabled |

Both are optional — the app works without them. Import with try/except
and disable the lip sync UI if not available:

```python
try:
    import nacl  # noqa
    import scipy  # noqa
    LIP_SYNC_AVAILABLE = True
except ImportError:
    LIP_SYNC_AVAILABLE = False
```

---

## Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| discord.py voice receive API changes | Breaks audio pipeline | Pin discord.py version, isolate in voice_receiver.py |
| 4-5 simultaneous FFTs cause CPU spikes | Laggy overlays | VowelDetector is <1ms per chunk. 5 streams × 50 chunks/sec = ~250 FFTs/sec — well within budget |
| Opus compression degrades formant detection | Poor vowel accuracy | Opus preserves speech well. Test and tune thresholds. Fallback to talk.png is always safe |
| Bot joining voice is unexpected for players | Social friction | Document clearly. Bot can be muted server-side. It only listens, never transmits |
| PyNaCl adds install complexity for .exe build | PyInstaller issues | PyNaCl has known PyInstaller hooks. Test early in build pipeline |
```
