# DM Puppeteer â€” Future Roadmap ðŸ—ºï¸

*Saved from our planning discussion. This is the vision for expanding DM Puppeteer from a character puppet tool into a full D&D Stream Command Center â€” all in one executable.*

---

## Current: ðŸŽ­ NPC Puppet Panel âœ…

- Character library with drag-drop frame setup (idle, blink, talk, talk_blink)
- Mic-reactive mouth animation with auto-blink
- Stream Deck hardware integration (direct USB control)
- Hotkey fallback mode when Stream Deck not connected
- Drag characters onto Stream Deck button grid
- Per-character settings (size, transparency, blink timing, animation effects)
- Draggable overlay with per-character scale slider
- Toggle character visibility by re-pressing the active deck button

---

## Phase 2: ðŸŽ¬ OBS Control Panel âœ…

**Replaces Elgato's Stream Deck software for OBS control.**

Uses `obsws-python` to talk to OBS Studio's built-in WebSocket server (port 4455, no plugin needed).

### Features
- Connect to OBS via WebSocket (host/port/password config in the app)
- Scene switching buttons assignable to Stream Deck
- Source toggling â€” show/hide overlays, camera, chat widget
- Start/stop stream and recording buttons
- Audio source mute/unmute

### The Killer Feature: Character-Linked Actions
When Raph presses a character button, the app can **simultaneously**:
1. Switch puppet overlay to that character
2. Switch OBS to a matching scene (e.g., "NPC Close-up")
3. Play the character's entrance sound (optional, first appearance only)
4. Update a text source in OBS with the character's name

All configurable per-character. One button press = total scene change.

### Stream Deck Page Support
- Page 1: NPC characters
- Page 2: Soundboard
- Page 3: OBS scenes / utility
- Physical buttons re-render with new icons when switching pages
- Dedicated page-flip buttons (or swipe on Stream Deck+)

---

## Phase 2.5: ðŸ‘¥ PC Portrait Overlays âœ…

**Player character portraits driven by OBS audio sources.**

### Features
- Configurable number of player slots (add/remove)
- Each slot: character + OBS audio source + glow color + glow intensity + threshold
- Real-time audio monitoring via OBS InputVolumeMeters events
- Per-player glow highlight when speaking (customizable color and intensity)
- Non-speaking portraits dim to configurable opacity
- Shade mask: adjustable dark overlay on non-speaking portraits (silhouette effect)
- Same animation effects as NPCs (bounce, pop-in, blink)
- Two overlay modes: Strip (one window) or Individual (per-player windows)
- Individual mode: position persistence across show/hide cycles
- All sliders: portrait size, spacing, dim opacity, shade amount
- Live audio level meters in the control panel

---

## Phase 3: ðŸŽ² Discord Bot Bridge âœ…

**Discord integration for live dice roll overlays and voice state.**

### Architecture
- `discord.py` bot runs in a background thread alongside the Qt app
- Thread-safe event queue bridges Discord events to Qt signals
- Avrae message parser extracts structured roll data from D&D Beyond rolls

### Features: Dice Roll Overlay
- Parses Avrae / D&D Beyond roll messages from `#disc-rolls-only`
- Animated overlay cards slide in showing: character name, check type, dice formula, total
- NAT 20 â†’ gold glow + "NAT 20!" label; NAT 1 â†’ red glow + "NAT 1" label
- Character-matched colors (links to PC slot glow colors)
- Display time slider (2â€“15 seconds)
- Roll log in the Discord tab shows recent rolls
- Test roll button for previewing without Discord connection

### Features: Voice State Monitoring
- Detects voice channel join/leave/mute/deafen events
- Foundation for Discord-powered PC portraits (replacing Fugi)

### Features: Custom Commands
- `!pm` prefix commands from Discord â†’ DM Puppeteer events
- Extensible command system for future initiative/soundboard/session features

---

## Phase 4: ðŸ”Š Soundboard Panel

**D&D-focused ambient sound and SFX system.**

### Features
- Drag-drop sound files (MP3/WAV/OGG) onto a grid
- Assign sounds to Stream Deck buttons with custom icons
- Per-sound volume control
- Categories: Ambiance (loops), SFX (one-shot), Music (background)
- Crossfade between ambiance tracks
- Per-character entrance themes (auto-play on first switch)
- Sound plays through a virtual audio cable or directly to OBS

### D&D Sound Categories (starter pack ideas)
- **Ambiance:** Tavern, Forest, Dungeon, Rain, Campfire, Battle, Market
- **SFX:** Sword clash, Thunder, Door creak, Spell cast, Dragon roar, Dice roll
- **Stingers:** Dramatic reveal, Victory fanfare, Death knell, Plot twist

---

## Phase 5: ðŸ“‹ Initiative & Session Panel

**Combat tracking that augments the DM's existing workflow â€” not a replacement.**

Note: Raph handles initiative manually and adds/removes mobs on the fly. This system must stay out of his way.

### Initiative Tracker (DM Director tab)
- Red "Begin Combat" button â†’ turns green (activates combat mode app-wide)
- PC initiatives auto-populate from Avrae roll messages (zero manual entry)
- Monster entry: name field with passive autocomplete (SRD + custom names) + initiative number
- Autocomplete is suggestions-only â€” never overwrites typed text, Escape/Delete cancels
- Enter adds combatant and auto-sorts the full list
- "Goblin x3" syntax for multiple mobs at same initiative
- Drag to reorder, click X to remove
- "Next Turn" button (also on Stream Deck) advances the tracker

### Stream Overlay (Baldur's Gate 3 style)
- Horizontal card strip across top of stream
- Current turn: raised/glowing card; upcoming: normal; passed: dimmed
- New round: shuffle animation back to start
- Monster eliminated: death animation (cracks/fade), cards close gap
- PC cards use character portraits; monster cards use creature-type silhouettes
- Smooth add/remove/reorder animations

### Session Tools
- Session timer (visible on stream or just for DM)
- Break timer with countdown overlay
- Quick notes panel (session reminders, NPC names, plot points)
- Episode counter / title display

---

## Phase 6: ðŸŽ¬ DM Director Panel

**Cinematic automation â€” making the stream feel like a produced show.**

### Mood System
- Single mood state: Combat, Exploration, Social, Tension, Celebration, Somber, Epic
- All overlays, effects, audio, and colors respond to current mood
- One button press transforms the entire stream aesthetic
- AI-assisted mood suggestions based on recent game events (DM can override)

### Cinematic Camera Presets
- "Dramatic Zoom" â€” tight crop on relevant PC portrait or DM cam via OBS
- Lighting filters toggled per mood (OBS filter control)
- Slide-in banner + D20 flash + particle effects on big rolls
- Screen shake on crits/fumbles
- Configurable per trigger (NAT 20, NAT 1, death save, location change)

### Death Save Overlay
- Dedicated overlay: 3 skull icons (failures) + 3 heart icons (successes)
- Red cracks draw inward on failed saves
- Blue glow brightens on successful saves
- Stabilize: white flash â†’ golden shimmer rolls down portrait
- Death: cracks overwhelm portrait â†’ fade to black
- AI narration: dramatic one-liner per save

### Location Card Transitions
- Stylized title card on location change ("The Whispering Caverns")
- Atmospheric gradient backgrounds, configurable fonts
- Chapter-card feel â€” gives the stream structure
- Triggered from notes panel or Stream Deck

### Story Recap Crawl
- Star Wars-style scrolling text at session start
- AI-generated from previous session's log (Raph reviews/approves)
- Separate transparent overlay with configurable speed and font

---

## Phase 7: ðŸ“Š Party Status Dashboard

**Persistent HUD overlay showing party vitals.**

### Features
- HP bars per PC (color-coded, animate on changes)
- Active conditions/status effects (poisoned, stunned, concentrating)
- Spell slot indicators
- RPG video game HUD aesthetic
- Updates via Avrae data, Discord commands, or manual entry
- Viewers see tension at a glance without DM narrating it

---

## Phase 8: ðŸ¤– AI Integration (Claude Haiku)

**Lightweight AI co-pilot for the DM â€” pennies per session.**

Uses Anthropic Claude Haiku 3.5 via API. Estimated ~$0.01-0.02 per 4-hour session.

### Confirmed Features
- **Session Recap Crawl** â€” Auto-generate dramatic 3-4 sentence recap from session log
- **Mood Suggestions** â€” AI watches recent rolls, suggests scene mood shifts
- **Death Save Narration** â€” Per-save dramatic one-liners for stream overlay
- **NPC Memory Teleprompter** â€” Quick NPC reminder when DM switches characters (DM-only)
- **Session Transcript** â€” Structured summary at session end (Key Events, Combat, MVP)

### * Pending Raph Approval
- **Combat Commentary** â€” Flavor text on rolls ("The guard believes every word"). Gated behind explicit approval flag since it involves AI interpreting RP elements.

### Architecture
- `ai_client.py` â€” Stubbed with prompt templates, background thread worker, Qt signal bridge
- All prompts centralized in `Prompts` class for easy tuning
- Token usage tracking with running cost display

---

## Phase 9: ðŸŒ Remote Control & Polish

### Web Remote Control
- Built-in web server accessible from phone/tablet on same network
- Mobile-friendly UI for character switching, soundboard, initiative
- Useful as a secondary controller or for a co-DM

### Import/Export
- Character packs (zip with frames + settings)
- Full session profiles (all characters + deck layout + OBS scenes)
- Share between DMs or across campaigns

### Quality of Life
- Transition animations between characters (fade, slide, pop)
- Character name overlay text (configurable font/position)
- Multiple overlay positions (different corners for different characters)
- Undo/redo for all actions
- Auto-backup of session data
- First-run setup wizard

---

## Technical Architecture

```
DM Puppeteer (one executable)
â”œâ”€â”€ Core
â”‚   â”œâ”€â”€ App State & Persistence (JSON)
â”‚   â”œâ”€â”€ Stream Deck Hardware Manager
â”‚   â”œâ”€â”€ Global Hotkey Listener (fallback)
â”‚   â””â”€â”€ Audio Monitor (mic input)
â”‚
â”œâ”€â”€ Panels (tabs in the control window)
â”‚   â”œâ”€â”€ ðŸŽ­ Puppet Panel
â”‚   â”œâ”€â”€ ðŸŽ¬ OBS Control Panel
â”‚   â”œâ”€â”€ ðŸ‘¥ PC Portraits Panel
â”‚   â”œâ”€â”€ ðŸŽ² Discord Panel
â”‚   â”œâ”€â”€ ðŸ”Š Soundboard Panel
â”‚   â”œâ”€â”€ ðŸ“‹ Initiative Panel
â”‚   â”œâ”€â”€ ðŸŽ¬ DM Director Panel
â”‚   â””â”€â”€ ðŸ“Š Party Dashboard Panel
â”‚
â”œâ”€â”€ Overlay Windows (transparent, OBS-captured)
â”‚   â”œâ”€â”€ Character Puppet Overlay
â”‚   â”œâ”€â”€ PC Portrait Overlay (strip / individual)
â”‚   â”œâ”€â”€ Dice Roll Overlay (with particle FX)
â”‚   â”œâ”€â”€ Death Save Overlay
â”‚   â”œâ”€â”€ Initiative Tracker Overlay
â”‚   â”œâ”€â”€ Party Status HUD
â”‚   â”œâ”€â”€ Story Recap Crawl
â”‚   â”œâ”€â”€ Location Card
â”‚   â””â”€â”€ Name/Title Overlay
â”‚
â””â”€â”€ Integrations
    â”œâ”€â”€ Stream Deck USB (python-elgato-streamdeck)
    â”œâ”€â”€ OBS WebSocket (obsws-python)
    â”œâ”€â”€ Discord Bot (discord.py)
    â”œâ”€â”€ Claude AI (Haiku 3.5 via Anthropic API)
    â””â”€â”€ Web Remote (built-in HTTP server)
```

### Key Python Libraries
| Library | Purpose |
|---------|---------|
| `PyQt6` | GUI framework, transparent overlays |
| `streamdeck` | Direct Stream Deck hardware control |
| `obsws-python` | OBS Studio WebSocket control |
| `discord.py` | Discord bot (dice rolls, voice, commands) |
| `sounddevice` + `numpy` | Mic input monitoring |
| `pynput` | Global keyboard hotkeys |
| `pygame.mixer` or `soundfile` | Soundboard audio playback |
| `Pillow` | Image processing for deck buttons |
| `urllib.request` | Claude AI API calls (stdlib, no dependency) |
| `aiohttp` or `flask` | Web remote control server |

### Stream Deck Hardware Recommendation
**Elgato Stream Deck MK.2** (15 keys, ~$150)
- 3Ã—5 LCD button grid, perfect for 10-12 NPCs + utility buttons
- Best supported by the python library
- USB-C, adjustable stand
- Sweet spot between the Neo (8 keys, too few) and XL (32 keys, overkill)

---

## Design Principles

1. **Raph-proof** â€” Everything is GUI. No config files, no command line, no code.
2. **One executable** â€” Single .exe with all panels built in.
3. **D&D-native** â€” Not a generic stream tool. Built around characters, sessions, and encounters.
4. **Stream Deck as first-class** â€” Characters show their faces on the physical buttons. The deck layout matches what's on screen.
5. **OBS integration, not replacement** â€” We control OBS, we don't try to be OBS. Raph still sets up his scenes in OBS, we just switch between them.
6. **Graceful degradation** â€” Works without a Stream Deck (hotkeys). Works without OBS connected (just the puppet overlay). Each panel is independent.
