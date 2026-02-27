"""Main application window -- DM Puppeteer control panel.
Three tabs: NPC Puppet | OBS Control | PC Portraits
"""

import shutil
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QSlider, QComboBox, QGroupBox,
    QFrame, QStatusBar, QSystemTrayIcon, QMenu, QTabWidget,
    QSizePolicy, QMessageBox, QApplication, QScrollArea, QCheckBox,
    QSpinBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QColor, QPainter, QFont, QIcon, QPen

from .models import (
    AppState, Character, PCSlot, get_characters_dir
)
from .widgets import (
    ImageDropZone, CharacterLibrary, DeckGrid,
    CharacterSettingsDialog, PCSlotEditor
)
from .audio import AudioMonitor
from .overlay import PuppetOverlay
from .deck_hw import DeckManager, STREAMDECK_AVAILABLE
from .hotkeys import HotkeyListener, DEFAULT_HOTKEYS
from .obs import OBSManager, OBS_AVAILABLE
from .pc_overlay import PCOverlayManager
from .discord_bot import DiscordBridge, DISCORD_AVAILABLE, DiceRollEvent, VoiceStateEvent
from .voice_receiver import VOICE_RECEIVE_AVAILABLE
from .dice_overlay import DiceRollOverlay
from .bestiary import BestiaryManager
from .combat_tab import CombatTab
from .initiative_overlay import InitiativeOverlay


class AppWindow(QMainWindow):

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.selected_char_id = None
        self._pc_slot_editors = []

        self.setWindowTitle("DM Puppeteer -- Stream Command Center")
        self.setMinimumSize(960, 680)
        self.resize(1020, 720)
        self.setStyleSheet(DARK_THEME)

        # Core systems
        self.overlay = PuppetOverlay(x=state.overlay_x, y=state.overlay_y)
        self.overlay.position_changed.connect(self._on_overlay_moved)

        self.audio = AudioMonitor(device=state.mic_device)
        self.audio.level_changed.connect(self._on_audio_level)
        if hasattr(self.audio, 'vowel_changed'):
            self.audio.vowel_changed.connect(self._on_dm_vowel)

        self.deck_manager = DeckManager()
        self.deck_manager.button_pressed.connect(self._on_deck_button)
        self.deck_manager.connection_changed.connect(self._on_deck_connection)

        self.hotkey_listener = HotkeyListener()
        self.hotkey_listener.hotkey_pressed.connect(self._on_deck_button)

        self.obs = OBSManager()
        self.obs.connection_changed.connect(self._on_obs_connection)
        self.obs.scenes_updated.connect(self._on_obs_scenes_updated)
        self.obs.scene_switched.connect(self._on_obs_scene_switched)
        self.obs.audio_levels.connect(self._on_obs_audio_levels)
        self.obs.inputs_updated.connect(self._on_obs_inputs_updated)
        self.obs.error_occurred.connect(self._on_obs_error)

        # PC overlay manager
        self.pc_manager = PCOverlayManager(state)
        self.pc_manager.set_save_callback(self._save_state)

        # Discord bot bridge
        self.discord = DiscordBridge()
        self.discord.connection_changed.connect(self._on_discord_connection)
        self.discord.dice_roll.connect(self._on_dice_roll)
        self.discord.voice_state.connect(self._on_voice_state)
        self.discord.error_occurred.connect(self._on_discord_error)
        
        # Voice receive signals
        self.discord.player_audio_update.connect(self._on_player_audio)
        self.discord.voice_connected.connect(self._on_voice_connected)
        self.discord.voice_disconnected.connect(self._on_voice_disconnected)
        self.discord.voice_channels_updated.connect(self._on_voice_channels_updated)

        # Dice roll overlay
        self.dice_overlay = DiceRollOverlay(
            x=state.dice_overlay_x, y=state.dice_overlay_y)
        self.dice_overlay.position_changed.connect(self._on_dice_overlay_moved)
        self.dice_overlay.set_display_time(state.dice_display_time)
        self.dice_overlay.set_side(state.dice_side)
        self.dice_overlay.set_stack(state.dice_stack)

        # Bestiary & Combat (Phase 5)
        self.bestiary_manager = BestiaryManager(state)

        # Build UI
        self._build_ui()
        self._populate_from_state()
        self._setup_tray()

        # Start systems
        self.audio.start()
        self._start_input_mode()

        active = state.get_active_character()
        if active:
            self.overlay.set_character(active)
            self.overlay.show()

        if STREAMDECK_AVAILABLE and state.deck_mode == "direct":
            QTimer.singleShot(500, self._try_connect_deck)
        if state.obs_auto_connect:
            QTimer.singleShot(1000, self._obs_connect)
        if state.discord_auto_connect and state.discord_token:
            QTimer.singleShot(2000, self._discord_connect)

    # ===================================================================
    # UI Construction
    # ===================================================================

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # Left: Character Library
        self.library = CharacterLibrary()
        self.library.setFixedWidth(160)
        self.library.character_selected.connect(self._on_character_selected)
        self.library.character_activated.connect(self._on_character_activated)
        self.library.character_deleted.connect(self._on_character_deleted)
        self.library.character_settings_requested.connect(self._open_character_settings)

        # Right: Tabbed panels
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""QTabWidget::pane { border: 1px solid #444; border-top: none; }
            QTabBar::tab {
                background: #2a2a2a; color: #aaa; border: 1px solid #444;
                padding: 8px 18px; margin-right: 2px; border-bottom: none;
                border-top-left-radius: 6px; border-top-right-radius: 6px;
            }
            QTabBar::tab:selected { background: #1e1e1e; color: #fff; }
            QTabBar::tab:hover { background: #333; color: #ddd; }
        """)

        self.tabs.addTab(self._build_puppet_tab(), "Puppet")
        self.tabs.addTab(self._build_obs_tab(), "OBS Control")
        self.tabs.addTab(self._build_pc_tab(), "PC Portraits")
        self.tabs.addTab(self._build_discord_tab(), "Discord")

        self.combat_tab = CombatTab(self.state, self.bestiary_manager)
        self.combat_tab.save_requested.connect(self._save_state)
        self.combat_tab.status_message.connect(
            lambda msg, ms: self.statusBar().showMessage(msg, ms))
        self.combat_tab.overlay_toggled.connect(self._toggle_initiative_overlay)
        self.combat_tab.combat_changed.connect(self._on_combat_changed)
        self.tabs.addTab(self.combat_tab, "DM Combat")

        # Initiative overlay (transparent, OBS window-captured)
        self.initiative_overlay = InitiativeOverlay(
            self.state, x=self.state.initiative_overlay_x, y=self.state.initiative_overlay_y)
        self.initiative_overlay.position_changed.connect(
            self._on_initiative_overlay_moved)

        main_layout.addWidget(self.library)
        main_layout.addWidget(self.tabs, stretch=1)
        self.statusBar().showMessage("Ready -- all settings auto-save on change")

    # ------------------------------------------------------------------
    # Tab 1: NPC Puppet
    # ------------------------------------------------------------------

    def _build_puppet_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Character Editor
        editor_group = QGroupBox("Character Setup")
        editor_layout = QVBoxLayout()

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter character name...")
        self.name_input.setMaximumWidth(250)
        name_row.addWidget(self.name_input)
        self.save_btn = QPushButton("Save Character")
        self.save_btn.setFixedWidth(140)
        self.save_btn.clicked.connect(self._save_character)
        name_row.addWidget(self.save_btn)
        self.new_btn = QPushButton("+  New")
        self.new_btn.setFixedWidth(80)
        self.new_btn.clicked.connect(self._new_character)
        name_row.addWidget(self.new_btn)
        name_row.addStretch()
        editor_layout.addLayout(name_row)

        frames_row = QHBoxLayout()
        frames_row.setSpacing(10)
        self.drop_zones = {}
        for fn, label in [("idle", "Idle"), ("blink", "Blink"),
                           ("talk", "Talk"), ("talk_blink", "Talk+Blink")]:
            zone = ImageDropZone(fn, label)
            zone.file_dropped.connect(self._on_frame_dropped)
            frames_row.addWidget(zone)
            self.drop_zones[fn] = zone
        frames_row.addStretch()
        editor_layout.addLayout(frames_row)

        # Vowel lip sync frames (optional)
        vowel_label = QLabel("Lip Sync Frames (optional):")
        vowel_label.setStyleSheet("color: #999; font-size: 10px; margin-top: 4px;")
        editor_layout.addWidget(vowel_label)

        vowel_row = QHBoxLayout()
        vowel_row.setSpacing(10)
        for fn, label in [("mouth_AH", "Mouth AH"),
                           ("mouth_EE", "Mouth EE"),
                           ("mouth_OO", "Mouth OO")]:
            zone = ImageDropZone(fn, label)
            zone.file_dropped.connect(self._on_frame_dropped)
            vowel_row.addWidget(zone)
            self.drop_zones[fn] = zone
        vowel_row.addStretch()
        editor_layout.addLayout(vowel_row)
        editor_group.setLayout(editor_layout)
        layout.addWidget(editor_group)

        # Bottom: Deck + Settings
        bottom = QHBoxLayout()

        deck_group = QGroupBox("Stream Deck")
        dl = QVBoxLayout()
        conn_row = QHBoxLayout()
        self.deck_status = QLabel("*  Not connected")
        self.deck_status.setStyleSheet("color: #888;")
        self.deck_status.setWordWrap(True)
        self.deck_status.setMinimumWidth(200)
        conn_row.addWidget(self.deck_status)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setFixedWidth(80)
        self.connect_btn.clicked.connect(self._try_connect_deck)
        conn_row.addWidget(self.connect_btn)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Direct (USB)", "Hotkey (Keyboard)"])
        self.mode_combo.setCurrentIndex(0 if self.state.deck_mode == "direct" else 1)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.mode_combo.setFixedWidth(140)
        conn_row.addWidget(self.mode_combo)
        conn_row.addStretch()
        dl.addLayout(conn_row)
        self.deck_grid = DeckGrid(3, 5)
        self.deck_grid.character_assigned.connect(self._on_deck_character_assigned)
        self.deck_grid.character_cleared.connect(self._on_deck_character_cleared)
        self.deck_grid.button_clicked.connect(self._on_deck_button)
        dl.addWidget(self.deck_grid)
        hint = QLabel("Drag characters -> buttons. Click = activate. Again = hide.")
        hint.setStyleSheet("color: #888; font-size: 10px;")
        hint.setWordWrap(True)
        dl.addWidget(hint)
        deck_group.setLayout(dl)
        bottom.addWidget(deck_group, stretch=3)

        settings_group = QGroupBox("Settings")
        sl = QVBoxLayout()
        sl.addWidget(QLabel("Mic Sensitivity:"))
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(1, 100)
        self.threshold_slider.setValue(int(self.state.mic_threshold * 1000))
        self.threshold_slider.valueChanged.connect(self._on_threshold_change)
        sl.addWidget(self.threshold_slider)
        self.level_bar = QLabel("Level: ")
        self.level_bar.setStyleSheet("color: #aaa; font-family: monospace; font-size: 10px;")
        sl.addWidget(self.level_bar)
        sl.addWidget(QLabel("Microphone:"))
        self.mic_combo = QComboBox()
        self.mic_combo.addItem("Default", None)
        for di, dn in AudioMonitor.list_devices():
            self.mic_combo.addItem(dn, di)
        self.mic_combo.currentIndexChanged.connect(self._on_mic_changed)
        sl.addWidget(self.mic_combo)
        sl.addSpacing(10)
        self.overlay_btn = QPushButton("Show Overlay")
        self.overlay_btn.setCheckable(True)
        self.overlay_btn.setChecked(self.state.active_character_id is not None)
        self.overlay_btn.clicked.connect(self._toggle_overlay)
        sl.addWidget(self.overlay_btn)
        sl.addStretch()
        settings_group.setLayout(sl)
        bottom.addWidget(settings_group, stretch=1)

        layout.addLayout(bottom)
        return tab

    # ------------------------------------------------------------------
    # Tab 2: OBS Control
    # ------------------------------------------------------------------

    def _build_obs_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Connection
        conn_group = QGroupBox("OBS Connection")
        cg = QHBoxLayout()
        cg.addWidget(QLabel("Host:"))
        self.obs_host_input = QLineEdit(self.state.obs_host)
        self.obs_host_input.setFixedWidth(120)
        cg.addWidget(self.obs_host_input)
        cg.addWidget(QLabel("Port:"))
        self.obs_port_input = QLineEdit(str(self.state.obs_port))
        self.obs_port_input.setFixedWidth(60)
        cg.addWidget(self.obs_port_input)
        cg.addWidget(QLabel("Password:"))
        self.obs_pass_input = QLineEdit(self.state.obs_password)
        self.obs_pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.obs_pass_input.setFixedWidth(120)
        self.obs_pass_input.setPlaceholderText("(optional)")
        cg.addWidget(self.obs_pass_input)
        self.obs_connect_btn = QPushButton("Connect")
        self.obs_connect_btn.setFixedWidth(100)
        self.obs_connect_btn.clicked.connect(self._obs_connect)
        cg.addWidget(self.obs_connect_btn)
        self.obs_status = QLabel("*  Not connected")
        self.obs_status.setStyleSheet("color: #888;")
        cg.addWidget(self.obs_status)
        self.obs_auto_check = QCheckBox("Auto-connect")
        self.obs_auto_check.setChecked(self.state.obs_auto_connect)
        self.obs_auto_check.stateChanged.connect(self._on_obs_auto_changed)
        cg.addWidget(self.obs_auto_check)
        cg.addStretch()
        conn_group.setLayout(cg)
        layout.addWidget(conn_group)

        content = QHBoxLayout()

        # Scenes
        scene_group = QGroupBox("Scenes")
        self.scene_layout = QVBoxLayout()
        self.scene_buttons_area = QWidget()
        self.scene_buttons_layout = QVBoxLayout(self.scene_buttons_area)
        self.scene_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scene_buttons_layout.setSpacing(4)
        self.scene_placeholder = QLabel(
            "Connect to OBS to see scenes.\n\n"
            "OBS 28+: Tools -> WebSocket Server Settings.\n\n"
            "Right-click a character -> Settings -> OBS Linked Actions\n"
            "to auto-switch scenes per character.")
        self.scene_placeholder.setStyleSheet("color: #888; padding: 20px;")
        self.scene_placeholder.setWordWrap(True)
        self.scene_buttons_layout.addWidget(self.scene_placeholder)
        scene_scroll = QScrollArea()
        scene_scroll.setWidget(self.scene_buttons_area)
        scene_scroll.setWidgetResizable(True)
        scene_scroll.setStyleSheet("QScrollArea { border: none; }")
        self.scene_layout.addWidget(scene_scroll)
        refresh_btn = QPushButton("Refresh Scenes")
        refresh_btn.clicked.connect(self._obs_refresh_scenes)
        self.scene_layout.addWidget(refresh_btn)
        scene_group.setLayout(self.scene_layout)
        content.addWidget(scene_group, stretch=2)

        # Controls
        ctrl_group = QGroupBox("Stream Controls")
        cl = QVBoxLayout()
        self.stream_btn = QPushButton("*  Toggle Stream")
        self.stream_btn.setFixedHeight(40)
        self.stream_btn.clicked.connect(self.obs.toggle_stream)
        self.stream_btn.setEnabled(False)
        cl.addWidget(self.stream_btn)
        self.record_btn = QPushButton("Toggle Recording")
        self.record_btn.setFixedHeight(40)
        self.record_btn.clicked.connect(self.obs.toggle_recording)
        self.record_btn.setEnabled(False)
        cl.addWidget(self.record_btn)
        cl.addSpacing(10)
        cl.addWidget(QLabel("Current Scene:"))
        self.current_scene_label = QLabel("--")
        self.current_scene_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.current_scene_label.setStyleSheet("color: #00cc66; padding: 4px;")
        cl.addWidget(self.current_scene_label)
        cl.addStretch()
        if not OBS_AVAILABLE:
            warn = QLabel("*  obsws-python not installed.\nRun: pip install obsws-python")
            warn.setStyleSheet("color: #cc6600; padding: 8px; font-weight: bold;")
            warn.setWordWrap(True)
            cl.addWidget(warn)
        ctrl_group.setLayout(cl)
        content.addWidget(ctrl_group, stretch=1)

        layout.addLayout(content)
        return tab

    # ------------------------------------------------------------------
    # Tab 3: PC Portraits
    # ------------------------------------------------------------------

    def _build_pc_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Top bar: mode + settings (two rows to avoid cramping)
        top_group = QGroupBox("PC Portrait Settings")
        top_vbox = QVBoxLayout()

        # Row 1: Mode + show button
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Overlay Mode:"))
        self.pc_mode_combo = QComboBox()
        self.pc_mode_combo.addItems(["Strip (one window)", "Individual (per player)"])
        self.pc_mode_combo.setCurrentIndex(
            0 if self.state.pc_overlay_mode == "strip" else 1)
        self.pc_mode_combo.currentIndexChanged.connect(self._on_pc_mode_changed)
        self.pc_mode_combo.setFixedWidth(170)
        row1.addWidget(self.pc_mode_combo)
        row1.addStretch()
        self.pc_show_btn = QPushButton("Show Portraits")
        self.pc_show_btn.setCheckable(True)
        self.pc_show_btn.clicked.connect(self._toggle_pc_overlay)
        row1.addWidget(self.pc_show_btn)
        top_vbox.addLayout(row1)

        # Row 2: Size, Spacing, Dim, Shade -- all sliders
        row2 = QHBoxLayout()

        row2.addWidget(QLabel("Size:"))
        self.pc_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.pc_size_slider.setRange(80, 500)
        self.pc_size_slider.setValue(self.state.pc_portrait_size)
        self.pc_size_slider.setFixedWidth(100)
        self.pc_size_slider.valueChanged.connect(self._on_pc_settings_changed)
        row2.addWidget(self.pc_size_slider)
        self.pc_size_label = QLabel(f"{self.state.pc_portrait_size}px")
        self.pc_size_label.setFixedWidth(38)
        row2.addWidget(self.pc_size_label)

        row2.addSpacing(8)
        row2.addWidget(QLabel("Spacing:"))
        self.pc_spacing_slider = QSlider(Qt.Orientation.Horizontal)
        self.pc_spacing_slider.setRange(0, 100)
        self.pc_spacing_slider.setValue(self.state.pc_strip_spacing)
        self.pc_spacing_slider.setFixedWidth(80)
        self.pc_spacing_slider.valueChanged.connect(self._on_pc_settings_changed)
        row2.addWidget(self.pc_spacing_slider)
        self.pc_spacing_label = QLabel(f"{self.state.pc_strip_spacing}px")
        self.pc_spacing_label.setFixedWidth(32)
        row2.addWidget(self.pc_spacing_label)

        row2.addSpacing(8)
        row2.addWidget(QLabel("Dim:"))
        self.pc_dim_slider = QSlider(Qt.Orientation.Horizontal)
        self.pc_dim_slider.setRange(0, 100)
        self.pc_dim_slider.setValue(int(self.state.pc_dim_opacity * 100))
        self.pc_dim_slider.setFixedWidth(80)
        self.pc_dim_slider.valueChanged.connect(self._on_pc_settings_changed)
        row2.addWidget(self.pc_dim_slider)
        self.pc_dim_label = QLabel(f"{int(self.state.pc_dim_opacity * 100)}%")
        self.pc_dim_label.setFixedWidth(32)
        row2.addWidget(self.pc_dim_label)

        row2.addSpacing(8)
        row2.addWidget(QLabel("Shade:"))
        self.pc_shade_slider = QSlider(Qt.Orientation.Horizontal)
        self.pc_shade_slider.setRange(0, 100)
        self.pc_shade_slider.setValue(int(self.state.pc_shade_amount * 100))
        self.pc_shade_slider.setFixedWidth(80)
        self.pc_shade_slider.setToolTip("Darken non-speaking portraits (silhouette effect)")
        self.pc_shade_slider.valueChanged.connect(self._on_pc_settings_changed)
        row2.addWidget(self.pc_shade_slider)
        self.pc_shade_label = QLabel(f"{int(self.state.pc_shade_amount * 100)}%")
        self.pc_shade_label.setFixedWidth(32)
        row2.addWidget(self.pc_shade_label)

        row2.addStretch()
        top_vbox.addLayout(row2)

# --- Voice Receive Controls ---
        voice_group = QGroupBox("Discord Voice Detection")
        voice_layout = QVBoxLayout()

        voice_row1 = QHBoxLayout()
        voice_row1.addWidget(QLabel("Voice Channel:"))
        self.voice_channel_combo = QComboBox()
        self.voice_channel_combo.setFixedWidth(250)
        self.voice_channel_combo.currentIndexChanged.connect(lambda _: self._update_discord_user_dropdowns())
        voice_row1.addWidget(self.voice_channel_combo)

        self.voice_refresh_btn = QPushButton("Refresh")
        self.voice_refresh_btn.setFixedWidth(32)
        self.voice_refresh_btn.setToolTip("Refresh voice channels")
        self.voice_refresh_btn.clicked.connect(self._refresh_voice_channels)
        voice_row1.addWidget(self.voice_refresh_btn)

        voice_row1.addStretch()

        self.voice_join_btn = QPushButton("Join Voice")
        self.voice_join_btn.setCheckable(True)
        self.voice_join_btn.setFixedWidth(130)
        self.voice_join_btn.clicked.connect(self._toggle_voice_receive)
        voice_row1.addWidget(self.voice_join_btn)

        self.voice_status_label = QLabel("")
        self.voice_status_label.setStyleSheet("color: #888; font-size: 11px;")
        voice_row1.addWidget(self.voice_status_label)

        voice_layout.addLayout(voice_row1)

        if not VOICE_RECEIVE_AVAILABLE:
            notice = QLabel(
                "Voice detection requires py-cord[voice].\n"
                "Run: pip install py-cord[voice]")
            notice.setStyleSheet("color: #cc8800; padding: 4px;")
            notice.setWordWrap(True)
            voice_layout.addWidget(notice)

        voice_group.setLayout(voice_layout)
        top_vbox.addWidget(voice_group)
        top_group.setLayout(top_vbox)
        layout.addWidget(top_group)

        # Player slots
        slots_group = QGroupBox("Player Slots")
        slots_layout = QVBoxLayout()

        self.pc_slot_scroll = QScrollArea()
        self.pc_slot_scroll.setWidgetResizable(True)
        self.pc_slot_scroll.setStyleSheet("QScrollArea { border: none; }")
        self.pc_slot_content = QWidget()
        self.pc_slot_layout = QVBoxLayout(self.pc_slot_content)
        self.pc_slot_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.pc_slot_layout.setSpacing(6)
        self.pc_slot_scroll.setWidget(self.pc_slot_content)
        slots_layout.addWidget(self.pc_slot_scroll)

        add_btn = QPushButton("+  Add Player Slot")
        add_btn.clicked.connect(self._add_pc_slot)
        slots_layout.addWidget(add_btn)

        slots_group.setLayout(slots_layout)
        layout.addWidget(slots_group, stretch=1)

        # Info
        info = QLabel(
            "Each slot maps a character to an OBS audio source. "
            "When that player speaks, their portrait highlights and animates. "
            "Connect to OBS first to pick audio sources.")
        info.setStyleSheet("color: #888; font-size: 10px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        return tab

    # ------------------------------------------------------------------
    # Tab 4: Discord Bot
    # ------------------------------------------------------------------

    def _build_discord_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Connection
        conn_group = QGroupBox("Discord Bot Connection")
        cg = QVBoxLayout()

        token_row = QHBoxLayout()
        token_row.addWidget(QLabel("Bot Token:"))
        self.discord_token_input = QLineEdit(self.state.discord_token)
        self.discord_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.discord_token_input.setPlaceholderText(
            "Paste your bot token from Discord Developer Portal")
        token_row.addWidget(self.discord_token_input)
        self.discord_connect_btn = QPushButton("Connect")
        self.discord_connect_btn.setFixedWidth(100)
        self.discord_connect_btn.clicked.connect(self._discord_connect)
        token_row.addWidget(self.discord_connect_btn)
        cg.addLayout(token_row)

        settings_row = QHBoxLayout()
        settings_row.addWidget(QLabel("Roll Channel ID:"))
        self.discord_channel_input = QLineEdit(
            str(self.state.discord_roll_channel_id) if self.state.discord_roll_channel_id else "")
        self.discord_channel_input.setPlaceholderText(
            "Right-click #disc-rolls-only -> Copy Channel ID")
        self.discord_channel_input.setFixedWidth(200)
        settings_row.addWidget(self.discord_channel_input)

        self.discord_status = QLabel("*  Not connected")
        self.discord_status.setStyleSheet("color: #888;")
        self.discord_status.setWordWrap(True)
        settings_row.addWidget(self.discord_status)

        self.discord_auto_check = QCheckBox("Auto-connect")
        self.discord_auto_check.setChecked(self.state.discord_auto_connect)
        self.discord_auto_check.stateChanged.connect(self._on_discord_auto_changed)
        settings_row.addWidget(self.discord_auto_check)
        settings_row.addStretch()
        cg.addLayout(settings_row)

        conn_group.setLayout(cg)
        layout.addWidget(conn_group)

        content = QHBoxLayout()

        # Dice overlay settings
        dice_group = QGroupBox("Dice Roll Overlay")
        dg = QVBoxLayout()

        dice_toggle = QHBoxLayout()
        self.dice_show_btn = QPushButton("Show Dice Overlay")
        self.dice_show_btn.setCheckable(True)
        self.dice_show_btn.clicked.connect(self._toggle_dice_overlay)
        dice_toggle.addWidget(self.dice_show_btn)

        dice_toggle.addWidget(QLabel("Display Time:"))
        self.dice_time_slider = QSlider(Qt.Orientation.Horizontal)
        self.dice_time_slider.setRange(2, 15)
        self.dice_time_slider.setValue(int(self.state.dice_display_time))
        self.dice_time_slider.setFixedWidth(100)
        self.dice_time_slider.valueChanged.connect(self._on_dice_time_changed)
        dice_toggle.addWidget(self.dice_time_slider)
        self.dice_time_label = QLabel(f"{int(self.state.dice_display_time)}s")
        self.dice_time_label.setFixedWidth(24)
        dice_toggle.addWidget(self.dice_time_label)
        dice_toggle.addStretch()
        dg.addLayout(dice_toggle)

        # Side & stack layout options
        dice_layout_row = QHBoxLayout()
        dice_layout_row.addWidget(QLabel("Slide From:"))
        self.dice_side_combo = QComboBox()
        self.dice_side_combo.addItems(["left", "right"])
        self.dice_side_combo.setCurrentText(self.state.dice_side)
        self.dice_side_combo.setFixedWidth(80)
        self.dice_side_combo.currentTextChanged.connect(self._on_dice_side_changed)
        dice_layout_row.addWidget(self.dice_side_combo)

        dice_layout_row.addWidget(QLabel("Stack From:"))
        self.dice_stack_combo = QComboBox()
        self.dice_stack_combo.addItems(["top", "bottom"])
        self.dice_stack_combo.setCurrentText(self.state.dice_stack)
        self.dice_stack_combo.setFixedWidth(80)
        self.dice_stack_combo.currentTextChanged.connect(self._on_dice_stack_changed)
        dice_layout_row.addWidget(self.dice_stack_combo)
        dice_layout_row.addStretch()
        dg.addLayout(dice_layout_row)

        # Roll log
        dg.addWidget(QLabel("Recent Rolls:"))
        self.roll_log_area = QScrollArea()
        self.roll_log_area.setWidgetResizable(True)
        self.roll_log_area.setStyleSheet("QScrollArea { border: 1px solid #444; }")
        self.roll_log_content = QWidget()
        self.roll_log_layout = QVBoxLayout(self.roll_log_content)
        self.roll_log_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.roll_log_layout.setSpacing(2)
        self.roll_log_area.setWidget(self.roll_log_content)

        placeholder = QLabel(
            "Dice rolls from Avrae / D&D Beyond will appear here.\n\n"
            "Make sure:\n"
            "1. Your bot is in Raph's Discord server\n"
            "2. The Roll Channel ID is set to #disc-rolls-only\n"
            "3. Bot has Read Messages permission in that channel\n\n"
            "Rolls will show on the stream overlay automatically!")
        placeholder.setStyleSheet("color: #888; padding: 12px;")
        placeholder.setWordWrap(True)
        self.roll_log_layout.addWidget(placeholder)

        dg.addWidget(self.roll_log_area)

        # Test button
        test_btn = QPushButton("Send Test Roll")
        test_btn.clicked.connect(self._send_test_roll)
        dg.addWidget(test_btn)

        dice_group.setLayout(dg)
        content.addWidget(dice_group, stretch=2)

        # Right: Setup guide
        guide_group = QGroupBox("Bot Setup Guide")
        gg = QVBoxLayout()
        guide = QLabel(
            "<b>One-time setup:</b><br><br>"
            "1. Go to <u>discord.com/developers</u><br>"
            "2. Create a New Application<br>"
            "3. Go to Bot -> Create Bot<br>"
            "4. Copy the token -> paste here<br>"
            "5. Enable these Intents:<br>"
            "   * Message Content<br>"
            "   * Server Members<br>"
            "   * Voice States (for portraits)<br>"
            "6. Go to OAuth2 -> URL Generator<br>"
            "   * Scopes: bot<br>"
            "   * Permissions: Read Messages,<br>"
            "Read Message History,<br>"
            "Connect (voice)<br>"
            "7. Copy URL -> send to Raph<br>"
            "8. He adds the bot to his server<br><br>"
            "<b>Roll Channel ID:</b><br>"
            "In Discord, enable Developer Mode<br>"
            "(Settings -> Advanced), then<br>"
            "right-click #disc-rolls-only<br>"
            "-> Copy Channel ID")
        guide.setStyleSheet("color: #bbb; font-size: 11px; padding: 8px;")
        guide.setWordWrap(True)
        gg.addWidget(guide)
        gg.addStretch()

        if not DISCORD_AVAILABLE:
            warn = QLabel("*  discord.py not installed.\n"
                          "Run: pip install discord.py")
            warn.setStyleSheet("color: #cc6600; padding: 8px; font-weight: bold;")
            warn.setWordWrap(True)
            gg.addWidget(warn)

        guide_group.setLayout(gg)
        content.addWidget(guide_group, stretch=1)

        layout.addLayout(content)
        return tab

    # ===================================================================
    # Populate from state
    # ===================================================================

    def _populate_from_state(self):
        for char in self.state.characters.values():
            self.library.add_character(char)

        for btn_idx, char_id in self.state.deck_assignments.items():
            char = self.state.characters.get(char_id)
            if char:
                btn = self.deck_grid.get_button(btn_idx)
                if btn:
                    btn.set_character(char)

        for btn_idx in range(15):
            btn = self.deck_grid.get_button(btn_idx)
            if btn:
                hk = self.state.hotkey_assignments.get(
                    btn_idx, DEFAULT_HOTKEYS.get(btn_idx, ""))
                short = hk.replace("ctrl+", "C+").replace("shift+", "S+").replace("alt+", "A+")
                btn.set_hotkey_text(short)

        if self.state.active_character_id:
            self.library.set_active(self.state.active_character_id)
            for bi, ci in self.state.deck_assignments.items():
                if ci == self.state.active_character_id:
                    self.deck_grid.set_active_button(bi)
                    break

        if self.state.characters:
            first = next(iter(self.state.characters.values()))
            self._on_character_selected(first.id)

        # PC slots
        self._pc_slot_editors = []
        for slot in self.state.pc_slots:
            self._add_pc_slot_editor(slot)

        # Restore combat state if active
        if self.state.combat.is_active:
            self.combat_tab.restore_from_state()
            # Restore initiative overlay visibility
            if self.state.initiative_overlay_visible:
                self.initiative_overlay.show()

    # ===================================================================
    # Character Editor
    # ===================================================================

    def _on_character_selected(self, char_id):
        self.selected_char_id = char_id
        self.library.set_selected(char_id)
        char = self.state.characters.get(char_id)
        if not char:
            return
        self.name_input.setText(char.name)
        for fn, zone in self.drop_zones.items():
            if char.has_frame(fn):
                zone.set_image(char.pixmaps.get(fn))
            else:
                zone.clear_image()

    def _on_character_activated(self, char_id):
        self._activate_character(char_id)

    def _activate_character(self, char_id):
        char = self.state.characters.get(char_id)
        if not char or not char.is_valid:
            return
        self.state.active_character_id = char_id
        self.overlay.set_character(char)
        self.library.set_active(char_id)
        if not self.overlay.isVisible():
            self.overlay.show()
            self.overlay_btn.setChecked(True)
            self.overlay_btn.setText("Hide Overlay")
        for bi, ci in self.state.deck_assignments.items():
            if ci == char_id:
                self.deck_grid.set_active_button(bi)
                break
        self._update_deck_hardware()
        self._run_character_obs_actions(char)
        self.statusBar().showMessage(f"Now showing: {char.name}")
        self._save_state()

    def _run_character_obs_actions(self, char):
        if not self.obs.is_connected:
            return
        s = char.settings
        if s.obs_scene:
            self.obs.switch_scene(s.obs_scene)
        if s.obs_text_source:
            self.obs.set_text_source(s.obs_text_source, char.name)
        for src in s.obs_show_sources:
            self.obs.set_source_visible(src, True)
        for src in s.obs_hide_sources:
            self.obs.set_source_visible(src, False)

    def _deactivate_character(self):
        self.state.active_character_id = None
        self.overlay.set_character(None)
        self.overlay.hide()
        self.overlay_btn.setChecked(False)
        self.overlay_btn.setText("Show Overlay")
        self.library.clear_active()
        self.deck_grid.clear_active()
        self._update_deck_hardware()
        self.statusBar().showMessage("Character hidden")
        self._save_state()

    def _on_frame_dropped(self, frame_name, file_path):
        if not self.selected_char_id:
            self._new_character()
        char = self.state.characters.get(self.selected_char_id)
        if not char:
            return
        char.set_frame_from_file(frame_name, file_path)
        char.load_frames()
        self.library.refresh_character(char)
        if self.state.active_character_id == char.id:
            self.overlay.set_character(char)
        self._save_state()

    def _save_character(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Name Required", "Enter a character name.")
            return
        if self.selected_char_id and self.selected_char_id in self.state.characters:
            char = self.state.characters[self.selected_char_id]
            char.name = name
            self.library.refresh_character(char)
        else:
            char = Character(name=name)
            char.folder = get_characters_dir() / char.id
            char.folder.mkdir(parents=True, exist_ok=True)
            self.state.add_character(char)
            self.library.add_character(char)
            self.selected_char_id = char.id
            self.library.set_selected(char.id)
        self.statusBar().showMessage(f"Saved: {name}")
        self._save_state()

    def _new_character(self):
        char = Character(name="")
        char.folder = get_characters_dir() / char.id
        char.folder.mkdir(parents=True, exist_ok=True)
        self.state.add_character(char)
        self.library.add_character(char)
        self.selected_char_id = char.id
        self.library.set_selected(char.id)
        self.name_input.setText("")
        self.name_input.setFocus()
        for zone in self.drop_zones.values():
            zone.clear_image()

    def _on_character_deleted(self, char_id):
        char = self.state.characters.get(char_id)
        if not char:
            return
        if char.folder and char.folder.exists():
            shutil.rmtree(char.folder, ignore_errors=True)
        self.state.remove_character(char_id)
        self.library.remove_character(char_id)
        for bi, btn in self.deck_grid.buttons.items():
            if btn.character and btn.character.id == char_id:
                btn.set_character(None)
        if self.state.active_character_id == char_id:
            self._deactivate_character()
        if self.selected_char_id == char_id:
            self.selected_char_id = None
            self.name_input.clear()
            for zone in self.drop_zones.values():
                zone.clear_image()
        self._update_deck_hardware()
        self._save_state()

    # ===================================================================
    # Character Settings Dialog
    # ===================================================================

    def _open_character_settings(self, char_id):
        char = self.state.characters.get(char_id)
        if not char:
            return
        dialog = CharacterSettingsDialog(char, parent=self)
        dialog.settings_changed.connect(self._on_settings_live_update)
        if self.obs.is_connected:
            dialog.populate_obs_scenes(self.obs.scenes)
        dialog.exec()
        if self.state.active_character_id == char_id:
            self.overlay.apply_settings(char.settings)
        self._save_state()

    def _on_settings_live_update(self):
        active = self.state.get_active_character()
        if active:
            self.overlay.apply_settings(active.settings)

    # ===================================================================
    # Stream Deck
    # ===================================================================

    def _on_deck_button(self, button_index):
        char = self.state.get_character_for_button(button_index)
        if not char:
            return
        if self.state.active_character_id == char.id and self.overlay.isVisible():
            self._deactivate_character()
        else:
            self._activate_character(char.id)

    def _on_deck_character_assigned(self, bi, cid):
        char = self.state.characters.get(cid)
        if not char:
            return
        self.state.assign_character_to_button(bi, cid)
        btn = self.deck_grid.get_button(bi)
        if btn:
            btn.set_character(char)
        self._update_deck_hardware()
        self._save_state()

    def _on_deck_character_cleared(self, bi):
        self.state.unassign_button(bi)
        btn = self.deck_grid.get_button(bi)
        if btn:
            btn.set_character(None)
        self._update_deck_hardware()
        self._save_state()

    def _try_connect_deck(self):
        if not STREAMDECK_AVAILABLE:
            self.deck_status.setText("*  Library not installed")
            self.deck_status.setStyleSheet("color: #cc6600;")
            return
        success = self.deck_manager.connect()
        if success:
            rows, cols = self.deck_manager.key_layout
            if rows > 0 and cols > 0:
                self.deck_grid.set_layout_size(rows, cols)
                self._populate_from_state()
            self.deck_manager.set_brightness(self.state.deck_brightness)
            self._update_deck_hardware()

    def _on_deck_connection(self, connected, info):
        if connected:
            self.deck_status.setText(f"*  {info}")
            self.deck_status.setStyleSheet("color: #00cc66;")
            self.connect_btn.setText("Disconnect")
            try: self.connect_btn.clicked.disconnect()
            except Exception: pass
            self.connect_btn.clicked.connect(self._disconnect_deck)
        else:
            self.deck_status.setText(f"*  {info}")
            self.deck_status.setStyleSheet("color: #888;")
            self.connect_btn.setText("Connect")
            try: self.connect_btn.clicked.disconnect()
            except Exception: pass
            self.connect_btn.clicked.connect(self._try_connect_deck)

    def _disconnect_deck(self):
        self.deck_manager.disconnect()

    def _update_deck_hardware(self):
        if not self.deck_manager.is_connected:
            return
        for bi in range(self.deck_manager.key_count):
            char = self.state.get_character_for_button(bi)
            if char and char.has_frame("idle"):
                idle_path = str(char.folder / "idle.png")
                if self.state.active_character_id == char.id:
                    self.deck_manager.set_button_highlight(bi, idle_path, char.name)
                else:
                    self.deck_manager.set_button_image(bi, idle_path, char.name)
            else:
                self.deck_manager.clear_button(bi)

    def _on_mode_changed(self, index):
        self.state.deck_mode = "direct" if index == 0 else "hotkey"
        self._start_input_mode()
        self._save_state()

    def _start_input_mode(self):
        self.hotkey_listener.stop()
        if self.state.deck_mode == "hotkey" or not self.deck_manager.is_connected:
            self.hotkey_listener.clear()
            for bi in range(15):
                hk = self.state.hotkey_assignments.get(bi, DEFAULT_HOTKEYS.get(bi, ""))
                if hk:
                    self.hotkey_listener.register(hk, bi)
            self.hotkey_listener.start()

    # ===================================================================
    # OBS Control
    # ===================================================================

    def _obs_connect(self):
        host = self.obs_host_input.text().strip() or "localhost"
        try:
            port = int(self.obs_port_input.text().strip())
        except ValueError:
            port = 4455
        password = self.obs_pass_input.text()
        self.state.obs_host = host
        self.state.obs_port = port
        self.state.obs_password = password
        self._save_state()
        if self.obs.is_connected:
            self.obs.disconnect()
        else:
            self.obs.connect(host, port, password)

    def _on_obs_connection(self, connected, info):
        if connected:
            self.obs_status.setText(f"*  {info}")
            self.obs_status.setStyleSheet("color: #00cc66;")
            self.obs_connect_btn.setText("Disconnect")
            self.stream_btn.setEnabled(True)
            self.record_btn.setEnabled(True)
            # Populate PC slot audio dropdowns
            QTimer.singleShot(500, self._refresh_pc_audio_sources)
        else:
            self.obs_status.setText(f"*  {info}")
            self.obs_status.setStyleSheet("color: #888;")
            self.obs_connect_btn.setText("Connect")
            self.stream_btn.setEnabled(False)
            self.record_btn.setEnabled(False)
            self.current_scene_label.setText("--")
            self._clear_scene_buttons()

    def _on_obs_auto_changed(self, state):
        self.state.obs_auto_connect = bool(state)
        self._save_state()

    def _on_obs_scenes_updated(self, scenes):
        self._rebuild_scene_buttons(scenes)

    def _on_obs_scene_switched(self, scene_name):
        self.current_scene_label.setText(scene_name)
        for i in range(self.scene_buttons_layout.count()):
            w = self.scene_buttons_layout.itemAt(i).widget()
            if w and isinstance(w, QPushButton):
                is_cur = w.property("scene_name") == scene_name
                if is_cur:
                    w.setStyleSheet(
                        "QPushButton { background: #1a4a2a; border: 2px solid #00cc66; "
                        "color: #00ee77; font-weight: bold; padding: 8px; "
                        "text-align: left; border-radius: 4px; }")
                else:
                    w.setStyleSheet(
                        "QPushButton { background: #2a2a2a; border: 1px solid #555; "
                        "padding: 8px; text-align: left; border-radius: 4px; color: #ddd; }"
                        "QPushButton:hover { background: #3a3a3a; }")

    def _on_obs_error(self, msg):
        self.statusBar().showMessage(f"OBS: {msg}", 5000)

    def _on_obs_inputs_updated(self, inputs):
        """OBS inputs list refreshed -- update PC slot audio dropdowns."""
        for editor in self._pc_slot_editors:
            editor.populate_audio_sources(inputs)

    def _on_obs_audio_levels(self, levels: dict):
        """Received real-time audio levels from OBS -- dispatch to PC system."""
        # Update PC overlay manager
        self.pc_manager.update_audio_levels(levels)

        # Update level meters in PC slot editors
        for editor in self._pc_slot_editors:
            src = editor.slot.obs_audio_source
            if src:
                editor.update_level_display(levels.get(src, 0.0))

    def _obs_refresh_scenes(self):
        if self.obs.is_connected:
            self.obs.refresh_scenes()
        else:
            self.statusBar().showMessage("Connect to OBS first", 3000)

    def _clear_scene_buttons(self):
        while self.scene_buttons_layout.count():
            item = self.scene_buttons_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        lbl = QLabel("Connect to OBS to see scenes.")
        lbl.setStyleSheet("color: #888; padding: 20px;")
        self.scene_buttons_layout.addWidget(lbl)

    def _rebuild_scene_buttons(self, scenes):
        while self.scene_buttons_layout.count():
            item = self.scene_buttons_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not scenes:
            lbl = QLabel("No scenes found.")
            lbl.setStyleSheet("color: #888; padding: 20px;")
            self.scene_buttons_layout.addWidget(lbl)
            return
        for sn in scenes:
            btn = QPushButton(f"  {sn}")
            btn.setFixedHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("scene_name", sn)
            btn.setStyleSheet(
                "QPushButton { background: #2a2a2a; border: 1px solid #555; "
                "padding: 8px; text-align: left; border-radius: 4px; color: #ddd; }"
                "QPushButton:hover { background: #3a3a3a; }")
            btn.clicked.connect(lambda checked, s=sn: self.obs.switch_scene(s))
            self.scene_buttons_layout.addWidget(btn)
        self.scene_buttons_layout.addStretch()
        if self.obs.current_scene:
            self._on_obs_scene_switched(self.obs.current_scene)

    # ===================================================================
    # PC Portraits Tab
    # ===================================================================

    def _add_pc_slot(self):
        slot = PCSlot()
        slot.player_name = f"Player {len(self.state.pc_slots) + 1}"
        self.state.pc_slots.append(slot)
        self._add_pc_slot_editor(slot)
        self._refresh_pc_overlay()
        self._update_discord_user_dropdowns()
        self._update_voice_player_map()
        self._save_state()

    def _add_pc_slot_editor(self, slot):
        editor = PCSlotEditor(
            slot, self.state.characters,
            obs_inputs=self.obs.inputs if self.obs.is_connected else None)
        editor.changed.connect(self._on_pc_slot_changed)
        editor.remove_requested.connect(self._remove_pc_slot)
        self.pc_slot_layout.addWidget(editor)
        self._pc_slot_editors.append(editor)

    def _remove_pc_slot(self, slot_id):
        # Remove from state
        self.state.pc_slots = [s for s in self.state.pc_slots if s.id != slot_id]
        # Remove editor
        to_remove = [e for e in self._pc_slot_editors if e.slot.id == slot_id]
        for editor in to_remove:
            self._pc_slot_editors.remove(editor)
            self.pc_slot_layout.removeWidget(editor)
            editor.deleteLater()
        self._refresh_pc_overlay()
        self._update_voice_player_map()
        self._save_state()

    def _on_pc_slot_changed(self):
        self._refresh_pc_overlay()
        self._update_voice_player_map()
        self._save_state()

    def _update_voice_player_map(self):
        """Rebuild and send the player map to the Discord bot after slot changes."""
        if not self.discord.is_voice_active:
            return
        player_map = {}
        for i, slot in enumerate(self.state.pc_slots):
            if slot.discord_user_id > 0 and not getattr(slot, 'is_dm', False):
                multiplier = getattr(slot, 'voice_adaptive_multiplier', 2.5)
                player_map[slot.discord_user_id] = (i, multiplier)
        self.discord.update_player_map(player_map)

    def _on_pc_mode_changed(self, index):
        self.state.pc_overlay_mode = "strip" if index == 0 else "individual"
        if self.pc_manager.is_visible:
            self.pc_manager.refresh_mode(self.state.pc_overlay_mode)
        self._save_state()

    def _on_pc_settings_changed(self):
        self.state.pc_portrait_size = self.pc_size_slider.value()
        self.state.pc_strip_spacing = self.pc_spacing_slider.value()
        self.state.pc_dim_opacity = self.pc_dim_slider.value() / 100.0
        self.state.pc_shade_amount = self.pc_shade_slider.value() / 100.0
        # Update labels
        self.pc_size_label.setText(f"{self.pc_size_slider.value()}px")
        self.pc_spacing_label.setText(f"{self.pc_spacing_slider.value()}px")
        self.pc_dim_label.setText(f"{self.pc_dim_slider.value()}%")
        self.pc_shade_label.setText(f"{self.pc_shade_slider.value()}%")
        self.pc_manager.apply_settings()
        self._save_state()

    def _toggle_pc_overlay(self, checked):
        if checked:
            self._refresh_pc_overlay()
            self.pc_manager.show(self.state.pc_overlay_mode)
            self.pc_show_btn.setText("Hide Portraits")
        else:
            self.pc_manager.hide()
            self.pc_show_btn.setText("Show Portraits")

    def _refresh_pc_overlay(self):
        self.pc_manager.rebuild(self.state.characters)
        if self.pc_manager.is_visible:
            self.pc_manager.show(self.state.pc_overlay_mode)

    def _refresh_pc_audio_sources(self):
        """Called after OBS connects to populate audio dropdowns."""
        if self.obs.is_connected:
            self.obs.refresh_inputs()
    
    # ------------------------------------------------------------------
    # Voice Receive Handlers
    # ------------------------------------------------------------------

    def _refresh_voice_channels(self):
        """Request voice channel list from Discord."""
        if not self.discord.is_connected:
            self.statusBar().showMessage("Connect to Discord first", 3000)
            return
        self.discord.request_voice_channels()

    def _on_voice_channels_updated(self, channels: list):
        """Voice channel list received from Discord."""
        self.voice_channel_combo.blockSignals(True)
        self.voice_channel_combo.clear()
        self._voice_channel_data = channels  # store for member lookups

        for ch in channels:
            label = f"{ch['name']} ({ch['guild']}) -- {ch['member_count']} members"
            self.voice_channel_combo.addItem(label, ch["id"])

            # Auto-select saved channel
            if ch["id"] == self.state.discord_voice_channel_id:
                self.voice_channel_combo.setCurrentIndex(
                    self.voice_channel_combo.count() - 1)

        self.voice_channel_combo.blockSignals(False)

        # Update Discord user dropdowns in slot editors
        self._update_discord_user_dropdowns()

    def _update_discord_user_dropdowns(self):
        """Populate Discord user dropdowns from the selected voice channel."""
        idx = self.voice_channel_combo.currentIndex()
        if idx < 0 or not hasattr(self, '_voice_channel_data'):
            return

        channel_id = self.voice_channel_combo.currentData()
        members = []
        for ch in self._voice_channel_data:
            if ch["id"] == channel_id:
                members = ch.get("members", [])
                break

        for editor in self._pc_slot_editors:
            if hasattr(editor, 'populate_discord_users'):
                editor.populate_discord_users(members)

    def _toggle_voice_receive(self, checked):
        """Join or leave Discord voice channel."""
        if checked:
            # Join voice
            idx = self.voice_channel_combo.currentIndex()
            if idx < 0:
                self.statusBar().showMessage(
                    "Select a voice channel first", 3000)
                self.voice_join_btn.setChecked(False)
                return

            channel_id = self.voice_channel_combo.currentData()
            if not channel_id:
                self.voice_join_btn.setChecked(False)
                return

            # Build player map from slot editors
            player_map = {}
            voice_slots = []
            for i, slot in enumerate(self.state.pc_slots):
                if slot.discord_user_id > 0 and not slot.is_dm:
                    multiplier = getattr(slot, 'voice_adaptive_multiplier', 2.5)
                    player_map[slot.discord_user_id] = (i, multiplier)
                    voice_slots.append(i)

            # -- DIAGNOSTIC: log what we're sending --
            print(f"[VOICE DIAG] Building player map from PC slots:")
            for uid, slot_data in player_map.items():
                idx = slot_data[0] if isinstance(slot_data, tuple) else slot_data
                slot = self.state.pc_slots[idx]
                print(f"  slot {idx}: discord_user_id={uid} "
                      f"(type={type(uid).__name__}) "
                      f"player_name={slot.player_name}")

            if not player_map:
                self.statusBar().showMessage(
                    "Assign Discord users to PC slots first", 3000)
                self.voice_join_btn.setChecked(False)
                return

            # Save channel selection
            self.state.discord_voice_channel_id = channel_id
            self._save_state()

            # Join and start receiving
            self.discord.join_voice(channel_id, player_map)
            self.voice_join_btn.setText("*  Leave Voice")
            self.voice_status_label.setText("Joining...")
            self.voice_status_label.setStyleSheet("color: #cc8800;")
        else:
            # Leave voice
            self.discord.leave_voice()
            self.voice_join_btn.setText("Join Voice")

    def _on_voice_connected(self, info: dict):
        """Bot joined voice channel and is receiving audio."""
        self.pc_manager.set_voice_active(True)
        self.voice_join_btn.setChecked(True)
        self.voice_join_btn.setText("*  Leave Voice")

        player_count = info.get("player_count", 0)
        channel_name = info.get("channel_name", "?")
        self.voice_status_label.setText(
            f"Listening in #{channel_name} ({player_count} players mapped)")
        self.voice_status_label.setStyleSheet("color: #00cc66;")

        self.statusBar().showMessage(
            f"Voice receive active -- {channel_name}", 3000)

    def _on_voice_disconnected(self):
        """Bot left the voice channel."""
        self.pc_manager.set_voice_active(False)
        self.voice_join_btn.setChecked(False)
        self.voice_join_btn.setText("Join Voice")
        self.voice_status_label.setText("")

        self.statusBar().showMessage("Voice receive stopped", 3000)

    def _on_player_audio(self, slot_index: int, rms: float, vowel: str,
                         threshold: float):
        """Per-player audio received from Discord voice.

        Routes to the PC overlay manager, which uses RMS to set
        speaking state (and in the future, vowel for mouth shapes).
        """
        self.pc_manager.update_player_audio(slot_index, rms, vowel, threshold)

    # ===================================================================
    # Discord Bot
    # ===================================================================

    def _discord_connect(self):
        token = self.discord_token_input.text().strip()
        if not token:
            self.statusBar().showMessage("Enter a Discord bot token first", 3000)
            return

        channel_text = self.discord_channel_input.text().strip()
        try:
            channel_id = int(channel_text) if channel_text else 0
        except ValueError:
            channel_id = 0

        self.state.discord_token = token
        self.state.discord_roll_channel_id = channel_id
        self._save_state()

        if self.discord.is_connected:
            self.discord.disconnect()
        else:
            self.discord.connect(token, roll_channel_id=channel_id)

    def _on_discord_connection(self, connected, info):
        if connected:
            self.discord_status.setText(f"*  {info}")
            self.discord_status.setStyleSheet("color: #00cc66;")
            self.discord_connect_btn.setText("Disconnect")
            
            # Auto-refresh voice channels when bot connects
            QTimer.singleShot(1000, self._refresh_voice_channels)
        else:
            self.discord_status.setText(f"*  {info}")
            self.discord_status.setStyleSheet("color: #888;")
            self.discord_connect_btn.setText("Connect")

    def _on_discord_auto_changed(self, state):
        self.state.discord_auto_connect = bool(state)
        self._save_state()

    def _on_discord_error(self, msg):
        self.statusBar().showMessage(f"Discord: {msg}", 5000)

    def _on_dice_roll(self, event: DiceRollEvent):
        """A dice roll was detected from Discord."""
        # Send to overlay
        self.dice_overlay.add_roll(event)

        # Add to log in the Discord tab
        self._add_roll_to_log(event)

        self.statusBar().showMessage(
            f"{event.character_name}: {event.check_type} = {event.total}",
            4000)

    def _on_voice_state(self, event: VoiceStateEvent):
        """Voice state changed in Discord -- for future PC portrait integration."""
        if event.joined:
            self.statusBar().showMessage(
                f"{event.display_name} joined voice", 3000)
        elif event.left:
            self.statusBar().showMessage(
                f"{event.display_name} left voice", 3000)

    def _add_roll_to_log(self, event: DiceRollEvent):
        """Add a roll entry to the log panel."""
        # Remove placeholder if present
        for i in range(self.roll_log_layout.count()):
            w = self.roll_log_layout.itemAt(i).widget()
            if w and isinstance(w, QLabel) and "Dice rolls from Avrae" in w.text():
                w.deleteLater()
                break

        # Color for crit/fumble
        if event.is_critical:
            color = "#ffd700"
            prefix = "^ NAT 20! "
        elif event.is_fumble:
            color = "#ff4444"
            prefix = "NAT 1! "
        else:
            color = "#aaa"
            prefix = ""

        text = (f"{prefix}<b>{event.character_name}</b> -- "
                f"{event.check_type}: "
                f"<span style='color:{color};font-weight:bold;'>{event.total}</span>")

        lbl = QLabel(text)
        lbl.setStyleSheet("color: #ccc; padding: 2px 4px; font-size: 11px;")
        lbl.setTextFormat(Qt.TextFormat.RichText)
        self.roll_log_layout.insertWidget(0, lbl)

        # Keep log manageable
        while self.roll_log_layout.count() > 30:
            item = self.roll_log_layout.takeAt(self.roll_log_layout.count() - 1)
            if item and item.widget():
                item.widget().deleteLater()

    def _toggle_dice_overlay(self, checked):
        if checked:
            # Build character color map from PC slots
            for slot in self.state.pc_slots:
                if slot.player_name:
                    self.dice_overlay.character_colors[slot.player_name] = slot.glow_color
                if slot.character_id and slot.character_id in self.state.characters:
                    char = self.state.characters[slot.character_id]
                    self.dice_overlay.character_colors[char.name] = slot.glow_color
            self.dice_overlay.show()
            self.dice_show_btn.setText("Hide Dice Overlay")
        else:
            self.dice_overlay.hide()
            self.dice_show_btn.setText("Show Dice Overlay")

    def _on_dice_time_changed(self, value):
        self.state.dice_display_time = float(value)
        self.dice_time_label.setText(f"{value}s")
        self.dice_overlay.set_display_time(value)
        self._save_state()

    def _on_dice_side_changed(self, value):
        self.state.dice_side = value
        self.dice_overlay.set_side(value)
        self._save_state()

    def _on_dice_stack_changed(self, value):
        self.state.dice_stack = value
        self.dice_overlay.set_stack(value)
        self._save_state()

    def _on_dice_overlay_moved(self, x, y):
        self.state.dice_overlay_x = x
        self.state.dice_overlay_y = y
        self._save_state()

    # ------------------------------------------------------------------
    # Initiative Overlay
    # ------------------------------------------------------------------

    def _toggle_initiative_overlay(self, visible):
        if visible:
            self.initiative_overlay.show()
        else:
            self.initiative_overlay.hide()

    def _on_combat_changed(self):
        """Combatants added or removed -- refresh overlay layout."""
        if self.initiative_overlay.isVisible():
            self.initiative_overlay.refresh()

    def _on_initiative_overlay_moved(self, x, y):
        self.state.initiative_overlay_x = x
        self.state.initiative_overlay_y = y
        self._save_state()

    def _send_test_roll(self):
        """Send a fake dice roll for testing the overlay."""
        import random
        names = ["Seraphyne", 'Theodore "Duke"Dumberry',
                 "Cornelia Maizington", "Lachlan Macrae"]
        checks = ["Deception check", "Perception check", "Stealth check",
                   "Athletics check", "Persuasion check", "Insight check",
                   "Attack: Longsword", "Dexterity saving throw"]
        nat = random.randint(1, 20)
        mod = random.randint(-1, 8)
        total = nat + mod

        event = DiceRollEvent(
            character_name=random.choice(names),
            check_type=random.choice(checks),
            roll_formula=f"1d20 ({nat}) + {mod} = {total}",
            natural_roll=nat,
            total=total,
            is_critical=(nat == 20),
            is_fumble=(nat == 1),
            campaign_name="Okora on the Edge"
        )
        self._on_dice_roll(event)

    # ===================================================================
    # Audio / Mic (NPC puppet)
    # ===================================================================

    def _on_audio_level(self, level):
        threshold = self.state.mic_threshold
        is_talking = level > threshold
        self.overlay.set_talking(is_talking)
        bar_len = int(min(level * 500, 25))
        bar = "#" * bar_len + "-" * (25 - bar_len)
        color = "#00cc66" if is_talking else "#888"
        self.level_bar.setText(f"[{bar}]")
        self.level_bar.setStyleSheet(
            f"color: {color}; font-family: monospace; font-size: 10px;")

        # Also drive any DM-flagged PC portrait slots via local mic
        for i, slot in enumerate(self.state.pc_slots):
            if slot.is_dm:
                self.pc_manager.update_player_audio(i, level, "")

    def _on_dm_vowel(self, vowel: str):
        """Forward detected vowel to the NPC puppet overlay."""
        self.overlay.set_vowel(vowel)

    def _on_threshold_change(self, value):
        self.state.mic_threshold = value / 1000.0
        self._save_state()

    def _on_mic_changed(self, index):
        device = self.mic_combo.currentData()
        self.state.mic_device = device
        self.audio.restart(device=device)
        self._save_state()

    # ===================================================================
    # Overlay
    # ===================================================================

    def _toggle_overlay(self, checked):
        if checked:
            self.overlay.show()
            self.overlay_btn.setText("Hide Overlay")
        else:
            self.overlay.hide()
            self.overlay_btn.setText("Show Overlay")

    def _on_overlay_moved(self, x, y):
        self.state.overlay_x = x
        self.state.overlay_y = y
        self._save_state()

    # ===================================================================
    # System Tray
    # ===================================================================

    def _setup_tray(self):
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(0, 0, 0, 0))
        p = QPainter(pixmap)
        p.setBrush(QColor(130, 80, 200))
        p.setPen(QColor(200, 160, 255))
        p.drawEllipse(4, 4, 56, 56)
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        p.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "P")
        p.end()
        self.tray = QSystemTrayIcon(QIcon(pixmap), self)
        self.tray.setToolTip("DM Puppeteer")
        menu = QMenu()
        show_action = menu.addAction("Show Control Panel")
        show_action.triggered.connect(self.show)
        show_action.triggered.connect(self.raise_)
        menu.addSeparator()
        for char in self.state.characters.values():
            act = menu.addAction(f"Switch to {char.name}")
            act.triggered.connect(lambda c, cid=char.id: self._activate_character(cid))
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(QApplication.quit)
        self.tray.setContextMenu(menu)
        self.tray.show()

    # ===================================================================
    # Persistence
    # ===================================================================

    def _save_state(self):
        try:
            self.state.save()
        except Exception as e:
            print(f"Save error: {e}")

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "DM Puppeteer", "Still running in tray. Right-click to quit.",
            QSystemTrayIcon.MessageIcon.Information, 2000)

    def shutdown(self):
        self._save_state()
        self.audio.stop()
        self.hotkey_listener.stop()
        self.deck_manager.disconnect()
        self.obs.disconnect()
        self.discord.disconnect()
        self.pc_manager.hide()
        self.dice_overlay.close()
        self.initiative_overlay.close()
        self.overlay.close()
        self.tray.hide()
        # Final backstop: if any daemon thread is stuck, don't let
        # the process hang forever. Schedule a hard exit.
        import threading
        def _force_exit():
            import os, signal
            print("Force exit: background thread did not stop cleanly")
            os._exit(0)
        watchdog = threading.Timer(5.0, _force_exit)
        watchdog.daemon = True
        watchdog.start()


# ---------------------------------------------------------------------------
# Dark theme (with checkbox fix)
# ---------------------------------------------------------------------------

DARK_THEME = """QMainWindow, QWidget {
        background-color: #1e1e1e; color: #ddd;
        font-family: "Segoe UI", sans-serif; font-size: 12px;
    }
    QGroupBox {
        border: 1px solid #444; border-radius: 6px;
        margin-top: 8px; padding-top: 12px;
        font-weight: bold; color: #ccc;
    }
    QGroupBox::title {
        subcontrol-origin: margin; left: 12px; padding: 0 6px;
    }
    QPushButton {
        background: #333; border: 1px solid #555; border-radius: 4px;
        padding: 6px 12px; color: #ddd;
    }
    QPushButton:hover { background: #444; border-color: #777; }
    QPushButton:pressed { background: #555; }
    QPushButton:checked {
        background: #2a4a3a; border-color: #00cc66; color: #00ee77;
    }
    QLineEdit {
        background: #2a2a2a; border: 1px solid #555; border-radius: 4px;
        padding: 4px 8px; color: #ddd;
    }
    QLineEdit:focus { border-color: #6688cc; }
    QComboBox {
        background: #2a2a2a; border: 1px solid #555; border-radius: 4px;
        padding: 4px 8px; color: #ddd;
    }
    QComboBox::drop-down { border: none; }
    QComboBox QAbstractItemView {
        background: #2a2a2a; color: #ddd; selection-background-color: #444;
    }
    QSlider::groove:horizontal {
        height: 6px; background: #333; border-radius: 3px;
    }
    QSlider::handle:horizontal {
        width: 16px; height: 16px; margin: -5px 0;
        background: #888; border-radius: 8px;
    }
    QSlider::handle:horizontal:hover { background: #aaa; }
    QCheckBox::indicator {
        width: 16px; height: 16px;
        border: 2px solid #888; border-radius: 3px;
        background: #2a2a2a;
    }
    QCheckBox::indicator:hover { border-color: #aaa; }
    QCheckBox::indicator:checked {
        background: #00cc66; border-color: #00cc66;
        image: none;
    }
    QSpinBox, QDoubleSpinBox {
        background: #2a2a2a; border: 1px solid #555;
        border-radius: 3px; padding: 2px 6px; color: #ddd;
    }
    QStatusBar { background: #181818; color: #888; font-size: 11px; }
    QScrollArea { border: none; }
    QLabel { color: #ccc; }
"""
