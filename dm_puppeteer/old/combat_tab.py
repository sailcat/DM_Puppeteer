"""
DM Combat tab -- encounter building, initiative tracking, quick actions.

Extracted from app_window.py to keep module sizes manageable.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QGroupBox, QSpinBox, QMessageBox,
    QInputDialog, QFrame, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon

from .models import AppState, Combatant, CombatState, BestiaryEntry
from .bestiary import BestiaryManager


class CombatTab(QWidget):
    """DM Combat encounter management tab."""

    # Signals to parent
    save_requested = pyqtSignal()
    status_message = pyqtSignal(str, int)  # (message, duration_ms)
    overlay_toggled = pyqtSignal(bool)     # initiative overlay show/hide
    combat_changed = pyqtSignal()          # combatants added/removed

    def __init__(self, state: AppState, bestiary_manager: BestiaryManager,
                 parent=None):
        super().__init__(parent)
        self.state = state
        self.bestiary_manager = bestiary_manager
        self._combat_roster: list[dict] = []
        self._selected_combatant_id: str = ""
        self._reinforcements_mode: bool = False
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ---- LEFT PANE: Encounter Roster (40%) ----
        left = QVBoxLayout()
        left.setSpacing(6)

        # Encounter name
        enc_row = QHBoxLayout()
        enc_row.addWidget(QLabel("Encounter:"))
        self.encounter_name_input = QLineEdit()
        self.encounter_name_input.setPlaceholderText("e.g. Goblin Ambush")
        self.encounter_name_input.textChanged.connect(self._on_encounter_name_changed)
        enc_row.addWidget(self.encounter_name_input)
        left.addLayout(enc_row)

        # Search bar (shared by roster mode and reinforcements mode)
        search_row = QHBoxLayout()
        self.monster_search = QLineEdit()
        self.monster_search.setPlaceholderText(
            "Search characters or monsters...")
        self.monster_search.textChanged.connect(self._on_roster_search)
        search_row.addWidget(self.monster_search)
        self.roster_add_btn = QPushButton("+ Add to Roster")
        self.roster_add_btn.setFixedWidth(120)
        self.roster_add_btn.clicked.connect(self._add_monster_from_search)
        search_row.addWidget(self.roster_add_btn)
        left.addLayout(search_row)

        # Search results dropdown
        self.search_results = QWidget()
        self.search_results_layout = QVBoxLayout(self.search_results)
        self.search_results_layout.setContentsMargins(0, 0, 0, 0)
        self.search_results_layout.setSpacing(1)
        self.search_results.setVisible(False)
        left.addWidget(self.search_results)

        # Encounter roster (scrollable)
        self.roster_label = QLabel("Encounter Roster:")
        self.roster_label.setStyleSheet("font-weight: bold; color: #ccc;")
        left.addWidget(self.roster_label)

        self.roster_scroll = QScrollArea()
        self.roster_scroll.setWidgetResizable(True)
        self.roster_scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #444; border-radius: 4px; }")
        self.roster_content = QWidget()
        self.roster_layout = QVBoxLayout(self.roster_content)
        self.roster_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.roster_layout.setSpacing(4)
        self.roster_layout.setContentsMargins(4, 4, 4, 4)

        self.roster_placeholder = QLabel(
            "Your party is listed above.\n"
            "Use 'Add to Roster' to add monsters or NPCs.")
        self.roster_placeholder.setStyleSheet("color: #666; padding: 12px;")
        self.roster_placeholder.setWordWrap(True)
        self.roster_layout.addWidget(self.roster_placeholder)

        self.roster_scroll.setWidget(self.roster_content)
        left.addWidget(self.roster_scroll, stretch=1)

        # Reinforcements hint (hidden until combat starts)
        self.reinforcements_hint = QLabel(
            "Combat is active. Use search to add\n"
            "reinforcements to the current encounter.")
        self.reinforcements_hint.setStyleSheet(
            "color: #888; padding: 12px; font-style: italic;")
        self.reinforcements_hint.setWordWrap(True)
        self.reinforcements_hint.setVisible(False)
        left.addWidget(self.reinforcements_hint)

        self.roster_scroll.setWidget(self.roster_content)
        left.addWidget(self.roster_scroll, stretch=1)

        # Big action buttons
        self.roll_initiative_btn = QPushButton("Roll Initiative!")
        self.roll_initiative_btn.setStyleSheet(
            "QPushButton { background: #2a5a2a; border: 2px solid #44aa44; "
            "border-radius: 6px; padding: 10px 20px; color: #fff; "
            "font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background: #3a6a3a; }"
            "QPushButton:disabled { background: #333; border-color: #555; color: #666; }")
        self.roll_initiative_btn.clicked.connect(self._start_combat)
        left.addWidget(self.roll_initiative_btn)

        self.end_combat_btn = QPushButton("End Combat")
        self.end_combat_btn.setStyleSheet(
            "QPushButton { background: #5a2a2a; border: 1px solid #aa4444; "
            "border-radius: 4px; padding: 6px 12px; color: #ddd; }"
            "QPushButton:hover { background: #6a3a3a; }"
            "QPushButton:disabled { background: #333; border-color: #555; color: #666; }")
        self.end_combat_btn.setEnabled(False)
        self.end_combat_btn.clicked.connect(self._end_combat)
        left.addWidget(self.end_combat_btn)

        layout.addLayout(left, stretch=4)

        # ---- RIGHT PANE: Initiative Order (60%) ----
        right = QVBoxLayout()
        right.setSpacing(6)

        # Round counter + turn controls
        turn_bar = QHBoxLayout()
        self.round_label = QLabel("Round: --")
        self.round_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #ddd;")
        turn_bar.addWidget(self.round_label)
        turn_bar.addStretch()

        self.prev_turn_btn = QPushButton("<< Prev")
        self.prev_turn_btn.setFixedWidth(80)
        self.prev_turn_btn.setEnabled(False)
        self.prev_turn_btn.clicked.connect(self._prev_turn)
        turn_bar.addWidget(self.prev_turn_btn)

        self.next_turn_btn = QPushButton("Next Turn >>")
        self.next_turn_btn.setStyleSheet(
            "QPushButton { background: #2a4a5a; border: 1px solid #4488aa; "
            "border-radius: 4px; padding: 6px 16px; color: #fff; font-weight: bold; }"
            "QPushButton:hover { background: #3a5a6a; }"
            "QPushButton:disabled { background: #333; border-color: #555; color: #666; }")
        self.next_turn_btn.setFixedWidth(120)
        self.next_turn_btn.setEnabled(False)
        self.next_turn_btn.clicked.connect(self._next_turn)
        turn_bar.addWidget(self.next_turn_btn)
        right.addLayout(turn_bar)

        # Initiative order list
        init_label = QLabel("Initiative Order:")
        init_label.setStyleSheet("font-weight: bold; color: #ccc;")
        right.addWidget(init_label)

        self.init_scroll = QScrollArea()
        self.init_scroll.setWidgetResizable(True)
        self.init_scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #444; border-radius: 4px; }")
        self.init_content = QWidget()
        self.init_layout = QVBoxLayout(self.init_content)
        self.init_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.init_layout.setSpacing(2)
        self.init_layout.setContentsMargins(4, 4, 4, 4)

        self.init_placeholder = QLabel(
            "Add monsters and click 'Roll Initiative!' to begin.\n\n"
            "PCs will join from PC Portraits tab automatically.")
        self.init_placeholder.setStyleSheet("color: #666; padding: 12px;")
        self.init_placeholder.setWordWrap(True)
        self.init_layout.addWidget(self.init_placeholder)

        self.init_scroll.setWidget(self.init_content)
        right.addWidget(self.init_scroll, stretch=1)

        # Quick actions
        actions_group = QGroupBox("Quick Actions")
        actions_layout = QHBoxLayout()

        self.damage_btn = QPushButton("Damage")
        self.damage_btn.setEnabled(False)
        self.damage_btn.clicked.connect(self._quick_damage)
        actions_layout.addWidget(self.damage_btn)

        self.heal_btn = QPushButton("Heal")
        self.heal_btn.setEnabled(False)
        self.heal_btn.clicked.connect(self._quick_heal)
        actions_layout.addWidget(self.heal_btn)

        self.kill_btn = QPushButton("Kill")
        self.kill_btn.setStyleSheet(
            "QPushButton { color: #cc4444; }"
            "QPushButton:hover { background: #4a2a2a; }")
        self.kill_btn.setEnabled(False)
        self.kill_btn.clicked.connect(self._quick_kill)
        actions_layout.addWidget(self.kill_btn)

        self.flee_btn = QPushButton("Flee")
        self.flee_btn.setEnabled(False)
        self.flee_btn.clicked.connect(self._quick_flee)
        actions_layout.addWidget(self.flee_btn)

        self.condition_btn = QPushButton("+ Condition")
        self.condition_btn.setEnabled(False)
        self.condition_btn.clicked.connect(self._quick_condition)
        actions_layout.addWidget(self.condition_btn)

        actions_group.setLayout(actions_layout)
        right.addWidget(actions_group)

        # Combatant detail panel
        detail_group = QGroupBox("Selected Combatant")
        detail_layout = QVBoxLayout()

        detail_row1 = QHBoxLayout()
        self.detail_name_label = QLabel("--")
        self.detail_name_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #fff;")
        detail_row1.addWidget(self.detail_name_label)
        detail_row1.addStretch()
        self.detail_hp_label = QLabel("HP: --/--")
        self.detail_hp_label.setStyleSheet("font-size: 12px; color: #88cc88;")
        detail_row1.addWidget(self.detail_hp_label)
        self.detail_ac_label = QLabel("AC: --")
        self.detail_ac_label.setStyleSheet("font-size: 12px; color: #8888cc;")
        detail_row1.addWidget(self.detail_ac_label)
        detail_layout.addLayout(detail_row1)

        detail_row2 = QHBoxLayout()
        self.detail_conditions_label = QLabel("Conditions: none")
        self.detail_conditions_label.setStyleSheet("color: #aaa; font-size: 11px;")
        detail_row2.addWidget(self.detail_conditions_label)
        detail_row2.addStretch()
        self.detail_init_label = QLabel("Init: --")
        self.detail_init_label.setStyleSheet("color: #aaa; font-size: 11px;")
        detail_row2.addWidget(self.detail_init_label)
        detail_layout.addLayout(detail_row2)

        note_row = QHBoxLayout()
        note_row.addWidget(QLabel("Notes:"))
        self.detail_notes = QLineEdit()
        self.detail_notes.setPlaceholderText("DM notes for this combatant...")
        self.detail_notes.textChanged.connect(self._on_combatant_notes_changed)
        note_row.addWidget(self.detail_notes)
        detail_layout.addLayout(note_row)

        detail_group.setLayout(detail_layout)
        right.addWidget(detail_group)

        # Overlay toggle
        overlay_row = QHBoxLayout()
        overlay_row.addStretch()
        self.init_overlay_btn = QPushButton("Show Initiative Overlay")
        self.init_overlay_btn.setCheckable(True)
        self.init_overlay_btn.setEnabled(False)
        self.init_overlay_btn.clicked.connect(self._toggle_initiative_overlay)
        overlay_row.addWidget(self.init_overlay_btn)
        right.addLayout(overlay_row)

        layout.addLayout(right, stretch=6)

        # Auto-populate PCs into the roster
        self._populate_pc_roster()

    # ------------------------------------------------------------------
    # State Restoration
    # ------------------------------------------------------------------

    def restore_from_state(self):
        """Restore UI from persisted combat state (called on app launch)."""
        self.encounter_name_input.setText(
            self.state.combat.encounter_name)
        self.roll_initiative_btn.setEnabled(False)
        self.end_combat_btn.setEnabled(True)
        self.next_turn_btn.setEnabled(True)
        self.prev_turn_btn.setEnabled(True)
        self.init_overlay_btn.setEnabled(True)
        self._set_quick_actions_enabled(True)
        self.round_label.setText(
            f"Round: {self.state.combat.round_number}")
        self._rebuild_initiative_ui()
        # Combat is active -- switch to reinforcements mode
        self._show_reinforcements_mode()

    # ------------------------------------------------------------------
    # Encounter Setup Handlers
    # ------------------------------------------------------------------

    def _on_encounter_name_changed(self, text):
        self.state.combat.encounter_name = text.strip()
        self.save_requested.emit()

    def _on_roster_search(self, query):
        """Search both characters and bestiary, display grouped results."""
        # Clear old results
        while self.search_results_layout.count():
            child = self.search_results_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        query = query.strip()
        if len(query) < 2:
            self.search_results.setVisible(False)
            return

        query_lower = query.lower()

        # Search characters
        char_matches = []
        for char in self.state.characters.values():
            if query_lower in char.name.lower():
                char_matches.append(char)

        # Search bestiary
        bestiary_matches = self.bestiary_manager.search(query, limit=8)

        if not char_matches and not bestiary_matches:
            no_match = QLabel(f'No match. Press + to add "{query}" as custom.')
            no_match.setStyleSheet("color: #888; padding: 4px;")
            self.search_results_layout.addWidget(no_match)
            self.search_results.setVisible(True)
            return

        # Character results section
        if char_matches:
            header = QLabel("CHARACTERS")
            header.setStyleSheet(
                "color: #d4a843; font-size: 10px; font-weight: bold; "
                "padding: 4px 8px 2px;")
            self.search_results_layout.addWidget(header)

            for char in char_matches:
                btn = QPushButton(f"  {char.name}")
                btn.setStyleSheet(
                    "QPushButton { text-align: left; padding: 4px 8px; "
                    "background: #2a2a20; border: 1px solid #554; "
                    "color: #ddd; }"
                    "QPushButton:hover { background: #3a3a2a; "
                    "border-color: #886; }")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                if self._reinforcements_mode:
                    btn.clicked.connect(
                        lambda _, c=char: self._add_reinforcement({
                            "type": "character",
                            "name": c.name,
                            "character_id": c.id,
                            "pc_slot_id": "",
                            "token_color": "#6688cc",
                            "count": 1, "hp": 0, "ac": 0,
                            "init_mod": 0, "token_path": "",
                        }))
                else:
                    btn.clicked.connect(
                        lambda _, c=char: self._add_character_to_roster(c))
                self.search_results_layout.addWidget(btn)

        # Bestiary results section
        if bestiary_matches:
            header = QLabel("BESTIARY")
            header.setStyleSheet(
                "color: #cc5555; font-size: 10px; font-weight: bold; "
                "padding: 4px 8px 2px;")
            self.search_results_layout.addWidget(header)

            for entry in bestiary_matches:
                btn = QPushButton(
                    f"  {entry.name}   HP:{entry.hp_default}  "
                    f"AC:{entry.ac}  DEX:+{entry.initiative_modifier}")
                btn.setStyleSheet(
                    "QPushButton { text-align: left; padding: 4px 8px; "
                    "background: #2a2a2a; border: 1px solid #444; "
                    "color: #ccc; }"
                    "QPushButton:hover { background: #3a3a3a; "
                    "border-color: #666; }")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                if self._reinforcements_mode:
                    btn.clicked.connect(
                        lambda _, e=entry: self._add_reinforcement({
                            "type": "monster",
                            "name": e.name,
                            "count": 1,
                            "hp": e.hp_default,
                            "ac": e.ac,
                            "init_mod": e.initiative_modifier,
                            "color": e.token_color,
                            "token_path": e.token_path,
                            "character_id": "",
                            "pc_slot_id": "",
                            "token_color": e.token_color,
                        }))
                else:
                    btn.clicked.connect(
                        lambda _, e=entry: self._add_bestiary_monster(e))
                self.search_results_layout.addWidget(btn)

        self.search_results.setVisible(True)

    def _add_monster_from_search(self):
        """Add current search text as a monster (bestiary match or custom)."""
        query = self.monster_search.text().strip()
        if not query:
            return

        if self._reinforcements_mode:
            # In reinforcements mode, try bestiary first, then custom
            entry = self.bestiary_manager.get_entry(query)
            if not entry:
                entry = BestiaryEntry(name=query, hp_default=10, ac=10,
                                      initiative_modifier=0, source="custom")
                self.bestiary_manager.add_custom(entry)
            self._add_reinforcement({
                "type": "monster",
                "name": entry.name,
                "count": 1,
                "hp": entry.hp_default,
                "ac": entry.ac,
                "init_mod": entry.initiative_modifier,
                "color": entry.token_color,
                "token_path": entry.token_path,
                "character_id": "",
                "pc_slot_id": "",
                "token_color": entry.token_color,
            })
            return

        entry = self.bestiary_manager.get_entry(query)
        if entry:
            self._add_bestiary_monster(entry)
        else:
            # Create custom entry with defaults
            entry = BestiaryEntry(name=query, hp_default=10, ac=10,
                                  initiative_modifier=0, source="custom")
            self.bestiary_manager.add_custom(entry)
            self._add_bestiary_monster(entry)

    def _add_bestiary_monster(self, entry):
        """Add a monster from the bestiary to the encounter roster."""
        self.bestiary_manager.record_usage(entry.name)

        # Check if already in roster (increment count for monsters)
        for roster_item in self._combat_roster:
            if (roster_item["type"] == "monster"
                    and roster_item["name"] == entry.name):
                roster_item["count"] += 1
                self._rebuild_roster_ui()
                self.monster_search.clear()
                self.search_results.setVisible(False)
                self.save_requested.emit()
                return

        # New entry
        self._combat_roster.append({
            "type": "monster",
            "name": entry.name,
            "count": 1,
            "hp": entry.hp_default,
            "ac": entry.ac,
            "init_mod": entry.initiative_modifier,
            "color": entry.token_color,
            "token_path": entry.token_path,
            "character_id": "",
            "pc_slot_id": "",
            "token_color": entry.token_color,
        })
        self._rebuild_roster_ui()
        self.monster_search.clear()
        self.search_results.setVisible(False)
        self.save_requested.emit()

    def _add_character_to_roster(self, char):
        """Add a character from the library to the encounter roster."""
        # Check if already in roster
        for item in self._combat_roster:
            if item.get("character_id") == char.id:
                self.status_message.emit(
                    f"{char.name} is already in the roster!", 3000)
                return

        self._combat_roster.append({
            "type": "character",
            "name": char.name,
            "character_id": char.id,
            "pc_slot_id": "",
            "token_color": "#6688cc",
            "count": 1,
            "hp": 0,
            "ac": 0,
            "init_mod": 0,
            "token_path": "",
        })
        self._rebuild_roster_ui()
        self.monster_search.clear()
        self.search_results.setVisible(False)
        self.status_message.emit(
            f"Added {char.name} to encounter roster.", 3000)

    # ------------------------------------------------------------------
    # PC Auto-Population
    # ------------------------------------------------------------------

    def _populate_pc_roster(self):
        """Add PC entries to the roster from PC slots.

        Called on tab build and when PC slots change externally.
        Only adds PCs that aren't already in the roster.
        """
        existing_slot_ids = {
            item["pc_slot_id"] for item in self._combat_roster
            if item["type"] == "pc"
        }

        for slot in self.state.pc_slots:
            if not slot.character_id:
                continue
            if slot.id in existing_slot_ids:
                continue
            char = self.state.characters.get(slot.character_id)
            if not char:
                continue

            self._combat_roster.append({
                "type": "pc",
                "name": slot.player_name or char.name,
                "character_id": slot.character_id,
                "pc_slot_id": slot.id,
                "token_color": slot.glow_color,
                "count": 1,
                "hp": 0,
                "ac": 0,
                "init_mod": 0,
                "token_path": "",
            })
        self._rebuild_roster_ui()

    def refresh_pc_roster(self):
        """Public method for app_window to call when PC slots change."""
        if not self._reinforcements_mode:
            self._populate_pc_roster()

    # ------------------------------------------------------------------
    # Roster UI
    # ------------------------------------------------------------------

    def _rebuild_roster_ui(self):
        """Rebuild the encounter roster widget list."""
        # Clear existing
        while self.roster_layout.count():
            child = self.roster_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        pc_items = [r for r in self._combat_roster
                    if r["type"] in ("pc", "character")]
        monster_items = [r for r in self._combat_roster
                         if r["type"] == "monster"]

        if not pc_items and not monster_items:
            placeholder = QLabel(
                "Your party is listed above.\n"
                "Use 'Add to Roster' to add monsters or NPCs.")
            placeholder.setStyleSheet("color: #666; padding: 12px;")
            placeholder.setWordWrap(True)
            self.roster_layout.addWidget(placeholder)
            return

        # --- PC / Character Section ---
        for item in pc_items:
            self._build_pc_roster_row(item)

        # --- Separator ---
        if pc_items and monster_items:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("color: #444;")
            self.roster_layout.addWidget(sep)

        # --- Monster Section ---
        for i, item in enumerate(monster_items):
            self._build_monster_roster_row(item, i)

    def _build_pc_roster_row(self, item):
        """Build one PC/character row in the encounter roster."""
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(4, 2, 4, 2)
        row.setSpacing(6)

        # Gold dot for PCs, blue-ish for library characters
        dot_color = item["token_color"]
        if item["type"] == "pc":
            dot_color = "#d4a843"  # gold accent
        color_dot = QLabel()
        color_dot.setFixedSize(12, 12)
        color_dot.setStyleSheet(
            f"background: {dot_color}; border-radius: 6px;")
        row.addWidget(color_dot)

        # Name
        name_label = QLabel(item["name"])
        name_label.setStyleSheet("font-weight: bold; color: #ddd;")
        row.addWidget(name_label)

        # Type hint for library characters
        if item["type"] == "character":
            hint = QLabel("(NPC)")
            hint.setStyleSheet("color: #6688cc; font-size: 10px;")
            row.addWidget(hint)

        row.addStretch()

        # Remove button (remove from THIS encounter, not from the app)
        remove_btn = QPushButton("X")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setToolTip("Remove from this encounter")
        remove_btn.setStyleSheet(
            "QPushButton { color: #cc4444; background: #2a2a2a; "
            "border: 1px solid #555; border-radius: 3px; }"
            "QPushButton:hover { background: #4a2a2a; }")
        cid = item.get("character_id", "")
        remove_btn.clicked.connect(
            lambda _, c=cid: self._roster_remove_by_character(c))
        row.addWidget(remove_btn)

        row_widget.setStyleSheet(
            "QWidget { background: #252520; border-radius: 3px; }")
        self.roster_layout.addWidget(row_widget)

    def _build_monster_roster_row(self, item, monster_index):
        """Build one monster row in the encounter roster."""
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(4, 2, 4, 2)
        row.setSpacing(6)

        # Token thumbnail (clickable -- opens file picker)
        token_btn = QPushButton()
        token_btn.setFixedSize(28, 28)
        token_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        token_btn.setToolTip("Click to set token image")

        if item.get("token_path"):
            pm = QPixmap(item["token_path"])
            if not pm.isNull():
                scaled = pm.scaled(
                    24, 24,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                token_btn.setIcon(QIcon(scaled))
                token_btn.setIconSize(scaled.size())
            else:
                token_btn.setStyleSheet(
                    f"background: {item['color']}; border-radius: 14px;")
        else:
            token_btn.setStyleSheet(
                f"background: {item['color']}; border-radius: 14px;")

        token_btn.clicked.connect(
            lambda _, idx=monster_index: self._pick_monster_token(idx))
        row.addWidget(token_btn)

        # Name + count
        name_text = item["name"]
        if item["count"] > 1:
            name_text += f" x{item['count']}"
        name_label = QLabel(name_text)
        name_label.setStyleSheet("font-weight: bold; color: #ddd;")
        row.addWidget(name_label)

        row.addStretch()

        # Count controls
        minus_btn = QPushButton("-")
        minus_btn.setFixedSize(24, 24)
        minus_btn.clicked.connect(
            lambda _, idx=monster_index: self._roster_change_count(idx, -1))
        row.addWidget(minus_btn)

        count_label = QLabel(str(item["count"]))
        count_label.setFixedWidth(20)
        count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(count_label)

        plus_btn = QPushButton("+")
        plus_btn.setFixedSize(24, 24)
        plus_btn.clicked.connect(
            lambda _, idx=monster_index: self._roster_change_count(idx, 1))
        row.addWidget(plus_btn)

        # HP/AC display
        stats_label = QLabel(f"HP:{item['hp']}  AC:{item['ac']}")
        stats_label.setStyleSheet("color: #888; font-size: 10px;")
        stats_label.setFixedWidth(80)
        row.addWidget(stats_label)

        # Remove button
        remove_btn = QPushButton("X")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setStyleSheet(
            "QPushButton { color: #cc4444; background: #2a2a2a; "
            "border: 1px solid #555; border-radius: 3px; }"
            "QPushButton:hover { background: #4a2a2a; }")
        remove_btn.clicked.connect(
            lambda _, idx=monster_index: self._roster_remove_monster(idx))
        row.addWidget(remove_btn)

        row_widget.setStyleSheet(
            "QWidget { background: #252525; border-radius: 3px; }")
        self.roster_layout.addWidget(row_widget)

    def _roster_change_count(self, monster_index, delta):
        """Change count for a monster in the roster by its monster-list index."""
        monster_items = [r for r in self._combat_roster
                         if r["type"] == "monster"]
        if 0 <= monster_index < len(monster_items):
            monster_items[monster_index]["count"] = max(
                1, monster_items[monster_index]["count"] + delta)
            self._rebuild_roster_ui()

    def _roster_remove_monster(self, monster_index):
        """Remove a monster entry by its monster-list index."""
        monster_items = [r for r in self._combat_roster
                         if r["type"] == "monster"]
        if 0 <= monster_index < len(monster_items):
            self._combat_roster.remove(monster_items[monster_index])
            self._rebuild_roster_ui()

    def _roster_remove_by_character(self, character_id):
        """Remove a PC/character entry by character_id."""
        self._combat_roster = [
            r for r in self._combat_roster
            if r.get("character_id") != character_id
        ]
        self._rebuild_roster_ui()

    def _pick_monster_token(self, monster_index):
        """Open file picker to assign a token image to a monster."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Token Image",
            "", "Images (*.png *.jpg *.jpeg *.webp)")

        if not path:
            return

        monster_items = [r for r in self._combat_roster
                         if r["type"] == "monster"]
        if 0 <= monster_index < len(monster_items):
            monster_items[monster_index]["token_path"] = path

            # Also update the bestiary entry so it persists
            entry = self.bestiary_manager.get_entry(
                monster_items[monster_index]["name"])
            if entry:
                entry.token_path = path
                if entry.source == "srd":
                    entry.source = "custom"
                    self.state.bestiary.append(entry)

            self._rebuild_roster_ui()
            self.save_requested.emit()

    # ------------------------------------------------------------------
    # Reinforcements Mode
    # ------------------------------------------------------------------

    def _show_reinforcements_mode(self):
        """Switch left pane to reinforcements mode during active combat."""
        self._reinforcements_mode = True
        self.roster_scroll.setVisible(False)
        self.roster_label.setText("Reinforcements:")
        self.roster_add_btn.setText("+ Reinforcement")
        self.monster_search.setPlaceholderText(
            "Search to add reinforcements...")
        self.reinforcements_hint.setVisible(True)

    def _show_roster_mode(self):
        """Switch left pane back to roster staging mode."""
        self._reinforcements_mode = False
        self.roster_scroll.setVisible(True)
        self.roster_label.setText("Encounter Roster:")
        self.roster_add_btn.setText("+ Add to Roster")
        self.monster_search.setPlaceholderText(
            "Search characters or monsters...")
        self.reinforcements_hint.setVisible(False)
        # Re-populate PCs (they may have changed during combat)
        self._populate_pc_roster()

    def _add_reinforcement(self, combatant_data):
        """Add a combatant to active combat as a reinforcement.

        Shows an initiative prompt so Raph can enter the rolled value
        or leave it at 0 to place at the end of the order.
        """
        if combatant_data["type"] == "pc":
            c = Combatant(name=combatant_data["name"])
            c.is_player = True
            c.pc_slot_id = combatant_data.get("pc_slot_id", "")
            c.character_id = combatant_data.get("character_id", "")
            c.token_color = combatant_data["token_color"]
            c.token_path = combatant_data.get("token_path", "")
        elif combatant_data["type"] == "character":
            c = Combatant(name=combatant_data["name"])
            c.is_player = False
            c.character_id = combatant_data.get("character_id", "")
            c.token_color = combatant_data.get("token_color", "#6688cc")
            c.token_path = combatant_data.get("token_path", "")
        else:
            # Monster
            c = Combatant(name=combatant_data["name"])
            c.is_player = False
            c.initiative_modifier = combatant_data.get("init_mod", 0)
            c.hp_max = combatant_data.get("hp", 0)
            c.hp_current = c.hp_max
            c.ac = combatant_data.get("ac", 0)
            c.token_color = combatant_data.get("color", "#cc4444")
            c.token_path = combatant_data.get("token_path", "")

        # Initiative prompt
        init_value, ok = QInputDialog.getInt(
            self, "Reinforcement Initiative",
            f"Initiative for {c.name}:\n\n"
            "(Enter rolled value, or 0 for end of order)",
            value=0, min=0, max=40)

        if not ok:
            return

        c.initiative = init_value
        self.state.combat.add_combatant(c)

        self._rebuild_initiative_ui()
        self._select_combatant(c.id)
        self.combat_changed.emit()
        self.status_message.emit(
            f"{c.name} joins the fight! (Initiative: {init_value})", 3000)
        self.save_requested.emit()

        self.monster_search.clear()
        self.search_results.setVisible(False)

    # ------------------------------------------------------------------
    # Combat Flow
    # ------------------------------------------------------------------

    def _start_combat(self):
        """Begin combat: create combatants from the encounter roster."""
        if not self._combat_roster:
            self.status_message.emit(
                "Add combatants to the roster first!", 3000)
            return

        self.state.combat.reset()
        self.state.combat.is_active = True
        self.state.combat.encounter_name = (
            self.encounter_name_input.text().strip())

        # Single pass through unified roster
        for item in self._combat_roster:
            if item["type"] == "pc":
                c = Combatant(name=item["name"])
                c.is_player = True
                c.pc_slot_id = item.get("pc_slot_id", "")
                c.character_id = item.get("character_id", "")
                c.initiative = 0
                c.initiative_modifier = 0
                c.hp_max = 0
                c.hp_current = 0
                c.token_color = item["token_color"]
                c.token_path = item.get("token_path", "")
                self.state.combat.combatants.append(c)

            elif item["type"] == "character":
                # Library character without a PC slot -- NPC/ally
                c = Combatant(name=item["name"])
                c.is_player = bool(item.get("pc_slot_id"))
                c.pc_slot_id = item.get("pc_slot_id", "")
                c.character_id = item.get("character_id", "")
                c.initiative = 0
                c.initiative_modifier = item.get("init_mod", 0)
                c.hp_max = item.get("hp", 0)
                c.hp_current = c.hp_max
                c.ac = item.get("ac", 0)
                c.token_color = item.get("token_color", "#6688cc")
                c.token_path = item.get("token_path", "")
                self.state.combat.combatants.append(c)

            elif item["type"] == "monster":
                for n in range(item["count"]):
                    suffix = f" #{n+1}" if item["count"] > 1 else ""
                    c = Combatant(name=f"{item['name']}{suffix}")
                    c.is_player = False
                    c.initiative = 0
                    c.initiative_modifier = item.get("init_mod", 0)
                    c.hp_max = item["hp"]
                    c.hp_current = item["hp"]
                    c.ac = item["ac"]
                    c.token_color = item["color"]
                    c.token_path = item.get("token_path", "")
                    self.state.combat.combatants.append(c)

        # Switch left pane to reinforcements mode
        self._show_reinforcements_mode()

        # Update UI state
        self.roll_initiative_btn.setEnabled(False)
        self.end_combat_btn.setEnabled(True)
        self.next_turn_btn.setEnabled(True)
        self.prev_turn_btn.setEnabled(True)
        self.init_overlay_btn.setEnabled(True)
        self._set_quick_actions_enabled(True)

        self._rebuild_initiative_ui()
        self.round_label.setText("Round: 1")
        self.status_message.emit(
            f"Combat started: {len(self.state.combat.combatants)} combatants. "
            "Set initiative values and click Next Turn to begin!", 5000)
        self.combat_changed.emit()
        self.save_requested.emit()

    def _end_combat(self):
        """End combat and clear the initiative order."""
        reply = QMessageBox.question(
            self, "End Combat",
            "End the current combat encounter?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.state.combat.reset()
        self.roll_initiative_btn.setEnabled(True)
        self.end_combat_btn.setEnabled(False)
        self.next_turn_btn.setEnabled(False)
        self.prev_turn_btn.setEnabled(False)
        self.init_overlay_btn.setEnabled(False)
        self.init_overlay_btn.setChecked(False)
        self._set_quick_actions_enabled(False)
        self.round_label.setText("Round: --")
        self._clear_detail_panel()

        # Switch left pane back to roster mode
        self._show_roster_mode()

        # Clear initiative list
        while self.init_layout.count():
            child = self.init_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.init_placeholder = QLabel(
            "Add combatants and click 'Roll Initiative!' to begin.")
        self.init_placeholder.setStyleSheet("color: #666; padding: 12px;")
        self.init_placeholder.setWordWrap(True)
        self.init_layout.addWidget(self.init_placeholder)

        self.status_message.emit("Combat ended.", 3000)
        # Explicitly hide overlay -- setChecked(False) does NOT emit clicked
        self.overlay_toggled.emit(False)
        self.combat_changed.emit()
        self.save_requested.emit()

    def _next_turn(self):
        result = self.state.combat.advance_turn()
        if result:
            self.round_label.setText(f"Round: {self.state.combat.round_number}")
            self._rebuild_initiative_ui()
            self._select_combatant(result.id)
            self.status_message.emit(f"Turn: {result.name}", 3000)
            self.save_requested.emit()

    def _prev_turn(self):
        result = self.state.combat.previous_turn()
        if result:
            self.round_label.setText(f"Round: {self.state.combat.round_number}")
            self._rebuild_initiative_ui()
            self._select_combatant(result.id)
            self.save_requested.emit()

    # ------------------------------------------------------------------
    # Initiative UI
    # ------------------------------------------------------------------

    def _rebuild_initiative_ui(self):
        """Rebuild the initiative order list in the right pane."""
        while self.init_layout.count():
            child = self.init_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self.state.combat.combatants:
            return

        current = self.state.combat.current_combatant()

        for i, c in enumerate(self.state.combat.combatants):
            row_widget = QWidget()
            row_widget.setCursor(Qt.CursorShape.PointingHandCursor)
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(6, 4, 6, 4)
            row.setSpacing(8)

            # Turn indicator
            turn_marker = QLabel()
            turn_marker.setFixedSize(8, 8)
            if current and c.id == current.id:
                turn_marker.setStyleSheet(
                    "background: #ffcc00; border-radius: 4px;")
            else:
                turn_marker.setStyleSheet(
                    "background: transparent;")
            row.addWidget(turn_marker)

            # Initiative value (editable spin)
            init_spin = QSpinBox()
            init_spin.setRange(0, 40)
            init_spin.setValue(c.initiative)
            init_spin.setFixedWidth(50)
            init_spin.setToolTip("Initiative roll")
            init_spin.valueChanged.connect(
                lambda val, cid=c.id: self._on_initiative_changed(cid, val))
            row.addWidget(init_spin)

            # Color dot
            color_dot = QLabel()
            color_dot.setFixedSize(10, 10)
            color_dot.setStyleSheet(
                f"background: {c.token_color}; border-radius: 5px;")
            row.addWidget(color_dot)

            # Name
            name_label = QLabel(c.name)
            name_style = "font-weight: bold; "
            if not c.is_active:
                name_style += "color: #666; text-decoration: line-through;"
            elif c.is_player:
                name_style += "color: #88ccff;"
            else:
                name_style += "color: #ddd;"
            name_label.setStyleSheet(name_style)
            row.addWidget(name_label)

            row.addStretch()

            # HP (editable for monsters, display for PCs)
            if not c.is_player and c.hp_max > 0:
                hp_text = f"{c.hp_current}/{c.hp_max}"
                hp_color = "#88cc88"
                if c.hp_fraction < 0.25:
                    hp_color = "#cc4444"
                elif c.hp_fraction < 0.5:
                    hp_color = "#ccaa44"
                hp_label = QLabel(hp_text)
                hp_label.setStyleSheet(f"color: {hp_color}; font-size: 11px;")
                row.addWidget(hp_label)

            # AC
            if c.ac > 0:
                ac_label = QLabel(f"AC:{c.ac}")
                ac_label.setStyleSheet("color: #8888cc; font-size: 10px;")
                row.addWidget(ac_label)

            # Conditions
            if c.conditions:
                cond_text = " ".join(c.conditions[:3])
                cond_label = QLabel(cond_text)
                cond_label.setStyleSheet("color: #aa88cc; font-size: 10px;")
                row.addWidget(cond_label)

            # Row styling
            bg = "#1a1a1a"
            border = "transparent"
            if current and c.id == current.id:
                bg = "#2a3a2a"
                border = "#44aa44"
            elif self._selected_combatant_id == c.id:
                bg = "#2a2a3a"
                border = "#4444aa"
            elif not c.is_active:
                bg = "#1a1a1a"

            row_widget.setStyleSheet(
                f"QWidget {{ background: {bg}; border: 1px solid {border}; "
                f"border-radius: 4px; }}")

            # Click to select
            row_widget.mousePressEvent = (
                lambda e, cid=c.id: self._select_combatant(cid))

            self.init_layout.addWidget(row_widget)

    def _select_combatant(self, combatant_id):
        """Select a combatant in the initiative list and show details."""
        self._selected_combatant_id = combatant_id
        c = self.state.combat.find_combatant_by_id(combatant_id)
        if not c:
            self._clear_detail_panel()
            return

        self.detail_name_label.setText(c.name)
        if c.hp_max > 0:
            self.detail_hp_label.setText(f"HP: {c.hp_current}/{c.hp_max}")
        else:
            self.detail_hp_label.setText("HP: (player-managed)")
        self.detail_ac_label.setText(f"AC: {c.ac}" if c.ac > 0 else "AC: --")
        self.detail_init_label.setText(f"Init: {c.initiative}")

        if c.conditions:
            self.detail_conditions_label.setText(
                "Conditions: " + ", ".join(c.conditions))
        else:
            self.detail_conditions_label.setText("Conditions: none")

        self.detail_notes.blockSignals(True)
        self.detail_notes.setText(c.notes)
        self.detail_notes.blockSignals(False)

        self._rebuild_initiative_ui()

    def _clear_detail_panel(self):
        self._selected_combatant_id = ""
        self.detail_name_label.setText("--")
        self.detail_hp_label.setText("HP: --/--")
        self.detail_ac_label.setText("AC: --")
        self.detail_init_label.setText("Init: --")
        self.detail_conditions_label.setText("Conditions: none")
        self.detail_notes.blockSignals(True)
        self.detail_notes.clear()
        self.detail_notes.blockSignals(False)

    def _on_initiative_changed(self, combatant_id, value):
        """Update a combatant's initiative value from the spin box."""
        c = self.state.combat.find_combatant_by_id(combatant_id)
        if c:
            c.initiative = value
            # Re-sort after change
            self.state.combat.sort_by_initiative()
            self._rebuild_initiative_ui()
            self.save_requested.emit()

    def _on_combatant_notes_changed(self, text):
        if self._selected_combatant_id:
            c = self.state.combat.find_combatant_by_id(
                self._selected_combatant_id)
            if c:
                c.notes = text
                self.save_requested.emit()

    # ------------------------------------------------------------------
    # Quick Actions
    # ------------------------------------------------------------------

    def _set_quick_actions_enabled(self, enabled):
        self.damage_btn.setEnabled(enabled)
        self.heal_btn.setEnabled(enabled)
        self.kill_btn.setEnabled(enabled)
        self.flee_btn.setEnabled(enabled)
        self.condition_btn.setEnabled(enabled)

    def _get_selected_or_current(self):
        """Get the selected combatant, or current turn combatant."""
        if self._selected_combatant_id:
            c = self.state.combat.find_combatant_by_id(
                self._selected_combatant_id)
            if c:
                return c
        return self.state.combat.current_combatant()

    def _quick_damage(self):
        c = self._get_selected_or_current()
        if not c:
            return
        amount, ok = QInputDialog.getInt(
            self, "Damage", f"Damage to {c.name}:", 0, 0, 9999)
        if ok and amount > 0:
            c.apply_damage(amount)
            self._rebuild_initiative_ui()
            self._select_combatant(c.id)
            self.status_message.emit(
                f"{c.name} takes {amount} damage! "
                f"(HP: {c.hp_current}/{c.hp_max})", 3000)
            self.save_requested.emit()

    def _quick_heal(self):
        c = self._get_selected_or_current()
        if not c:
            return
        amount, ok = QInputDialog.getInt(
            self, "Heal", f"Heal {c.name}:", 0, 0, 9999)
        if ok and amount > 0:
            c.apply_heal(amount)
            self._rebuild_initiative_ui()
            self._select_combatant(c.id)
            self.status_message.emit(
                f"{c.name} heals {amount}! "
                f"(HP: {c.hp_current}/{c.hp_max})", 3000)
            self.save_requested.emit()

    def _quick_kill(self):
        c = self._get_selected_or_current()
        if not c:
            return
        reply = QMessageBox.question(
            self, "Kill Combatant",
            f"Kill {c.name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            c.hp_current = 0
            c.is_active = False
            self._rebuild_initiative_ui()
            self._select_combatant(c.id)
            self.status_message.emit(f"{c.name} has been slain!", 3000)
            self.save_requested.emit()

    def _quick_flee(self):
        c = self._get_selected_or_current()
        if not c:
            return
        reply = QMessageBox.question(
            self, "Flee",
            f"Remove {c.name} from combat (fled)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.state.combat.remove_combatant(c.id)
            self._clear_detail_panel()
            self._rebuild_initiative_ui()
            self.status_message.emit(
                f"{c.name} has fled the battlefield!", 3000)
            self.combat_changed.emit()
            self.save_requested.emit()

    def _quick_condition(self):
        c = self._get_selected_or_current()
        if not c:
            return
        conditions = [
            "Blinded", "Charmed", "Deafened", "Frightened",
            "Grappled", "Incapacitated", "Invisible", "Paralyzed",
            "Petrified", "Poisoned", "Prone", "Restrained",
            "Stunned", "Unconscious", "Concentrating", "Exhaustion"]
        # Show existing conditions for removal
        if c.conditions:
            choices = [f"REMOVE: {cond}" for cond in c.conditions] + conditions
        else:
            choices = conditions
        choice, ok = QInputDialog.getItem(
            self, "Condition", f"Add/remove condition for {c.name}:",
            choices, 0, False)
        if ok and choice:
            if choice.startswith("REMOVE: "):
                cond = choice[8:]
                c.remove_condition(cond)
                self.status_message.emit(
                    f"Removed {cond} from {c.name}", 3000)
            else:
                c.add_condition(choice)
                self.status_message.emit(
                    f"{c.name} is now {choice}", 3000)
            self._rebuild_initiative_ui()
            self._select_combatant(c.id)
            self.save_requested.emit()

    # ------------------------------------------------------------------
    # Overlay Toggle
    # ------------------------------------------------------------------

    def _toggle_initiative_overlay(self):
        checked = self.init_overlay_btn.isChecked()
        self.state.initiative_overlay_visible = checked
        if checked:
            self.init_overlay_btn.setText("Hide Initiative Overlay")
        else:
            self.init_overlay_btn.setText("Show Initiative Overlay")
        self.overlay_toggled.emit(checked)
        self.save_requested.emit()
