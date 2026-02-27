"""
Real-time vowel shape detection using formant analysis.

Analyzes audio chunks and returns detected vowel shape (AH, EE, OO).
Designed for use in both the Discord voice receive pipeline (48kHz)
and the local mic pipeline (44.1kHz).

Dependency: scipy (optional -- if not installed, always returns None)
"""

import numpy as np
from typing import Optional

try:
    from scipy.signal import find_peaks
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


class VowelDetector:
    """
    Detects vowel shapes (AH, EE, OO) from audio using formant analysis.

    Formants are resonant frequencies in the vocal tract. Different vowels
    produce distinct F1/F2 formant patterns that can be detected via FFT.

    Usage:
        detector = VowelDetector(sample_rate=48000)
        vowel = detector.analyze_chunk(mono_audio_array)
        # Returns 'AH', 'EE', 'OO', or None
    """

    # Vowel classification thresholds (in Hz)
    # Based on standard adult formant ranges
    VOWEL_PROFILES = {
        'AH': {'f1_range': (600, 850), 'f2_range': (1000, 1400)},  # "ah" as in "father"
        'EE': {'f1_range': (250, 450), 'f2_range': (2100, 2700)},  # "ee" as in "see"
        'OO': {'f1_range': (250, 450), 'f2_range': (600, 1000)},   # "oo" as in "boot"
    }

    def __init__(self, sample_rate: int = 48000, frame_size: int = 2048):
        """
        Args:
            sample_rate: Audio sample rate in Hz (48000 for Discord, 44100 for mic)
            frame_size: FFT window size. 2048 gives ~23ms at 48kHz -- good balance
                        of frequency resolution vs latency.
        """
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.min_speaking_level = 0.01  # Minimum RMS to consider speech
        self._min_confidence = 0.3      # Minimum classification confidence

    def analyze_chunk(self, audio_data: np.ndarray) -> Optional[str]:
        """
        Analyze audio chunk and return detected vowel shape.

        Args:
            audio_data: NumPy array of mono audio samples, normalized -1.0 to 1.0

        Returns:
            'AH', 'EE', 'OO', or None (if no clear vowel or below threshold)
        """
        if not SCIPY_AVAILABLE:
            return None

        if audio_data is None or len(audio_data) < 256:
            return None

        # Check if audio is loud enough to be speech
        rms = float(np.sqrt(np.mean(audio_data ** 2)))
        if rms < self.min_speaking_level:
            return None

        # Use the last frame_size samples (or all if shorter)
        chunk = audio_data[-self.frame_size:] if len(audio_data) > self.frame_size else audio_data

        # Compute FFT with Hanning window
        window = np.hanning(len(chunk))
        windowed = chunk * window
        fft = np.fft.rfft(windowed)
        magnitude = np.abs(fft)
        freqs = np.fft.rfftfreq(len(windowed), 1.0 / self.sample_rate)

        # Find formant peaks (first 2)
        formants = self._extract_formants(freqs, magnitude)
        if len(formants) < 2:
            return None

        f1, f2 = formants[0], formants[1]

        # Classify vowel based on formant positions
        return self._classify_vowel(f1, f2)

    def _extract_formants(self, freqs: np.ndarray, magnitude: np.ndarray,
                          n_formants: int = 2) -> list:
        """
        Extract formant frequencies from spectrum.

        Formants appear as peaks in the frequency spectrum.
        We look for the N strongest peaks in the speech range (100-3500 Hz).
        """
        # Focus on speech frequency range
        speech_mask = (freqs >= 100) & (freqs <= 3500)
        speech_freqs = freqs[speech_mask]
        speech_mag = magnitude[speech_mask]

        if len(speech_mag) == 0:
            return []

        # Find peaks with minimum prominence
        peak_threshold = np.max(speech_mag) * 0.3
        try:
            peaks, properties = find_peaks(
                speech_mag, height=peak_threshold, distance=20
            )
        except Exception:
            return []

        if len(peaks) == 0:
            return []

        # Sort peaks by magnitude, take strongest N
        peak_magnitudes = properties['peak_heights']
        strongest_indices = np.argsort(peak_magnitudes)[-n_formants:][::-1]
        formant_peaks = peaks[strongest_indices]

        # Sort formants by frequency (F1 < F2)
        formant_freqs = speech_freqs[formant_peaks]
        formant_freqs.sort()

        return formant_freqs.tolist()

    def _classify_vowel(self, f1: float, f2: float) -> Optional[str]:
        """
        Classify vowel based on F1 and F2 formant frequencies.
        Uses overlapping ranges with confidence thresholds.
        """
        best_match = None
        best_confidence = 0.0

        for vowel, profile in self.VOWEL_PROFILES.items():
            f1_match = profile['f1_range'][0] <= f1 <= profile['f1_range'][1]
            f2_match = profile['f2_range'][0] <= f2 <= profile['f2_range'][1]

            if f1_match and f2_match:
                f1_lo, f1_hi = profile['f1_range']
                f2_lo, f2_hi = profile['f2_range']
                f1_center = (f1_lo + f1_hi) / 2
                f2_center = (f2_lo + f2_hi) / 2
                f1_dist = abs(f1 - f1_center) / (f1_hi - f1_lo)
                f2_dist = abs(f2 - f2_center) / (f2_hi - f2_lo)
                confidence = 1.0 - (f1_dist + f2_dist) / 2

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = vowel

        return best_match if best_confidence > self._min_confidence else None


class VowelSmoother:
    """
    Prevents vowel flicker by requiring consecutive consistent detections.

    During rapid speech, formant detection can bounce between vowels
    frame-to-frame. The smoother requires N consecutive same-vowel
    readings before committing to a change.

    Normal rapid speech -> stays on None (or current vowel)
    Held "AHHHHH!" -> AH locks in after buffer fills
    """

    def __init__(self, buffer_size: int = 3):
        """
        Args:
            buffer_size: How many consecutive same-vowel detections needed
                         before switching. 3 at 50fps = ~60ms lag.
        """
        self._buffer_size = buffer_size
        self._buffer: list[Optional[str]] = []
        self._current_vowel: Optional[str] = None

    @property
    def current_vowel(self) -> Optional[str]:
        return self._current_vowel

    def update(self, raw_vowel: Optional[str]) -> Optional[str]:
        """
        Feed a raw vowel detection and get the smoothed result.

        Args:
            raw_vowel: 'AH', 'EE', 'OO', or None from VowelDetector

        Returns:
            Smoothed vowel -- only changes after N consistent readings
        """
        if raw_vowel is None:
            # Silence or no detection -- clear buffer, drop to None immediately
            self._buffer.clear()
            self._current_vowel = None
            return None

        if raw_vowel == self._current_vowel:
            # Same as current -- keep it, clear any pending change
            self._buffer.clear()
            return self._current_vowel

        # Different vowel -- buffer it
        self._buffer.append(raw_vowel)

        # Check if buffer is consistently the new vowel
        if len(self._buffer) >= self._buffer_size:
            if all(v == raw_vowel for v in self._buffer[-self._buffer_size:]):
                self._current_vowel = raw_vowel
                self._buffer.clear()
                return self._current_vowel

        # Not enough consistent readings yet -- keep current
        return self._current_vowel

    def reset(self):
        """Clear all state."""
        self._buffer.clear()
        self._current_vowel = None
