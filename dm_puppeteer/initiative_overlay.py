"""
Initiative Overlay -- BG3-style horizontal card strip for stream.

Transparent overlay showing combatants in initiative order. Current turn
is highlighted with scale + vertical lift. Dead/fled combatants are greyed
out but remain in position so the strip never shifts unexpectedly.

Follows the same transparent QMainWindow + QTimer render loop pattern
established by dice_overlay.py and pc_overlay.py.
"""

from PyQt6.QtWidgets import QMainWindow, QWidget
from PyQt6.QtCore import Qt, QTimer, QRect, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QPixmap, QPainterPath, QBrush
)

from .models import AppState, Combatant


# -- Border colors ---------------------------------------------------------

BORDER_PLAYER = QColor(218, 165, 32)            # gold
BORDER_MONSTER = QColor(180, 40, 40)            # dark red
BORDER_PLAYER_ACTIVE = QColor(255, 215, 0)      # bright gold
BORDER_MONSTER_ACTIVE = QColor(220, 60, 60)     # bright red
BORDER_INACTIVE = QColor(80, 80, 80)            # grey

# -- Card background -------------------------------------------------------

CARD_BG = QColor(20, 20, 25, 220)
CARD_BG_ACTIVE = QColor(30, 30, 40, 240)


class InitiativeOverlay(QMainWindow):
    """Transparent overlay showing initiative order as a horizontal card strip."""

    position_changed = pyqtSignal(int, int)

    CARD_SIZE = 72
    CARD_SPACING = 4
    ACTIVE_SCALE = 1.15      # current turn card is 15% larger
    ACTIVE_LIFT = 6           # pixels the active card rises above the strip
    BORDER_WIDTH = 3
    CORNER_RADIUS = 6
    NAME_FONT_SIZE = 10
    INITIAL_FONT_DIVISOR = 3  # card_size // this = initial letter font size

    def __init__(self, state: AppState, x=0, y=0):
        super().__init__()
        self.state = state
        self._drag_pos = None
        self._portrait_cache: dict[str, QPixmap] = {}

        self.setWindowTitle("DM Puppeteer - Initiative")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.move(x, y)

        self.canvas = _InitiativeCanvas(self)
        self.setCentralWidget(self.canvas)

        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(self._tick)
        # Timer starts on show(), stops on hide() -- saves CPU when hidden

    # ------------------------------------------------------------------
    # Show / Hide
    # ------------------------------------------------------------------

    def show(self):
        self._rebuild_portrait_cache()
        self._update_size()
        self.render_timer.start(33)   # ~30fps
        super().show()

    def hide(self):
        self.render_timer.stop()
        super().hide()

    # ------------------------------------------------------------------
    # Refresh (called when combatants added/removed)
    # ------------------------------------------------------------------

    def refresh(self):
        """Rebuild portrait cache and resize window.

        Call when combatants are added or removed. NOT needed for turn
        changes or HP changes -- the paint loop reads live state.
        """
        self._rebuild_portrait_cache()
        self._update_size()

    # ------------------------------------------------------------------
    # Portrait Cache
    # ------------------------------------------------------------------

    def _rebuild_portrait_cache(self):
        """Cache scaled portrait pixmaps for all current combatants."""
        self._portrait_cache.clear()
        size = self.CARD_SIZE - (self.BORDER_WIDTH * 2) - 2  # room for border

        for c in self.state.combat.combatants:
            pixmap = self._resolve_portrait(c)
            if pixmap and not pixmap.isNull():
                scaled = pixmap.scaled(
                    size, size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
                # Center-crop to square
                if scaled.width() != scaled.height():
                    side = min(scaled.width(), scaled.height())
                    sx = (scaled.width() - side) // 2
                    sy = (scaled.height() - side) // 2
                    scaled = scaled.copy(sx, sy, side, side)
                self._portrait_cache[c.id] = scaled

    def _resolve_portrait(self, combatant: Combatant):
        """Look up the portrait image for a combatant.

        PCs: PCSlot -> Character -> idle pixmap
        Characters (no slot): character_id -> Character -> idle pixmap
        Monsters: token_path -> QPixmap (if file exists)
        Returns None to trigger colored-circle fallback.
        """
        if combatant.is_player and combatant.pc_slot_id:
            for slot in self.state.pc_slots:
                if slot.id == combatant.pc_slot_id:
                    char = self.state.characters.get(slot.character_id)
                    if char and "idle" in char.pixmaps:
                        return char.pixmaps["idle"]
                    break
        # Direct character lookup (NPC/character added without a slot)
        if combatant.character_id:
            char = self.state.characters.get(combatant.character_id)
            if char and "idle" in char.pixmaps:
                return char.pixmaps["idle"]
        if combatant.token_path:
            try:
                pm = QPixmap(combatant.token_path)
                if not pm.isNull():
                    return pm
            except Exception:
                pass
        return None

    # ------------------------------------------------------------------
    # Dynamic Window Sizing
    # ------------------------------------------------------------------

    def _update_size(self):
        """Resize the overlay window to fit the current combatant count."""
        n = len(self.state.combat.combatants)
        if n == 0:
            self.resize(100, 100)
            return

        active_size = int(self.CARD_SIZE * self.ACTIVE_SCALE)

        # Width: all normal cards + one card at active size + spacing + padding
        width = (
            (n - 1) * (self.CARD_SIZE + self.CARD_SPACING)
            + active_size
            + self.CARD_SPACING
            + 20   # padding
        )
        # Height: active card + lift + room for name label below
        height = active_size + self.ACTIVE_LIFT + 30
        self.resize(width, height)

    # ------------------------------------------------------------------
    # Render Tick
    # ------------------------------------------------------------------

    def _tick(self):
        """Called at ~30fps -- trigger repaint of the canvas."""
        self.canvas.update()

    # ------------------------------------------------------------------
    # Mouse Drag
    # ------------------------------------------------------------------

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


# ======================================================================
# Canvas (paint surface)
# ======================================================================

class _InitiativeCanvas(QWidget):
    """Inner widget that handles all QPainter rendering."""

    def __init__(self, overlay: InitiativeOverlay):
        super().__init__(overlay)
        self.overlay = overlay

    def paintEvent(self, event):
        ov = self.overlay
        combatants = ov.state.combat.combatants
        if not combatants:
            return

        current_index = ov.state.combat.current_turn_index

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        x_cursor = 10  # left padding
        active_size = int(ov.CARD_SIZE * ov.ACTIVE_SCALE)

        # Vertical baseline: active cards sit higher, normal cards lower
        # The baseline puts normal cards at the bottom of the available space
        baseline_y = ov.ACTIVE_LIFT + (active_size - ov.CARD_SIZE)

        for i, c in enumerate(combatants):
            is_current = (i == current_index)

            if is_current:
                card_size = active_size
                card_y = 0   # raised to top
            else:
                card_size = ov.CARD_SIZE
                card_y = baseline_y

            self._paint_card(painter, c, x_cursor, card_y,
                             card_size, is_current)

            # Paint name label below the active card
            if is_current:
                self._paint_name_label(painter, c.name,
                                       x_cursor, card_y + card_size + 2,
                                       card_size)

            x_cursor += card_size + ov.CARD_SPACING

        painter.end()

    # ------------------------------------------------------------------
    # Card Rendering
    # ------------------------------------------------------------------

    def _paint_card(self, painter, combatant, x, y, size, is_current):
        """Paint one initiative card at (x, y) with the given size."""
        ov = self.overlay

        # -- Determine opacity and border color --
        if not combatant.is_active:
            opacity = 0.35
            border_color = BORDER_INACTIVE
            bg_color = CARD_BG
        elif is_current:
            opacity = 1.0
            border_color = (BORDER_PLAYER_ACTIVE if combatant.is_player
                            else BORDER_MONSTER_ACTIVE)
            bg_color = CARD_BG_ACTIVE
        else:
            opacity = 0.75
            border_color = (BORDER_PLAYER if combatant.is_player
                            else BORDER_MONSTER)
            bg_color = CARD_BG

        painter.setOpacity(opacity)

        # -- Card background (dark, rounded rect) --
        card_rect = QRect(x, y, size, size)
        path = QPainterPath()
        path.addRoundedRect(
            float(x), float(y), float(size), float(size),
            ov.CORNER_RADIUS, ov.CORNER_RADIUS
        )
        painter.setClipPath(path)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(card_rect, ov.CORNER_RADIUS, ov.CORNER_RADIUS)

        # -- Portrait image or fallback token --
        inset = ov.BORDER_WIDTH + 1
        portrait_size = size - (inset * 2)
        portrait_rect = QRect(x + inset, y + inset,
                              portrait_size, portrait_size)

        cached = ov._portrait_cache.get(combatant.id)
        if cached and not cached.isNull():
            # Scale cached portrait to the card's portrait area
            scaled = cached.scaled(
                portrait_size, portrait_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            painter.drawPixmap(portrait_rect, scaled)
        else:
            self._paint_fallback_token(painter, combatant,
                                       x + inset, y + inset, portrait_size)

        # Remove clip so border draws cleanly on top
        painter.setClipRect(self.rect())

        # -- Border ring --
        pen = QPen(border_color, ov.BORDER_WIDTH)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(card_rect, ov.CORNER_RADIUS, ov.CORNER_RADIUS)

        # -- Glow effect for active card --
        if is_current:
            glow_color = QColor(border_color)
            glow_color.setAlpha(60)
            glow_pen = QPen(glow_color, ov.BORDER_WIDTH + 3)
            glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(glow_pen)
            painter.drawRoundedRect(card_rect, ov.CORNER_RADIUS, ov.CORNER_RADIUS)

        # -- Inactive overlay: subtle diagonal slash --
        if not combatant.is_active:
            slash_pen = QPen(QColor(200, 50, 50, 140), 2)
            painter.setPen(slash_pen)
            # Draw a thin diagonal line from top-right to bottom-left
            margin = size // 6
            painter.drawLine(
                x + size - margin, y + margin,
                x + margin, y + size - margin
            )

        painter.setOpacity(1.0)

    # ------------------------------------------------------------------
    # Fallback Token (colored circle with initial)
    # ------------------------------------------------------------------

    def _paint_fallback_token(self, painter, combatant, x, y, size):
        """Draw a colored circle with the combatant's first initial."""
        color = QColor(combatant.token_color)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(x, y, size, size)

        # Draw initial letter
        painter.setPen(QColor(255, 255, 255))
        font_size = max(10, size // self.overlay.INITIAL_FONT_DIVISOR)
        font = QFont("Segoe UI", font_size, QFont.Weight.Bold)
        painter.setFont(font)
        initial = combatant.name[0].upper() if combatant.name else "?"
        painter.drawText(QRect(x, y, size, size),
                         Qt.AlignmentFlag.AlignCenter, initial)

    # ------------------------------------------------------------------
    # Name Label (below active card)
    # ------------------------------------------------------------------

    def _paint_name_label(self, painter, name, x, y, card_width):
        """Paint a small name label centered below the active card."""
        painter.setOpacity(1.0)
        font = QFont("Segoe UI", self.overlay.NAME_FONT_SIZE, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor(240, 240, 240))

        # Truncate long names
        display_name = name
        if len(display_name) > 14:
            display_name = display_name[:12] + ".."

        text_rect = QRect(x - 10, y, card_width + 20, 18)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter, display_name)
