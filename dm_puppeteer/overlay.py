"""
Transparent overlay window with animation effects.
"""

import math
import random
import time

from PyQt6.QtWidgets import QMainWindow, QWidget
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QColor

from .models import Character, CharacterSettings


class PuppetOverlay(QMainWindow):
    """Transparent frameless window showing the current animated character."""

    position_changed = pyqtSignal(int, int)

    def __init__(self, x=100, y=100):
        super().__init__()

        self.current_character: Character | None = None
        self.is_talking = False
        self.is_blinking = False
        self._was_talking = False
        self._current_vowel: str = ""

        # Animation state
        self._bounce_phase = 0.0
        self._popin_active = False
        self._popin_start = 0.0
        self._anim_offset_y = 0.0

        # Dragging
        self._drag_pos = None

        self._setup_window(x, y)
        self._setup_display()
        self._setup_blink_timer()
        self._setup_render_timer()

    def _setup_window(self, x, y):
        self.setWindowTitle("DM Puppeteer")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(80, 80)
        self.move(x, y)
        self.resize(400, 400)

    def _setup_display(self):
        self.canvas = OverlayCanvas(self)
        self.setCentralWidget(self.canvas)

    def _setup_blink_timer(self):
        self._blink_min = 2.0
        self._blink_max = 6.0
        self._blink_dur = 0.15

        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._trigger_blink)
        self._schedule_next_blink()

        self.blink_end_timer = QTimer(self)
        self.blink_end_timer.setSingleShot(True)
        self.blink_end_timer.timeout.connect(self._end_blink)

    def _setup_render_timer(self):
        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(self._update_frame)
        self.render_timer.start(33)

    # --- Public API ---

    def set_character(self, char: Character | None):
        self.current_character = char
        if char:
            s = char.settings
            self.resize(s.width, s.height)
            self.setWindowOpacity(s.opacity)
            self._blink_min = s.blink_interval_min
            self._blink_max = s.blink_interval_max
            self._blink_dur = s.blink_duration
        self._update_frame()

    def set_talking(self, talking: bool):
        if talking and not self._was_talking:
            self._trigger_popin()
        self._was_talking = self.is_talking
        self.is_talking = talking
        if not talking:
            self._current_vowel = ""

    def set_vowel(self, vowel: str):
        """Set the current detected vowel for lip sync frame selection."""
        self._current_vowel = vowel if self.is_talking else ""

    def apply_settings(self, settings: CharacterSettings):
        """Apply updated settings live."""
        self.resize(settings.width, settings.height)
        self.setWindowOpacity(settings.opacity)
        self._blink_min = settings.blink_interval_min
        self._blink_max = settings.blink_interval_max
        self._blink_dur = settings.blink_duration

    # --- Blinking ---

    def _schedule_next_blink(self):
        interval = random.uniform(self._blink_min, self._blink_max)
        self.blink_timer.start(int(interval * 1000))

    def _trigger_blink(self):
        self.is_blinking = True
        self.blink_end_timer.start(int(self._blink_dur * 1000))
        self._schedule_next_blink()

    def _end_blink(self):
        self.is_blinking = False

    # --- Animation effects ---

    def _trigger_popin(self):
        if self.current_character and self.current_character.settings.popin_enabled:
            self._popin_active = True
            self._popin_start = time.monotonic()

    def _compute_animation_offset(self):
        offset = 0.0
        char = self.current_character
        if not char:
            return 0.0

        s = char.settings
        now = time.monotonic()

        # Bounce
        if s.bounce_enabled:
            should_bounce = (not s.bounce_on_talk_only) or self.is_talking
            if should_bounce:
                self._bounce_phase += s.bounce_speed * 0.033
                offset += math.sin(self._bounce_phase * 2 * math.pi) * s.bounce_amount
            else:
                self._bounce_phase *= 0.9

        # Pop-in
        if self._popin_active and s.popin_enabled:
            elapsed = now - self._popin_start
            if elapsed < s.popin_duration:
                t = elapsed / s.popin_duration
                offset -= s.popin_amount * (1.0 - (2 * t - 1) ** 2)
            else:
                self._popin_active = False

        return offset

    # --- Rendering ---

    def _update_frame(self):
        self._anim_offset_y = self._compute_animation_offset()
        self.canvas.update()

    # --- Draggable ---

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_pos:
            pos = self.pos()
            self.position_changed.emit(pos.x(), pos.y())
        self._drag_pos = None


class OverlayCanvas(QWidget):
    """The painting surface inside the overlay window."""

    def __init__(self, overlay: PuppetOverlay):
        super().__init__(overlay)
        self.overlay = overlay

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        ov = self.overlay
        char = ov.current_character
        if not char:
            painter.end()
            return

        pixmap = char.get_frame(ov.is_talking, ov.is_blinking, ov._current_vowel)
        if not pixmap:
            painter.end()
            return

        scaled = pixmap.scaled(
            self.width(), self.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        x = (self.width() - scaled.width()) // 2
        y = self.height() - scaled.height()  # bottom-anchored
        y += int(ov._anim_offset_y)

        painter.drawPixmap(x, y, scaled)
        painter.end()
