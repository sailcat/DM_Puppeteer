"""
Custom UI widgets for drag-and-drop character management
"""

from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QSizePolicy, QPushButton, QScrollArea, QLineEdit,
    QMessageBox, QDialog, QGroupBox, QSlider, QCheckBox, QSpinBox,
    QDoubleSpinBox, QMenu, QComboBox, QColorDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPoint
from PyQt6.QtGui import (
    QPixmap, QPainter, QColor, QFont, QDrag, QPen,
    QDragEnterEvent, QDropEvent, QPaintEvent, QMouseEvent
)

from .models import Character, CharacterSettings, PCSlot


# ---------------------------------------------------------------------------
# Character Settings Dialog
# ---------------------------------------------------------------------------

class CharacterSettingsDialog(QDialog):
    """Right-click settings dialog for per-character display options"""

    settings_changed = pyqtSignal()

    def __init__(self, character: Character, parent=None):
        super().__init__(parent)
        self.character = character
        self.settings = character.settings

        self.setWindowTitle(f"Settings -- {character.name or 'Character'}")
        self.setFixedWidth(380)
        self.setStyleSheet("""
            QDialog { background: #1e1e1e; color: #ddd; }
            QGroupBox { border: 1px solid #444; border-radius: 6px;
                        margin-top: 8px; padding-top: 14px;
                        font-weight: bold; color: #ccc; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
            QSlider::groove:horizontal { height: 6px; background: #333; border-radius: 3px; }
            QSlider::handle:horizontal { width: 14px; height: 14px; margin: -4px 0;
                                          background: #888; border-radius: 7px; }
            QLabel { color: #ccc; }
            QCheckBox { color: #ccc; }
            QSpinBox, QDoubleSpinBox { background: #2a2a2a; border: 1px solid #555;
                                        border-radius: 3px; padding: 2px 6px; color: #ddd; }
            QPushButton { background: #333; border: 1px solid #555; border-radius: 4px;
                          padding: 6px 16px; color: #ddd; }
            QPushButton:hover { background: #444; }
        """)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        s = self.settings

        # --- Size (unified slider) ---
        size_group = QGroupBox("Size")
        sg = QVBoxLayout()

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Scale:"))
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(80, 1000)
        self.size_slider.setValue(s.width)
        self.size_slider.valueChanged.connect(self._on_size_change)
        size_row.addWidget(self.size_slider)

        self.size_label = QLabel(f"{s.width} Ãƒâ€” {s.height} px")
        self.size_label.setFixedWidth(100)
        size_row.addWidget(self.size_label)
        sg.addLayout(size_row)

        size_group.setLayout(sg)
        layout.addWidget(size_group)

        # --- Transparency ---
        trans_group = QGroupBox("Transparency")
        tg = QHBoxLayout()
        tg.addWidget(QLabel("Opacity:"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(int(s.opacity * 100))
        self.opacity_slider.valueChanged.connect(self._on_change)
        tg.addWidget(self.opacity_slider)
        self.opacity_label = QLabel(f"{int(s.opacity * 100)}%")
        self.opacity_label.setFixedWidth(40)
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"{v}%"))
        tg.addWidget(self.opacity_label)
        trans_group.setLayout(tg)
        layout.addWidget(trans_group)

        # --- Blink ---
        blink_group = QGroupBox("Blink Timing")
        bg = QGridLayout()
        bg.addWidget(QLabel("Min interval:"), 0, 0)
        self.blink_min_spin = QDoubleSpinBox()
        self.blink_min_spin.setRange(0.5, 20.0)
        self.blink_min_spin.setValue(s.blink_interval_min)
        self.blink_min_spin.setSuffix(" s")
        self.blink_min_spin.setSingleStep(0.5)
        self.blink_min_spin.valueChanged.connect(self._on_change)
        bg.addWidget(self.blink_min_spin, 0, 1)

        bg.addWidget(QLabel("Max interval:"), 1, 0)
        self.blink_max_spin = QDoubleSpinBox()
        self.blink_max_spin.setRange(0.5, 20.0)
        self.blink_max_spin.setValue(s.blink_interval_max)
        self.blink_max_spin.setSuffix(" s")
        self.blink_max_spin.setSingleStep(0.5)
        self.blink_max_spin.valueChanged.connect(self._on_change)
        bg.addWidget(self.blink_max_spin, 1, 1)

        bg.addWidget(QLabel("Blink duration:"), 2, 0)
        self.blink_dur_spin = QDoubleSpinBox()
        self.blink_dur_spin.setRange(0.05, 1.0)
        self.blink_dur_spin.setValue(s.blink_duration)
        self.blink_dur_spin.setSuffix(" s")
        self.blink_dur_spin.setSingleStep(0.05)
        self.blink_dur_spin.setDecimals(2)
        self.blink_dur_spin.valueChanged.connect(self._on_change)
        bg.addWidget(self.blink_dur_spin, 2, 1)

        blink_group.setLayout(bg)
        layout.addWidget(blink_group)

        # --- Effects ---
        fx_group = QGroupBox("Animation Effects")
        fg = QVBoxLayout()

        # Bounce
        bounce_row = QHBoxLayout()
        self.bounce_check = QCheckBox("Bounce / Bob")
        self.bounce_check.setChecked(s.bounce_enabled)
        self.bounce_check.stateChanged.connect(self._on_change)
        bounce_row.addWidget(self.bounce_check)
        self.bounce_talk_check = QCheckBox("Only while talking")
        self.bounce_talk_check.setChecked(s.bounce_on_talk_only)
        self.bounce_talk_check.stateChanged.connect(self._on_change)
        bounce_row.addWidget(self.bounce_talk_check)
        bounce_row.addStretch()
        fg.addLayout(bounce_row)

        bounce_params = QHBoxLayout()
        bounce_params.addWidget(QLabel("  Amount:"))
        self.bounce_amount_spin = QDoubleSpinBox()
        self.bounce_amount_spin.setRange(1.0, 50.0)
        self.bounce_amount_spin.setValue(s.bounce_amount)
        self.bounce_amount_spin.setSuffix(" px")
        self.bounce_amount_spin.valueChanged.connect(self._on_change)
        bounce_params.addWidget(self.bounce_amount_spin)
        bounce_params.addWidget(QLabel("Speed:"))
        self.bounce_speed_spin = QDoubleSpinBox()
        self.bounce_speed_spin.setRange(0.5, 10.0)
        self.bounce_speed_spin.setValue(s.bounce_speed)
        self.bounce_speed_spin.setSuffix(" Hz")
        self.bounce_speed_spin.setSingleStep(0.5)
        self.bounce_speed_spin.valueChanged.connect(self._on_change)
        bounce_params.addWidget(self.bounce_speed_spin)
        bounce_params.addStretch()
        fg.addLayout(bounce_params)

        fg.addSpacing(6)

        # Pop-in
        popin_row = QHBoxLayout()
        self.popin_check = QCheckBox("Pop-in on mic activate")
        self.popin_check.setChecked(s.popin_enabled)
        self.popin_check.stateChanged.connect(self._on_change)
        popin_row.addWidget(self.popin_check)
        popin_row.addStretch()
        fg.addLayout(popin_row)

        popin_params = QHBoxLayout()
        popin_params.addWidget(QLabel("  Jump:"))
        self.popin_amount_spin = QDoubleSpinBox()
        self.popin_amount_spin.setRange(1.0, 60.0)
        self.popin_amount_spin.setValue(s.popin_amount)
        self.popin_amount_spin.setSuffix(" px")
        self.popin_amount_spin.valueChanged.connect(self._on_change)
        popin_params.addWidget(self.popin_amount_spin)
        popin_params.addWidget(QLabel("Duration:"))
        self.popin_dur_spin = QDoubleSpinBox()
        self.popin_dur_spin.setRange(0.05, 0.5)
        self.popin_dur_spin.setValue(s.popin_duration)
        self.popin_dur_spin.setSuffix(" s")
        self.popin_dur_spin.setSingleStep(0.02)
        self.popin_dur_spin.setDecimals(2)
        self.popin_dur_spin.valueChanged.connect(self._on_change)
        popin_params.addWidget(self.popin_dur_spin)
        popin_params.addStretch()
        fg.addLayout(popin_params)

        fx_group.setLayout(fg)
        layout.addWidget(fx_group)

        # --- OBS Linked Actions ---
        obs_group = QGroupBox("OBS Linked Actions")
        og = QVBoxLayout()

        scene_row = QHBoxLayout()
        scene_row.addWidget(QLabel("Switch to scene:"))
        self.obs_scene_combo = QComboBox()
        self.obs_scene_combo.addItem("(don't switch)", "")
        self.obs_scene_combo.setMinimumWidth(180)
        self.obs_scene_combo.currentIndexChanged.connect(self._on_change)
        scene_row.addWidget(self.obs_scene_combo)
        scene_row.addStretch()
        og.addLayout(scene_row)

        text_row = QHBoxLayout()
        text_row.addWidget(QLabel("Update text source:"))
        self.obs_text_input = QLineEdit()
        self.obs_text_input.setPlaceholderText("Text source name in OBS (optional)")
        self.obs_text_input.setText(s.obs_text_source)
        self.obs_text_input.setMaximumWidth(200)
        self.obs_text_input.textChanged.connect(self._on_change)
        text_row.addWidget(self.obs_text_input)
        text_row.addStretch()
        og.addLayout(text_row)

        hint = QLabel("Scene auto-switches when this character activates.\n"
                       "Text source updates with the character's name.")
        hint.setStyleSheet("color: #888; font-size: 10px;")
        hint.setWordWrap(True)
        og.addWidget(hint)

        obs_group.setLayout(og)
        layout.addWidget(obs_group)

        # Close button
        close_btn = QPushButton("Done")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _on_size_change(self, value):
        """Unified size slider -- sets both width and height to the same value."""
        self.settings.width = value
        self.settings.height = value
        self.size_label.setText(f"{value} Ãƒâ€” {value} px")
        self.settings_changed.emit()

    def _on_change(self, *_):
        """Read all non-size widgets back into settings and emit signal."""
        s = self.settings
        s.opacity = self.opacity_slider.value() / 100.0
        s.blink_interval_min = self.blink_min_spin.value()
        s.blink_interval_max = self.blink_max_spin.value()
        s.blink_duration = self.blink_dur_spin.value()
        s.bounce_enabled = self.bounce_check.isChecked()
        s.bounce_amount = self.bounce_amount_spin.value()
        s.bounce_speed = self.bounce_speed_spin.value()
        s.bounce_on_talk_only = self.bounce_talk_check.isChecked()
        s.popin_enabled = self.popin_check.isChecked()
        s.popin_amount = self.popin_amount_spin.value()
        s.popin_duration = self.popin_dur_spin.value()
        # OBS
        s.obs_scene = self.obs_scene_combo.currentData() or ""
        s.obs_text_source = self.obs_text_input.text().strip()
        self.settings_changed.emit()

    def populate_obs_scenes(self, scene_names: list[str]):
        """Fill the OBS scene combo with available scenes from OBS."""
        current = self.settings.obs_scene
        self.obs_scene_combo.blockSignals(True)
        self.obs_scene_combo.clear()
        self.obs_scene_combo.addItem("(don't switch)", "")
        for name in scene_names:
            self.obs_scene_combo.addItem(name, name)
        # Re-select the saved scene if it exists
        idx = self.obs_scene_combo.findData(current)
        if idx >= 0:
            self.obs_scene_combo.setCurrentIndex(idx)
        self.obs_scene_combo.blockSignals(False)


# ---------------------------------------------------------------------------
# Image Drop Zone
# ---------------------------------------------------------------------------

class ImageDropZone(QFrame):
    file_dropped = pyqtSignal(str, str)

    def __init__(self, frame_name, label="", parent=None):
        super().__init__(parent)
        self.frame_name = frame_name
        self.setAcceptDrops(True)
        self.setMinimumSize(120, 140)
        self.setMaximumSize(160, 180)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._pixmap = None
        self._label_text = label or frame_name.replace('_', ' ').title()
        self._hover = False
        self.setStyleSheet("""
            ImageDropZone {
                border: 2px dashed #666; border-radius: 8px; background: #2a2a2a;
            }
        """)

    def set_image(self, pixmap):
        self._pixmap = pixmap
        self.update()

    def set_image_from_file(self, path):
        pm = QPixmap(path)
        if not pm.isNull():
            self._pixmap = pm
            self.update()

    def clear_image(self):
        self._pixmap = None
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        if self._hover:
            painter.fillRect(rect, QColor(60, 60, 80))
        if self._pixmap:
            scaled = self._pixmap.scaled(
                rect.width() - 10, rect.height() - 30,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            x = rect.x() + (rect.width() - scaled.width()) // 2
            painter.drawPixmap(x, rect.y() + 5, scaled)
        else:
            painter.setPen(QColor(120, 120, 120))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(rect.adjusted(0, 0, 0, -25),
                             Qt.AlignmentFlag.AlignCenter, "Drop PNG\nhere")
        painter.setPen(QColor(200, 200, 200))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        label_rect = rect.adjusted(0, rect.height() - 22, 0, 0)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, self._label_text)
        painter.end()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].toLocalFile().lower().endswith('.png'):
                event.acceptProposedAction()
                self._hover = True
                self.update()
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._hover = False
        self.update()

    def dropEvent(self, event):
        self._hover = False
        urls = event.mimeData().urls()
        if urls:
            fp = urls[0].toLocalFile()
            if fp.lower().endswith('.png'):
                self.file_dropped.emit(self.frame_name, fp)
                self.set_image_from_file(fp)
                event.acceptProposedAction()
                self.update()
                return
        event.ignore()
        self.update()


# ---------------------------------------------------------------------------
# Character Card
# ---------------------------------------------------------------------------

class CharacterCard(QFrame):
    clicked = pyqtSignal(str)
    double_clicked = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    settings_requested = pyqtSignal(str)

    def __init__(self, character, parent=None):
        super().__init__(parent)
        self.character = character
        self._selected = False
        self._active = False
        self.setFixedSize(140, 100)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

    def _update_style(self):
        if self._active:
            border = "border: 2px solid #00cc66;"
            bg = "background: #1a3a2a;"
        elif self._selected:
            border = "border: 2px solid #6688cc;"
            bg = "background: #2a2a3a;"
        else:
            border = "border: 1px solid #444;"
            bg = "background: #2a2a2a;"
        self.setStyleSheet(f"CharacterCard {{ {border} {bg} border-radius: 6px; }}")

    def set_selected(self, sel):
        self._selected = sel
        self._update_style()

    def set_active(self, act):
        self._active = act
        self._update_style()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        idle = self.character.get_idle_pixmap()
        if idle:
            thumb = idle.scaled(60, 60, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            x = (self.width() - thumb.width()) // 2
            painter.drawPixmap(x, 8, thumb)
        else:
            painter.setPen(QColor(100, 100, 100))
            painter.drawText(self.rect().adjusted(0, 5, 0, -25),
                             Qt.AlignmentFlag.AlignCenter, "?")
        painter.setPen(QColor(220, 220, 220))
        painter.setFont(QFont("Segoe UI", 9))
        name_rect = self.rect().adjusted(5, self.height() - 25, -5, 0)
        fm = painter.fontMetrics()
        elided = fm.elidedText(self.character.name, Qt.TextElideMode.ElideRight, name_rect.width())
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignCenter, elided)
        if self._active:
            painter.setPen(QColor(0, 200, 100))
            painter.setFont(QFont("Segoe UI", 7))
            painter.drawText(self.rect().adjusted(0, 2, -5, 0),
                             Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight, "*Â LIVE")
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.character.id)
            self._drag_start = event.pos()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.character.id)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not hasattr(self, '_drag_start'):
            return
        if (event.pos() - self._drag_start).manhattanLength() < 20:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(f"character:{self.character.id}")
        drag.setMimeData(mime)
        idle = self.character.get_idle_pixmap()
        if idle:
            thumb = idle.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            drag.setPixmap(thumb)
            drag.setHotSpot(QPoint(thumb.width() // 2, thumb.height() // 2))
        drag.exec(Qt.DropAction.CopyAction)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        settings_action = menu.addAction("âš™  Settings...")
        menu.addSeparator()
        delete_action = menu.addAction("Ã°Å¸â€”â€˜  Delete Character")

        action = menu.exec(event.globalPos())
        if action == settings_action:
            self.settings_requested.emit(self.character.id)
        elif action == delete_action:
            reply = QMessageBox.question(
                self, "Delete Character",
                f"Delete '{self.character.name}'?\nThis removes all frame files.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.delete_requested.emit(self.character.id)


# ---------------------------------------------------------------------------
# Deck Button Widget
# ---------------------------------------------------------------------------

class DeckButtonWidget(QFrame):
    character_assigned = pyqtSignal(int, str)
    character_cleared = pyqtSignal(int)
    button_clicked = pyqtSignal(int)

    def __init__(self, button_index, parent=None):
        super().__init__(parent)
        self.button_index = button_index
        self.character = None
        self.hotkey_text = ""
        self._is_active = False
        self._hover = False
        self.setAcceptDrops(True)
        self.setFixedSize(80, 80)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            DeckButtonWidget {
                border: 1px solid #555; border-radius: 6px; background: #1a1a1a;
            }
        """)

    def set_character(self, char):
        self.character = char
        self.update()

    def set_active(self, active):
        self._is_active = active
        self.update()

    def set_hotkey_text(self, text):
        self.hotkey_text = text
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        if self._is_active:
            painter.fillRect(rect, QColor(20, 50, 30))
        elif self._hover:
            painter.fillRect(rect, QColor(40, 40, 60))
        else:
            painter.fillRect(rect, QColor(25, 25, 25))
        if self._is_active:
            painter.setPen(QPen(QColor(0, 200, 100), 2))
            painter.drawRoundedRect(rect, 5, 5)
        if self.character:
            idle = self.character.get_idle_pixmap()
            if idle:
                thumb = idle.scaled(50, 50, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
                x = rect.x() + (rect.width() - thumb.width()) // 2
                painter.drawPixmap(x, rect.y() + 3, thumb)
            painter.setPen(QColor(200, 200, 200))
            painter.setFont(QFont("Segoe UI", 7))
            fm = painter.fontMetrics()
            name = fm.elidedText(self.character.name, Qt.TextElideMode.ElideRight, rect.width() - 4)
            painter.drawText(rect.adjusted(2, 0, -2, -2),
                             Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, name)
        else:
            painter.setPen(QColor(80, 80, 80))
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self.button_index + 1}")
        if self.hotkey_text:
            painter.setPen(QColor(100, 100, 140))
            painter.setFont(QFont("Segoe UI", 6))
            painter.drawText(rect.adjusted(3, 2, 0, 0),
                             Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, self.hotkey_text)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.button_clicked.emit(self.button_index)

    def contextMenuEvent(self, event):
        if self.character:
            menu = QMenu(self)
            clear_action = menu.addAction("Clear this button")
            action = menu.exec(event.globalPos())
            if action == clear_action:
                self.character = None
                self.character_cleared.emit(self.button_index)
                self.update()

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text().startswith("character:"):
            event.acceptProposedAction()
            self._hover = True
            self.update()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._hover = False
        self.update()

    def dropEvent(self, event):
        self._hover = False
        text = event.mimeData().text()
        if text.startswith("character:"):
            char_id = text.split(":", 1)[1]
            self.character_assigned.emit(self.button_index, char_id)
            event.acceptProposedAction()
        self.update()


# ---------------------------------------------------------------------------
# Deck Grid
# ---------------------------------------------------------------------------

class DeckGrid(QWidget):
    character_assigned = pyqtSignal(int, str)
    character_cleared = pyqtSignal(int)
    button_clicked = pyqtSignal(int)

    def __init__(self, rows=3, cols=5, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.cols = cols
        self.buttons: dict[int, DeckButtonWidget] = {}
        layout = QGridLayout(self)
        layout.setSpacing(6)
        idx = 0
        for r in range(rows):
            for c in range(cols):
                btn = DeckButtonWidget(idx)
                btn.character_assigned.connect(self.character_assigned)
                btn.character_cleared.connect(self.character_cleared)
                btn.button_clicked.connect(self.button_clicked)
                layout.addWidget(btn, r, c)
                self.buttons[idx] = btn
                idx += 1

    def set_layout_size(self, rows, cols):
        layout = self.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.buttons.clear()
        self.rows = rows
        self.cols = cols
        idx = 0
        for r in range(rows):
            for c in range(cols):
                btn = DeckButtonWidget(idx)
                btn.character_assigned.connect(self.character_assigned)
                btn.character_cleared.connect(self.character_cleared)
                btn.button_clicked.connect(self.button_clicked)
                layout.addWidget(btn, r, c)
                self.buttons[idx] = btn
                idx += 1

    def get_button(self, index):
        return self.buttons.get(index)

    def set_active_button(self, index):
        for idx, btn in self.buttons.items():
            btn.set_active(idx == index)

    def clear_active(self):
        for btn in self.buttons.values():
            btn.set_active(False)


# ---------------------------------------------------------------------------
# Character Library Panel
# ---------------------------------------------------------------------------

class CharacterLibrary(QWidget):
    character_selected = pyqtSignal(str)
    character_activated = pyqtSignal(str)
    character_deleted = pyqtSignal(str)
    character_settings_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards: dict[str, CharacterCard] = {}
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)

        header = QLabel("Ã°Å¸â€œÅ¡  Characters")
        header.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        header.setStyleSheet("color: #ddd; padding: 4px;")
        main_layout.addWidget(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_layout.setSpacing(6)
        self.scroll.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll)

    def add_character(self, char):
        card = CharacterCard(char)
        card.clicked.connect(self._on_card_clicked)
        card.double_clicked.connect(self.character_activated)
        card.delete_requested.connect(self.character_deleted)
        card.settings_requested.connect(self.character_settings_requested)
        self.scroll_layout.addWidget(card)
        self.cards[char.id] = card

    def remove_character(self, char_id):
        card = self.cards.pop(char_id, None)
        if card:
            self.scroll_layout.removeWidget(card)
            card.deleteLater()

    def refresh_character(self, char):
        card = self.cards.get(char.id)
        if card:
            card.character = char
            card.update()

    def set_selected(self, char_id):
        for cid, card in self.cards.items():
            card.set_selected(cid == char_id)

    def set_active(self, char_id):
        for cid, card in self.cards.items():
            card.set_active(cid == char_id)

    def clear_active(self):
        for card in self.cards.values():
            card.set_active(False)

    def _on_card_clicked(self, char_id):
        self.set_selected(char_id)
        self.character_selected.emit(char_id)

    def clear(self):
        for card in self.cards.values():
            card.deleteLater()
        self.cards.clear()


# ---------------------------------------------------------------------------
# PC Slot Editor
# ---------------------------------------------------------------------------

class PCSlotEditor(QFrame):
    """Editor card for a single PC portrait slot."""

    changed = pyqtSignal()
    remove_requested = pyqtSignal(str)  # slot.id

    def __init__(self, slot: PCSlot, characters: dict, obs_inputs: list = None,
                 parent=None):
        super().__init__(parent)
        self.slot = slot
        self._characters = characters

        self.setStyleSheet("""
            PCSlotEditor {
                border: 1px solid #444; border-radius: 6px;
                background: #252525; padding: 6px;
            }
        """)
        self.setFixedHeight(158)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # Thumbnail
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(64, 64)
        self.thumb_label.setStyleSheet("border: 1px solid #555; border-radius: 4px;"
                                        " background: #1a1a1a;")
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.thumb_label)

        # Config column
        config = QVBoxLayout()
        config.setSpacing(4)

        # Row 1: Name + Character picker
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit(slot.player_name)
        self.name_input.setPlaceholderText("Player name")
        self.name_input.setFixedWidth(100)
        self.name_input.textChanged.connect(self._on_change)
        row1.addWidget(self.name_input)

        row1.addWidget(QLabel("Char:"))
        self.char_combo = QComboBox()
        self.char_combo.addItem("(none)", "")
        for cid, char in characters.items():
            self.char_combo.addItem(char.name, cid)
        idx = self.char_combo.findData(slot.character_id)
        if idx >= 0:
            self.char_combo.setCurrentIndex(idx)
        self.char_combo.currentIndexChanged.connect(self._on_change)
        self.char_combo.setFixedWidth(120)
        row1.addWidget(self.char_combo)
        row1.addStretch()
        config.addLayout(row1)

        # Row 2: Audio source + threshold
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Audio:"))
        self.audio_combo = QComboBox()
        self.audio_combo.addItem("(none)", "")
        self.audio_combo.setFixedWidth(160)
        self.audio_combo.currentIndexChanged.connect(self._on_change)
        row2.addWidget(self.audio_combo)

        row2.addWidget(QLabel("Sens:"))
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(1, 100)
        self.threshold_slider.setValue(int(slot.audio_threshold * 1000))
        self.threshold_slider.setFixedWidth(80)
        self.threshold_slider.valueChanged.connect(self._on_change)
        row2.addWidget(self.threshold_slider)
        row2.addStretch()
        config.addLayout(row2)

        # Row 3: Glow color + intensity + remove
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Glow:"))
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(28, 22)
        self._update_color_btn()
        self.color_btn.clicked.connect(self._pick_color)
        row3.addWidget(self.color_btn)

        self.glow_slider = QSlider(Qt.Orientation.Horizontal)
        self.glow_slider.setRange(0, 100)
        self.glow_slider.setValue(int(slot.glow_intensity * 100))
        self.glow_slider.setFixedWidth(70)
        self.glow_slider.setToolTip("Glow intensity")
        self.glow_slider.valueChanged.connect(self._on_change)
        row3.addWidget(self.glow_slider)

        # Level meter
        self.level_label = QLabel("-" * 10)
        self.level_label.setStyleSheet("color: #555; font-family: monospace; font-size: 9px;")
        self.level_label.setFixedWidth(80)
        row3.addWidget(self.level_label)

        row3.addStretch()
        remove_btn = QPushButton("X")
        remove_btn.setFixedSize(24, 22)
        remove_btn.setStyleSheet("QPushButton { color: #cc4444; background: #2a2020; "
                                  "border: 1px solid #663333; border-radius: 3px; }"
                                  "QPushButton:hover { background: #3a2020; }")
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.slot.id))
        row3.addWidget(remove_btn)
        config.addLayout(row3)

        # Row 4: Discord user mapping
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Discord:"))
        self.discord_user_combo = QComboBox()
        self.discord_user_combo.setFixedWidth(160)
        self.discord_user_combo.addItem("(none)", 0)
        # Restore saved selection if we have one
        if slot.discord_user_id:
            self.discord_user_combo.addItem(f"User {slot.discord_user_id}", slot.discord_user_id)
            self.discord_user_combo.setCurrentIndex(1)
        self.discord_user_combo.currentIndexChanged.connect(
            self._on_discord_user_changed)
        row4.addWidget(self.discord_user_combo)

        self.dm_slot_check = QCheckBox("DM (use local mic)")
        self.dm_slot_check.setChecked(slot.is_dm)
        self.dm_slot_check.setToolTip(
            "DM's portrait uses the local microphone instead of Discord.\n"
            "Use this when the DM pipes music/sounds through Discord.")
        self.dm_slot_check.toggled.connect(self._on_dm_slot_changed)
        row4.addWidget(self.dm_slot_check)
        # Grey out Discord combo if DM slot
        self.discord_user_combo.setEnabled(not slot.is_dm)

        row4.addStretch()
        config.addLayout(row4)

        # Row 5: Voice tuning presets
        row5 = QHBoxLayout()
        row5.addWidget(QLabel("Voice:"))

        self._voice_presets = {
            # (attack_ms, decay_ms, smoothing, adaptive_multiplier)
            "Default":    (50, 250, 0.30, 2.5),
            "Responsive": (30, 150, 0.40, 2.0),   # more sensitive
            "Smooth":     (80, 400, 0.20, 3.0),   # less sensitive, filters more
            "Dramatic":   (50, 600, 0.30, 2.5),
        }
        self._voice_preset_tips = {
            "Default":    "Balanced -- good starting point (threshold auto-adjusts)",
            "Responsive": "Fast talker -- snappy response, more sensitive",
            "Smooth":     "Reduces noise -- filters out brief sounds",
            "Dramatic":   "Long hold -- portrait stays lit through pauses",
        }
        self._preset_buttons: dict[str, QPushButton] = {}
        for name in self._voice_presets:
            btn = QPushButton(name)
            btn.setFixedHeight(22)
            btn.setToolTip(self._voice_preset_tips[name])
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, n=name: self._apply_voice_preset(n))
            self._preset_buttons[name] = btn
            row5.addWidget(btn)

        row5.addStretch()
        config.addLayout(row5)

        # Identify which preset matches current values (or "Custom")
        self._active_preset = self._detect_current_preset()
        self._style_preset_buttons()

        layout.addLayout(config, stretch=1)

        # Populate audio sources if provided
        if obs_inputs:
            self.populate_audio_sources(obs_inputs)

        self._update_thumbnail()

    def populate_audio_sources(self, input_names: list):
        """Fill the audio source combo with OBS inputs"""
        current = self.slot.obs_audio_source
        self.audio_combo.blockSignals(True)
        self.audio_combo.clear()
        self.audio_combo.addItem("(none)", "")
        for name in input_names:
            self.audio_combo.addItem(name, name)
        idx = self.audio_combo.findData(current)
        if idx >= 0:
            self.audio_combo.setCurrentIndex(idx)
        self.audio_combo.blockSignals(False)

    def _on_discord_user_changed(self, index):
        user_id = self.discord_user_combo.currentData() or 0
        self.slot.discord_user_id = user_id
        self.changed.emit()

    def _on_dm_slot_changed(self, checked):
        self.slot.is_dm = checked
        self.discord_user_combo.setEnabled(not checked)
        self.changed.emit()

    def _apply_voice_preset(self, preset_name: str):
        """Apply a voice tuning preset to this slot."""
        attack, decay, smooth, multiplier = self._voice_presets[preset_name]
        self.slot.voice_attack_ms = attack
        self.slot.voice_decay_ms = decay
        self.slot.voice_smoothing = smooth
        self.slot.voice_adaptive_multiplier = multiplier
        self._active_preset = preset_name
        self._style_preset_buttons()
        self.changed.emit()

    def _detect_current_preset(self) -> str:
        """Check if current slot values match any preset."""
        current = (self.slot.voice_attack_ms, self.slot.voice_decay_ms,
                   self.slot.voice_smoothing,
                   getattr(self.slot, 'voice_adaptive_multiplier', 2.5))
        for name, values in self._voice_presets.items():
            if current == values:
                return name
        return ""

    def _style_preset_buttons(self):
        """Highlight the active preset button."""
        for name, btn in self._preset_buttons.items():
            if name == self._active_preset:
                btn.setStyleSheet(
                    "QPushButton { background: #2a5a3a; border: 1px solid #00cc66; "
                    "border-radius: 3px; padding: 2px 8px; color: #fff; font-size: 10px; }"
                    "QPushButton:hover { background: #3a6a4a; }")
            else:
                btn.setStyleSheet(
                    "QPushButton { background: #333; border: 1px solid #555; "
                    "border-radius: 3px; padding: 2px 8px; color: #aaa; font-size: 10px; }"
                    "QPushButton:hover { background: #444; color: #ddd; }")

    def populate_discord_users(self, members: list):
        """Populate the Discord user dropdown from voice channel members.

        Args:
            members: list of {"id": int, "name": str} dicts
        """
        current_id = self.slot.discord_user_id
        self.discord_user_combo.blockSignals(True)
        self.discord_user_combo.clear()
        self.discord_user_combo.addItem("(none)", 0)
        selected_index = 0
        for i, member in enumerate(members):
            self.discord_user_combo.addItem(member["name"], member["id"])
            if member["id"] == current_id:
                selected_index = i + 1
        self.discord_user_combo.setCurrentIndex(selected_index)
        self.discord_user_combo.blockSignals(False)

    def update_level_display(self, level: float):
        """Update the visual audio level meter"""
        bars = int(min(level * 500, 10))
        text = "#" * bars + "-" * (10 - bars)
        color = self.slot.glow_color if bars > 0 else "#555"
        self.level_label.setText(text)
        self.level_label.setStyleSheet(
            f"color: {color}; font-family: monospace; font-size: 9px;")

    def _on_change(self, *_):
        self.slot.player_name = self.name_input.text().strip()
        self.slot.character_id = self.char_combo.currentData() or ""
        self.slot.obs_audio_source = self.audio_combo.currentData() or ""
        self.slot.audio_threshold = self.threshold_slider.value() / 1000.0
        self.slot.glow_intensity = self.glow_slider.value() / 100.0
        self._update_thumbnail()
        self.changed.emit()

    def _pick_color(self):
        color = QColorDialog.getColor(
            QColor(self.slot.glow_color), self, "Glow Color")
        if color.isValid():
            self.slot.glow_color = color.name()
            self._update_color_btn()
            self.changed.emit()

    def _update_color_btn(self):
        self.color_btn.setStyleSheet(
            f"QPushButton {{ background: {self.slot.glow_color}; "
            f"border: 1px solid #888; border-radius: 3px; }}")

    def _update_thumbnail(self):
        cid = self.slot.character_id
        if cid and cid in self._characters:
            char = self._characters[cid]
            idle = char.get_idle_pixmap()
            if idle:
                thumb = idle.scaled(60, 60, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
                self.thumb_label.setPixmap(thumb)
                return
        self.thumb_label.clear()
        self.thumb_label.setText("?")
        self.thumb_label.setStyleSheet("border: 1px solid #555; border-radius: 4px;"
                                        " background: #1a1a1a; color: #666;")

