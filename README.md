# DM Puppeteer ­

**D&D stream command center character overlays, OBS control, player portraits, and live dice roll visuals, all from one app.**

Import characters, configure animated overlays, parse live dice rolls from Discord, and control everything from your Stream Deck. Built for DMs who stream on Twitch/YouTube.

---

## What It Does

### NPC Puppet Tab
- 4-frame animated character sprites (idle, blink, talk, talk+blink)
- Mic-reactive mouth movement + random auto-blink
- Per-character settings: size, transparency, blink timing, bounce/pop-in animations
- Stream Deck hardware integration or keyboard hotkeys
- Drag characters onto buttons, press to activate, press again to hide

### OBS Control Tab
- Connect to OBS Studio via WebSocket (built into OBS 28+, no plugin needed)
- Scene switching with clickable buttons
- Source toggling â€” show/hide overlays, camera, chat widgets
- Start/stop stream and recording controls
- Audio source mute/unmute
- **Character-Linked Actions:** Activate a character OBS auto-switches scene + updates text source + toggles sources all in one button press

### PC Portraits Tab
- Configurable player slots with per-player glow colors
- Audio monitoring via OBS input sources (each player's Discord audio)
- Active speaker gets a glowing highlight border, others dim + optional shade silhouette
- Two overlay modes: Strip (one window) or Individual (per-player, draggable, positions saved)
- All sliders: size, spacing, dim opacity, shade amount, per-player glow intensity
- Same animation effects (bounce, pop-in, blink) as NPCs

### Discord Bot Tab
- Discord bot connects to your server and monitors channels in the background
- **Dice Roll Overlay:** Parses Avrae / D&D Beyond roll messages and displays animated overlay cards on stream â€” character name, check type, dice formula, and total
- Character-matched colors (links to PC slot glow colors)
- Configurable display time (2â€“15 seconds)
- Roll log in the Discord tab shows recent rolls
- Test roll button for previewing the overlay without a Discord connection
- Voice state monitoring (join/leave/mute/deafen events)
- `!pm` custom command system for future expansion

---

## Quick Start

### 1. Install
```
pip install PyQt6 sounddevice numpy pynput obsws-python Pillow discord.py
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
1. Click **New** in the control panel
2. Type a character name and drag 4 PNG sprite frames onto the drop zones
3. Click **Save Character**

Works for both NPCs and PCs â€” same character library, different tabs.

### 4. Stream Deck / Hotkeys
- Drag character cards from the library onto the deck grid
- Click or press a physical button to activate/hide characters
- Default hotkeys: Ctrl+Shift+1 through Ctrl+Shift+0

### 5. Per-Character Settings
Right-click any character ’ **Settings**:
- Scale, opacity, blink timing
- Bounce/bob and pop-in animations
- OBS Linked Actions (scene + text source + show/hide sources per character)

### 6. OBS Integration
1. In OBS: **Tools WebSocket Server Settings â†’ Enable**
2. In DM Puppeteer: **OBS Control** tab Connect
3. Assign scenes to characters via right-click Settings

### 7. PC Portraits
1. In the **PC Portraits** tab, add player slots
2. Assign a character and OBS audio source to each
3. Pick glow colors and adjust sensitivity
4. Hit **Show Portraits** peaking players light up

### 8. Discord Bot (Dice Rolls)
1. Create a Discord bot at [discord.com/developers](https://discord.com/developers/applications) with Message Content + Server Members intents enabled
2. In the **Discord** tab, paste your bot token and roll channel ID
3. Click **Connect** dice rolls from Avrae will appear as animated overlay cards on stream
4. The setup guide in the Discord tab walks through the full process

---

## Building an Executable
```
pip install pyinstaller
python -m PyInstaller --onefile --windowed --name "DM Puppeteer" run.py
```
Or use the included `build.bat` on Windows.

## File Structure
```
dm_puppeteer/
â”œâ”€â”€ run.py                      # Entry point
â”œâ”€â”€ requirements.txt
â”œâ”€â”€ build.bat                   # PyInstaller build script
â”œâ”€â”€ create_test_characters.py   # Generate test character frames
â”œâ”€â”€ dm_puppeteer/
â”‚   â”œâ”€â”€ models.py               # Character, PCSlot, Settings, AppState
â”‚   â”œâ”€â”€ audio.py                # Mic input monitoring
â”‚   â”œâ”€â”€ overlay.py              # NPC puppet overlay
â”‚   â”œâ”€â”€ pc_overlay.py           # PC portrait overlays (strip + individual)
â”‚   â”œâ”€â”€ dice_overlay.py         # Animated dice roll cards
â”‚   â”œâ”€â”€ dice_effects.py         # Particle FX, D20 flash, screen shake (stub)
â”‚   â”œâ”€â”€ ai_client.py            # Claude Haiku API bridge (stub)
â”‚   â”œâ”€â”€ obs.py                  # OBS WebSocket manager
â”‚   â”œâ”€â”€ discord_bot.py          # Discord bot + Avrae parser
â”‚   â”œâ”€â”€ deck_hw.py              # Stream Deck hardware control
â”‚   â”œâ”€â”€ hotkeys.py              # Keyboard hotkey fallback
â”‚   â”œâ”€â”€ widgets.py              # Custom UI components
â”‚   â””â”€â”€ app_window.py           # Main control panel (4 tabs)
â””â”€â”€ data/                       # Created at runtime
    â”œâ”€â”€ state.json
    â””â”€â”€ characters/
```

## Requirements
- Python 3.10+
- OBS Studio 28+ (for WebSocket, no plugin needed)
- Elgato Stream Deck recommended (works without via hotkeys)
- Discord bot token (for dice roll overlay, optional)
- Windows 10/11 (tested), macOS/Linux should work

## Design Principles
- **Everything is GUI** â€” no config files, no command line, no code editing
- **One executable** â€” single .exe with all panels built in
- **D&D-native** â€” built around characters, sessions, and encounters
- **Graceful degradation** â€” works without Stream Deck (hotkeys), without OBS (just the puppet overlay), without Discord (just local features). Each integration is independent and optional.
