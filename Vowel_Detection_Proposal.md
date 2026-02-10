# Vowel Detection Lip Sync — Development Proposal

**Feature:** Real-time vowel shape detection for PC portrait mouth animations
**Goal:** Match mouth shapes to vowel sounds (AH, EE, OO) for dramatic moments like "AHHHHH!" or "NOOOOO!"
**Scope:** PC portraits + DM NPC puppet, basic 3-vowel detection, real-time (<50ms latency)
**Effort Estimate:** 2-3 days implementation + testing

---

## Overview

Currently, PC portraits use simple threshold-based mouth animation (talk/idle based on audio level). This enhancement adds formant analysis to detect which vowel sound the player is making and displays the corresponding mouth shape.

### Visual Impact
- Player yells "AHHHHH!" → Wide open A-shaped mouth holds
- Player shouts "NOOOOO!" → Round O-shaped mouth
- Player exclaims "YEEEES!" → Wide smile E-shaped mouth
- Normal speech → Generic talk frame (fallback)

### Technical Approach
Use FFT (Fast Fourier Transform) to analyze audio frequency spectrum in real-time and detect formant peaks that distinguish vowels. Lightweight, runs locally, minimal CPU overhead.

---

## Asset Requirements

### New Mouth Frames Per Character

Each PC needs 3 additional mouth frame files:

```
characters/Alaric/
├── idle.png          (existing)
├── blink.png         (existing)
├── talk.png          (existing — now used as generic fallback)
├── talk_blink.png    (existing)
├── mouth_AH.png      (NEW — wide open, "AH" sound)
├── mouth_EE.png      (NEW — wide smile, "EE" sound)
├── mouth_OO.png      (NEW — round lips, "OO" sound)
```

Design notes:
- `mouth_AH.png`: Wide vertical oval (jaw dropped, tongue low)
- `mouth_EE.png`: Wide horizontal smile (teeth showing)
- `mouth_OO.png`: Round/circular opening (puckered lips)

Fallback: If new frames don't exist for a character, use existing `talk.png` (graceful degradation).

---

## Core Module: vowel_detector.py

```python
"""
Real-time vowel shape detection using formant analysis.

Analyzes audio chunks and returns detected vowel shape.
Runs in the same audio monitoring loop as existing mic-reactive animation.
"""

import numpy as np
from scipy.signal import find_peaks
from typing import Optional


class VowelDetector:
    """
    Detects vowel shapes (AH, EE, OO) from audio using formant analysis.
    
    Formants are resonant frequencies in the vocal tract. Different vowels
    produce distinct F1/F2 formant patterns that can be detected via FFT.
    """
    
    # Vowel classification thresholds (in Hz)
    # Based on standard adult formant ranges
    VOWEL_PROFILES = {
        'AH': {'f1_range': (600, 850), 'f2_range': (1000, 1400)},   # "ah" as in "father"
        'EE': {'f1_range': (250, 450), 'f2_range': (2100, 2700)},   # "ee" as in "see"
        'OO': {'f1_range': (250, 450), 'f2_range': (600, 1000)},    # "oo" as in "boot"
    }
    
    def __init__(self, sample_rate: int = 44100, frame_size: int = 2048):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.min_speaking_level = 0.01  # Minimum RMS to consider speech
        
    def analyze_chunk(self, audio_data: np.ndarray) -> Optional[str]:
        """
        Analyze audio chunk and return detected vowel shape.
        
        Args:
            audio_data: NumPy array of audio samples (mono, normalized -1.0 to 1.0)
            
        Returns:
            'AH', 'EE', 'OO', or None (if no clear vowel or below threshold)
        """
        # Check if audio is loud enough to be speech
        rms = np.sqrt(np.mean(audio_data**2))
        if rms < self.min_speaking_level:
            return None
        
        # Compute FFT
        window = np.hanning(len(audio_data))
        windowed = audio_data * window
        fft = np.fft.rfft(windowed)
        magnitude = np.abs(fft)
        freqs = np.fft.rfftfreq(len(windowed), 1/self.sample_rate)
        
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
        We look for the N strongest peaks in typical speech range (100-3500 Hz).
        """
        # Focus on speech frequency range
        speech_range_mask = (freqs >= 100) & (freqs <= 3500)
        speech_freqs = freqs[speech_range_mask]
        speech_mag = magnitude[speech_range_mask]
        
        # Find peaks with minimum prominence
        peak_threshold = np.max(speech_mag) * 0.3
        peaks, properties = find_peaks(speech_mag, height=peak_threshold, distance=20)
        
        if len(peaks) == 0:
            return []
        
        # Sort peaks by magnitude, take strongest N
        peak_magnitudes = properties['peak_heights']
        strongest_indices = np.argsort(peak_magnitudes)[-n_formants:][::-1]
        formant_peaks = peaks[strongest_indices]
        
        # Sort formants by frequency (F1 < F2 < F3...)
        formant_freqs = speech_freqs[formant_peaks]
        formant_freqs.sort()
        
        return formant_freqs.tolist()
    
    def _classify_vowel(self, f1: float, f2: float) -> Optional[str]:
        """
        Classify vowel based on F1 and F2 formant frequencies.
        Uses overlapping ranges with confidence thresholds.
        """
        best_match = None
        best_confidence = 0
        
        for vowel, profile in self.VOWEL_PROFILES.items():
            f1_match = profile['f1_range'][0] <= f1 <= profile['f1_range'][1]
            f2_match = profile['f2_range'][0] <= f2 <= profile['f2_range'][1]
            
            if f1_match and f2_match:
                f1_center = (profile['f1_range'][0] + profile['f1_range'][1]) / 2
                f2_center = (profile['f2_range'][0] + profile['f2_range'][1]) / 2
                f1_dist = abs(f1 - f1_center) / (profile['f1_range'][1] - profile['f1_range'][0])
                f2_dist = abs(f2 - f2_center) / (profile['f2_range'][1] - profile['f2_range'][0])
                confidence = 1.0 - (f1_dist + f2_dist) / 2
                
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = vowel
        
        return best_match if best_confidence > 0.3 else None
```

---

## Implementation Plan

### Phase 1: Core Vowel Detector (Day 1)
- Create `vowel_detector.py` module with VowelDetector class
- Write unit tests with synthetic sine wave vowels
- Test with recorded voice samples (AH, EE, OO sounds)
- Verify <50ms processing latency per chunk

### Phase 2: Audio Pipeline Integration (Day 2)
- Extend `audio.py` to emit vowel alongside RMS (DM path)
- Build `voice_receiver.py` for Discord per-player audio (Player path)
- Update `pc_overlay.py` to consume vowel data
- Implement per-player smoothing buffers

### Phase 3: Asset Creation & Testing (Day 2-3)
- Create test vowel mouth frames for one PC character
- Test with real Discord audio
- Tune formant thresholds
- Add per-character "Enable Lip Sync" toggle in UI

### Phase 4: Polish (Day 3)
- UI controls in PC Portraits tab
- Document asset requirements in character creation UI
- Performance testing with 4-6 simultaneous PC streams

---

## Success Criteria

- Vowel detector correctly identifies AH/EE/OO with >80% accuracy on sustained vowels (200ms+)
- Processing latency <50ms per audio chunk
- Works with 4-6 simultaneous PC audio streams without performance degradation
- Graceful fallback when vowel frames don't exist (uses generic talk.png)
- Smooth transitions between vowel shapes (no flickering)
- Normal rapid speech stays on talk.png (vowels only trigger on held sounds)
- Easy to disable via UI toggle

---

## Dependencies

**Existing:** numpy, sounddevice
**New:** scipy (for find_peaks), PyNaCl (for Discord voice receive)

Both optional — app works without them. Import with try/except and disable lip sync UI if unavailable.
