# DM Puppeteer 🎭

**Character overlay & Stream Deck controller for D&D streams.**

Import characters, configure animated overlays, and control everything from your Stream Deck — NPCs, player portraits, OBS scenes, all in one app.

---

## What It Does

### 🎭 NPC Puppet Tab
- 4-frame animated character sprites (idle, blink, talk, talk+blink)
- Mic-reactive mouth movement + random auto-blink
- Per-character settings: size, transparency, blink timing, bounce/pop-in animations
- Stream Deck hardware integration or keyboard hotkeys
- Drag characters onto buttons, press to activate, press again to hide

### 🎬 OBS Control Tab
- Connect to OBS Studio via WebSocket (built into OBS 28+)
- Scene switching with clickable buttons
- Stream/recording toggle controls
- **Character-Linked Actions:** Activate a character → OBS auto-switches scene + updates text source

### 👥 PC Portraits Tab
- Configurable player slots with per-player glow colors
- Audio monitoring via OBS input sources (each player's Discord audio)
- Active speaker gets a glowing highlight border, others dim + optional shade silhouette
- Two overlay modes: Strip (one window) or Individual (per-player, draggable, positions saved)
- All sliders: size, spacing, dim opacity, shade amount, per-player glow intensity
- Same animation effects (bounce, pop-in, blink) as NPCs

---

## Quick Start

### 1. Install
```
pip install PyQt6 sounddevice numpy pynput obsws-python Pillow
```
For Stream Deck hardware (optional):
```
pip install streamdeck hid
```

### 2. Run
```
python run.py
```

### 3. Create Characters
1. Click **➕ New** in the control panel
2. Type a character name and drag 4 PNG sprite frames onto the drop zones
3. Click **💾 Save Character**

Works for both NPCs and PCs — same character library, different tabs.

### 4. Stream Deck / Hotkeys
- Drag character cards from the library onto the deck grid
- Click or press a physical button to activate/hide characters
- Default hotkeys: Ctrl+Shift+1 through Ctrl+Shift+0

### 5. Per-Character Settings
Right-click any character → **Settings**:
- Scale, opacity, blink timing
- Bounce/bob and pop-in animations
- OBS Linked Actions (scene + text source per character)

### 6. OBS Integration
1. In OBS: **Tools → WebSocket Server Settings → Enable**
2. In DM Puppeteer: **🎬 OBS Control** tab → Connect
3. Assign scenes to characters via right-click → Settings

### 7. PC Portraits
1. In the **👥 PC Portraits** tab, add player slots
2. Assign a character and OBS audio source to each
3. Pick glow colors and adjust sensitivity
4. Hit **Show Portraits** — speaking players light up

---

## Building an Executable
```
pip install pyinstaller
python -m PyInstaller --onefile --windowed --name "DM Puppeteer" run.py
```

## File Structure
```
dm_puppeteer/
├── run.py                      # Entry point
├── requirements.txt
├── build.bat
├── dm_puppeteer/
│   ├── models.py               # Character, PCSlot, Settings, AppState
│   ├── audio.py                # Mic input monitoring
│   ├── overlay.py              # NPC puppet overlay
│   ├── pc_overlay.py           # PC portrait overlays (strip + individual)
│   ├── obs.py                  # OBS WebSocket manager
│   ├── deck_hw.py              # Stream Deck hardware control
│   ├── hotkeys.py              # Keyboard hotkey fallback
│   ├── widgets.py              # Custom UI components
│   └── app_window.py           # Main control panel (3 tabs)
└── data/                       # Created at runtime
    ├── state.json
    └── characters/
```

## Requirements
- Python 3.10+
- OBS Studio 28+ (for WebSocket, no plugin needed)
- Elgato Stream Deck recommended (works without via hotkeys)
- Windows 10/11 (tested), macOS/Linux should work
