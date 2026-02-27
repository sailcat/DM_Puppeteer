"""
Stream Deck hardware integration.
Optional - works without a Stream Deck connected.

NOTE: The Elgato Stream Deck software must be CLOSED while this app
is running in direct mode, as both cannot control the device at once.
"""

import threading
from pathlib import Path
from typing import Optional, Callable

from PyQt6.QtCore import QObject, pyqtSignal

# Try to import Stream Deck library (optional dependency)
try:
    from StreamDeck.DeviceManager import DeviceManager
    from StreamDeck.ImageHelpers import PILHelper
    from StreamDeck.Transport.Transport import TransportError
    from PIL import Image, ImageDraw, ImageFont
    STREAMDECK_AVAILABLE = True
except ImportError:
    STREAMDECK_AVAILABLE = False


class DeckManager(QObject):
    """Manages Stream Deck hardware connection and button images."""

    button_pressed = pyqtSignal(int)  # button index
    connection_changed = pyqtSignal(bool, str)  # connected, device_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.deck = None
        self.device_name = ""
        self.key_count = 0
        self.key_layout = (0, 0)  # (rows, cols)
        self._connected = False

    @property
    def is_available(self):
        return STREAMDECK_AVAILABLE

    @property
    def is_connected(self):
        return self._connected and self.deck is not None

    def connect(self) -> bool:
        """Try to connect to a Stream Deck device."""
        if not STREAMDECK_AVAILABLE:
            self.connection_changed.emit(False, "streamdeck library not installed")
            return False

        try:
            decks = DeviceManager().enumerate()
            if not decks:
                self.connection_changed.emit(False, "No Stream Deck found")
                return False

            self.deck = decks[0]
            self.deck.open()
            self.deck.reset()

            self.device_name = self.deck.deck_type()
            self.key_count = self.deck.key_count()
            self.key_layout = self.deck.key_layout()

            self.deck.set_key_callback(self._key_callback)
            self._connected = True

            self.connection_changed.emit(True, self.device_name)
            print(f"Stream Deck connected: {self.device_name} "
                  f"({self.key_layout[1]}x{self.key_layout[0]}, {self.key_count} keys)")
            return True

        except Exception as e:
            msg = str(e)
            # Provide friendly messages for common errors
            if "HID" in msg or "hidapi" in msg or "libusb" in msg or "TransportError" in msg:
                friendly = ("Stream Deck driver not found.\n"
                            "Install the hidapi library:\n"
                            "  * Windows: pip install hidapi\n"
                            "  * macOS: brew install hidapi\n"
                            "  * Linux: sudo apt install libhidapi-hidraw0\n"
                            "Then restart the app.")
            elif "access" in msg.lower() or "permission" in msg.lower():
                friendly = ("Permission denied -- is the Elgato Stream Deck\n"
                            "software running? Close it first, then retry.\n"
                            "On Linux, you may need udev rules for HID access.")
            elif "busy" in msg.lower() or "in use" in msg.lower():
                friendly = ("Stream Deck is in use by another app.\n"
                            "Close the Elgato software and try again.")
            else:
                friendly = f"Connection failed: {msg}"

            self.connection_changed.emit(False, friendly)
            print(f"Stream Deck connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from Stream Deck."""
        if self.deck:
            try:
                self.deck.reset()
                self.deck.close()
            except Exception:
                pass
        self.deck = None
        self._connected = False
        self.connection_changed.emit(False, "Disconnected")

    def set_brightness(self, percent: int):
        """Set deck brightness (0-100)."""
        if self.is_connected:
            try:
                with self.deck:
                    self.deck.set_brightness(percent)
            except Exception as e:
                print(f"Brightness error: {e}")

    def set_button_image(self, button_index: int, image_path: str, label: str = ""):
        """Set a button's image from a PNG file path, with optional label text."""
        if not self.is_connected or not STREAMDECK_AVAILABLE:
            return

        try:
            icon = Image.open(image_path).convert("RGBA")

            # Create a black background, composite the character onto it
            bg = Image.new("RGBA", icon.size, (0, 0, 0, 255))
            bg.paste(icon, mask=icon)
            bg = bg.convert("RGB")

            # Scale to button size with optional label margin
            margin_bottom = 20 if label else 0
            image = PILHelper.create_scaled_key_image(
                self.deck, bg, margins=[0, 0, margin_bottom, 0]
            )

            # Draw label if provided
            if label:
                draw = ImageDraw.Draw(image)
                try:
                    font = ImageFont.truetype("arial.ttf", 12)
                except OSError:
                    font = ImageFont.load_default()
                draw.text(
                    (image.width / 2, image.height - 3),
                    text=label, font=font, anchor="ms", fill="white"
                )

            native = PILHelper.to_native_key_format(self.deck, image)

            with self.deck:
                self.deck.set_key_image(button_index, native)

        except Exception as e:
            print(f"Set button image error (key {button_index}): {e}")

    def clear_button(self, button_index: int):
        """Clear a button's image (set to black)."""
        if not self.is_connected or not STREAMDECK_AVAILABLE:
            return
        try:
            image = PILHelper.create_key_image(self.deck)
            native = PILHelper.to_native_key_format(self.deck, image)
            with self.deck:
                self.deck.set_key_image(button_index, native)
        except Exception as e:
            print(f"Clear button error: {e}")

    def set_button_highlight(self, button_index: int, image_path: str, label: str = ""):
        """Set a button with a colored border to indicate it's the active character."""
        if not self.is_connected or not STREAMDECK_AVAILABLE:
            return

        try:
            icon = Image.open(image_path).convert("RGBA")
            bg = Image.new("RGBA", icon.size, (0, 0, 0, 255))
            bg.paste(icon, mask=icon)
            bg = bg.convert("RGB")

            margin_bottom = 20 if label else 0
            image = PILHelper.create_scaled_key_image(
                self.deck, bg, margins=[3, 3, margin_bottom + 3, 3]
            )

            # Draw highlight border
            draw = ImageDraw.Draw(image)
            w, h = image.size
            for i in range(3):
                draw.rectangle([i, i, w - 1 - i, h - 1 - i], outline=(0, 200, 100))

            if label:
                try:
                    font = ImageFont.truetype("arial.ttf", 12)
                except OSError:
                    font = ImageFont.load_default()
                draw.text(
                    (image.width / 2, image.height - 3),
                    text=label, font=font, anchor="ms", fill=(0, 255, 130)
                )

            native = PILHelper.to_native_key_format(self.deck, image)
            with self.deck:
                self.deck.set_key_image(button_index, native)

        except Exception as e:
            print(f"Set highlight error: {e}")

    def _key_callback(self, deck, key, state):
        """Called from the Stream Deck's internal thread when a button is pressed."""
        if state:  # Only on press, not release
            self.button_pressed.emit(key)
