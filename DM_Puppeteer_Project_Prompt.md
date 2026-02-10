# DM Puppeteer — Project Prompt

## What This Is
DM Puppeteer is a PyQt6 desktop application — a D&D stream command center built as a gift for DM Raph, who streams the "Okora on the Edge" campaign on Twitch. It combines NPC puppet overlays, PC portrait overlays, OBS Studio control, Stream Deck hardware integration, and a Discord bot bridge into a single executable. The goal is a "produced show" feel for Twitch viewers while staying invisible to the DM during gameplay.

## Who This Is For
**Raph** — the DM and sole operator. He is not technical. Every feature must be GUI-driven with zero learning curve. We call this the "Raph-proof" standard. If it needs a config file, a command line, or code editing, it's wrong.

## Design Principles
1. **Raph-proof** — Everything is GUI. No config files, no terminal, no code.
2. **One executable** — Single .exe via PyInstaller. All panels built in.
3. **D&D-native** — Not a generic stream tool. Built around characters, sessions, encounters.
4. **Augment, don't replace** — We control OBS, we don't try to be OBS. Raph keeps his existing workflows. Critical example: Raph handles initiative manually and adds/removes mobs on the fly — the initiative tracker must stay out of his way and auto-populate from Avrae where possible.
5. **Stream Deck first-class** — Character faces on physical buttons. Deck layout matches screen.
6. **Graceful degradation** — Works without Stream Deck (hotkeys), without OBS (just puppet overlay), without Discord (local features only). Each integration is independent and optional.

## Architecture Overview
```
Entry: run.py → app_window.py (QTabWidget with 4 active tabs)

Core Threading Model:
- Main thread: PyQt6 GUI + overlay rendering
- Background thread: discord.py bot (asyncio event loop)
- Thread bridge: Event queue → Qt signals (thread-safe)
- Audio: sounddevice callback thread → Qt signals

Module Map (14 files, ~6,046 lines):
  models.py         — Character, PCSlot, Settings, AppState (JSON persistence)
  audio.py          — Mic input monitoring via sounddevice + numpy
  overlay.py        — NPC puppet overlay (transparent QWidget, OBS window capture)
  pc_overlay.py     — PC portrait overlays (strip mode + individual draggable windows)
  dice_overlay.py   — Animated dice roll cards with slide-in/out
  dice_effects.py   — Particle FX, D20 flash, screen shake [STUB]
  ai_client.py      — Claude Haiku API bridge [STUB]
  obs.py            — OBS WebSocket manager (obsws-python, port 4455)
  discord_bot.py    — Discord bot + Avrae message parser
  deck_hw.py        — Stream Deck hardware control (python-elgato-streamdeck)
  hotkeys.py        — Global keyboard hotkey fallback (pynput)
  widgets.py        — Custom UI components
  app_window.py     — Main control panel window

Overlay Windows (transparent, frameless, OBS window-captured):
  - Character Puppet Overlay
  - PC Portrait Overlay (strip / individual mode)
  - Dice Roll Overlay (with particle FX)

Data: data/state.json + data/characters/<name>/{idle,blink,talk,talk_blink}.png
```

## Phase Status

| Phase | Name | Status |
|-------|------|--------|
| 1 | NPC Puppet Panel | ✅ Complete |
| 2 | OBS Control Panel | ✅ Complete |
| 2.5 | PC Portrait Overlays | ✅ Complete |
| 3 | Discord Bot Bridge (dice rolls, voice state, Avrae parser) | ✅ Complete |
| — | Vowel Detection Lip Sync (PC portraits + DM) | 📋 Proposed |
| 4 | Soundboard Panel | 🔲 Not started |
| 5 | Initiative & Session Panel | 🔲 Not started |
| 6 | DM Director Panel (mood system, cinematic FX, death saves) | 🔲 Not started |
| 7 | Party Status Dashboard (HP bars, conditions, spell slots) | 🔲 Not started |
| 8 | AI Integration (Claude Haiku — recaps, mood, narration) | 🔲 Stubbed (ai_client.py) |
| 9 | Remote Control & Polish | 🔲 Not started |

### Stubbed / Ready for Integration
- `dice_effects.py` — Particle system, D20 flash, screen shake (code written, not wired to dice_overlay)
- `ai_client.py` — Claude Haiku 3.5 API bridge with prompt templates, background thread worker, Qt signal bridge

## Key Integration Patterns
**Pattern: Background service → Qt GUI**
Used by Discord bot, audio monitoring, and (future) AI client. All follow the same shape:
1. Service runs in a background thread (asyncio for Discord, callback for audio)
2. Events are pushed to a thread-safe queue or emitted via `pyqtSignal`
3. Qt main thread picks up signals and updates UI/overlays
Never touch Qt widgets from a background thread.

**Pattern: Character-Linked Actions**
One Stream Deck button press can simultaneously: switch puppet overlay, switch OBS scene, update OBS text source, toggle OBS sources, play entrance sound. All configured per-character via GUI.

**Pattern: OBS Audio Monitoring**
PC portrait speaking detection uses OBS `InputVolumeMeters` WebSocket events (RMS levels only — no raw audio). This is important context for the vowel detection feature, which will need raw audio via Discord voice receive or sounddevice.

## Current Technical Decisions & Constraints
- **Python 3.10+**, Windows 10/11 primary target (macOS/Linux untested but should work)
- **OBS Studio 28+** required for built-in WebSocket (no plugin)
- **Elgato Stream Deck MK.2** recommended (15 keys), but fully functional without via hotkeys
- **Discord bot** requires Message Content + Server Members intents
- **Avrae parser** extracts structured roll data from D&D Beyond roll messages in a specific channel
- All state persisted as JSON — no database, no external config files
- PyInstaller single-file build via `build.bat`

## Open Questions / Active Exploration
- Vowel detection for PC lip sync: Discord voice receive (Option A, preferred) vs. virtual audio cables (Option B, rejected as not Raph-proof)
- Discord voice receive needs PyNaCl for Opus decryption — dependency and complexity tradeoff
- Avrae embed format testing: need to verify parser handles all roll types
- Bot token security: currently pasted into GUI, may need keyring or env var approach
- Soundboard audio routing: virtual audio cable vs. direct OBS media source

## When Making Implementation Decisions
- Will Raph have to learn something new? → Minimize or eliminate.
- Does this break without an external service? → Must degrade gracefully.
- Does this add a dependency? → Justify it. Prefer stdlib where reasonable.
- Is this visible on stream? → Visual design matters. Reference Baldur's Gate 3 aesthetic for overlays.
- Does this touch Qt from a background thread? → Stop. Use signals.

## Dependencies
```
PyQt6              — GUI framework, transparent overlays
sounddevice+numpy  — Mic input monitoring
pynput             — Global keyboard hotkeys
obsws-python       — OBS Studio WebSocket control
Pillow             — Image processing for deck buttons
discord.py         — Discord bot (dice rolls, voice, commands)
streamdeck+hid     — Stream Deck hardware (optional)
scipy              — Signal processing (proposed, for vowel detection)
```
