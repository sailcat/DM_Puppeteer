"""
Dice pack asset loader and cache for DM Puppeteer.

Discovers dice packs from data/dice_packs/<pack_name>/ folders,
loads and caches sprites, applies hue shifting for color variants,
and generates placeholder assets when no real packs exist.

Folder structure:
    data/dice_packs/
      classic/
        pack.json
        d20/
          land_01.png .. land_20.png
          tumble/           (optional)
            frame_001.png ..
      transparent/
        pack.json
        d20/ ...

pack.json schema:
    {
      "name": "Classic",
      "author": "...",
      "description": "...",
      "license": "...",
      "preview_image": "preview.png",
      "tier": "default",
      "unlock_type": "none",
      "unlock_threshold": 0,
      "colors": {
        "red": { "hue_shift": 0 },
        "blue": { "hue_shift": 210 },
        ...
      }
    }
"""

import json
import random
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import (
    QPixmap, QImage, QColor, QPainter, QFont, QPen,
    QPolygonF, QBrush
)
from PyQt6.QtCore import QPointF

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Placeholder generator
# ---------------------------------------------------------------------------

# Size for generated placeholders -- matches DiceSprite.DIE_SIZE range.
# No point generating large images that get scaled down immediately.
PLACEHOLDER_SIZE = 128


def _generate_placeholder_face(face_value: int, die_type: str = "d20",
                                base_hue: int = 0,
                                size: int = PLACEHOLDER_SIZE) -> QPixmap:
    """Generate a single placeholder die face sprite.

    Draws a diamond shape with the face number centered on it.
    base_hue controls the color (HSV hue 0-360, or -1 for white/grey).

    Returns a QPixmap of the given size with transparent background.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))  # transparent

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Diamond shape (rotated square)
    margin = size * 0.08
    cx, cy = size / 2.0, size / 2.0
    half = (size / 2.0) - margin

    diamond = QPolygonF([
        QPointF(cx, cy - half),       # top
        QPointF(cx + half, cy),       # right
        QPointF(cx, cy + half),       # bottom
        QPointF(cx - half, cy),       # left
    ])

    # Face color from hue
    if base_hue < 0:
        face_color = QColor(220, 220, 225)
        border_color = QColor(180, 180, 185)
    else:
        face_color = QColor.fromHsv(base_hue, 160, 220)
        border_color = QColor.fromHsv(base_hue, 200, 180)

    # Draw filled diamond with border
    painter.setPen(QPen(border_color, 3))
    painter.setBrush(QBrush(face_color))
    painter.drawPolygon(diamond)

    # Inner highlight (lighter diamond, offset up slightly)
    highlight = QColor(255, 255, 255, 50)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(highlight))
    inner_half = half * 0.6
    inner_diamond = QPolygonF([
        QPointF(cx, cy - inner_half - 2),
        QPointF(cx + inner_half, cy - 2),
        QPointF(cx, cy + inner_half - 2),
        QPointF(cx - inner_half, cy - 2),
    ])
    painter.drawPolygon(inner_diamond)

    # Number text
    font_size = int(size * 0.28) if face_value < 10 else int(size * 0.24)
    font = QFont("Arial", font_size, QFont.Weight.Bold)
    painter.setFont(font)
    painter.setPen(QPen(QColor(255, 255, 255, 230)))

    # Draw text with slight shadow for readability
    text = str(face_value)
    shadow_color = QColor(0, 0, 0, 100)
    painter.setPen(shadow_color)
    painter.drawText(pixmap.rect().adjusted(1, 1, 1, 1),
                     Qt.AlignmentFlag.AlignCenter, text)
    painter.setPen(QColor(255, 255, 255, 240))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)

    # Die type label at bottom
    label_font = QFont("Arial", int(size * 0.1))
    painter.setFont(label_font)
    painter.setPen(QColor(255, 255, 255, 150))
    label_rect = pixmap.rect().adjusted(0, 0, 0, -int(size * 0.06))
    painter.drawText(label_rect,
                     Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                     die_type.upper())

    painter.end()
    return pixmap


def _max_face(die_type: str) -> int:
    """Return the maximum face value for a die type."""
    try:
        return int(die_type.lstrip("d"))
    except (ValueError, AttributeError):
        return 20


# ---------------------------------------------------------------------------
# Color hue definitions for placeholder and default pack
# ---------------------------------------------------------------------------

DEFAULT_COLORS = {
    "red": 0,
    "gold": 45,
    "green": 120,
    "cyan": 180,
    "blue": 210,
    "purple": 270,
    "white": -1,
}


# ---------------------------------------------------------------------------
# DicePackLoader
# ---------------------------------------------------------------------------

class DicePackLoader:
    """Loads and caches dice sprite assets from pack folders.

    If no pack folders exist, generates placeholder sprites on demand.
    Placeholder sprites are colored diamonds with the face number.

    Usage:
        loader = DicePackLoader(data_dir)
        packs = loader.available_packs()
        frame = loader.get_landing_frame("classic", "d20", 17, "blue")
        tumble = loader.get_tumble_frames("classic", "d20", "blue")
    """

    # Name used for the auto-generated placeholder pack
    PLACEHOLDER_PACK = "_placeholder"

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir / "dice_packs"
        self._packs: dict[str, dict] = {}       # pack_name -> pack.json data
        self._cache: dict[str, object] = {}      # cache key -> QPixmap or list[QPixmap]
        self._scan_packs()

    def _scan_packs(self):
        """Discover available dice packs from folder structure."""
        if not self.data_dir.exists():
            return
        for folder in self.data_dir.iterdir():
            if not folder.is_dir():
                continue
            meta_file = folder / "pack.json"
            if not meta_file.exists():
                continue
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta["_folder"] = str(folder)
                self._packs[folder.name] = meta
            except (json.JSONDecodeError, IOError):
                pass

    def available_packs(self) -> list[str]:
        """Return list of available pack folder names.

        Always includes at least one entry -- if no real packs are found,
        returns the placeholder pack name.
        """
        if self._packs:
            return list(self._packs.keys())
        return [self.PLACEHOLDER_PACK]

    def pack_info(self, pack_name: str) -> dict:
        """Return pack.json metadata for a pack."""
        if pack_name == self.PLACEHOLDER_PACK:
            return {
                "name": "Placeholder",
                "author": "DM Puppeteer",
                "description": "Auto-generated placeholder dice",
                "tier": "default",
                "colors": {name: {"hue_shift": hue}
                           for name, hue in DEFAULT_COLORS.items()},
            }
        return self._packs.get(pack_name, {})

    def available_colors(self, pack_name: str) -> list[str]:
        """Return available color names for a pack."""
        info = self.pack_info(pack_name)
        return list(info.get("colors", {}).keys())

    def get_landing_frame(self, pack_name: str, die_type: str,
                          face_value: int, color: str = "red") -> QPixmap:
        """Get the sprite for a specific die face (the 'result' frame).

        Args:
            pack_name: folder name (e.g., "classic") or PLACEHOLDER_PACK
            die_type: "d20", "d12", "d6", etc.
            face_value: the number showing (1-20 for d20)
            color: color variant name

        Returns:
            QPixmap of the die face, or generated placeholder if not found.
        """
        cache_key = f"land:{pack_name}:{die_type}:{face_value:02d}:{color}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # Try loading from pack folder
        pixmap = self._load_landing_from_folder(pack_name, die_type,
                                                 face_value, color)

        # Fallback to placeholder
        if pixmap is None or pixmap.isNull():
            hue = DEFAULT_COLORS.get(color, 0)
            pixmap = _generate_placeholder_face(face_value, die_type,
                                                 base_hue=hue)

        self._cache[cache_key] = pixmap
        return pixmap

    def _load_landing_from_folder(self, pack_name: str, die_type: str,
                                   face_value: int,
                                   color: str) -> QPixmap | None:
        """Attempt to load a landing frame from a real pack folder."""
        pack = self._packs.get(pack_name)
        if not pack:
            return None

        folder = Path(pack["_folder"])
        img_path = folder / die_type / f"land_{face_value:02d}.png"
        if not img_path.exists():
            return None

        pixmap = QPixmap(str(img_path))
        if pixmap.isNull():
            return None

        # Apply color hue shift if needed
        colors = pack.get("colors", {})
        color_info = colors.get(color, {})
        hue_shift = color_info.get("hue_shift", -1)
        if hue_shift >= 0:
            pixmap = self._apply_hue_shift(pixmap, hue_shift)

        return pixmap

    def get_tumble_frames(self, pack_name: str, die_type: str,
                          color: str = "red") -> list[QPixmap]:
        """Get all tumble animation frames for a die type.

        Resolution order:
        1. Pre-rendered tumble/ subfolder (Blender packs)
        2. Landing frames in shuffled order (pseudo-tumble)
        3. Generated placeholder faces in shuffled order

        Returns:
            List of QPixmaps for tumble animation.
        """
        cache_key = f"tumble:{pack_name}:{die_type}:{color}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        frames = self._load_tumble_from_folder(pack_name, die_type, color)

        # Fallback: use landing frames (real or placeholder) in shuffled order
        if not frames:
            max_val = _max_face(die_type)
            faces = list(range(1, max_val + 1))
            random.shuffle(faces)
            frames = [self.get_landing_frame(pack_name, die_type, v, color)
                      for v in faces]
            frames = [f for f in frames if f and not f.isNull()]

        self._cache[cache_key] = frames
        return frames

    def _load_tumble_from_folder(self, pack_name: str, die_type: str,
                                  color: str) -> list[QPixmap]:
        """Attempt to load tumble frames from a real pack folder."""
        pack = self._packs.get(pack_name)
        if not pack:
            return []

        folder = Path(pack["_folder"])
        tumble_dir = folder / die_type / "tumble"
        frames = []

        if tumble_dir.exists():
            # Pre-rendered tumble frames (Blender packs)
            for img_path in sorted(tumble_dir.glob("*.png")):
                pm = QPixmap(str(img_path))
                if pm.isNull():
                    continue
                colors = pack.get("colors", {})
                color_info = colors.get(color, {})
                hue_shift = color_info.get("hue_shift", -1)
                if hue_shift >= 0:
                    pm = self._apply_hue_shift(pm, hue_shift)
                frames.append(pm)
        else:
            # Fallback: use landing frames in shuffled order
            die_dir = folder / die_type
            if die_dir.exists():
                land_files = sorted(die_dir.glob("land_*.png"))
                random.shuffle(land_files)
                for img_path in land_files:
                    pm = QPixmap(str(img_path))
                    if pm.isNull():
                        continue
                    colors = pack.get("colors", {})
                    color_info = colors.get(color, {})
                    hue_shift = color_info.get("hue_shift", -1)
                    if hue_shift >= 0:
                        pm = self._apply_hue_shift(pm, hue_shift)
                    frames.append(pm)

        return frames

    @staticmethod
    def _apply_hue_shift(pixmap: QPixmap, target_hue: int) -> QPixmap:
        """Shift the hue of a pixmap to a target hue value (0-360).

        Uses numpy fast path when available (approx 100x faster for
        large images). Falls back to per-pixel QImage manipulation.

        Only shifts pixels with meaningful saturation (avoids shifting
        white/black/grey pixels). Preserves alpha channel.
        """
        image = pixmap.toImage().convertToFormat(
            QImage.Format.Format_ARGB32)

        if HAS_NUMPY:
            return QPixmap.fromImage(
                _hue_shift_numpy(image, target_hue))
        return QPixmap.fromImage(
            _hue_shift_fallback(image, target_hue))

    def clear_cache(self):
        """Clear the pixmap cache (call when changing packs at runtime)."""
        self._cache.clear()

    def rescan(self):
        """Re-scan pack folders and clear cache. Call after adding packs."""
        self._packs.clear()
        self._cache.clear()
        self._scan_packs()


# ---------------------------------------------------------------------------
# Hue shifting implementations
# ---------------------------------------------------------------------------

def _hue_shift_numpy(image: QImage, target_hue: int) -> QImage:
    """Fast hue shift using numpy array operations."""
    width = image.width()
    height = image.height()
    bytes_per_line = image.bytesPerLine()

    # Get raw pixel data as numpy array
    ptr = image.bits()
    ptr.setsize(height * bytes_per_line)
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((height, bytes_per_line))

    # ARGB32 format: each pixel is 4 bytes [B, G, R, A] on little-endian
    # Slice to just the pixel data (ignore padding bytes if any)
    pixels = arr[:, :width * 4].reshape((height, width, 4)).copy()

    b_ch = pixels[:, :, 0].astype(np.float32)
    g_ch = pixels[:, :, 1].astype(np.float32)
    r_ch = pixels[:, :, 2].astype(np.float32)
    a_ch = pixels[:, :, 3]

    # Convert RGB to HSV-ish to find saturation
    max_c = np.maximum(np.maximum(r_ch, g_ch), b_ch)
    min_c = np.minimum(np.minimum(r_ch, g_ch), b_ch)
    delta = max_c - min_c

    # Mask: only shift pixels with meaningful saturation and alpha
    saturation = np.where(max_c > 0, delta / max_c, 0)
    mask = (saturation > 0.08) & (a_ch > 10)

    if not np.any(mask):
        return image

    # For masked pixels, convert to QColor HSV and shift
    # This hybrid approach: use numpy for masking, QColor for HSV math
    result = image.copy()
    ys, xs = np.where(mask)
    for y, x in zip(ys, xs):
        color = QColor(result.pixel(int(x), int(y)))
        h, s, v, a = color.getHsv()
        color.setHsv(target_hue, s, v, a)
        result.setPixel(int(x), int(y), color.rgba())

    return result


def _hue_shift_fallback(image: QImage, target_hue: int) -> QImage:
    """Per-pixel hue shift using QColor. Slow but always works."""
    result = image.copy()
    for y in range(result.height()):
        for x in range(result.width()):
            color = QColor(result.pixel(x, y))
            if color.alpha() < 10:
                continue   # skip transparent pixels
            h, s, v, a = color.getHsv()
            if s < 20:
                continue   # skip near-grey pixels
            color.setHsv(target_hue, s, v, a)
            result.setPixel(x, y, color.rgba())
    return result
