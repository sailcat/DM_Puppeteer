"""
OBS Studio WebSocket integration via obsws-python.

Provides scene switching, source toggling, text source updates,
and stream/recording control — all through OBS's built-in WebSocket
server (port 4455 by default, no plugin needed on OBS 28+).
"""

import traceback
import threading
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

try:
    import obsws_python as obsws
    OBS_AVAILABLE = True
except ImportError:
    OBS_AVAILABLE = False


class OBSManager(QObject):
    """Manages the connection to OBS Studio via WebSocket."""

    connection_changed = pyqtSignal(bool, str)    # connected, info_text
    scenes_updated = pyqtSignal(list)             # list of scene names
    sources_updated = pyqtSignal(list)            # list of source dicts
    scene_switched = pyqtSignal(str)              # current scene name
    audio_levels = pyqtSignal(dict)               # {source_name: peak_level}
    inputs_updated = pyqtSignal(list)             # list of input names (audio sources)
    error_occurred = pyqtSignal(str)              # error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._client = None
        self._evt_client = None
        self._connected = False
        self._current_scene = ""
        self._scenes: list[str] = []
        self._sources: list[dict] = []
        self._inputs: list[str] = []

        # Audio level bridging (EventClient runs in bg thread)
        self._latest_levels: dict[str, float] = {}
        self._levels_lock = threading.Lock()

        # Periodic scene poll
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_current_scene)

        # Audio level bridge timer (reads from bg thread dict)
        self._audio_timer = QTimer(self)
        self._audio_timer.timeout.connect(self._emit_audio_levels)

    @property
    def is_connected(self):
        return self._connected

    @property
    def current_scene(self):
        return self._current_scene

    @property
    def scenes(self):
        return self._scenes

    @property
    def sources(self):
        return self._sources

    @property
    def inputs(self):
        return self._inputs

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self, host="localhost", port=4455, password=""):
        """Connect to OBS WebSocket server."""
        if not OBS_AVAILABLE:
            self.connection_changed.emit(False, "obsws-python not installed")
            self.error_occurred.emit(
                "Install obsws-python:  pip install obsws-python")
            return False

        try:
            self._client = obsws.ReqClient(
                host=host, port=port, password=password or None, timeout=5
            )
            self._connected = True

            # Fetch initial data
            self._refresh_scenes()
            self._refresh_sources()
            self._refresh_inputs()
            self._poll_current_scene()

            # Start polling every 2 seconds
            self._poll_timer.start(2000)

            # Start audio level EventClient
            self._start_audio_monitor(host, port, password)

            version = ""
            try:
                v = self._client.get_version()
                version = f"OBS {v.obs_version}"
            except Exception:
                version = "OBS connected"

            self.connection_changed.emit(True, version)
            return True

        except Exception as e:
            self._connected = False
            self._client = None
            msg = str(e)
            if "refused" in msg.lower() or "connect" in msg.lower():
                msg = "Connection refused - is OBS running with WebSocket enabled?"
            self.connection_changed.emit(False, msg)
            self.error_occurred.emit(msg)
            return False

    def disconnect(self):
        """Disconnect from OBS."""
        self._poll_timer.stop()
        self._audio_timer.stop()
        self._stop_audio_monitor()
        if self._client:
            try:
                self._client = None
            except Exception:
                pass
        self._connected = False
        self._scenes.clear()
        self._sources.clear()
        self._inputs.clear()
        self._current_scene = ""
        self.connection_changed.emit(False, "Disconnected")

    # ------------------------------------------------------------------
    # Scene Control
    # ------------------------------------------------------------------

    def switch_scene(self, scene_name: str):
        """Switch to the named scene in OBS."""
        if not self._connected or not self._client:
            return False
        try:
            self._client.set_current_program_scene(scene_name)
            self._current_scene = scene_name
            self.scene_switched.emit(scene_name)
            return True
        except Exception as e:
            self.error_occurred.emit(f"Scene switch failed: {e}")
            return False

    def get_scene_list(self) -> list[str]:
        """Return cached scene list."""
        return self._scenes.copy()

    def refresh_scenes(self):
        """Public method to force-refresh scene list."""
        self._refresh_scenes()

    def _refresh_scenes(self):
        if not self._connected or not self._client:
            return
        try:
            resp = self._client.get_scene_list()
            self._scenes = [s["sceneName"] for s in resp.scenes]
            self._scenes.reverse()  # OBS returns them bottom-to-top
            self.scenes_updated.emit(self._scenes)
        except Exception as e:
            self.error_occurred.emit(f"Failed to get scenes: {e}")

    def _poll_current_scene(self):
        if not self._connected or not self._client:
            return
        try:
            resp = self._client.get_current_program_scene()
            name = resp.scene_name if hasattr(resp, 'scene_name') else str(resp.current_program_scene_name)
            if name != self._current_scene:
                self._current_scene = name
                self.scene_switched.emit(name)
        except Exception as e:
            # Connection may have dropped
            if self._connected:
                self._connected = False
                self._poll_timer.stop()
                self.connection_changed.emit(False, "Connection lost")

    # ------------------------------------------------------------------
    # Source Control
    # ------------------------------------------------------------------

    def _refresh_sources(self):
        """Get all sources from the current scene."""
        if not self._connected or not self._client:
            return
        try:
            # Get sources from current scene
            scene = self._current_scene or self._scenes[0] if self._scenes else None
            if not scene:
                return
            resp = self._client.get_scene_item_list(scene)
            self._sources = []
            for item in resp.scene_items:
                self._sources.append({
                    "id": item.get("sceneItemId"),
                    "name": item.get("sourceName", ""),
                    "kind": item.get("inputKind", ""),
                    "visible": item.get("sceneItemEnabled", True),
                })
            self.sources_updated.emit(self._sources)
        except Exception as e:
            self.error_occurred.emit(f"Failed to get sources: {e}")

    def set_source_visible(self, source_name: str, visible: bool, scene_name: str = None):
        """Show or hide a source in the given scene (or current scene)."""
        if not self._connected or not self._client:
            return False
        scene = scene_name or self._current_scene
        if not scene:
            return False
        try:
            # Find the scene item ID for this source
            resp = self._client.get_scene_item_list(scene)
            for item in resp.scene_items:
                if item.get("sourceName") == source_name:
                    item_id = item["sceneItemId"]
                    self._client.set_scene_item_enabled(
                        scene_name=scene,
                        scene_item_id=item_id,
                        scene_item_enabled=visible
                    )
                    return True
            return False
        except Exception as e:
            self.error_occurred.emit(f"Source toggle failed: {e}")
            return False

    def toggle_source(self, source_name: str, scene_name: str = None):
        """Toggle a source's visibility."""
        if not self._connected or not self._client:
            return False
        scene = scene_name or self._current_scene
        if not scene:
            return False
        try:
            resp = self._client.get_scene_item_list(scene)
            for item in resp.scene_items:
                if item.get("sourceName") == source_name:
                    item_id = item["sceneItemId"]
                    current = item.get("sceneItemEnabled", True)
                    self._client.set_scene_item_enabled(
                        scene_name=scene,
                        scene_item_id=item_id,
                        scene_item_enabled=not current
                    )
                    return True
            return False
        except Exception as e:
            self.error_occurred.emit(f"Source toggle failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Text Source
    # ------------------------------------------------------------------

    def set_text_source(self, source_name: str, text: str):
        """Update a text (GDI+/FreeType) source's content."""
        if not self._connected or not self._client:
            return False
        try:
            self._client.set_input_settings(
                input_name=source_name,
                input_settings={"text": text},
                overlay=True
            )
            return True
        except Exception as e:
            self.error_occurred.emit(f"Text update failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Stream / Recording
    # ------------------------------------------------------------------

    def start_stream(self):
        if self._connected and self._client:
            try:
                self._client.start_stream()
            except Exception as e:
                self.error_occurred.emit(f"Start stream failed: {e}")

    def stop_stream(self):
        if self._connected and self._client:
            try:
                self._client.stop_stream()
            except Exception as e:
                self.error_occurred.emit(f"Stop stream failed: {e}")

    def toggle_stream(self):
        if self._connected and self._client:
            try:
                self._client.toggle_stream()
            except Exception as e:
                self.error_occurred.emit(f"Toggle stream failed: {e}")

    def start_recording(self):
        if self._connected and self._client:
            try:
                self._client.start_record()
            except Exception as e:
                self.error_occurred.emit(f"Start recording failed: {e}")

    def stop_recording(self):
        if self._connected and self._client:
            try:
                self._client.stop_record()
            except Exception as e:
                self.error_occurred.emit(f"Stop recording failed: {e}")

    def toggle_recording(self):
        if self._connected and self._client:
            try:
                self._client.toggle_record()
            except Exception as e:
                self.error_occurred.emit(f"Toggle recording failed: {e}")

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------

    def toggle_mute(self, source_name: str):
        """Toggle mute on an audio source."""
        if self._connected and self._client:
            try:
                self._client.toggle_input_mute(input_name=source_name)
            except Exception as e:
                self.error_occurred.emit(f"Mute toggle failed: {e}")

    # ------------------------------------------------------------------
    # Input (Audio Source) List
    # ------------------------------------------------------------------

    def get_input_list(self) -> list[str]:
        """Return cached input names."""
        return self._inputs.copy()

    def refresh_inputs(self):
        self._refresh_inputs()

    def _refresh_inputs(self):
        if not self._connected or not self._client:
            return
        try:
            resp = self._client.get_input_list()
            self._inputs = [inp["inputName"] for inp in resp.inputs]
            self.inputs_updated.emit(self._inputs)
        except Exception as e:
            self.error_occurred.emit(f"Failed to get inputs: {e}")

    # ------------------------------------------------------------------
    # Audio Level Monitoring (via EventClient)
    # ------------------------------------------------------------------

    def _start_audio_monitor(self, host, port, password):
        """Start a separate EventClient to receive InputVolumeMeters."""
        self._stop_audio_monitor()
        try:
            # Subscribe only to InputVolumeMeters for efficiency
            subs = 0
            if hasattr(obsws, 'Subs'):
                subs = obsws.Subs.INPUT_VOLUME_METERS
            elif hasattr(obsws, 'EventSubscription'):
                subs = obsws.EventSubscription.INPUT_VOLUME_METERS

            self._evt_client = obsws.EventClient(
                host=host, port=port,
                password=password or None,
                subs=subs, timeout=5
            )
            self._evt_client.callback.register(self._on_volume_meters)

            # Start the Qt timer that bridges bg thread levels to signals
            self._audio_timer.start(50)  # ~20Hz, smooth enough for animation

        except Exception as e:
            print(f"Audio monitor EventClient failed: {e}")
            # Fallback: no audio level monitoring, features still work
            self._evt_client = None

    def _stop_audio_monitor(self):
        if self._evt_client:
            try:
                self._evt_client.unsubscribe()
            except Exception:
                pass
            try:
                self._evt_client = None
            except Exception:
                pass

    def _on_volume_meters(self, data):
        """Called from EventClient bg thread with audio levels."""
        try:
            levels = {}
            # data.inputs is a list of input level info
            for inp in data.inputs:
                name = ""
                peak = 0.0

                # Handle different obsws-python API formats
                if isinstance(inp, dict):
                    name = inp.get("inputName", "")
                    raw_levels = inp.get("inputLevelsMul", [])
                elif isinstance(inp, (list, tuple)):
                    name = inp[0] if len(inp) > 0 else ""
                    raw_levels = inp[1] if len(inp) > 1 else []
                else:
                    continue

                # Extract peak from channel levels
                # Each channel: [rms, peak] or similar
                for ch in raw_levels:
                    if isinstance(ch, (list, tuple)) and len(ch) >= 2:
                        ch_peak = float(ch[1])  # peak value
                        peak = max(peak, ch_peak)
                    elif isinstance(ch, (int, float)):
                        peak = max(peak, float(ch))

                if name:
                    levels[name] = peak

            with self._levels_lock:
                self._latest_levels = levels

        except Exception as e:
            pass  # Don't crash on malformed data

    def _emit_audio_levels(self):
        """Called from Qt main thread timer — emit the latest levels."""
        with self._levels_lock:
            if self._latest_levels:
                self.audio_levels.emit(self._latest_levels.copy())
