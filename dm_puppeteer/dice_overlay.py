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
    ParticleEmitter, ScreenShake, D20Flash, Particle, DiceSprite,
    trigger_nat20_effect, trigger_nat1_effect
)
from .dice_assets import DicePackLoader
from .models import get_data_dir


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

        # --- Card display delay (for dice_and_card mode) ---
        self._delay = 0.0    # seconds to wait before entering

    def update(self, display_time: float = 6.0, dt: float = 0.033):
        """Update animation state. Returns True if still alive."""
        age = time.monotonic() - self.created

        # Wait for delay before starting enter animation
        if self._delay > 0 and age < self._delay:
            return True   # alive but not visible yet

        effective_age = age - self._delay

        if self.phase == "enter":
            # Slide in + fade in over 0.4s
            t = min(effective_age / 0.4, 1.0)
            ease = 1.0 - (1.0 - t) ** 3  # ease-out cubic
            self.slide_x = self._start_x * (1.0 - ease)
            self.opacity = ease
            if t >= 1.0:
                self.phase = "hold"
                self.slide_x = 0.0
                self.opacity = 1.0

        elif self.phase == "hold":
            hold_start = self._delay + 0.4
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

    BASE_CARD_WIDTH = 380
    BASE_CARD_HEIGHT = 100
    CARD_SPACING = 8
    MAX_VISIBLE = 4

    @property
    def card_width(self):
        scale = self.state.dice_scale if self.state else 1.0
        return int(self.BASE_CARD_WIDTH * scale)

    @property
    def card_height(self):
        scale = self.state.dice_scale if self.state else 1.0
        return int(self.BASE_CARD_HEIGHT * scale)

    @property
    def _dice_zone_height(self):
        """Height of the dice sprite zone in dice_and_card mode."""
        scale = self.state.dice_scale if self.state else 1.0
        return int(400 * scale)

    def _scaled_font(self, family, base_size, weight=QFont.Weight.Normal,
                     italic=False):
        """Return a QFont scaled by the current dice_scale factor."""
        scale = self.state.dice_scale if self.state else 1.0
        return QFont(family, max(6, int(base_size * scale)), weight, italic)

    def __init__(self, state=None, x=50, y=50):
        super().__init__()
        self.state = state
        self.cards: list[DiceRollCard] = []
        self.dice_sprites: list[DiceSprite] = []
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

        # --- Dice pack loader ---
        self.pack_loader = DicePackLoader(get_data_dir())

        self.setWindowTitle("DM Puppeteer - Dice Rolls")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._apply_sizing()
        self.move(x, y)

        self.canvas = _DiceCanvas(self)
        self.setCentralWidget(self.canvas)

        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(self._tick)
        self.render_timer.start(33)

    def _apply_sizing(self):
        """Set overlay window size based on display mode and scale."""
        scale = self.state.dice_scale if self.state else 1.0
        mode = self._get_display_mode()
        if mode == "card_only":
            width = self.card_width + int(120 * scale)
            height = (self.MAX_VISIBLE
                      * (self.card_height + self.CARD_SPACING)
                      + int(200 * scale))
        elif mode == "dice_only":
            width = int(500 * scale)
            height = int(400 * scale)
        else:  # dice_and_card
            width = max(int(500 * scale),
                        self.card_width + int(120 * scale))
            height = (int(400 * scale) + self.MAX_VISIBLE
                      * (self.card_height + self.CARD_SPACING))
        self.resize(width, height)

    def _get_display_mode(self) -> str:
        """Get current display mode from state, with fallback."""
        if self.state:
            return self.state.dice_display_mode
        return "dice_and_card"

    def set_state(self, state):
        """Link to AppState for display mode and PC slot preferences."""
        self.state = state
        self._apply_sizing()

    def set_display_time(self, seconds: float):
        self._display_time = max(1.0, seconds)

    def set_side(self, side: str):
        """Set slide direction: 'left' or 'right'."""
        self._side = side if side in ("left", "right") else "left"

    def set_stack(self, stack: str):
        """Set stack direction: 'top' (newest at top) or 'bottom' (newest at bottom)."""
        self._stack = stack if stack in ("top", "bottom") else "top"

    def add_roll(self, event: DiceRollEvent):
        """Add a new dice roll to display.

        Creates dice sprites and/or roll cards depending on
        the current display mode (dice_only, card_only, dice_and_card).
        """
        # Find color, pack, and dice color for this character
        color = "#00cc66"
        pack_name = self.state.dice_default_pack if self.state else "classic"
        dice_color = "red"
        name_lower = event.character_name.lower()

        # Try PC slot lookup for pack/color preferences
        if self.state:
            for slot in self.state.pc_slots:
                char = self.state.characters.get(slot.character_id)
                char_name = char.name.lower() if char else ""
                slot_name = slot.player_name.lower()
                # Match on player name or character name
                matched = False
                if slot_name and (slot_name in name_lower
                                  or name_lower in slot_name):
                    matched = True
                elif char_name and (char_name in name_lower
                                    or name_lower in char_name):
                    matched = True
                if matched:
                    color = slot.glow_color
                    pack_name = (slot.dice_pack
                                 or self.state.dice_default_pack)
                    dice_color = (slot.dice_color
                                  or self._glow_to_dice_color(
                                      slot.glow_color))
                    break

        # Fallback: use character_colors dict (legacy path)
        if color == "#00cc66":
            for key, c in self.character_colors.items():
                if key.lower() in name_lower or name_lower in key.lower():
                    color = c
                    dice_color = self._glow_to_dice_color(c)
                    break

        mode = self._get_display_mode()

        # Per-player entry direction
        side, entry_dx, entry_dy = self._get_entry_vector_for_character(
            event.character_name)
        entry_edge = self._vector_to_edge(entry_dx, entry_dy)

        # --- Dice sprite(s) ---
        if mode in ("dice_only", "dice_and_card"):
            land_x, land_y = self._random_landing_position()

            # Resolve pack -- fallback to placeholder if pack not found
            available = self.pack_loader.available_packs()
            if pack_name not in available:
                pack_name = (available[0] if available
                             else DicePackLoader.PLACEHOLDER_PACK)

            # Primary die
            dice_scale = self.state.dice_scale if self.state else 1.0
            sprite = DiceSprite(
                result=event.natural_roll or event.total,
                die_type=event.die_type,
                pack_loader=self.pack_loader,
                pack_name=pack_name,
                color=dice_color,
                landing_x=land_x,
                landing_y=land_y,
                entry_edge=entry_edge,
                scale=dice_scale,
            )

            # Crits/fumbles get extended hold for dramatic effect
            if event.is_critical or event.is_fumble:
                sprite._hold_duration_override = 2.0

            self.dice_sprites.append(sprite)

            # Secondary die for advantage/disadvantage
            if event.is_advantage or event.is_disadvantage:
                die_sz = int(DiceSprite.BASE_DIE_SIZE * dice_scale)
                land_x2 = land_x + die_sz + 20
                land_y2 = land_y + random.uniform(-15, 15)
                secondary = DiceSprite(
                    result=event.secondary_roll,
                    die_type="d20",
                    pack_loader=self.pack_loader,
                    pack_name=pack_name,
                    color=dice_color,
                    landing_x=land_x2,
                    landing_y=land_y2,
                    entry_edge=entry_edge,
                    scale=dice_scale,
                )
                secondary._is_secondary = True
                self.dice_sprites.append(secondary)

        # --- Roll card (existing system) ---
        if mode in ("card_only", "dice_and_card"):
            card = DiceRollCard(event, color, slide_from=side)
            if mode == "dice_and_card":
                # Delay card entry until die settles
                card._delay = 1.8
            self.cards.append(card)

        # Trim old
        while len(self.cards) > self.MAX_VISIBLE + 2:
            self.cards.pop(0)
        while len(self.dice_sprites) > 6:
            self.dice_sprites.pop(0)

    def _tick(self):
        dt = 0.033

        # Update dice sprites and trigger crit/fumble effects
        for sprite in self.dice_sprites:
            was_holding = (sprite.phase == "hold")
            sprite.update(dt, self._display_time)

            # Trigger NAT 20/NAT 1 exit effects when hold phase ends
            # (the sprite's own update transitions from hold -> exit;
            # we intercept to override with explode/shatter instead)
            if was_holding and sprite.phase == "exit":
                if (sprite.result == 20 and sprite.die_type == "d20"
                        and not sprite._is_secondary):
                    sprite.trigger_explode()
                    self.d20_flash = trigger_nat20_effect(
                        self.emitter, sprite.x, sprite.y)
                elif (sprite.result == 1 and sprite.die_type == "d20"
                      and not sprite._is_secondary):
                    sprite.trigger_shatter()
                    self.d20_flash = trigger_nat1_effect(
                        self.emitter, sprite.x, sprite.y)
                    self.screen_shake.trigger(intensity=8)

        self.dice_sprites = [s for s in self.dice_sprites
                             if not s.is_finished]

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

        cw = self.card_width
        ch = self.card_height

        # X position
        if self._side == "right":
            base_x = self.canvas.width() - cw - 10
        else:
            base_x = 10
        x = base_x + int(card.slide_x)

        # Y offset for dice_and_card mode
        mode = self._get_display_mode()
        card_area_top = self._dice_zone_height if mode == "dice_and_card" else 0

        # Y position
        if self._stack == "bottom":
            total_h = self.MAX_VISIBLE * (ch + self.CARD_SPACING)
            y = card_area_top + 10 + total_h \
                - (ch + self.CARD_SPACING) \
                - idx * (ch + self.CARD_SPACING)
        else:
            y = card_area_top + 10 + idx * (ch + self.CARD_SPACING)

        return x, y, cw, ch

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

    # --- Dice sprite helpers ---

    def _random_landing_position(self) -> tuple:
        """Calculate a randomized landing position for a dice sprite.

        Lands in the upper portion of the overlay (above cards).
        """
        scale = self.state.dice_scale if self.state else 1.0
        margin = int(DiceSprite.BASE_DIE_SIZE * scale)
        w = self.canvas.width()
        mode = self._get_display_mode()
        if mode == "dice_only":
            h = self.canvas.height()
        else:
            # dice_and_card: land in the scaled dice zone
            h = self._dice_zone_height
        x = random.uniform(margin, max(margin + 1, w - margin * 2))
        y = random.uniform(margin, max(margin + 1, h * 0.6))
        return x, y

    @staticmethod
    def _glow_to_dice_color(glow_hex: str) -> str:
        """Map a PC slot glow color to the nearest dice pack color.

        Compares the glow color's hue to available pack colors
        and returns the closest match by hue distance.
        """
        glow = QColor(glow_hex)
        glow_hue = glow.hsvHue()

        color_hues = {
            "red": 0, "gold": 45, "green": 120,
            "cyan": 180, "blue": 210, "purple": 270, "white": -1,
        }

        best_color = "red"
        best_dist = 999
        for name, hue in color_hues.items():
            if hue < 0:
                continue
            dist = min(abs(glow_hue - hue), 360 - abs(glow_hue - hue))
            if dist < best_dist:
                best_dist = dist
                best_color = name

        return best_color

    # --- Per-player entry direction ---

    def _get_entry_vector_for_character(self, character_name: str):
        """Calculate entry direction based on player's portrait position.

        Returns:
            (side, entry_x, entry_y) where:
            - side: "left" or "right" (for card slide direction)
            - entry_x, entry_y: normalized direction for sprite trajectory

        Falls back to default side if no portrait position is available.
        """
        if not self.state:
            return self._side, 0.0, 0.0

        # Find matching PC slot
        name_lower = character_name.lower()
        matched_slot = None
        matched_index = -1
        for i, slot in enumerate(self.state.pc_slots):
            slot_name = slot.player_name.lower()
            char = self.state.characters.get(slot.character_id)
            char_name = char.name.lower() if char else ""
            if ((slot_name and (slot_name in name_lower
                                or name_lower in slot_name))
                    or (char_name and (char_name in name_lower
                                       or name_lower in char_name))):
                matched_slot = slot
                matched_index = i
                break

        if matched_slot is None or matched_index < 0:
            return self._side, 0.0, 0.0

        # Calculate portrait center in screen coordinates
        if self.state.pc_overlay_mode == "strip":
            portrait_cx = (
                self.state.pc_overlay_x
                + matched_index * (self.state.pc_portrait_size
                                   + self.state.pc_strip_spacing)
                + self.state.pc_portrait_size // 2)
            portrait_cy = (self.state.pc_overlay_y
                           + self.state.pc_portrait_size // 2)
        else:
            # Individual mode: use saved position
            if (matched_slot.individual_x >= 0
                    and matched_slot.individual_y >= 0):
                portrait_cx = (matched_slot.individual_x
                               + self.state.pc_portrait_size // 2)
                portrait_cy = (matched_slot.individual_y
                               + self.state.pc_portrait_size // 2)
            else:
                return self._side, 0.0, 0.0

        # Dice overlay center
        dice_cx = self.x() + self.width() // 2
        dice_cy = self.y() + self.height() // 2

        # Direction vector (portrait -> dice overlay, normalized)
        dx = portrait_cx - dice_cx
        dy = portrait_cy - dice_cy
        magnitude = max(1.0, (dx**2 + dy**2) ** 0.5)
        norm_x = dx / magnitude
        norm_y = dy / magnitude

        # Card slide direction: based on horizontal component
        side = "left" if dx < 0 else "right"

        return side, norm_x, norm_y

    def _vector_to_edge(self, dx: float, dy: float) -> str:
        """Convert a direction vector to an entry edge for DiceSprite.

        Returns "left" or "right" based on the horizontal component.
        With a typical layout (portrait strip below/beside the overlay),
        left/right entry makes each player's dice visually distinct.
        Using "top" would make most entries identical when portraits
        are all below the overlay.
        """
        if abs(dx) < 0.01 and abs(dy) < 0.01:
            return self._side  # fallback to default

        return "left" if dx < 0 else "right"

    def set_display_mode(self, mode: str):
        """Set display mode and resize overlay accordingly."""
        if self.state:
            self.state.dice_display_mode = mode
        self._apply_sizing()

    def set_scale(self, scale: float):
        """Set the dice/card scale factor (0.5 - 2.0)."""
        if self.state:
            self.state.dice_scale = max(0.5, min(2.0, scale))
        self._apply_sizing()

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
        mode = ov._get_display_mode()

        # 1. Dice sprites (behind cards)
        if mode in ("dice_only", "dice_and_card"):
            for sprite in ov.dice_sprites:
                sprite.paint(painter)

        # 2. Roll cards
        if mode in ("card_only", "dice_and_card"):
            # Filter visible cards (skip delayed cards not yet entering)
            visible = []
            for c in ov.cards:
                if c.phase == "done":
                    continue
                # Skip cards still waiting for their delay
                if (c._delay > 0 and c.phase == "enter"
                        and c.opacity <= 0):
                    continue
                visible.append(c)
            to_draw = visible[-ov.MAX_VISIBLE:]

            # Y offset for dice_and_card: cards below the dice zone
            card_area_top = (ov._dice_zone_height
                             if mode == "dice_and_card" else 0)

            cw = ov.card_width
            ch = ov.card_height

            # Stack direction
            if ov._stack == "bottom":
                total_h = (ov.MAX_VISIBLE
                           * (ch + ov.CARD_SPACING))
                y_offset = (card_area_top + 10 + total_h
                            - (ch + ov.CARD_SPACING))
                step = -(ch + ov.CARD_SPACING)
            else:
                y_offset = card_area_top + 10
                step = ch + ov.CARD_SPACING

            # Side positioning
            if ov._side == "right":
                base_x = ov.width() - cw - 10
            else:
                base_x = 10

            for card in to_draw:
                card_x = base_x + int(card.slide_x)
                self._paint_card(painter, card, card_x, y_offset,
                                 cw, ch)
                y_offset += step

        # 3. Effects on top of everything (particles, d20 flash)
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

        ov = self.overlay
        evt = card.event
        color = card.color
        scale = ov.state.dice_scale if ov.state else 1.0
        rect = QRect(x, y, w, h)

        # Scaled layout helpers
        pad = int(14 * scale)
        right_zone = int(90 * scale)
        text_w = w - right_zone - pad

        # Background with gradient
        path = QPainterPath()
        path.addRoundedRect(float(x), float(y), float(w), float(h), 10, 10)

        grad = QLinearGradient(x, y, x + w, y)
        grad.setColorAt(0, QColor(20, 20, 25, 230))
        grad.setColorAt(1, QColor(30, 30, 40, 220))
        painter.fillPath(path, grad)

        # Colored accent bar on entry side
        accent_path = QPainterPath()
        if ov._side == "right":
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
        painter.setFont(ov._scaled_font("Segoe UI", 11, QFont.Weight.Bold))
        name_rect = QRect(x + pad, y + int(6 * scale), text_w, int(22 * scale))
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft |
                         Qt.AlignmentFlag.AlignVCenter,
                         evt.character_name)

        # Check type (smaller, muted)
        painter.setPen(QColor(180, 180, 200, 200))
        painter.setFont(ov._scaled_font("Segoe UI", 9))
        type_rect = QRect(x + pad, y + int(28 * scale), text_w, int(18 * scale))
        painter.drawText(type_rect, Qt.AlignmentFlag.AlignLeft |
                         Qt.AlignmentFlag.AlignVCenter,
                         evt.check_type)

        # Roll formula
        painter.setPen(QColor(160, 160, 180, 180))
        painter.setFont(ov._scaled_font("Consolas", 9))
        formula_rect = QRect(x + pad, y + int(48 * scale),
                             text_w, int(18 * scale))
        formula_text = evt.roll_formula
        # Clean up markdown artifacts
        formula_text = formula_text.replace('**', '').replace('`', '')
        painter.drawText(formula_rect, Qt.AlignmentFlag.AlignLeft |
                         Qt.AlignmentFlag.AlignVCenter,
                         formula_text)

        # Campaign name (small, at bottom)
        if evt.campaign_name:
            painter.setPen(QColor(120, 120, 140, 140))
            painter.setFont(ov._scaled_font("Segoe UI", 7,
                            QFont.Weight.Normal, italic=True))
            camp_rect = QRect(x + pad, y + h - int(20 * scale),
                              text_w, int(16 * scale))
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
        painter.setFont(ov._scaled_font("Segoe UI", 28, QFont.Weight.Bold))
        painter.setPen(total_color)
        total_rect = QRect(x + w - right_zone, y + int(8 * scale),
                           int(80 * scale), int(50 * scale))
        painter.drawText(total_rect, Qt.AlignmentFlag.AlignCenter,
                         total_str)

        # Crit/fumble label
        if total_label:
            painter.setFont(ov._scaled_font("Segoe UI", 8,
                            QFont.Weight.Bold))
            painter.setPen(total_color)
            label_rect = QRect(x + w - right_zone, y + int(58 * scale),
                               int(80 * scale), int(16 * scale))
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter,
                             total_label)

        # Natural roll indicator
        if evt.natural_roll > 0:
            painter.setPen(QColor(140, 140, 160, 160))
            painter.setFont(ov._scaled_font("Segoe UI", 8))
            d20_rect = QRect(x + w - right_zone, y + h - int(22 * scale),
                             int(80 * scale), int(16 * scale))
            painter.drawText(d20_rect, Qt.AlignmentFlag.AlignCenter,
                             f"[d20] -> {evt.natural_roll}")

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
        ov = self.overlay
        evt = card.event
        color = card.color
        scale = ov.state.dice_scale if ov.state else 1.0

        pad = int(14 * scale)
        right_zone = int(90 * scale)
        text_w = w - right_zone - pad

        # Background
        path = QPainterPath()
        path.addRoundedRect(float(x), float(y), float(w), float(h), 10, 10)
        grad = QLinearGradient(x, y, x + w, y)
        grad.setColorAt(0, QColor(20, 20, 25, 230))
        grad.setColorAt(1, QColor(30, 30, 40, 220))
        painter.fillPath(path, grad)

        # Accent bar
        accent_path = QPainterPath()
        if ov._side == "right":
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
        painter.setFont(ov._scaled_font("Segoe UI", 11, QFont.Weight.Bold))
        painter.drawText(QRect(x + pad, y + int(6 * scale),
                               text_w, int(22 * scale)),
                         Qt.AlignmentFlag.AlignLeft |
                         Qt.AlignmentFlag.AlignVCenter,
                         evt.character_name)

        # Check type
        painter.setPen(QColor(180, 180, 200, 200))
        painter.setFont(ov._scaled_font("Segoe UI", 9))
        painter.drawText(QRect(x + pad, y + int(28 * scale),
                               text_w, int(18 * scale)),
                         Qt.AlignmentFlag.AlignLeft |
                         Qt.AlignmentFlag.AlignVCenter,
                         evt.check_type)

        # Formula
        painter.setPen(QColor(160, 160, 180, 180))
        painter.setFont(ov._scaled_font("Consolas", 9))
        formula = evt.roll_formula.replace('**', '').replace('`', '')
        painter.drawText(QRect(x + pad, y + int(48 * scale),
                               text_w, int(18 * scale)),
                         Qt.AlignmentFlag.AlignLeft |
                         Qt.AlignmentFlag.AlignVCenter,
                         formula)

        # Total number in red
        painter.setFont(ov._scaled_font("Segoe UI", 28, QFont.Weight.Bold))
        painter.setPen(QColor(255, 60, 60))
        painter.drawText(QRect(x + w - right_zone, y + int(8 * scale),
                               int(80 * scale), int(50 * scale)),
                         Qt.AlignmentFlag.AlignCenter, str(evt.total))

        # NAT 1 label
        painter.setFont(ov._scaled_font("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(QRect(x + w - right_zone, y + int(58 * scale),
                               int(80 * scale), int(16 * scale)),
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
