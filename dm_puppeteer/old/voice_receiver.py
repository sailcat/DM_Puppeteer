"""
Discord Voice Receive -- Per-Player Audio Processing.

Receives decoded PCM audio from Discord voice channel via py-cord's
recording API, routes it to per-player processors, and emits
(slot_index, rms, vowel) tuples for the PC portrait overlay system.

Threading: write() is called from the voice receive thread.
All Qt communication goes through the callback -> event queue.

Dependencies:
    - py-cord[voice]  (NOT discord.py -- voice receive is py-cord only)
    - PyNaCl           (included with py-cord[voice])
    - numpy            (already installed for audio.py)

IMPORTANT: Requires Python 3.12. py-cord 2.6 uses audioop which was
removed in Python 3.13+.
"""

import io
import numpy as np
from typing import Dict, Optional, Callable

try:
    from .vowel_detector import VowelDetector, VowelSmoother, SCIPY_AVAILABLE
    VOWEL_DETECTION_AVAILABLE = SCIPY_AVAILABLE
except ImportError:
    VOWEL_DETECTION_AVAILABLE = False

try:
    from .voice_diagnostics import diag as _diag
except ImportError:
    try:
        from voice_diagnostics import diag as _diag
    except ImportError:
        _diag = None

try:
    import discord
    import discord.sinks
    from discord.sinks.core import Filters, Sink, default_filters
    VOICE_RECEIVE_AVAILABLE = True
except (ImportError, AttributeError):
    VOICE_RECEIVE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Adaptive Noise Floor (Per-Player Auto-Threshold)
# ---------------------------------------------------------------------------

class AdaptiveThreshold:
    """Per-player adaptive noise floor tracking.

    Continuously tracks a rolling baseline of "quiet" RMS levels.
    The activation threshold is baseline * multiplier + minimum floor.

    This means:
    - A player with a noisy mic (baseline 0.01) gets threshold ~0.03
    - A player with a quiet mic (baseline 0.002) gets threshold ~0.008
    - A player piping music (baseline 0.05) gets threshold ~0.12

    The baseline only updates when the signal is "quiet" (below current
    threshold), so active speech doesn't drag the baseline up.
    """

    def __init__(self, multiplier: float = 2.5, min_floor: float = 0.005,
                 adaptation_rate: float = 0.002, warmup_frames: int = 50):
        """
        Args:
            multiplier: Threshold = baseline * multiplier + min_floor.
                        2.5 means "speech must be 2.5x louder than noise."
            min_floor: Absolute minimum threshold. Prevents threshold from
                       going to zero on dead-silent mics.
            adaptation_rate: How fast the baseline adapts (0.002 = slow,
                             stable; 0.01 = fast, responsive).
                             Slow is better -- we don't want the baseline
                             chasing speech up.
            warmup_frames: Frames before the adaptive threshold activates.
                           During warmup, use a generous static threshold
                           so portraits don't flicker on connect.
        """
        self.multiplier = multiplier
        self.min_floor = min_floor
        self._adaptation_rate = adaptation_rate
        self._warmup_remaining = warmup_frames

        # State
        self._baseline = 0.01           # initial guess
        self._current_threshold = 0.02  # start at default, adapt from there

    @property
    def threshold(self) -> float:
        """Current adaptive threshold for this player."""
        return self._current_threshold

    @property
    def baseline(self) -> float:
        """Current noise floor estimate for this player."""
        return self._baseline

    def update(self, rms: float) -> float:
        """Feed an RMS value, get back the current adaptive threshold.

        Call this BEFORE passing rms to the attack/decay gate.
        The gate should use this returned threshold instead of the
        static slot.audio_threshold.

        Args:
            rms: Current RMS level

        Returns:
            Current adaptive threshold to use for speaking detection
        """
        # Warmup: just collect data, use static threshold
        if self._warmup_remaining > 0:
            self._warmup_remaining -= 1
            # Seed the baseline from early frames
            self._baseline = (
                (1 - self._adaptation_rate * 10) * self._baseline +
                self._adaptation_rate * 10 * rms
            )
            self._current_threshold = max(
                self._baseline * self.multiplier + self.min_floor,
                self.min_floor
            )
            return self._current_threshold

        # Only update baseline when NOT speaking (below current threshold)
        # This prevents speech from dragging the baseline up
        if rms < self._current_threshold:
            self._baseline = (
                (1 - self._adaptation_rate) * self._baseline +
                self._adaptation_rate * rms
            )

        # Recalculate threshold
        self._current_threshold = max(
            self._baseline * self.multiplier + self.min_floor,
            self.min_floor
        )

        return self._current_threshold

    def reset(self):
        """Reset to initial state (e.g., on reconnect)."""
        self._baseline = 0.01
        self._current_threshold = 0.02
        self._warmup_remaining = 50


# ---------------------------------------------------------------------------
# Per-Player Audio Processor
# ---------------------------------------------------------------------------

class PlayerAudioProcessor:
    """
    Computes RMS level and detects vowel shapes from raw PCM audio
    for one player. Each player gets their own VowelDetector + smoother
    so Player A's audio doesn't bleed into Player B's animation.
    """

    def __init__(self, slot_index: int, sample_rate: int = 48000,
                 smooth_factor: float = 0.3, enable_vowels: bool = True,
                 adaptive_multiplier: float = 2.5):
        self.slot_index = slot_index
        self.sample_rate = sample_rate
        self._smoothed_rms = 0.0
        self._smooth_factor = smooth_factor  # 0 = no smoothing, 1 = no memory

        # Adaptive noise floor
        self._adaptive_threshold = AdaptiveThreshold(
            multiplier=adaptive_multiplier)

        # Vowel detection (optional -- degrades gracefully)
        self._vowel_detector: Optional[VowelDetector] = None
        self._vowel_smoother: Optional[VowelSmoother] = None
        if enable_vowels and VOWEL_DETECTION_AVAILABLE:
            self._vowel_detector = VowelDetector(sample_rate=sample_rate)
            self._vowel_smoother = VowelSmoother(buffer_size=3)

    def set_smoothing(self, factor: float):
        """Update smoothing factor. 0 = heavy smoothing, 1 = raw signal."""
        self._smooth_factor = max(0.05, min(1.0, factor))

    def process_audio(self, pcm_bytes: bytes) -> tuple:
        """
        Process raw PCM audio bytes. Returns (rms, vowel, threshold).

        Discord sends 48kHz, 16-bit, stereo PCM via Opus decode.
        Each frame is ~3840 bytes (20ms of stereo audio).
        """
        if not pcm_bytes or len(pcm_bytes) < 4:
            return 0.0, "", self._adaptive_threshold.threshold

        try:
            audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
            audio /= 32768.0  # normalize to -1.0 .. 1.0
        except (ValueError, TypeError):
            return 0.0, "", self._adaptive_threshold.threshold

        # Downmix stereo -> mono
        if len(audio) >= 2:
            mono = (audio[0::2] + audio[1::2]) / 2.0
        else:
            mono = audio

        # Compute RMS with exponential smoothing
        rms = float(np.sqrt(np.mean(mono ** 2))) if len(mono) > 0 else 0.0
        self._smoothed_rms = (
            self._smooth_factor * rms +
            (1.0 - self._smooth_factor) * self._smoothed_rms
        )

        # Update adaptive threshold
        adaptive_thresh = self._adaptive_threshold.update(self._smoothed_rms)

        # Vowel detection
        vowel = ""
        if self._vowel_detector and self._vowel_smoother and len(mono) > 0:
            raw_vowel = self._vowel_detector.analyze_chunk(mono)
            smoothed = self._vowel_smoother.update(raw_vowel)
            if smoothed:
                vowel = smoothed

        return self._smoothed_rms, vowel, adaptive_thresh

    def reset(self):
        self._smoothed_rms = 0.0
        if self._vowel_smoother:
            self._vowel_smoother.reset()
        self._adaptive_threshold.reset()


# ---------------------------------------------------------------------------
# Discord Audio Sink (receives per-user audio from py-cord)
# ---------------------------------------------------------------------------

if VOICE_RECEIVE_AVAILABLE:

    class VoiceReceiveSink(Sink):
        """
        Custom py-cord Sink for real-time per-user audio processing.

        Matches the exact init pattern used by py-cord's built-in sinks
        (WaveSink, MP3Sink, etc.) to ensure compatibility.
        """

        def __init__(self, on_audio_processed: Callable, *, filters=None):
            """
            Args:
                on_audio_processed: Callback receiving (slot_index, rms, vowel).
                                    Must be thread-safe (pushes to event queue).
                filters: py-cord sink filters (optional).
            """
            # Initialize exactly like py-cord's built-in sinks do
            if filters is None:
                filters = default_filters
            self.filters = filters
            Filters.__init__(self, **self.filters)
            self.encoding = "pcm"
            self.vc = None
            self.audio_data = {}

            # Custom state
            self.processors: Dict[int, PlayerAudioProcessor] = {}
            self._on_audio_processed = on_audio_processed
            self._frame_count = 0
            self._throttle = 2  # process every Nth frame to reduce CPU

        def init(self, vc):
            """Called by py-cord when recording starts."""
            self.vc = vc
            try:
                super().init(vc)
            except Exception:
                pass  # Non-fatal -- timer filter may fail, we don't use it

        def register_player(self, discord_user_id: int, slot_index: int,
                            sample_rate: int = 48000, smooth_factor: float = 0.3,
                            adaptive_multiplier: float = 2.5):
            """Map a Discord user to a PC portrait slot."""
            self.processors[discord_user_id] = PlayerAudioProcessor(
                slot_index=slot_index,
                sample_rate=sample_rate,
                smooth_factor=smooth_factor,
                adaptive_multiplier=adaptive_multiplier,
            )
            # -- DIAGNOSTIC --
            if _diag:
                _diag.set_registered_players(self.processors.keys())

        def unregister_player(self, discord_user_id: int):
            """Remove a player mapping."""
            proc = self.processors.pop(discord_user_id, None)
            if proc:
                proc.reset()

        @Filters.container
        def write(self, data, user):
            """
            Receive audio data for a single user.

            Called by py-cord's voice receive thread for each audio packet.
            Entire body is wrapped in try/except -- an unhandled exception
            here kills the voice receive thread and drops the connection.
            """
            try:
                self._frame_count += 1

                # Get user ID (before throttle so we log ALL incoming users)
                user_id = user if isinstance(user, int) else getattr(user, 'id', 0)

                # -- DIAGNOSTIC: record every call --
                if _diag:
                    _diag.record_write_call(user, user_id, data)

                # Throttle to reduce CPU
                if self._frame_count % self._throttle != 0:
                    if _diag:
                        _diag.record_throttled(user_id)
                    return

                if user_id not in self.processors:
                    if _diag:
                        _diag.record_not_registered(user_id)
                    return

                # Extract raw bytes
                if isinstance(data, (bytes, bytearray)):
                    pcm_bytes = bytes(data)
                elif hasattr(data, 'read'):
                    pcm_bytes = data.read()
                    if hasattr(data, 'seek'):
                        data.seek(0)
                elif hasattr(data, 'file') and hasattr(data.file, 'getvalue'):
                    pcm_bytes = data.file.getvalue()
                else:
                    if _diag:
                        _diag.record_exception(
                            user_id,
                            ValueError(f"Unknown data type: {type(data).__name__}"))
                    return

                if not pcm_bytes:
                    return

                proc = self.processors[user_id]
                rms, vowel, threshold = proc.process_audio(pcm_bytes)

                # -- DIAGNOSTIC: record successful processing --
                if _diag:
                    _diag.record_processed(user_id, rms, threshold)

                self._on_audio_processed(proc.slot_index, rms, vowel, threshold)

                # -- DIAGNOSTIC: record queue put --
                if _diag:
                    _diag.record_queue_put()

                # -- DIAGNOSTIC: periodic summary dump --
                if _diag:
                    _diag.maybe_dump()

            except Exception as exc:
                # NEVER let an exception escape write() --
                # it kills the voice receive thread
                if _diag:
                    _diag.record_exception(
                        user_id if 'user_id' in locals() else 'unknown', exc)

        def cleanup(self):
            """Called when recording stops."""
            self.finished = True
            for proc in self.processors.values():
                proc.reset()

        def format_audio(self, audio):
            """Required by Sink interface. We don't convert audio."""
            pass

else:
    # Stub when py-cord voice receive is not available
    class VoiceReceiveSink:
        """Stub -- voice receive not available."""
        def __init__(self, *args, **kwargs):
            pass
        def register_player(self, *args, **kwargs):
            pass
        def unregister_player(self, *args, **kwargs):
            pass
        def cleanup(self):
            pass
