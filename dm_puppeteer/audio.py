"""
Microphone audio level monitoring with optional vowel detection.
"""

import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QObject, pyqtSignal

try:
    from .vowel_detector import VowelDetector, VowelSmoother, SCIPY_AVAILABLE
    VOWEL_DETECTION_AVAILABLE = SCIPY_AVAILABLE
except ImportError:
    VOWEL_DETECTION_AVAILABLE = False


class AudioMonitor(QObject):
    """Monitors microphone input level using sounddevice."""

    level_changed = pyqtSignal(float)
    vowel_changed = pyqtSignal(str)       # "AH", "EE", "OO", or ""

    def __init__(self, device=None, parent=None):
        super().__init__(parent)
        self.device = device
        self.stream = None
        self.running = False

        # Vowel detection (optional)
        self._vowel_detector = None
        self._vowel_smoother = None
        if VOWEL_DETECTION_AVAILABLE:
            self._vowel_detector = VowelDetector(sample_rate=44100, frame_size=2048)
            self._vowel_smoother = VowelSmoother(buffer_size=3)

    def start(self):
        try:
            self.running = True
            self.stream = sd.InputStream(
                device=self.device,
                channels=1,
                samplerate=44100,
                blocksize=1024,
                callback=self._audio_callback
            )
            self.stream.start()
        except Exception as e:
            print(f"Audio monitor error: {e}")
            self.running = False

    def stop(self):
        self.running = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def restart(self, device=None):
        self.stop()
        if device is not None:
            self.device = device
        self.start()

    def _audio_callback(self, indata, frames, time_info, status):
        mono = indata[:, 0]
        rms = float(np.sqrt(np.mean(mono ** 2)))
        self.level_changed.emit(rms)

        # Vowel detection on the same audio data
        if self._vowel_detector and self._vowel_smoother:
            raw_vowel = self._vowel_detector.analyze_chunk(mono)
            smoothed = self._vowel_smoother.update(raw_vowel)
            self.vowel_changed.emit(smoothed or "")

    @staticmethod
    def list_devices():
        """Return list of input devices as (index, name) tuples."""
        devices = sd.query_devices()
        result = []
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                result.append((i, dev['name']))
        return result
