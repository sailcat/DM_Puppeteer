"""
Dice Roll Overlay.

Animated transparent overlay that shows dice rolls on stream.
Rolls slide in, display for a few seconds, then fade out.

NAT 20: Card holds briefly, then explodes into gold particles.
NAT 1:  Card cracks, splits apart, and falls away as shards.

Supports theming per character via glow color.
"""

import time
import math
import random

from PyQt6.QtWidgets import QMainWindow, QWidget
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRect, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QLinearGradient,
    QPainterPath, QFontMetrics
)

from .discord_bot import DiceRollEvent
from .dice_effects import (
    ParticleEmitter, ScreenShake, D20Flash, Particle
)


class DiceRollCard:
    """Data + animation state for one dice roll display."""

    def __init__(self, event: DiceRollEvent, color: str = "#00cc66",
                 slide_from: str = "left"):
        self.event = event
        self.color = QColor(color)
        self.created = time.monotonic()

        # Animation state
        self._start_x = -400.0 if slide_from == "left" else 400.0
        self.opacity = 0.0
        self.slide_x = self._start_x
        self.phase = "enter"     # enter, hold, explode, shatter, exit, done

        # --- NAT 1 crack & fall state ---
        self.crack_progress = 0.0       # 0-1, drives crack line growth
        self.crack_lines = []           # generated once when shatter starts
        self.split_offset = 0.0         # top/bottom halves separate
        self.split_rotation = 0.0       # slight tilt as pieces fall
        self.fall_velocity = 0.0        # accelerating fall
        self._shatter_start = 0.0
        self._shards_emitted = False

        # --- NAT 20 explode state ---
        self._explode_start = 0.0
        self._explode_triggered = False

    def update(self, display_time: float = 6.0, dt: float = 0.033):
        """Update animation state. Returns True if still alive."""
        age = time.monotonic() - self.created

        if self.phase == "enter":
            # Slide in + fade in over 0.4s
            t = min(age / 0.4, 1.0)
            ease = 1.0 - (1.0 - t) ** 3  # ease-out cubic
            self.slide_x = self._start_x * (1.0 - ease)
            self.opacity = ease
            if t >= 1.0:
                self.phase = "hold"
                self.slide_x = 0.0
                self.opacity = 1.0

        elif self.phase == "hold":
            hold_start = 0.4
            # Crits/fumbles get shorter hold before their special exit
            if self.event.is_critical or self.event.is_fumble:
                hold_duration = min(display_time, 2.5)
            else:
                hold_duration = display_time

            if age > hold_start + hold_duration:
                if self.event.is_critical:
                    self.phase = "explode"
                    self._explode_start = time.monotonic()
                elif self.event.is_fumble:
                    self.phase = "shatter"
                    self._shatter_start = time.monotonic()
                    self._generate_crack_lines()
                else:
                    self.phase = "exit"

        elif self.phase == "explode":
            # Card rapidly fades as particles take over
            t = (time.monotonic() - self._explode_start)
            # Quick flash-bright then fade over 0.5s
            if t < 0.08:
                self.opacity = 1.0
            else:
                self.opacity = max(0.0, 1.0 - ((t - 0.08) / 0.4))
            if t > 0.5:
                self.phase = "done"

        elif self.phase == "shatter":
            elapsed = time.monotonic() - self._shatter_start
            # Phase 1: Cracks spread (0 - 0.4s)
            if elapsed < 0.4:
                self.crack_progress = elapsed / 0.4
                self.opacity = 1.0
            # Phase 2: Split and fall (0.4 - 1.4s)
            elif elapsed < 1.4:
                self.crack_progress = 1.0
                fall_t = elapsed - 0.4
                self.fall_velocity += 1200 * dt  # gravity
                self.split_offset += self.fall_velocity * dt
                self.split_rotation = fall_t * 15  # degrees
                self.opacity = max(0.0, 1.0 - (fall_t / 1.0))
            else:
                self.phase = "done"

        elif self.phase == "exit":
            exit_start = 0.4 + display_time
            t = min((age - exit_start) / 0.5, 1.0)
            self.opacity = 1.0 - t
            self.slide_x = -self._start_x * 0.25 * t  # drift away while fading
            if t >= 1.0:
                self.phase = "done"

        return self.phase != "done"

    def _generate_crack_lines(self):
        """Generate random crack paths across the card for NAT 1."""
        self.crack_lines = []
        # Main crack: roughly horizontal across the middle
        mid_y = 0.4 + random.uniform(-0.1, 0.1)  # relative to card height
        points = [(0.0, mid_y)]
        x = 0.0
        while x < 1.0:
            x += random.uniform(0.08, 0.2)
            y = mid_y + random.uniform(-0.15, 0.15)
            points.append((min(x, 1.0), y))
        self.crack_lines.append(points)

        # 2-3 branch cracks
        for _ in range(random.randint(2, 3)):
            # Start from a random point on the main crack
            start_idx = random.randint(1, max(1, len(points) - 2))
            sx, sy = points[start_idx]
            branch = [(sx, sy)]
            bx, by = sx, sy
            for _ in range(random.randint(2, 4)):
                bx += random.uniform(0.02, 0.12) * random.choice([-1, 1])
                by += random.uniform(0.05, 0.15) * random.choice([-1, 1])
                bx = max(0, min(1, bx))
                by = max(0, min(1, by))
                branch.append((bx, by))
            self.crack_lines.append(branch)


class DiceRollOverlay(QMainWindow):
    """Transparent overlay window that displays dice roll cards."""

    position_changed = pyqtSignal(int, int)

    CARD_WIDTH = 380
    CARD_HEIGHT = 100
    CARD_SPACING = 8
    MAX_VISIBLE = 4

    def __init__(self, x=50, y=50):
        super().__init__()
        self.cards: list[DiceRollCard] = []
        self._display_time = 6.0
        self._drag_pos = None

        # Layout: "left" or "right" side, "top" or "bottom" stack
        self._side = "left"
        self._stack = "top"

        # Character -> color mapping (set from PC slots or manually)
        self.character_colors: dict[str, str] = {}

        # --- Effects system ---
        self.emitter = ParticleEmitter()
        self.d20_flash = None
        self.screen_shake = ScreenShake()
        self._base_pos = None  # stored position for shake offset

        self.setWindowTitle("DM Puppeteer - Dice Rolls")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Extra height/width for particles that fly beyond cards
        self.resize(self.CARD_WIDTH + 120,
                    self.MAX_VISIBLE * (self.CARD_HEIGHT + self.CARD_SPACING) + 200)
        self.move(x, y)

        self.canvas = _DiceCanvas(self)
        self.setCentralWidget(self.canvas)

        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(self._tick)
        self.render_timer.start(33)

    def set_display_time(self, seconds: float):
        self._display_time = max(1.0, seconds)

    def set_side(self, side: str):
        """Set slide direction: 'left' or 'right'."""
        self._side = side if side in ("left", "right") else "left"

    def set_stack(self, stack: str):
        """Set stack direction: 'top' (newest at top) or 'bottom' (newest at bottom)."""
        self._stack = stack if stack in ("top", "bottom") else "top"

    def add_roll(self, event: DiceRollEvent):
        """Add a new dice roll to display."""
        # Find color for this character
        color = "#00cc66"
        name_lower = event.character_name.lower()
        for key, c in self.character_colors.items():
            if key.lower() in name_lower or name_lower in key.lower():
                color = c
                break

        card = DiceRollCard(event, color, slide_from=self._side)
        self.cards.append(card)

        # Trim old cards
        while len(self.cards) > self.MAX_VISIBLE + 2:
            self.cards.pop(0)

    def _tick(self):
        dt = 0.033

        # Update all cards and trigger effects on phase transitions
        for card in self.cards:
            card.update(self._display_time, dt)

            # NAT 20: trigger explosion once
            if card.phase == "explode" and not card._explode_triggered:
                card._explode_triggered = True
                cx, cy = self._card_center(card)
                self._trigger_card_explode(cx, cy, card)

            # NAT 1: emit shards once when cracks finish spreading
            if (card.phase == "shatter" and card.crack_progress >= 1.0
                    and not card._shards_emitted):
                card._shards_emitted = True
                cx, cy = self._card_center(card)
                self._trigger_card_shatter(cx, cy, card)

        self.cards = [c for c in self.cards if c.phase != "done"]

        # Update effects
        self.emitter.update(dt)
        if self.d20_flash:
            if not self.d20_flash.update(dt):
                self.d20_flash = None
        self.screen_shake.update(dt)

        # Apply screen shake
        if self.screen_shake.is_active:
            if self._base_pos is None:
                self._base_pos = self.pos()
            self.move(
                self._base_pos.x() + int(self.screen_shake.offset_x),
                self._base_pos.y() + int(self.screen_shake.offset_y)
            )
        elif self._base_pos is not None:
            self.move(self._base_pos)
            self._base_pos = None

        self.canvas.update()

    def _card_center(self, card: DiceRollCard) -> tuple:
        """Get the canvas-local center point of a card."""
        rx, ry, rw, rh = self._card_rect(card)
        return float(rx + rw // 2), float(ry + rh // 2)

    def _card_rect(self, card: DiceRollCard) -> tuple:
        """Get the (x, y, w, h) of a card on the canvas."""
        visible = [c for c in self.cards if c.phase != "done"]
        to_draw = visible[-self.MAX_VISIBLE:]
        try:
            idx = to_draw.index(card)
        except ValueError:
            idx = 0

        # X position
        if self._side == "right":
            base_x = self.canvas.width() - self.CARD_WIDTH - 10
        else:
            base_x = 10
        x = base_x + int(card.slide_x)

        # Y position
        if self._stack == "bottom":
            total_h = self.MAX_VISIBLE * (self.CARD_HEIGHT + self.CARD_SPACING)
            y = 10 + total_h - (self.CARD_HEIGHT + self.CARD_SPACING) \
                - idx * (self.CARD_HEIGHT + self.CARD_SPACING)
        else:
            y = 10 + idx * (self.CARD_HEIGHT + self.CARD_SPACING)

        return x, y, self.CARD_WIDTH, self.CARD_HEIGHT

    def _trigger_card_explode(self, cx, cy, card):
        """NAT 20: Card explodes into golden particles."""
        gold = QColor(255, 215, 0)
        rx, ry, rw, rh = self._card_rect(card)

        # Particles burst outward from across the card's full rectangle
        for _ in range(50):
            px = random.uniform(rx, rx + rw)
            py = random.uniform(ry, ry + rh)
            angle = math.atan2(py - cy, px - cx) + random.uniform(-0.3, 0.3)
            speed = random.uniform(200, 500)
            p = Particle(
                x=px, y=py,
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed - random.uniform(50, 150),
                size=random.uniform(2, 6),
                color=QColor(
                    255, random.randint(180, 255),
                    random.randint(0, 100),
                ),
                lifetime=random.uniform(0.8, 1.6),
                gravity=150.0,
                shape=random.choice(["circle", "spark"]),
            )
            self.emitter.particles.append(p)

        # Spark fountain from the card center
        self.emitter.emit_fountain(cx, cy, count=25, color=gold)

        # Slow shimmer (floaty gold dust)
        for _ in range(20):
            p = Particle(
                x=cx + random.uniform(-rw * 0.4, rw * 0.4),
                y=cy + random.uniform(-rh * 0.3, rh * 0.3),
                vx=random.uniform(-40, 40),
                vy=random.uniform(-100, -30),
                size=random.uniform(1, 3),
                color=QColor(255, random.randint(200, 255),
                             random.randint(50, 150), 200),
                lifetime=random.uniform(1.5, 2.5),
                gravity=15.0,
                drag=0.995,
                shape="circle",
            )
            self.emitter.particles.append(p)

        # D20 flash at card center
        self.d20_flash = D20Flash(20, cx, cy, color=gold, is_crit=True)

    def _trigger_card_shatter(self, cx, cy, card):
        """NAT 1: Card shatters into red/dark shards + screen shake."""
        rx, ry, rw, rh = self._card_rect(card)

        # Shard particles from across the card
        for _ in range(15):
            px = random.uniform(rx, rx + rw)
            py = random.uniform(ry, ry + rh)
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(80, 250)
            p = Particle(
                x=px, y=py,
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed + random.uniform(30, 80),
                size=random.uniform(4, 10),
                color=QColor(
                    random.randint(150, 220),
                    random.randint(20, 60),
                    random.randint(20, 60),
                ),
                lifetime=random.uniform(0.5, 1.0),
                gravity=500.0,
                drag=0.95,
                shape="shard",
            )
            self.emitter.particles.append(p)

        # Despair dust drifting down
        for _ in range(10):
            p = Particle(
                x=cx + random.uniform(-rw * 0.3, rw * 0.3),
                y=cy + random.uniform(-10, 10),
                vx=random.uniform(-20, 20),
                vy=random.uniform(20, 80),
                size=random.uniform(2, 4),
                color=QColor(120, 20, 20),
                lifetime=random.uniform(1.0, 1.8),
                gravity=60.0,
                drag=0.99,
                shape="circle",
            )
            self.emitter.particles.append(p)

        # Screen shake
        self.screen_shake.trigger(intensity=10)

    # Draggable
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


class _DiceCanvas(QWidget):
    def __init__(self, overlay: DiceRollOverlay):
        super().__init__(overlay)
        self.overlay = overlay

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        ov = self.overlay
        visible = [c for c in ov.cards if c.phase != "done"]
        to_draw = visible[-ov.MAX_VISIBLE:]

        # Stack direction
        if ov._stack == "bottom":
            # Newest at bottom: start from bottom of overlay, work up
            total_h = ov.MAX_VISIBLE * (ov.CARD_HEIGHT + ov.CARD_SPACING)
            y_offset = 10 + total_h - (ov.CARD_HEIGHT + ov.CARD_SPACING)
            step = -(ov.CARD_HEIGHT + ov.CARD_SPACING)
        else:
            # Newest at top (default)
            y_offset = 10
            step = ov.CARD_HEIGHT + ov.CARD_SPACING

        # Side positioning
        if ov._side == "right":
            base_x = ov.width() - ov.CARD_WIDTH - 10
        else:
            base_x = 10

        for card in to_draw:
            card_x = base_x + int(card.slide_x)
            self._paint_card(painter, card, card_x, y_offset,
                             ov.CARD_WIDTH, ov.CARD_HEIGHT)
            y_offset += step

        # Draw effects on top of cards
        if ov.d20_flash:
            ov.d20_flash.paint(painter)
        ov.emitter.paint(painter)

        painter.end()

    def _paint_card(self, painter: QPainter, card: DiceRollCard,
                    x: int, y: int, w: int, h: int):
        """Paint a single dice roll card."""

        # --- NAT 1 shatter: draw two halves splitting apart ---
        if card.phase == "shatter" and card.split_offset > 0:
            self._paint_shattered_card(painter, card, x, y, w, h)
            return

        painter.save()
        painter.setOpacity(min(card.opacity, 1.0))

        evt = card.event
        color = card.color
        rect = QRect(x, y, w, h)

        # Background with gradient
        path = QPainterPath()
        path.addRoundedRect(float(x), float(y), float(w), float(h), 10, 10)

        grad = QLinearGradient(x, y, x + w, y)
        grad.setColorAt(0, QColor(20, 20, 25, 230))
        grad.setColorAt(1, QColor(30, 30, 40, 220))
        painter.fillPath(path, grad)

        # Colored accent bar on entry side
        accent_path = QPainterPath()
        if self.overlay._side == "right":
            accent_path.addRoundedRect(float(x + w - 6), float(y),
                                       6, float(h), 3, 3)
        else:
            accent_path.addRoundedRect(float(x), float(y), 6, float(h), 3, 3)
        painter.fillPath(accent_path, color)

        # Glow border for crits
        if evt.is_critical:
            glow = QColor(255, 215, 0, 150)  # gold
            painter.setPen(QPen(glow, 2))
            painter.drawRoundedRect(rect, 10, 10)
        elif evt.is_fumble:
            glow = QColor(255, 50, 50, 150)  # red
            painter.setPen(QPen(glow, 2))
            painter.drawRoundedRect(rect, 10, 10)
        else:
            painter.setPen(QPen(QColor(color.red(), color.green(),
                                       color.blue(), 80), 1))
            painter.drawRoundedRect(rect, 10, 10)

        # Character name
        painter.setPen(QColor(255, 255, 255, 240))
        name_font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        painter.setFont(name_font)
        name_rect = QRect(x + 14, y + 6, w - 100, 22)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft |
                         Qt.AlignmentFlag.AlignVCenter,
                         evt.character_name)

        # Check type (smaller, muted)
        painter.setPen(QColor(180, 180, 200, 200))
        type_font = QFont("Segoe UI", 9)
        painter.setFont(type_font)
        type_rect = QRect(x + 14, y + 28, w - 100, 18)
        painter.drawText(type_rect, Qt.AlignmentFlag.AlignLeft |
                         Qt.AlignmentFlag.AlignVCenter,
                         evt.check_type)

        # Roll formula
        painter.setPen(QColor(160, 160, 180, 180))
        formula_font = QFont("Consolas", 9)
        painter.setFont(formula_font)
        formula_rect = QRect(x + 14, y + 48, w - 100, 18)
        formula_text = evt.roll_formula
        # Clean up markdown artifacts
        formula_text = formula_text.replace('**', '').replace('`', '')
        painter.drawText(formula_rect, Qt.AlignmentFlag.AlignLeft |
                         Qt.AlignmentFlag.AlignVCenter,
                         formula_text)

        # Campaign name (small, at bottom)
        if evt.campaign_name:
            painter.setPen(QColor(120, 120, 140, 140))
            camp_font = QFont("Segoe UI", 7, QFont.Weight.Normal,
                              italic=True)
            painter.setFont(camp_font)
            camp_rect = QRect(x + 14, y + h - 20, w - 100, 16)
            painter.drawText(camp_rect, Qt.AlignmentFlag.AlignLeft |
                             Qt.AlignmentFlag.AlignVCenter,
                             evt.campaign_name)

        # Total (big number on right)
        total_str = str(evt.total)

        # Color based on result type
        if evt.is_critical:
            total_color = QColor(255, 215, 0)       # gold
            total_label = "NAT 20!"
        elif evt.is_fumble:
            total_color = QColor(255, 60, 60)        # red
            total_label = "NAT 1"
        else:
            total_color = QColor(color.lighter(130))
            total_label = ""

        # Big total number
        total_font = QFont("Segoe UI", 28, QFont.Weight.Bold)
        painter.setFont(total_font)
        painter.setPen(total_color)
        total_rect = QRect(x + w - 90, y + 8, 80, 50)
        painter.drawText(total_rect, Qt.AlignmentFlag.AlignCenter,
                         total_str)

        # Crit/fumble label
        if total_label:
            label_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
            painter.setFont(label_font)
            painter.setPen(total_color)
            label_rect = QRect(x + w - 90, y + 58, 80, 16)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter,
                             total_label)

        # Natural roll indicator (small d20 icon)
        if evt.natural_roll > 0:
            painter.setPen(QColor(140, 140, 160, 160))
            d20_font = QFont("Segoe UI", 8)
            painter.setFont(d20_font)
            d20_rect = QRect(x + w - 90, y + h - 22, 80, 16)
            painter.drawText(d20_rect, Qt.AlignmentFlag.AlignCenter,
                             f"\U0001f3b2 d20 \u2192 {evt.natural_roll}")

        # --- NAT 1: Draw crack lines over the card ---
        if card.phase == "shatter" and card.crack_progress > 0:
            self._paint_cracks(painter, card, x, y, w, h)

        painter.restore()

    def _paint_cracks(self, painter: QPainter, card: DiceRollCard,
                      x: int, y: int, w: int, h: int):
        """Draw animated crack lines across the card."""
        progress = card.crack_progress

        # Bright crack line
        painter.setPen(QPen(QColor(255, 80, 80, 220), 2.5))
        for crack_line in card.crack_lines:
            if len(crack_line) < 2:
                continue
            visible_points = max(2, int(len(crack_line) * progress))
            path = QPainterPath()
            path.moveTo(x + crack_line[0][0] * w, y + crack_line[0][1] * h)
            for i in range(1, visible_points):
                path.lineTo(x + crack_line[i][0] * w,
                            y + crack_line[i][1] * h)
            painter.drawPath(path)

        # Dark inner line for depth
        painter.setPen(QPen(QColor(40, 0, 0, 180), 1))
        for crack_line in card.crack_lines:
            if len(crack_line) < 2:
                continue
            visible_points = max(2, int(len(crack_line) * progress))
            path = QPainterPath()
            path.moveTo(x + crack_line[0][0] * w, y + crack_line[0][1] * h)
            for i in range(1, visible_points):
                path.lineTo(x + crack_line[i][0] * w,
                            y + crack_line[i][1] * h)
            painter.drawPath(path)

    def _paint_shattered_card(self, painter: QPainter, card: DiceRollCard,
                              x: int, y: int, w: int, h: int):
        """Paint the card as two halves splitting and falling apart."""
        painter.save()
        painter.setOpacity(min(card.opacity, 1.0))

        split_y = h * 0.45  # split point (near middle)
        offset = card.split_offset
        rotation = card.split_rotation

        # --- TOP HALF: falls left and rotates ---
        painter.save()
        pivot_x = x + w * 0.5
        pivot_y = y + split_y
        painter.translate(pivot_x, pivot_y)
        painter.rotate(-rotation * 0.7)
        painter.translate(-pivot_x, -pivot_y)
        painter.translate(-offset * 0.3, -offset * 0.1)

        clip_top = QPainterPath()
        clip_top.addRect(float(x - 20), float(y - 20),
                         float(w + 40), float(split_y + 20))
        painter.setClipPath(clip_top)
        self._paint_card_body(painter, card, x, y, w, h)
        painter.restore()

        # --- BOTTOM HALF: falls right and rotates ---
        painter.save()
        painter.translate(pivot_x, pivot_y)
        painter.rotate(rotation)
        painter.translate(-pivot_x, -pivot_y)
        painter.translate(offset * 0.2, offset)

        clip_bottom = QPainterPath()
        clip_bottom.addRect(float(x - 20), float(y + split_y),
                            float(w + 40), float(h - split_y + 200))
        painter.setClipPath(clip_bottom)
        self._paint_card_body(painter, card, x, y, w, h)
        painter.restore()

        painter.restore()

    def _paint_card_body(self, painter: QPainter, card: DiceRollCard,
                         x: int, y: int, w: int, h: int):
        """Paint card background + content (used by shatter halves)."""
        evt = card.event
        color = card.color

        # Background
        path = QPainterPath()
        path.addRoundedRect(float(x), float(y), float(w), float(h), 10, 10)
        grad = QLinearGradient(x, y, x + w, y)
        grad.setColorAt(0, QColor(20, 20, 25, 230))
        grad.setColorAt(1, QColor(30, 30, 40, 220))
        painter.fillPath(path, grad)

        # Accent bar
        accent_path = QPainterPath()
        if self.overlay._side == "right":
            accent_path.addRoundedRect(float(x + w - 6), float(y),
                                       6, float(h), 3, 3)
        else:
            accent_path.addRoundedRect(float(x), float(y), 6, float(h), 3, 3)
        painter.fillPath(accent_path, color)

        # Red border
        painter.setPen(QPen(QColor(255, 50, 50, 150), 2))
        painter.drawRoundedRect(QRect(x, y, w, h), 10, 10)

        # Character name
        painter.setPen(QColor(255, 255, 255, 240))
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        painter.drawText(QRect(x + 14, y + 6, w - 100, 22),
                         Qt.AlignmentFlag.AlignLeft |
                         Qt.AlignmentFlag.AlignVCenter,
                         evt.character_name)

        # Check type
        painter.setPen(QColor(180, 180, 200, 200))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(QRect(x + 14, y + 28, w - 100, 18),
                         Qt.AlignmentFlag.AlignLeft |
                         Qt.AlignmentFlag.AlignVCenter,
                         evt.check_type)

        # Formula
        painter.setPen(QColor(160, 160, 180, 180))
        painter.setFont(QFont("Consolas", 9))
        formula = evt.roll_formula.replace('**', '').replace('`', '')
        painter.drawText(QRect(x + 14, y + 48, w - 100, 18),
                         Qt.AlignmentFlag.AlignLeft |
                         Qt.AlignmentFlag.AlignVCenter,
                         formula)

        # Total number in red
        painter.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        painter.setPen(QColor(255, 60, 60))
        painter.drawText(QRect(x + w - 90, y + 8, 80, 50),
                         Qt.AlignmentFlag.AlignCenter, str(evt.total))

        # NAT 1 label
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(QRect(x + w - 90, y + 58, 80, 16),
                         Qt.AlignmentFlag.AlignCenter, "NAT 1")

        # Crack lines on the body pieces
        if card.crack_lines:
            painter.setPen(QPen(QColor(255, 80, 80, 220), 2.5))
            for crack_line in card.crack_lines:
                if len(crack_line) < 2:
                    continue
                crack_path = QPainterPath()
                crack_path.moveTo(x + crack_line[0][0] * w,
                                  y + crack_line[0][1] * h)
                for pt in crack_line[1:]:
                    crack_path.lineTo(x + pt[0] * w, y + pt[1] * h)
                painter.drawPath(crack_path)
