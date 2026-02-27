"""
Global hotkey listener using pynput.
Used as fallback when Stream Deck hardware is not available.
"""

from pynput import keyboard
from PyQt6.QtCore import QObject, pyqtSignal


class HotkeyListener(QObject):
    """Listens for global keyboard shortcuts."""

    hotkey_pressed = pyqtSignal(int)  # button_index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hotkeys: dict[frozenset, int] = {}  # key_combo -> button_index
        self.current_keys: set[str] = set()
        self.listener = None

    def register(self, hotkey_string: str, button_index: int):
        """Register a hotkey like 'ctrl+shift+1' for a button index."""
        normalized = self._normalize(hotkey_string)
        if normalized:
            self.hotkeys[normalized] = button_index

    def clear(self):
        self.hotkeys.clear()

    def start(self):
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self.listener.daemon = True
        self.listener.start()

    def stop(self):
        if self.listener:
            self.listener.stop()
            self.listener = None

    def _normalize(self, hotkey_string: str) -> frozenset | None:
        if not hotkey_string:
            return None
        parts = hotkey_string.lower().strip().split('+')
        keys = set()
        for part in parts:
            part = part.strip()
            if part in ('ctrl', 'control'):
                keys.add('ctrl')
            elif part == 'shift':
                keys.add('shift')
            elif part == 'alt':
                keys.add('alt')
            elif part in ('cmd', 'super', 'win'):
                keys.add('cmd')
            else:
                keys.add(part)
        return frozenset(keys)

    def _key_to_str(self, key):
        try:
            return key.char
        except AttributeError:
            mapping = {
                keyboard.Key.ctrl_l: 'ctrl', keyboard.Key.ctrl_r: 'ctrl',
                keyboard.Key.shift: 'shift', keyboard.Key.shift_l: 'shift',
                keyboard.Key.shift_r: 'shift',
                keyboard.Key.alt_l: 'alt', keyboard.Key.alt_r: 'alt',
                keyboard.Key.cmd: 'cmd', keyboard.Key.cmd_l: 'cmd',
                keyboard.Key.cmd_r: 'cmd',
            }
            return mapping.get(key, str(key).replace('Key.', ''))

    def _on_press(self, key):
        key_str = self._key_to_str(key)
        if key_str:
            self.current_keys.add(key_str)
            current = frozenset(self.current_keys)
            for combo, btn_idx in self.hotkeys.items():
                if combo == current:
                    self.hotkey_pressed.emit(btn_idx)

    def _on_release(self, key):
        key_str = self._key_to_str(key)
        if key_str:
            self.current_keys.discard(key_str)


# Default hotkey assignments for buttons 0-14
DEFAULT_HOTKEYS = {
    0: "ctrl+shift+1",
    1: "ctrl+shift+2",
    2: "ctrl+shift+3",
    3: "ctrl+shift+4",
    4: "ctrl+shift+5",
    5: "ctrl+shift+6",
    6: "ctrl+shift+7",
    7: "ctrl+shift+8",
    8: "ctrl+shift+9",
    9: "ctrl+shift+0",
    10: "ctrl+alt+1",
    11: "ctrl+alt+2",
    12: "ctrl+alt+3",
    13: "ctrl+alt+4",
    14: "ctrl+alt+5",
}
