"""
PC Portrait overlay system.

Displays player character portraits that react to OBS audio levels.
Supports two modes:
  - Strip: all portraits in one horizontal window
  - Individual: separate windows per portrait (with position persistence)
"""

import math
import random
import time

from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRect
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QFont

from .models import Character, PCSlot, AppState


class PCPortraitRenderer:
    """Renders a single PC portrait with glow, shade, animation, and dimming."""

    def __init__(self):
        self.character: Character | None = None
        self.slot: PCSlot | None = None

        # State
        self.is_speaking = False
        self._was_speaking = False
        self.is_blinking = False

        # Attack/decay state machine
        self._raw_above_threshold = False     # raw RMS vs threshold result
        self._above_threshold_since = 0.0     # when RMS first crossed above
        self._below_threshold_since = 0.0     # when RMS first dropped below
        self._speaking_confirmed = False      # passed attack gate
        self._speaking_since = 0.0            # when speaking started (for max duration)
        self._max_speaking_s = 6.0            # hard ceiling -- force reset after this
        self._cooldown_until = 0.0            # ignore audio until this time (post-reset)

        # Vowel detection state
        self._current_vowel: str = ""         # current vowel: "AH", "EE", "OO", or ""

        # Animation
        self._bounce_phase = 0.0
        self._popin_active = False
        self._popin_start = 0.0
        self._anim_offset_y = 0.0

        # Glow animation (smooth pulse)
        self._glow_amount = 0.0

        # Blink scheduling
        self._next_blink_time = time.monotonic() + random.uniform(2, 6)
        self._blink_end_time = 0.0

    def set_audio_level(self, rms: float, override_threshold: float = 0.0):
        """
        Feed raw RMS level and apply attack/decay gating.

        Call this instead of setting is_speaking directly when using
        Discord voice receive or OBS audio meters.

        Attack: RMS must stay above threshold for voice_attack_ms before
                is_speaking activates. Prevents single noise spikes.
        Decay:  RMS must stay below threshold for voice_decay_ms before
                is_speaking deactivates. Prevents flicker during speech pauses.
        """
        now = time.monotonic()
        threshold = override_threshold if override_threshold > 0 else (
            self.slot.audio_threshold if self.slot else 0.02)
        attack_s = (self.slot.voice_attack_ms / 1000.0) if self.slot else 0.05
        decay_s = (self.slot.voice_decay_ms / 1000.0) if self.slot else 0.25

        above = rms > threshold

        # Cooldown: after a forced reset, ignore audio for 1 second
        # so background noise doesn't immediately re-trigger speaking.
        if now < self._cooldown_until:
            self.is_speaking = False
            self._current_vowel = ""
            return

        # Safety valve: force reset after max duration of continuous speaking.
        # Catches stuck states from background noise or threshold misconfiguration.
        if (self._speaking_confirmed and self._speaking_since > 0.0
                and (now - self._speaking_since) >= self._max_speaking_s):
            self._speaking_confirmed = False
            self.is_speaking = False
            self._raw_above_threshold = False
            self._above_threshold_since = 0.0
            self._below_threshold_since = 0.0
            self._speaking_since = 0.0
            self._cooldown_until = now + 1.0  # 1 second deaf period
            return

        if above:
            # Reset silence timer
            self._below_threshold_since = 0.0

            if not self._raw_above_threshold:
                # Just crossed above â€” start attack timer
                self._above_threshold_since = now
                self._raw_above_threshold = True

            # Check attack gate
            if not self._speaking_confirmed:
                elapsed = now - self._above_threshold_since
                if elapsed >= attack_s:
                    self._speaking_confirmed = True
                    self._speaking_since = now
                    self.is_speaking = True
            else:
                self.is_speaking = True
        else:
            # Reset attack timer
            self._above_threshold_since = 0.0
            self._raw_above_threshold = False

            if self._speaking_confirmed:
                # Was speaking â€” start decay timer
                if self._below_threshold_since == 0.0:
                    self._below_threshold_since = now

                elapsed = now - self._below_threshold_since
                if elapsed >= decay_s:
                    # Decay expired â€” stop speaking
                    self._speaking_confirmed = False
                    self.is_speaking = False
                    self._below_threshold_since = 0.0
                    self._speaking_since = 0.0
                # else: still in decay hold â€” keep is_speaking True
            else:
                # Wasn't speaking yet (attack never completed)
                self.is_speaking = False

    def update_state(self, dt: float = 0.033):
        """Update animation state. Call at ~30fps."""
        now = time.monotonic()

        # Blink
        if now >= self._next_blink_time and not self.is_blinking:
            self.is_blinking = True
            blink_dur = 0.15
            if self.character:
                blink_dur = self.character.settings.blink_duration
            self._blink_end_time = now + blink_dur
            blink_min = 2.0
            blink_max = 6.0
            if self.character:
                blink_min = self.character.settings.blink_interval_min
                blink_max = self.character.settings.blink_interval_max
            self._next_blink_time = now + random.uniform(blink_min, blink_max)

        if self.is_blinking and now >= self._blink_end_time:
            self.is_blinking = False

        # Pop-in on speaking edge
        if self.is_speaking and not self._was_speaking:
            if self.character and self.character.settings.popin_enabled:
                self._popin_active = True
                self._popin_start = now
        self._was_speaking = self.is_speaking

        # Compute animation offset
        self._anim_offset_y = 0.0
        if self.character:
            s = self.character.settings

            # Bounce
            if s.bounce_enabled:
                should_bounce = (not s.bounce_on_talk_only) or self.is_speaking
                if should_bounce:
                    self._bounce_phase += s.bounce_speed * dt
                    self._anim_offset_y += math.sin(
                        self._bounce_phase * 2 * math.pi) * s.bounce_amount
                else:
                    self._bounce_phase *= 0.9

            # Pop-in
            if self._popin_active and s.popin_enabled:
                elapsed = now - self._popin_start
                if elapsed < s.popin_duration:
                    t = elapsed / s.popin_duration
                    self._anim_offset_y -= s.popin_amount * (
                        1.0 - (2 * t - 1) ** 2)
                else:
                    self._popin_active = False

        # Glow transition (smooth)
        target = 1.0 if self.is_speaking else 0.0
        self._glow_amount += (target - self._glow_amount) * 0.2

    def paint(self, painter: QPainter, rect: QRect,
              dim_opacity: float = 0.4, shade_amount: float = 0.0):
        """Paint this portrait into the given rect."""
        if not self.character:
            return

        painter.save()

        is_active = self.is_speaking or self._glow_amount > 0.1

        # Dimming for non-speaking
        effective_opacity = 1.0 if is_active else dim_opacity
        painter.setOpacity(effective_opacity)

        # Get frame
        pixmap = self.character.get_frame(self.is_speaking, self.is_blinking, self._current_vowel)
        if not pixmap:
            painter.restore()
            return

        # Scale to rect keeping aspect ratio
        scaled = pixmap.scaled(
            rect.width(), rect.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        # Center horizontally, anchor to bottom, apply animation
        x = rect.x() + (rect.width() - scaled.width()) // 2
        y = rect.y() + rect.height() - scaled.height()
        y += int(self._anim_offset_y)

        img_rect = QRect(x, y, scaled.width(), scaled.height())

        # Draw glow border behind the character
        if self._glow_amount > 0.05 and self.slot:
            glow_str = self.slot.glow_intensity
            glow_color = QColor(self.slot.glow_color)

            # Outer glow layers
            for i in range(3):
                spread = 6 - i * 2
                alpha = int(self._glow_amount * glow_str * (180 - i * 50))
                alpha = max(0, min(255, alpha))
                gc = QColor(glow_color)
                gc.setAlpha(alpha)
                pen = QPen(gc, 2 + i)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(
                    img_rect.adjusted(-spread, -spread, spread, spread),
                    8, 8)

            # Inner bright border
            painter.setOpacity(effective_opacity)
            bright = QColor(self.slot.glow_color)
            bright.setAlpha(int(self._glow_amount * glow_str * 255))
            painter.setPen(QPen(bright, 3))
            painter.drawRoundedRect(img_rect.adjusted(-2, -2, 2, 2), 6, 6)

        # Draw the character
        painter.setOpacity(effective_opacity)
        painter.drawPixmap(x, y, scaled)

        # Shade mask (dark overlay on non-speaking --Â silhouette effect)
        if not is_active and shade_amount > 0.01:
            painter.setOpacity(shade_amount * effective_opacity)
            painter.fillRect(img_rect, QColor(0, 0, 0))
            painter.setOpacity(effective_opacity)

        # Player name label
        if self.slot and self.slot.player_name:
            painter.setOpacity(max(effective_opacity, 0.6))
            painter.setPen(QColor(255, 255, 255, 220))
            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            name_rect = QRect(rect.x(), rect.bottom() - 24, rect.width(), 24)
            painter.drawText(
                name_rect, Qt.AlignmentFlag.AlignCenter,
                self.slot.player_name)

        painter.restore()


# ---------------------------------------------------------------------------
# Strip Overlay (all portraits in one window)
# ---------------------------------------------------------------------------

class PCStripOverlay(QMainWindow):
    """Single transparent window showing all PC portraits in a row."""

    position_changed = pyqtSignal(int, int)

    def __init__(self, x=0, y=700):
        super().__init__()
        self.portraits: list[PCPortraitRenderer] = []
        self._spacing = 10
        self._portrait_size = 200
        self._dim_opacity = 0.4
        self._shade_amount = 0.0
        self._drag_pos = None

        self.setWindowTitle("PC Portraits --Â Strip")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.move(x, y)

        self.canvas = _StripCanvas(self)
        self.setCentralWidget(self.canvas)

        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(self._tick)
        self.render_timer.start(33)

    def set_portraits(self, portraits):
        self.portraits = portraits
        self._update_size()

    def set_spacing(self, spacing):
        self._spacing = spacing
        self._update_size()

    def set_portrait_size(self, size):
        self._portrait_size = size
        self._update_size()

    def set_dim_opacity(self, opacity):
        self._dim_opacity = opacity

    def set_shade_amount(self, amount):
        self._shade_amount = amount

    def _update_size(self):
        n = len(self.portraits)
        if n == 0:
            self.resize(100, 100)
            return
        w = n * self._portrait_size + (n - 1) * self._spacing
        self.resize(w, self._portrait_size + 30)

    def _tick(self):
        for p in self.portraits:
            p.update_state()
        self.canvas.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (event.globalPosition().toPoint()
                              - self.frameGeometry().topLeft())

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        if self._drag_pos:
            pos = self.pos()
            self.position_changed.emit(pos.x(), pos.y())
        self._drag_pos = None


class _StripCanvas(QWidget):
    def __init__(self, overlay):
        super().__init__(overlay)
        self.overlay = overlay

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        ov = self.overlay
        x_off = 0
        for p in ov.portraits:
            rect = QRect(x_off, 0, ov._portrait_size, ov._portrait_size)
            p.paint(painter, rect, ov._dim_opacity, ov._shade_amount)
            x_off += ov._portrait_size + ov._spacing
        painter.end()


# ---------------------------------------------------------------------------
# Individual Overlay (one window per portrait)
# ---------------------------------------------------------------------------

class PCIndividualOverlay(QMainWindow):
    """A single floating transparent window for one PC portrait."""

    position_changed = pyqtSignal(str, int, int)  # slot_id, x, y

    def __init__(self, slot_id, x=0, y=0, size=200):
        super().__init__()
        self.slot_id = slot_id
        self.portrait: PCPortraitRenderer | None = None
        self._portrait_size = size
        self._dim_opacity = 0.4
        self._shade_amount = 0.0
        self._drag_pos = None

        self.setWindowTitle(f"PC Portrait --Â {slot_id}")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(size, size + 30)
        self.move(x, y)

        self.canvas = _IndividualCanvas(self)
        self.setCentralWidget(self.canvas)

        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(self._tick)
        self.render_timer.start(33)

    def set_portrait(self, portrait):
        self.portrait = portrait

    def set_size(self, size):
        self._portrait_size = size
        self.resize(size, size + 30)

    def set_dim_opacity(self, opacity):
        self._dim_opacity = opacity

    def set_shade_amount(self, amount):
        self._shade_amount = amount

    def _tick(self):
        if self.portrait:
            self.portrait.update_state()
        self.canvas.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (event.globalPosition().toPoint()
                              - self.frameGeometry().topLeft())

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        if self._drag_pos:
            pos = self.pos()
            self.position_changed.emit(self.slot_id, pos.x(), pos.y())
        self._drag_pos = None


class _IndividualCanvas(QWidget):
    def __init__(self, overlay):
        super().__init__(overlay)
        self.overlay = overlay

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        ov = self.overlay
        if ov.portrait:
            rect = QRect(0, 0, ov._portrait_size, ov._portrait_size)
            ov.portrait.paint(painter, rect, ov._dim_opacity, ov._shade_amount)
        painter.end()


# ---------------------------------------------------------------------------
# Manager --Â coordinates between strip/individual modes
# ---------------------------------------------------------------------------

class PCOverlayManager:
    """Manages the PC portrait overlays in either strip or individual mode."""

    def __init__(self, state: AppState):
        self.state = state
        self.portraits: list[PCPortraitRenderer] = []
        self.strip_overlay: PCStripOverlay | None = None
        self.individual_overlays: list[PCIndividualOverlay] = []
        self._visible = False
        self._mode = state.pc_overlay_mode
        self._save_callback = None

        # Voice receive state -- tracks which slots are driven by Discord
        self._voice_active = False
        self._voice_slots: set[int] = set()  # slot indices driven by Discord

    def set_save_callback(self, callback):
        """Set a callback to trigger state save (for position persistence)."""
        self._save_callback = callback

    def rebuild(self, characters: dict):
        """Rebuild portrait renderers from current state."""
        self.portraits.clear()
        for slot in self.state.pc_slots:
            renderer = PCPortraitRenderer()
            renderer.slot = slot
            if slot.character_id and slot.character_id in characters:
                renderer.character = characters[slot.character_id]
            self.portraits.append(renderer)

    def update_audio_levels(self, levels: dict):
        """Receive audio levels dict and update portrait speaking states.

        This is the OBS audio path. Slots that are voice-active (driven by
        Discord voice receive) are skipped -- Discord takes priority.
        """
        for i, portrait in enumerate(self.portraits):
            # Skip slots driven by Discord voice receive
            if self._voice_active and i in self._voice_slots:
                continue

            if portrait.slot and portrait.slot.obs_audio_source:
                source = portrait.slot.obs_audio_source
                level = levels.get(source, 0.0)
                portrait.set_audio_level(level)

    def update_player_audio(self, slot_index: int, rms: float, vowel: str,
                            threshold: float = 0.0):
        """
        Receive per-player audio from Discord voice receive.

        This is the Discord audio path. When active for a slot, it takes
        priority over OBS audio meters for that slot.

        Args:
            slot_index: PC portrait slot index
            rms: Audio RMS level (0.0 - 1.0)
            vowel: Detected vowel shape ("AH", "EE", "OO", or "")
                   Empty string until vowel detection is implemented.
            threshold: Adaptive threshold from voice processor (0.0 = use static)
        """
        if slot_index < 0 or slot_index >= len(self.portraits):
            return

        portrait = self.portraits[slot_index]
        if not portrait.slot:
            return

        portrait.set_audio_level(rms, override_threshold=threshold)

        # Set vowel for frame selection (empty string = use generic talk.png)
        portrait._current_vowel = vowel if portrait.is_speaking else ""

    def set_voice_active(self, active: bool, voice_slot_indices: list[int] = None):
        """
        Enable/disable Discord voice receive for portrait driving.

        When active, the specified slots are driven by Discord audio
        instead of OBS audio meters. Unspecified slots continue using OBS.

        Args:
            active: Whether voice receive is active
            voice_slot_indices: Which slot indices are driven by Discord.
                                If None, all slots with discord_user_id are used.
        """
        self._voice_active = active

        if active and voice_slot_indices is not None:
            self._voice_slots = set(voice_slot_indices)
        elif active:
            # Auto-detect from slot config
            self._voice_slots = {
                i for i, slot in enumerate(self.state.pc_slots)
                if slot.discord_user_id > 0
            }
        else:
            self._voice_slots.clear()
            # Reset all portraits to non-speaking when voice disconnects
            for portrait in self.portraits:
                portrait.is_speaking = False
                portrait._speaking_confirmed = False
                portrait._raw_above_threshold = False
                portrait._above_threshold_since = 0.0
                portrait._below_threshold_since = 0.0
                portrait._speaking_since = 0.0
                portrait._cooldown_until = 0.0
                portrait._current_vowel = ""

    def show(self, mode=None):
        """Show overlays in the specified mode."""
        if mode:
            self._mode = mode
        self.hide()

        if self._mode == "strip":
            self._show_strip()
        else:
            self._show_individual()
        self._visible = True

    def hide(self):
        """Hide all overlays, saving positions first."""
        # Save individual positions before destroying
        for ov in self.individual_overlays:
            pos = ov.pos()
            for slot in self.state.pc_slots:
                if slot.id == ov.slot_id:
                    slot.individual_x = pos.x()
                    slot.individual_y = pos.y()
                    break
            ov.hide()
            ov.render_timer.stop()
            ov.deleteLater()
        self.individual_overlays.clear()

        if self.strip_overlay:
            pos = self.strip_overlay.pos()
            self.state.pc_overlay_x = pos.x()
            self.state.pc_overlay_y = pos.y()
            self.strip_overlay.hide()
            self.strip_overlay.render_timer.stop()
            self.strip_overlay.deleteLater()
            self.strip_overlay = None

        self._visible = False

        if self._save_callback:
            self._save_callback()

    @property
    def is_visible(self):
        return self._visible

    def _show_strip(self):
        self.strip_overlay = PCStripOverlay(
            x=self.state.pc_overlay_x, y=self.state.pc_overlay_y)
        self.strip_overlay.set_portrait_size(self.state.pc_portrait_size)
        self.strip_overlay.set_spacing(self.state.pc_strip_spacing)
        self.strip_overlay.set_dim_opacity(self.state.pc_dim_opacity)
        self.strip_overlay.set_shade_amount(self.state.pc_shade_amount)
        self.strip_overlay.set_portraits(self.portraits)
        self.strip_overlay.position_changed.connect(self._on_strip_moved)
        self.strip_overlay.show()

    def _show_individual(self):
        size = self.state.pc_portrait_size
        spacing = self.state.pc_strip_spacing
        base_x = self.state.pc_overlay_x
        base_y = self.state.pc_overlay_y

        for i, (portrait, slot) in enumerate(
                zip(self.portraits, self.state.pc_slots)):
            # Use saved position if available, otherwise auto-place
            if slot.individual_x >= 0 and slot.individual_y >= 0:
                x, y = slot.individual_x, slot.individual_y
            else:
                x = base_x + i * (size + spacing)
                y = base_y

            ov = PCIndividualOverlay(slot.id, x=x, y=y, size=size)
            ov.set_dim_opacity(self.state.pc_dim_opacity)
            ov.set_shade_amount(self.state.pc_shade_amount)
            ov.set_portrait(portrait)
            ov.position_changed.connect(self._on_individual_moved)
            ov.show()
            self.individual_overlays.append(ov)

    def _on_strip_moved(self, x, y):
        self.state.pc_overlay_x = x
        self.state.pc_overlay_y = y
        if self._save_callback:
            self._save_callback()

    def _on_individual_moved(self, slot_id, x, y):
        """Save individual overlay position to the matching slot."""
        for slot in self.state.pc_slots:
            if slot.id == slot_id:
                slot.individual_x = x
                slot.individual_y = y
                break
        if self._save_callback:
            self._save_callback()

    def apply_settings(self):
        """Reapply current settings to visible overlays."""
        if self.strip_overlay:
            self.strip_overlay.set_portrait_size(self.state.pc_portrait_size)
            self.strip_overlay.set_spacing(self.state.pc_strip_spacing)
            self.strip_overlay.set_dim_opacity(self.state.pc_dim_opacity)
            self.strip_overlay.set_shade_amount(self.state.pc_shade_amount)
            self.strip_overlay._update_size()
        for ov in self.individual_overlays:
            ov.set_size(self.state.pc_portrait_size)
            ov.set_dim_opacity(self.state.pc_dim_opacity)
            ov.set_shade_amount(self.state.pc_shade_amount)

    def refresh_mode(self, mode):
        """Switch between strip and individual mode."""
        was_visible = self._visible
        self._mode = mode
        if was_visible:
            self.show(mode)
