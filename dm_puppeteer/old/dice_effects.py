"""
Dice visual effects -- particle system + d20 flash + crit/fumble celebrations.

STUB for integration into dice_overlay.py. This module provides:
  - A lightweight particle emitter (QPainter-based, no dependencies)
  - A d20 flash effect (big number scales up then shrinks into the card)
  - NAT 20 celebration (gold particles, screen shimmer, pulse)
  - NAT 1 despair (red particles, shake, crack lines)

Integration point: call from DiceRollOverlay when a new roll arrives.
The particle system runs on the same 33ms render timer.
"""

import math
import random
import time
from dataclasses import dataclass, field

from PyQt6.QtCore import Qt, QRect, QPointF
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QRadialGradient, QPainterPath


# ---------------------------------------------------------------------------
# Particle System
# ---------------------------------------------------------------------------

@dataclass
class Particle:
    """A single particle with position, velocity, color, and lifetime."""
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    size: float = 4.0
    color: QColor = field(default_factory=lambda: QColor(255, 215, 0))
    lifetime: float = 1.0       # total seconds
    age: float = 0.0
    gravity: float = 200.0      # pixels/sec^2 downward
    drag: float = 0.98          # velocity multiplier per frame
    shape: str = "circle"       # "circle", "spark", "shard"

    @property
    def alive(self):
        return self.age < self.lifetime

    @property
    def alpha(self):
        """Fade out over lifetime."""
        remaining = 1.0 - (self.age / self.lifetime)
        return max(0.0, min(1.0, remaining))

    def update(self, dt: float):
        self.age += dt
        self.vy += self.gravity * dt
        self.vx *= self.drag
        self.vy *= self.drag
        self.x += self.vx * dt
        self.y += self.vy * dt


class ParticleEmitter:
    """Manages a collection of particles. Paint them onto any QPainter."""

    def __init__(self):
        self.particles: list[Particle] = []

    def emit_burst(self, x: float, y: float, count: int = 30,
                   color: QColor = None, spread: float = 300.0,
                   lifetime: float = 1.2, gravity: float = 200.0,
                   size_range: tuple = (2, 6), shape: str = "circle"):
        """Emit a burst of particles from a point."""
        if color is None:
            color = QColor(255, 215, 0)  # gold

        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(spread * 0.3, spread)
            p = Particle(
                x=x + random.uniform(-5, 5),
                y=y + random.uniform(-5, 5),
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed - random.uniform(50, 150),  # bias upward
                size=random.uniform(*size_range),
                color=QColor(
                    color.red() + random.randint(-20, 20),
                    color.green() + random.randint(-20, 20),
                    color.blue() + random.randint(-10, 10),
                ),
                lifetime=lifetime * random.uniform(0.6, 1.0),
                gravity=gravity,
                shape=shape,
            )
            self.particles.append(p)

    def emit_fountain(self, x: float, y: float, count: int = 15,
                      color: QColor = None):
        """Emit particles upward like a fountain/firework."""
        if color is None:
            color = QColor(255, 215, 0)
        for _ in range(count):
            angle = random.uniform(-math.pi * 0.8, -math.pi * 0.2)  # mostly upward
            speed = random.uniform(100, 400)
            p = Particle(
                x=x, y=y,
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                size=random.uniform(2, 5),
                color=color,
                lifetime=random.uniform(0.8, 1.5),
                gravity=300.0,
                shape="spark",
            )
            self.particles.append(p)

    def emit_shatter(self, x: float, y: float, count: int = 8,
                     color: QColor = None):
        """Emit shard-like particles (for NAT 1 crack effect)."""
        if color is None:
            color = QColor(255, 60, 60)
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(80, 250)
            p = Particle(
                x=x, y=y,
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                size=random.uniform(4, 10),
                color=color,
                lifetime=random.uniform(0.5, 1.0),
                gravity=400.0,
                drag=0.95,
                shape="shard",
            )
            self.particles.append(p)

    def update(self, dt: float):
        """Update all particles, remove dead ones."""
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.alive]

    def paint(self, painter: QPainter):
        """Draw all particles."""
        for p in self.particles:
            painter.save()
            alpha = int(p.alpha * 255)
            c = QColor(p.color.red(), p.color.green(), p.color.blue(), alpha)

            if p.shape == "circle":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(c)
                painter.drawEllipse(QPointF(p.x, p.y), p.size, p.size)

            elif p.shape == "spark":
                # Elongated along velocity direction
                painter.setPen(QPen(c, max(1, p.size * 0.5)))
                speed = math.sqrt(p.vx ** 2 + p.vy ** 2)
                if speed > 1:
                    nx, ny = p.vx / speed, p.vy / speed
                    tail = p.size * 3
                    painter.drawLine(
                        QPointF(p.x, p.y),
                        QPointF(p.x - nx * tail, p.y - ny * tail)
                    )

            elif p.shape == "shard":
                # Small triangle shard
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(c)
                path = QPainterPath()
                s = p.size
                path.moveTo(p.x, p.y - s)
                path.lineTo(p.x - s * 0.6, p.y + s * 0.5)
                path.lineTo(p.x + s * 0.6, p.y + s * 0.5)
                path.closeSubpath()
                # Rotate based on velocity direction
                painter.translate(p.x, p.y)
                angle = math.atan2(p.vy, p.vx)
                painter.rotate(math.degrees(angle))
                painter.translate(-p.x, -p.y)
                painter.fillPath(path, c)

            painter.restore()

    @property
    def is_active(self):
        return len(self.particles) > 0


# ---------------------------------------------------------------------------
# D20 Flash Effect
# ---------------------------------------------------------------------------

class D20Flash:
    """
    Big d20 number that scales up, holds briefly, then shrinks away.
    Shows the natural d20 roll before the result card appears.

    Timeline:
      0.0 - 0.2s: Scale up from 0 to 1.2x (overshoot)
      0.2 - 0.3s: Settle to 1.0x
      0.3 - 0.6s: Hold
      0.6 - 0.8s: Shrink to 0 + fade out
    """

    def __init__(self, natural_roll: int, x: float, y: float,
                 color: QColor = None, is_crit: bool = False,
                 is_fumble: bool = False):
        self.natural_roll = natural_roll
        self.x = x
        self.y = y
        self.color = color or QColor(255, 255, 255)
        self.is_crit = is_crit
        self.is_fumble = is_fumble
        self.created = time.monotonic()
        self.duration = 0.8
        self.scale = 0.0
        self.opacity = 0.0
        self.phase = "grow"  # grow, hold, shrink, done

    def update(self, dt: float):
        age = time.monotonic() - self.created

        if age < 0.2:
            # Scale up with overshoot
            t = age / 0.2
            self.scale = 1.2 * self._ease_out_back(t)
            self.opacity = min(1.0, t * 2)
            self.phase = "grow"
        elif age < 0.3:
            # Settle
            t = (age - 0.2) / 0.1
            self.scale = 1.2 - 0.2 * t
            self.opacity = 1.0
            self.phase = "grow"
        elif age < 0.6:
            # Hold
            self.scale = 1.0
            self.opacity = 1.0
            self.phase = "hold"
        elif age < 0.8:
            # Shrink + fade
            t = (age - 0.6) / 0.2
            self.scale = 1.0 - t
            self.opacity = 1.0 - t
            self.phase = "shrink"
        else:
            self.phase = "done"

        return self.phase != "done"

    def paint(self, painter: QPainter):
        if self.phase == "done" or self.opacity < 0.01:
            return

        painter.save()
        painter.setOpacity(self.opacity)

        # Background glow
        if self.is_crit:
            glow_color = QColor(255, 215, 0, 80)
        elif self.is_fumble:
            glow_color = QColor(255, 40, 40, 80)
        else:
            glow_color = QColor(255, 255, 255, 40)

        glow_size = 60 * self.scale
        grad = QRadialGradient(self.x, self.y, glow_size)
        grad.setColorAt(0, glow_color)
        grad.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(QPointF(self.x, self.y), glow_size, glow_size)

        # The number
        font_size = int(48 * self.scale)
        if font_size < 1:
            painter.restore()
            return

        font = QFont("Segoe UI", font_size, QFont.Weight.Black)
        painter.setFont(font)

        # Text color
        if self.is_crit:
            painter.setPen(QColor(255, 215, 0))
        elif self.is_fumble:
            painter.setPen(QColor(255, 60, 60))
        else:
            painter.setPen(self.color)

        text = str(self.natural_roll)
        rect = QRect(
            int(self.x - 50 * self.scale),
            int(self.y - 40 * self.scale),
            int(100 * self.scale),
            int(80 * self.scale)
        )
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        painter.restore()

    @staticmethod
    def _ease_out_back(t):
        """Overshoot easing -- goes past 1.0 then settles."""
        c1 = 1.70158
        c3 = c1 + 1
        return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


# ---------------------------------------------------------------------------
# Screen Shake
# ---------------------------------------------------------------------------

class ScreenShake:
    """
    Provides offset values for shaking an overlay window.
    Call update() each frame, apply offset_x/offset_y to window position.
    """

    def __init__(self, intensity: float = 8.0, duration: float = 0.4,
                 decay: float = 0.9):
        self.intensity = intensity
        self.duration = duration
        self.decay = decay
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._start_time = 0.0
        self._active = False

    def trigger(self, intensity: float = None):
        self._start_time = time.monotonic()
        self._active = True
        if intensity is not None:
            self.intensity = intensity

    def update(self, dt: float):
        if not self._active:
            self.offset_x = 0.0
            self.offset_y = 0.0
            return

        elapsed = time.monotonic() - self._start_time
        if elapsed > self.duration:
            self._active = False
            self.offset_x = 0.0
            self.offset_y = 0.0
            return

        # Decaying random offset
        remaining = 1.0 - (elapsed / self.duration)
        magnitude = self.intensity * remaining
        self.offset_x = random.uniform(-magnitude, magnitude)
        self.offset_y = random.uniform(-magnitude, magnitude)

    @property
    def is_active(self):
        return self._active


# ---------------------------------------------------------------------------
# Effect Presets (call these from dice_overlay.py)
# ---------------------------------------------------------------------------

def trigger_nat20_effect(emitter: ParticleEmitter, center_x: float,
                         center_y: float) -> D20Flash:
    """
    Full NAT 20 celebration. Call this when a crit is detected.
    Returns a D20Flash to render.

    Effects:
      - Gold particle burst (firework-style)
      - Secondary fountain of sparks
      - Gold shimmer particles (slow, floaty)
      - D20 flash showing "20" in gold
    """
    gold = QColor(255, 215, 0)
    white = QColor(255, 255, 240)

    # Main burst
    emitter.emit_burst(
        center_x, center_y, count=40,
        color=gold, spread=350, lifetime=1.5,
        size_range=(2, 6), shape="circle"
    )

    # Spark fountain
    emitter.emit_fountain(
        center_x, center_y, count=20,
        color=white
    )

    # Slow shimmer (low gravity, long life)
    for _ in range(15):
        p = Particle(
            x=center_x + random.uniform(-80, 80),
            y=center_y + random.uniform(-40, 40),
            vx=random.uniform(-30, 30),
            vy=random.uniform(-80, -20),
            size=random.uniform(1, 3),
            color=QColor(
                255, random.randint(200, 255),
                random.randint(50, 150), 200
            ),
            lifetime=random.uniform(1.5, 2.5),
            gravity=20.0,  # very slow fall
            drag=0.995,
            shape="circle",
        )
        emitter.particles.append(p)

    flash = D20Flash(20, center_x, center_y,
                     color=gold, is_crit=True)
    return flash


def trigger_nat1_effect(emitter: ParticleEmitter, center_x: float,
                        center_y: float) -> D20Flash:
    """
    NAT 1 despair effect.

    Effects:
      - Red shard burst (things breaking apart)
      - Dark red particles drifting down
      - D20 flash showing "1" in red
      - (Caller should also trigger ScreenShake)
    """
    red = QColor(200, 40, 40)
    dark_red = QColor(120, 20, 20)

    # Shatter burst
    emitter.emit_shatter(
        center_x, center_y, count=12,
        color=red
    )

    # Slow falling dark particles (despair dust)
    for _ in range(10):
        p = Particle(
            x=center_x + random.uniform(-60, 60),
            y=center_y + random.uniform(-20, 20),
            vx=random.uniform(-20, 20),
            vy=random.uniform(10, 60),  # drift downward
            size=random.uniform(2, 4),
            color=dark_red,
            lifetime=random.uniform(1.0, 2.0),
            gravity=50.0,
            drag=0.99,
            shape="circle",
        )
        emitter.particles.append(p)

    flash = D20Flash(1, center_x, center_y,
                     color=red, is_fumble=True)
    return flash


# ---------------------------------------------------------------------------
# Integration Notes (for next session)
# ---------------------------------------------------------------------------
#
# To integrate into dice_overlay.py:
#
# 1. Add to DiceRollOverlay.__init__:
#        self.emitter = ParticleEmitter()
#        self.d20_flash = None
#        self.screen_shake = ScreenShake()
#
# 2. In DiceRollOverlay.add_roll(), after creating the card:
#        if event.is_critical:
#            self.d20_flash = trigger_nat20_effect(
#                self.emitter, self.CARD_WIDTH / 2, self.height() / 2)
#        elif event.is_fumble:
#            self.d20_flash = trigger_nat1_effect(
#                self.emitter, self.CARD_WIDTH / 2, self.height() / 2)
#            self.screen_shake.trigger(intensity=10)
#
# 3. In DiceRollOverlay._tick():
#        self.emitter.update(0.033)
#        self.screen_shake.update(0.033)
#        if self.d20_flash and not self.d20_flash.update(0.033):
#            self.d20_flash = None
#        # Apply screen shake to window position
#        if self.screen_shake.is_active:
#            base = self.pos()
#            self.move(base.x() + int(self.screen_shake.offset_x),
#                      base.y() + int(self.screen_shake.offset_y))
#
# 4. In _DiceCanvas.paintEvent(), after painting cards:
#        if ov.d20_flash:
#            ov.d20_flash.paint(painter)
#        ov.emitter.paint(painter)
#
# 5. Optional: Add sound triggers
#        if event.is_critical and self.soundboard:
#            self.soundboard.play("nat20_fanfare")
#        elif event.is_fumble and self.soundboard:
#            self.soundboard.play("nat1_sad_trombone")
