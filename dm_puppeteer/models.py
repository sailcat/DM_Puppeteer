"""
Data models and persistence for DM Puppeteer.
"""

import json
import shutil
import uuid
from pathlib import Path
from typing import Optional

from PyQt6.QtGui import QPixmap


def get_data_dir():
    import sys
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / "data"
    return Path(__file__).parent.parent / "data"


def get_characters_dir():
    return get_data_dir() / "characters"


# ---------------------------------------------------------------------------
# Per-character display settings
# ---------------------------------------------------------------------------

class CharacterSettings:
    """Per-character display and animation settings."""

    def __init__(self):
        self.width: int = 400
        self.height: int = 400
        self.opacity: float = 1.0

        # Blink timing
        self.blink_interval_min: float = 2.0
        self.blink_interval_max: float = 6.0
        self.blink_duration: float = 0.15

        # Bounce effect (bob up/down)
        self.bounce_enabled: bool = False
        self.bounce_amount: float = 6.0       # pixels
        self.bounce_speed: float = 3.0        # Hz
        self.bounce_on_talk_only: bool = True

        # Pop-in effect (jump on mic activate)
        self.popin_enabled: bool = False
        self.popin_amount: float = 12.0       # pixels
        self.popin_duration: float = 0.12     # seconds

        # OBS linked actions (per-character)
        self.obs_scene: str = ""              # scene to switch to (empty = don't switch)
        self.obs_text_source: str = ""        # text source to update with character name
        self.obs_show_sources: list[str] = [] # sources to show on activate
        self.obs_hide_sources: list[str] = [] # sources to hide on activate

    def to_dict(self):
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data):
        s = cls()
        for key in s.__dict__:
            if key in data:
                setattr(s, key, data[key])
        return s


# ---------------------------------------------------------------------------
# Character
# ---------------------------------------------------------------------------

class Character:
    FRAME_NAMES = ["idle", "blink", "talk", "talk_blink"]
    VOWEL_FRAME_NAMES = ["mouth_AH", "mouth_EE", "mouth_OO"]

    def __init__(self, char_id=None, name="Unnamed", folder=None):
        self.id = char_id or str(uuid.uuid4())[:8]
        self.name = name
        self.folder = folder
        self.pixmaps: dict[str, QPixmap] = {}
        self.settings = CharacterSettings()

    def load_frames(self):
        self.pixmaps.clear()
        if not self.folder or not self.folder.exists():
            return
        # Load standard frames
        for fn in self.FRAME_NAMES:
            path = self.folder / f"{fn}.png"
            if path.exists():
                pm = QPixmap(str(path))
                if not pm.isNull():
                    self.pixmaps[fn] = pm
        # Load vowel mouth frames (optional)
        for fn in self.VOWEL_FRAME_NAMES:
            path = self.folder / f"{fn}.png"
            if path.exists():
                pm = QPixmap(str(path))
                if not pm.isNull():
                    self.pixmaps[fn] = pm
        # Fallbacks
        if "blink" not in self.pixmaps and "idle" in self.pixmaps:
            self.pixmaps["blink"] = self.pixmaps["idle"]
        if "talk" not in self.pixmaps and "idle" in self.pixmaps:
            self.pixmaps["talk"] = self.pixmaps["idle"]
        if "talk_blink" not in self.pixmaps:
            self.pixmaps["talk_blink"] = self.pixmaps.get("blink", self.pixmaps.get("idle"))

    def get_frame(self, is_talking, is_blinking, vowel: str = ""):
        """
        Get the appropriate frame pixmap.

        Args:
            is_talking: Whether the character is currently speaking
            is_blinking: Whether the character is currently blinking
            vowel: Detected vowel shape ("AH", "EE", "OO", or "")

        Returns:
            QPixmap for the current frame, with fallback chain:
            vowel frame -> talk frame -> idle frame
        """
        if is_talking:
            # Try vowel-specific frame first
            if vowel:
                vowel_key = f"mouth_{vowel}"
                if vowel_key in self.pixmaps:
                    return self.pixmaps[vowel_key]
            # Fall back to standard talk frames
            if is_blinking:
                return self.pixmaps.get("talk_blink")
            return self.pixmaps.get("talk")
        elif is_blinking:
            return self.pixmaps.get("blink")
        return self.pixmaps.get("idle")

    @property
    def has_vowel_frames(self) -> bool:
        """Check if this character has any vowel mouth frames loaded."""
        return any(f"mouth_{v}" in self.pixmaps for v in ("AH", "EE", "OO"))

    def get_idle_pixmap(self):
        return self.pixmaps.get("idle")

    @property
    def is_valid(self):
        return "idle" in self.pixmaps

    def has_frame(self, frame_name):
        if not self.folder:
            return False
        return (self.folder / f"{frame_name}.png").exists()

    def set_frame_from_file(self, frame_name, source_path):
        if not self.folder:
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        dest = self.folder / f"{frame_name}.png"
        shutil.copy2(source_path, dest)
        pm = QPixmap(str(dest))
        if not pm.isNull():
            self.pixmaps[frame_name] = pm

    def remove_frame(self, frame_name):
        if self.folder:
            path = self.folder / f"{frame_name}.png"
            if path.exists():
                path.unlink()
        self.pixmaps.pop(frame_name, None)
        self.load_frames()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "folder": str(self.folder) if self.folder else None,
            "settings": self.settings.to_dict(),
        }

    @classmethod
    def from_dict(cls, data):
        char = cls(
            char_id=data.get("id"),
            name=data.get("name", "Unnamed"),
            folder=Path(data["folder"]) if data.get("folder") else None,
        )
        if "settings" in data:
            char.settings = CharacterSettings.from_dict(data["settings"])
        char.load_frames()
        return char


# ---------------------------------------------------------------------------
# PC Portrait Slot
# ---------------------------------------------------------------------------

class PCSlot:
    """A player character portrait slot with OBS audio linkage."""

    def __init__(self, slot_id=None):
        self.id = slot_id or str(uuid.uuid4())[:8]
        self.character_id: str = ""          # references a Character
        self.obs_audio_source: str = ""      # OBS input name to monitor
        self.glow_color: str = "#00cc66"     # highlight color when speaking
        self.glow_intensity: float = 1.0     # glow strength 0-1
        self.audio_threshold: float = 0.02   # sensitivity
        self.player_name: str = ""           # display name
        self.individual_x: int = -1          # saved position for individual mode
        self.individual_y: int = -1          # (-1 = auto-place)

        # Discord voice receive mapping (NEW -- Phase 3.5)
        self.discord_user_id: int = 0        # maps this slot to a Discord user
        self.is_dm: bool = False             # DM slot: use local mic instead of Discord

        # Voice tuning (Phase 3.5+)
        self.voice_attack_ms: int = 50       # ms above threshold before speaking activates
        self.voice_decay_ms: int = 250       # ms below threshold before speaking deactivates
        self.voice_smoothing: float = 0.3    # RMS smoothing factor (0=no smoothing, 1=raw)
        self.voice_adaptive_multiplier: float = 2.5  # adaptive threshold sensitivity

        # Dice display (Brief 005)
        self.dice_pack: str = ""             # pack folder name, empty = use global default
        self.dice_color: str = ""            # color variant name, empty = auto from glow_color

    def to_dict(self):
        return {
            "id": self.id,
            "character_id": self.character_id,
            "obs_audio_source": self.obs_audio_source,
            "glow_color": self.glow_color,
            "glow_intensity": self.glow_intensity,
            "audio_threshold": self.audio_threshold,
            "player_name": self.player_name,
            "individual_x": self.individual_x,
            "individual_y": self.individual_y,
            "discord_user_id": self.discord_user_id,
            "is_dm": self.is_dm,
            "voice_attack_ms": self.voice_attack_ms,
            "voice_decay_ms": self.voice_decay_ms,
            "voice_smoothing": self.voice_smoothing,
            "voice_adaptive_multiplier": self.voice_adaptive_multiplier,
            "dice_pack": self.dice_pack,
            "dice_color": self.dice_color,
        }

    @classmethod
    def from_dict(cls, data):
        s = cls(slot_id=data.get("id"))
        s.character_id = data.get("character_id", "")
        s.obs_audio_source = data.get("obs_audio_source", "")
        s.glow_color = data.get("glow_color", "#00cc66")
        s.glow_intensity = data.get("glow_intensity", 1.0)
        s.audio_threshold = data.get("audio_threshold", 0.02)
        s.player_name = data.get("player_name", "")
        s.individual_x = data.get("individual_x", -1)
        s.individual_y = data.get("individual_y", -1)
        s.discord_user_id = data.get("discord_user_id", 0)
        s.is_dm = data.get("is_dm", False)
        s.voice_attack_ms = data.get("voice_attack_ms", 50)
        s.voice_decay_ms = data.get("voice_decay_ms", 250)
        s.voice_smoothing = data.get("voice_smoothing", 0.3)
        s.voice_adaptive_multiplier = data.get("voice_adaptive_multiplier", 2.5)
        s.dice_pack = data.get("dice_pack", "")
        s.dice_color = data.get("dice_color", "")
        return s


# ---------------------------------------------------------------------------
# Bestiary Entry (monster/NPC template)
# ---------------------------------------------------------------------------

class BestiaryEntry:
    """A monster or NPC template for quick-add to encounters."""

    def __init__(self, name="", hp_default=0, ac=0, initiative_modifier=0,
                 token_path="", token_color="#cc4444", source="custom",
                 times_used=0):
        self.name = name
        self.hp_default = hp_default
        self.ac = ac
        self.initiative_modifier = initiative_modifier  # DEX mod
        self.token_path = token_path
        self.token_color = token_color
        self.source = source          # "srd", "custom", "history"
        self.times_used = times_used  # for autocomplete ranking

    def to_dict(self):
        return {
            "name": self.name,
            "hp_default": self.hp_default,
            "ac": self.ac,
            "initiative_modifier": self.initiative_modifier,
            "token_path": self.token_path,
            "token_color": self.token_color,
            "source": self.source,
            "times_used": self.times_used,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data.get("name", ""),
            hp_default=data.get("hp_default", 0),
            ac=data.get("ac", 0),
            initiative_modifier=data.get("initiative_modifier", 0),
            token_path=data.get("token_path", ""),
            token_color=data.get("token_color", "#cc4444"),
            source=data.get("source", "custom"),
            times_used=data.get("times_used", 0),
        )


# ---------------------------------------------------------------------------
# Combatant (one entry in initiative order)
# ---------------------------------------------------------------------------

class Combatant:
    """One combatant in the initiative order -- PC, NPC, or monster."""

    def __init__(self, combatant_id=None, name="Unknown"):
        self.id = combatant_id or str(uuid.uuid4())[:8]
        self.name = name
        self.initiative = 0
        self.initiative_modifier = 0   # DEX mod for tiebreaking
        self.hp_current = 0
        self.hp_max = 0
        self.ac = 0
        self.is_player = False         # True = PC, False = NPC/monster
        self.pc_slot_id = ""           # links to PCSlot if is_player
        self.character_id = ""         # links to Character for portrait lookup
        self.token_path = ""           # path to circular token image
        self.token_color = "#666666"   # fallback ring color if no token
        self.conditions: list[str] = []
        self.is_active = True          # False = dead/removed (greyed out)
        self.group_id = ""             # for grouped monsters
        self.notes = ""                # DM-only notes

    def apply_damage(self, amount):
        """Apply damage, clamping HP to 0."""
        self.hp_current = max(0, self.hp_current - amount)
        if self.hp_current == 0:
            self.is_active = False

    def apply_heal(self, amount):
        """Apply healing, clamping HP to max."""
        self.hp_current = min(self.hp_max, self.hp_current + amount)
        if self.hp_current > 0:
            self.is_active = True

    def add_condition(self, condition):
        """Add a condition if not already present."""
        if condition and condition not in self.conditions:
            self.conditions.append(condition)

    def remove_condition(self, condition):
        """Remove a condition if present."""
        if condition in self.conditions:
            self.conditions.remove(condition)

    @property
    def hp_fraction(self):
        """HP as a 0-1 fraction for rendering HP arcs."""
        if self.hp_max <= 0:
            return 1.0
        return self.hp_current / self.hp_max

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "initiative": self.initiative,
            "initiative_modifier": self.initiative_modifier,
            "hp_current": self.hp_current,
            "hp_max": self.hp_max,
            "ac": self.ac,
            "is_player": self.is_player,
            "pc_slot_id": self.pc_slot_id,
            "character_id": self.character_id,
            "token_path": self.token_path,
            "token_color": self.token_color,
            "conditions": self.conditions.copy(),
            "is_active": self.is_active,
            "group_id": self.group_id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data):
        c = cls(
            combatant_id=data.get("id"),
            name=data.get("name", "Unknown"),
        )
        c.initiative = data.get("initiative", 0)
        c.initiative_modifier = data.get("initiative_modifier", 0)
        c.hp_current = data.get("hp_current", 0)
        c.hp_max = data.get("hp_max", 0)
        c.ac = data.get("ac", 0)
        c.is_player = data.get("is_player", False)
        c.pc_slot_id = data.get("pc_slot_id", "")
        c.character_id = data.get("character_id", "")
        c.token_path = data.get("token_path", "")
        c.token_color = data.get("token_color", "#666666")
        c.conditions = data.get("conditions", [])
        c.is_active = data.get("is_active", True)
        c.group_id = data.get("group_id", "")
        c.notes = data.get("notes", "")
        return c


# ---------------------------------------------------------------------------
# Combat State (full initiative tracker)
# ---------------------------------------------------------------------------

class CombatState:
    """Full state of an active (or inactive) combat encounter."""

    def __init__(self):
        self.combatants: list[Combatant] = []
        self.current_turn_index = 0
        self.round_number = 1
        self.is_active = False
        self.encounter_name = ""

    def current_combatant(self):
        """Return the combatant whose turn it is, or None."""
        if not self.combatants or self.current_turn_index >= len(self.combatants):
            return None
        return self.combatants[self.current_turn_index]

    def advance_turn(self):
        """Move to the next active combatant. Skip dead/removed.
        Returns the new active combatant, or None if combat is empty."""
        if not self.combatants:
            return None
        attempts = 0
        while attempts < len(self.combatants):
            self.current_turn_index = (self.current_turn_index + 1) % len(self.combatants)
            if self.current_turn_index == 0:
                self.round_number += 1
            if self.combatants[self.current_turn_index].is_active:
                return self.combatants[self.current_turn_index]
            attempts += 1
        return None

    def previous_turn(self):
        """Move to the previous active combatant (undo). Returns the combatant."""
        if not self.combatants:
            return None
        attempts = 0
        while attempts < len(self.combatants):
            self.current_turn_index = (self.current_turn_index - 1) % len(self.combatants)
            if self.current_turn_index == len(self.combatants) - 1 and self.round_number > 1:
                self.round_number -= 1
            if self.combatants[self.current_turn_index].is_active:
                return self.combatants[self.current_turn_index]
            attempts += 1
        return None

    def sort_by_initiative(self):
        """Sort combatants by initiative (descending), DEX mod tiebreak,
        then alphabetical for identical values."""
        self.combatants.sort(
            key=lambda c: (-c.initiative, -c.initiative_modifier, c.name))

    def add_combatant(self, combatant):
        """Add a combatant at the correct initiative position."""
        self.combatants.append(combatant)
        self.sort_by_initiative()

    def remove_combatant(self, combatant_id):
        """Remove a combatant by ID. Adjusts current_turn_index if needed."""
        for i, c in enumerate(self.combatants):
            if c.id == combatant_id:
                if i < self.current_turn_index:
                    self.current_turn_index -= 1
                elif i == self.current_turn_index:
                    if self.current_turn_index >= len(self.combatants) - 1:
                        self.current_turn_index = 0
                self.combatants.pop(i)
                break
        if self.combatants:
            self.current_turn_index = min(
                self.current_turn_index, len(self.combatants) - 1)
        else:
            self.current_turn_index = 0

    def find_combatant(self, name):
        """Find a combatant by name (case-insensitive). Returns first match."""
        name_lower = name.lower()
        for c in self.combatants:
            if c.name.lower() == name_lower:
                return c
        return None

    def find_combatant_by_id(self, combatant_id):
        """Find a combatant by ID."""
        for c in self.combatants:
            if c.id == combatant_id:
                return c
        return None

    def active_combatants(self):
        """Return only living/active combatants."""
        return [c for c in self.combatants if c.is_active]

    def active_monsters(self):
        """Return only active non-player combatants."""
        return [c for c in self.combatants if c.is_active and not c.is_player]

    def active_players(self):
        """Return only active player combatants."""
        return [c for c in self.combatants if c.is_active and c.is_player]

    def reset(self):
        """Clear all combat state."""
        self.combatants.clear()
        self.current_turn_index = 0
        self.round_number = 1
        self.is_active = False
        self.encounter_name = ""

    def to_dict(self):
        return {
            "combatants": [c.to_dict() for c in self.combatants],
            "current_turn_index": self.current_turn_index,
            "round_number": self.round_number,
            "is_active": self.is_active,
            "encounter_name": self.encounter_name,
        }

    @classmethod
    def from_dict(cls, data):
        state = cls()
        for cdata in data.get("combatants", []):
            try:
                state.combatants.append(Combatant.from_dict(cdata))
            except Exception:
                pass
        state.current_turn_index = data.get("current_turn_index", 0)
        state.round_number = data.get("round_number", 1)
        state.is_active = data.get("is_active", False)
        state.encounter_name = data.get("encounter_name", "")
        return state


# ---------------------------------------------------------------------------
# App State
# ---------------------------------------------------------------------------

class AppState:
    def __init__(self):
        self.characters: dict[str, Character] = {}
        self.deck_assignments: dict[int, str] = {}
        self.active_character_id: Optional[str] = None
        self.mic_threshold: float = 0.02
        self.mic_device: Optional[int] = None
        self.overlay_x: int = 100
        self.overlay_y: int = 100
        self.deck_mode: str = "direct"
        self.deck_brightness: int = 80
        self.hotkey_assignments: dict[int, str] = {}

        # OBS connection settings
        self.obs_host: str = "localhost"
        self.obs_port: int = 4455
        self.obs_password: str = ""
        self.obs_auto_connect: bool = False

        # PC portrait settings
        self.pc_slots: list[PCSlot] = []
        self.pc_overlay_mode: str = "strip"  # "strip" or "individual"
        self.pc_overlay_x: int = 0
        self.pc_overlay_y: int = 700
        self.pc_strip_spacing: int = 10
        self.pc_portrait_size: int = 200
        self.pc_dim_opacity: float = 0.4     # opacity for non-speaking PCs
        self.pc_shade_amount: float = 0.0    # dark overlay on non-speaking (0=off, 1=silhouette)

        # Discord bot settings
        self.discord_token: str = ""
        self.discord_roll_channel_id: int = 0
        self.discord_auto_connect: bool = False
        self.dice_overlay_x: int = 50
        self.dice_overlay_y: int = 50
        self.dice_display_time: float = 6.0
        self.dice_side: str = "left"       # "left" or "right"
        self.dice_stack: str = "top"       # "top" or "bottom"
        self.dice_display_mode: str = "dice_and_card"  # "dice_only", "card_only", "dice_and_card"
        self.dice_default_pack: str = "classic"

        # Discord voice receive settings (NEW -- Phase 3.5)
        self.discord_voice_channel_id: int = 0

        # Initiative & Combat (Phase 5)
        self.combat: CombatState = CombatState()
        self.bestiary: list[BestiaryEntry] = []
        self.initiative_overlay_x: int = 0
        self.initiative_overlay_y: int = 0
        self.initiative_overlay_visible: bool = False

    def get_active_character(self):
        if self.active_character_id and self.active_character_id in self.characters:
            return self.characters[self.active_character_id]
        return None

    def add_character(self, char):
        self.characters[char.id] = char

    def remove_character(self, char_id):
        self.characters.pop(char_id, None)
        to_remove = [k for k, v in self.deck_assignments.items() if v == char_id]
        for k in to_remove:
            del self.deck_assignments[k]
        if self.active_character_id == char_id:
            self.active_character_id = None

    def get_character_for_button(self, button_index):
        cid = self.deck_assignments.get(button_index)
        if cid and cid in self.characters:
            return self.characters[cid]
        return None

    def assign_character_to_button(self, btn, cid):
        self.deck_assignments[btn] = cid

    def unassign_button(self, btn):
        self.deck_assignments.pop(btn, None)

    def save(self, path=None):
        if path is None:
            path = get_data_dir() / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "characters": [c.to_dict() for c in self.characters.values()],
            "deck_assignments": {str(k): v for k, v in self.deck_assignments.items()},
            "hotkey_assignments": {str(k): v for k, v in self.hotkey_assignments.items()},
            "active_character_id": self.active_character_id,
            "mic_threshold": self.mic_threshold,
            "mic_device": self.mic_device,
            "overlay_x": self.overlay_x,
            "overlay_y": self.overlay_y,
            "deck_mode": self.deck_mode,
            "deck_brightness": self.deck_brightness,
            "obs_host": self.obs_host,
            "obs_port": self.obs_port,
            "obs_password": self.obs_password,
            "obs_auto_connect": self.obs_auto_connect,
            "pc_slots": [s.to_dict() for s in self.pc_slots],
            "pc_overlay_mode": self.pc_overlay_mode,
            "pc_overlay_x": self.pc_overlay_x,
            "pc_overlay_y": self.pc_overlay_y,
            "pc_strip_spacing": self.pc_strip_spacing,
            "pc_portrait_size": self.pc_portrait_size,
            "pc_dim_opacity": self.pc_dim_opacity,
            "pc_shade_amount": self.pc_shade_amount,
            "discord_token": self.discord_token,
            "discord_roll_channel_id": self.discord_roll_channel_id,
            "discord_auto_connect": self.discord_auto_connect,
            "dice_overlay_x": self.dice_overlay_x,
            "dice_overlay_y": self.dice_overlay_y,
            "dice_display_time": self.dice_display_time,
            "dice_side": self.dice_side,
            "dice_stack": self.dice_stack,
            "dice_display_mode": self.dice_display_mode,
            "dice_default_pack": self.dice_default_pack,
            "discord_voice_channel_id": self.discord_voice_channel_id,
            "combat": self.combat.to_dict(),
            "bestiary": [b.to_dict() for b in self.bestiary],
            "initiative_overlay_x": self.initiative_overlay_x,
            "initiative_overlay_y": self.initiative_overlay_y,
            "initiative_overlay_visible": self.initiative_overlay_visible,
        }
        # Atomic write: dump to temp file, then rename into place.
        # This prevents corruption if the process is killed mid-write.
        tmp_path = path.with_suffix('.json.tmp')
        with open(tmp_path, 'w') as f:
            json.dump(data, f, indent=2)
            f.flush()
            import os
            os.fsync(f.fileno())
        tmp_path.replace(path)

    @classmethod
    def load(cls, path=None):
        if path is None:
            path = get_data_dir() / "state.json"
        state = cls()
        if not path.exists():
            return state
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return state

        for cdata in data.get("characters", []):
            try:
                char = Character.from_dict(cdata)
                state.characters[char.id] = char
            except Exception as e:
                print(f"Warning: Could not load character: {e}")

        state.deck_assignments = {int(k): v for k, v in data.get("deck_assignments", {}).items()}
        state.hotkey_assignments = {int(k): v for k, v in data.get("hotkey_assignments", {}).items()}
        state.active_character_id = data.get("active_character_id")
        state.mic_threshold = data.get("mic_threshold", 0.02)
        state.mic_device = data.get("mic_device")
        state.overlay_x = data.get("overlay_x", 100)
        state.overlay_y = data.get("overlay_y", 100)
        state.deck_mode = data.get("deck_mode", "direct")
        state.deck_brightness = data.get("deck_brightness", 80)
        state.obs_host = data.get("obs_host", "localhost")
        state.obs_port = data.get("obs_port", 4455)
        state.obs_password = data.get("obs_password", "")
        state.obs_auto_connect = data.get("obs_auto_connect", False)

        for sdata in data.get("pc_slots", []):
            try:
                state.pc_slots.append(PCSlot.from_dict(sdata))
            except Exception:
                pass
        state.pc_overlay_mode = data.get("pc_overlay_mode", "strip")
        state.pc_overlay_x = data.get("pc_overlay_x", 0)
        state.pc_overlay_y = data.get("pc_overlay_y", 700)
        state.pc_strip_spacing = data.get("pc_strip_spacing", 10)
        state.pc_portrait_size = data.get("pc_portrait_size", 200)
        state.pc_dim_opacity = data.get("pc_dim_opacity", 0.4)
        state.pc_shade_amount = data.get("pc_shade_amount", 0.0)
        state.discord_token = data.get("discord_token", "")
        state.discord_roll_channel_id = data.get("discord_roll_channel_id", 0)
        state.discord_auto_connect = data.get("discord_auto_connect", False)
        state.dice_overlay_x = data.get("dice_overlay_x", 50)
        state.dice_overlay_y = data.get("dice_overlay_y", 50)
        state.dice_display_time = data.get("dice_display_time", 6.0)
        state.dice_side = data.get("dice_side", "left")
        state.dice_stack = data.get("dice_stack", "top")
        state.dice_display_mode = data.get("dice_display_mode", "dice_and_card")
        state.dice_default_pack = data.get("dice_default_pack", "classic")
        state.discord_voice_channel_id = data.get("discord_voice_channel_id", 0)

        # Combat state (Phase 5)
        if "combat" in data:
            try:
                state.combat = CombatState.from_dict(data["combat"])
            except Exception:
                state.combat = CombatState()
        for bdata in data.get("bestiary", []):
            try:
                state.bestiary.append(BestiaryEntry.from_dict(bdata))
            except Exception:
                pass
        state.initiative_overlay_x = data.get("initiative_overlay_x", 0)
        state.initiative_overlay_y = data.get("initiative_overlay_y", 0)
        state.initiative_overlay_visible = data.get("initiative_overlay_visible", False)

        return state
