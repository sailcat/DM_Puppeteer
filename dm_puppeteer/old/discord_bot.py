"""Discord Bot Bridge.

Runs a Discord bot in a background thread and bridges events
to the Qt main thread via signals. Monitors:
  - Voice state (who's speaking) for PC portraits
  - Avrae dice roll messages for stream overlays
  - Custom commands for DM tools
  - Voice receive for per-player audio (portrait speaking detection)
"""

import asyncio
import json
import re
import threading
import queue
from dataclasses import dataclass, field
from typing import Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

try:
    import discord
    from discord import Intents
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False

try:
    from .voice_receiver import VoiceReceiveSink, VOICE_RECEIVE_AVAILABLE
except ImportError:
    try:
        from voice_receiver import VoiceReceiveSink, VOICE_RECEIVE_AVAILABLE
    except ImportError:
        VOICE_RECEIVE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Event data classes
# ---------------------------------------------------------------------------

@dataclass
class VoiceStateEvent:
    """A user's voice state changed."""
    user_id: int
    username: str
    display_name: str
    is_speaking: bool = False
    is_muted: bool = False
    is_deafened: bool = False
    joined: bool = False
    left: bool = False


@dataclass
class DiceRollEvent:
    """A dice roll was detected from Avrae / D&D Beyond."""
    character_name: str = ""
    check_type: str = ""       # "Deception check", "Attack", "Saving Throw"
    roll_formula: str = ""     # "1d20 (13) + 6"
    natural_roll: int = 0      # the d20 result (the one that COUNTS)
    total: int = 0
    is_critical: bool = False  # nat 20
    is_fumble: bool = False    # nat 1
    campaign_name: str = ""
    raw_text: str = ""

    # Advantage / disadvantage (Brief 005) -- parser deferred to 005-B
    is_advantage: bool = False
    is_disadvantage: bool = False
    secondary_roll: int = 0    # the d20 result that was DROPPED
    die_type: str = "d20"      # "d20", "d6", etc. -- for future damage dice


@dataclass
class CommandEvent:
    """A custom command was issued in Discord."""
    command: str = ""
    args: list = field(default_factory=list)
    user: str = ""
    channel: str = ""


# ---------------------------------------------------------------------------
# Avrae Message Parser
# ---------------------------------------------------------------------------

class AvraeParser:
    """Parse Avrae bot messages and D&D Beyond roll messages.

    Handles two real Avrae formats:

    Format 1 -- Bare rolls (!r d20, !r 1d20+5):
        Plain text, no embeds.
        '<@USER_ID>  :game_die:\\n**Result**: 1d20 (15) + 5\\n**Total**: 20'

    Format 2 -- Character-linked rolls (!check dex, !save wis, !attack):
        Embed, no content.
        title:       'Human Fighter makes a Dexterity check!'
        description: '1d20 (16) + 1 = `17`'
        footer.text: 'Rolled in Campaign Name'
    """

    AVRAE_BOT_ID = 261302296103747584

    CHECK_PATTERN = re.compile(
        r'^(.+?)\s+makes?\s+(?:a |an )?(.+?)!?\s*$', re.IGNORECASE)
    ATTACK_PATTERN = re.compile(
        r'^(.+?)\s+attacks?\s+with\s+(?:a |an |their )?(.+?)!?\s*$', re.IGNORECASE)
    ROLL_WITH_TOTAL = re.compile(
        r'(\d+d\d+)\s*\((\d+)\)\s*(.*?)\s*=\s*`?(\d+)`?', re.IGNORECASE)
    ROLL_DICE_ONLY = re.compile(
        r'(\d+d\d+)\s*\((\d+)\)', re.IGNORECASE)
    ROLL_ARROW = re.compile(
        r'(\d*d\d+)\w*\s*\(\*\*\d+\s*->\s*(\d+)\*\*\)', re.IGNORECASE)
    RESULT_LINE = re.compile(
        r'\*\*Result\*\*:\s*(.+)', re.IGNORECASE)
    TOTAL_LINE = re.compile(
        r'\*\*Total\*\*:\s*`?(\d+)`?', re.IGNORECASE)
    CAMPAIGN_PATTERN = re.compile(
        r'Rolled\s+in\s+(.+)', re.IGNORECASE)

    @classmethod
    def parse_message(cls, content: str, embeds: list = None,
                      author_name: str = "") -> Optional[DiceRollEvent]:
        if embeds:
            for embed in embeds:
                event = cls._parse_embed(embed)
                if event:
                    return event
        event = cls._parse_text(content, author_name)
        return event if event else None

    @classmethod
    def _parse_text(cls, text: str, author_name: str = "") -> Optional[DiceRollEvent]:
        if not text or len(text) < 10:
            return None
        event = DiceRollEvent(raw_text=text)
        result_match = cls.RESULT_LINE.search(text)
        if not result_match:
            return None
        result_formula = result_match.group(1).strip()
        event.roll_formula = result_formula
        dice_match = cls.ROLL_DICE_ONLY.search(result_formula)
        die_type = ""
        if dice_match:
            event.natural_roll = int(dice_match.group(2))
            die_type = dice_match.group(1).lower()
        else:
            arrow_match = cls.ROLL_ARROW.search(result_formula)
            if arrow_match:
                event.natural_roll = int(arrow_match.group(2))
                die_type = arrow_match.group(1).lower()
                if die_type and not die_type[0].isdigit():
                    die_type = "1" + die_type
        total_match = cls.TOTAL_LINE.search(text)
        if total_match:
            event.total = int(total_match.group(1))
        elif event.natural_roll > 0:
            event.total = event.natural_roll
        if event.total <= 0:
            return None
        if die_type in ('1d20', 'd20') and event.natural_roll > 0:
            event.is_critical = event.natural_roll == 20
            event.is_fumble = event.natural_roll == 1
        event.character_name = author_name or "Unknown"
        event.check_type = "Dice Roll"
        return event

    @classmethod
    def _parse_embed(cls, embed) -> Optional[DiceRollEvent]:
        event = DiceRollEvent()
        title = ""
        if hasattr(embed, 'title') and embed.title:
            title = embed.title
        if title:
            check_match = cls.CHECK_PATTERN.match(title)
            attack_match = cls.ATTACK_PATTERN.match(title)
            if check_match:
                event.character_name = check_match.group(1).strip()
                event.check_type = check_match.group(2).strip()
            elif attack_match:
                event.character_name = attack_match.group(1).strip()
                event.check_type = f"Attack: {attack_match.group(2).strip()}"
            else:
                event.check_type = title
        if not event.character_name:
            if hasattr(embed, 'author') and embed.author:
                name = getattr(embed.author, 'name', None)
                if name:
                    event.character_name = name
        desc = ""
        if hasattr(embed, 'description') and embed.description:
            desc = embed.description
            event.raw_text = desc
        roll_match = cls.ROLL_WITH_TOTAL.search(desc)
        if roll_match:
            event.roll_formula = desc.replace('`', '').replace('**', '').strip()
            event.natural_roll = int(roll_match.group(2))
            event.total = int(roll_match.group(4))
        else:
            dice_match = cls.ROLL_DICE_ONLY.search(desc)
            if dice_match:
                event.roll_formula = desc.replace('`', '').replace('**', '').strip()
                event.natural_roll = int(dice_match.group(2))
        if hasattr(embed, 'fields'):
            for f in embed.fields:
                name = (f.name or "").lower()
                val = f.value or ""
                if "total" in name or "result" in name:
                    num_match = re.search(r'`?(\d+)`?', val)
                    if num_match:
                        event.total = int(num_match.group(1))
        if hasattr(embed, 'footer') and embed.footer:
            footer_text = getattr(embed.footer, 'text', None)
            if footer_text:
                camp_match = cls.CAMPAIGN_PATTERN.match(footer_text)
                if camp_match:
                    event.campaign_name = camp_match.group(1).strip()
        if event.natural_roll > 0:
            d20_check = cls.ROLL_DICE_ONLY.search(desc)
            if d20_check and d20_check.group(1).lower() in ('1d20', 'd20'):
                event.is_critical = event.natural_roll == 20
                event.is_fumble = event.natural_roll == 1
        if event.total > 0:
            if not event.character_name:
                event.character_name = "Unknown"
            return event
        return None


# ---------------------------------------------------------------------------
# Discord Bot (runs in background thread)
# ---------------------------------------------------------------------------

class _DiscordBotRunner:
    """Internal bot runner that executes in a background thread."""

    def __init__(self, token: str, event_queue: queue.Queue,
                 roll_channel_id: int = 0, guild_id: int = 0):
        self.token = token
        self.event_queue = event_queue
        self.roll_channel_id = roll_channel_id
        self.guild_id = guild_id
        self.loop = None
        self.client = None
        self._running = False

        # Voice receive state
        self._voice_client = None
        self._voice_sink = None
        self._player_map: Dict[int, int] = {}  # discord_user_id -> slot_index

        # Command queue -- main thread sends commands to bot thread
        self._command_queue: queue.Queue = queue.Queue()

    def run(self):
        """Run the bot (called from background thread)."""
        if not DISCORD_AVAILABLE:
            self.event_queue.put(("error", "discord.py not installed"))
            return

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        intents = Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True
        intents.members = True

        self.client = discord.Client(intents=intents)
        self._setup_handlers()

        try:
            self.loop.run_until_complete(self.client.start(self.token))
        except discord.LoginFailure:
            self.event_queue.put(("error", "Invalid bot token"))
        except Exception as e:
            self.event_queue.put(("error", str(e)))
        finally:
            self._running = False

    def stop(self):
        """Request the bot to stop."""
        self._running = False
        if self.client and self.loop:
            # Clean up voice connection first
            try:
                if self._voice_client:
                    future = asyncio.run_coroutine_threadsafe(
                        self._disconnect_voice(), self.loop)
                    future.result(timeout=2)
            except Exception:
                pass
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self.client.close(), self.loop)
                future.result(timeout=3)
            except Exception:
                pass
            try:
                self.loop.call_soon_threadsafe(self.loop.stop)
            except Exception:
                pass

    def _setup_handlers(self):
        client = self.client

        @client.event
        async def on_ready():
            self._running = True
            guild_count = len(client.guilds)
            guild_names = [g.name for g in client.guilds]
            self.event_queue.put(("connected", {
                "bot_name": client.user.name,
                "guild_count": guild_count,
                "guilds": guild_names,
            }))
            # Start background task to process commands from the main thread
            client.loop.create_task(self._command_loop())

        @client.event
        async def on_message(message):
            if message.author == client.user:
                return
            if self.roll_channel_id and message.channel.id == self.roll_channel_id:
                self._handle_roll_message(message)
            elif message.author.bot and message.author.id == AvraeParser.AVRAE_BOT_ID:
                self._handle_roll_message(message)
            if message.content.startswith("!pm "):
                parts = message.content[4:].strip().split()
                if parts:
                    cmd_event = CommandEvent(
                        command=parts[0],
                        args=parts[1:],
                        user=message.author.display_name,
                        channel=message.channel.name,
                    )
                    self.event_queue.put(("command", cmd_event))

        @client.event
        async def on_voice_state_update(member, before, after):
            if before.channel is None and after.channel is not None:
                evt = VoiceStateEvent(
                    user_id=member.id, username=member.name,
                    display_name=member.display_name, joined=True,
                    is_muted=after.self_mute or after.mute,
                    is_deafened=after.self_deaf or after.deaf)
                self.event_queue.put(("voice_state", evt))
            elif before.channel is not None and after.channel is None:
                evt = VoiceStateEvent(
                    user_id=member.id, username=member.name,
                    display_name=member.display_name, left=True)
                self.event_queue.put(("voice_state", evt))
            elif before.channel is not None and after.channel is not None:
                evt = VoiceStateEvent(
                    user_id=member.id, username=member.name,
                    display_name=member.display_name,
                    is_muted=after.self_mute or after.mute,
                    is_deafened=after.self_deaf or after.deaf)
                self.event_queue.put(("voice_state", evt))

    def _handle_roll_message(self, message):
        """Parse a potential dice roll message."""
        content = message.content or ""
        embeds = message.embeds if message.embeds else []
        author_name = ""
        if message.mentions:
            author_name = message.mentions[0].display_name
        elif not message.author.bot:
            author_name = message.author.display_name

        # --- DEBUG: dump raw message structure to file ---
        try:
            from pathlib import Path
            from datetime import datetime
            debug_dir = Path(__file__).parent.parent / "data"
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_file = debug_dir / "avrae_debug.txt"
            with open(debug_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"TIMESTAMP: {datetime.now().isoformat()}\n")
                f.write(f"AUTHOR: {message.author} (ID: {message.author.id}, bot={message.author.bot})\n")
                f.write(f"CHANNEL: {message.channel.name} (ID: {message.channel.id})\n")
                f.write(f"CONTENT: {repr(content)}\n")
                f.write(f"EMBED COUNT: {len(embeds)}\n")
                f.write(f"MENTIONS: {[(m.display_name, m.id) for m in message.mentions]}\n")
                for i, embed in enumerate(embeds):
                    f.write(f"\n--- EMBED {i} ---\n")
                    f.write(f"  title:       {repr(embed.title)}\n")
                    f.write(f"  description: {repr(embed.description)}\n")
                    f.write(f"  author:      {repr(embed.author)}\n")
                    if embed.author:
                        f.write(f"    author.name: {repr(embed.author.name)}\n")
                    f.write(f"  footer:      {repr(embed.footer)}\n")
                    if embed.footer:
                        f.write(f"    footer.text: {repr(embed.footer.text)}\n")
                    f.write(f"  fields ({len(embed.fields)}):\n")
                    for fi, field in enumerate(embed.fields):
                        f.write(f"    [{fi}] name={repr(field.name)} value={repr(field.value)} inline={field.inline}\n")
                    f.write(f"  color:       {repr(embed.color)}\n")
                    f.write(f"  url:         {repr(embed.url)}\n")
                f.write(f"\nPARSE RESULT: ")
                test_event = AvraeParser.parse_message(content, embeds, author_name)
                f.write(f"{test_event}\n" if test_event else "None (parser returned nothing)\n")
                f.write(f"{'='*60}\n")
        except Exception as e:
            print(f"[DEBUG] Failed to write debug log: {e}")
        # --- END DEBUG ---

        event = AvraeParser.parse_message(content, embeds, author_name)
        if event:
            self.event_queue.put(("dice_roll", event))

    # ------------------------------------------------------------------
    # Voice receive -- join/leave/manage
    # ------------------------------------------------------------------

    async def join_voice_channel(self, channel_id: int, player_map: Dict[int, int]):
        """Join a voice channel and start receiving per-user audio."""
        if not VOICE_RECEIVE_AVAILABLE:
            self.event_queue.put(("error",
                "Voice receive not available.\nInstall: pip install py-cord[voice]"))
            return

        # Disconnect existing (without emitting spurious event)
        await self._disconnect_voice()

        channel = self.client.get_channel(channel_id)
        if channel is None:
            self.event_queue.put(("error", f"Voice channel {channel_id} not found"))
            return

        self._player_map = player_map.copy()

        def on_audio_processed(slot_index: int, rms: float, vowel: str,
                               threshold: float):
            self.event_queue.put(("player_audio", (slot_index, rms, vowel, threshold)))

        try:
            # Create sink and register players
            self._voice_sink = VoiceReceiveSink(on_audio_processed)
            for user_id, slot_data in self._player_map.items():
                if isinstance(slot_data, tuple):
                    slot_idx, multiplier = slot_data
                else:
                    slot_idx, multiplier = slot_data, 2.5
                self._voice_sink.register_player(
                    user_id, slot_idx, adaptive_multiplier=multiplier)

            # -- DIAGNOSTIC: log the full player map --
            print(f"[VOICE DIAG] Player map: {self._player_map}")
            print(f"[VOICE DIAG] Registered processor keys: "
                  f"{list(self._voice_sink.processors.keys())}")
            print(f"[VOICE DIAG] Processor key types: "
                  f"{[type(k).__name__ for k in self._voice_sink.processors.keys()]}")

            # Connect to voice channel
            self._voice_client = await channel.connect()
            vc = self._voice_client

            # Wait for voice handshake to settle
            await asyncio.sleep(2)

            # py-cord workaround: _connected threading.Event may not get set
            # even though the voice WebSocket is fully established. Force it
            # when we can verify the connection infrastructure is present.
            if hasattr(vc, '_connected') and hasattr(vc._connected, 'set'):
                vc._connected.set()

            # Start recording with retry (connection may still be settling)
            async def on_recording_finished(sink, *args):
                pass

            recording_started = False
            for attempt in range(50):  # up to 5 seconds
                # Re-force _connected on each attempt
                if hasattr(vc, '_connected') and hasattr(vc._connected, 'set'):
                    vc._connected.set()
                try:
                    vc.start_recording(
                        self._voice_sink,
                        on_recording_finished,
                        channel,
                    )
                    recording_started = True
                    break
                except Exception:
                    if attempt < 49:
                        await asyncio.sleep(0.1)

            if not recording_started:
                self.event_queue.put(("error", "Could not start voice recording"))
                await self._disconnect_voice()
                return

            # Report success
            member_names = [m.display_name for m in channel.members
                           if m.id != self.client.user.id]
            self.event_queue.put(("voice_connected", {
                "channel_name": channel.name,
                "channel_id": channel.id,
                "members": member_names,
                "player_count": len(self._player_map),
            }))

        except Exception as e:
            self.event_queue.put(("error", f"Voice join failed: {e}"))
            self._voice_client = None
            self._voice_sink = None

    async def leave_voice_channel(self):
        """Disconnect from voice, stop receiving audio, and notify Qt."""
        was_connected = self._voice_client is not None
        await self._disconnect_voice()
        if was_connected:
            self.event_queue.put(("voice_disconnected", None))

    async def _disconnect_voice(self):
        """Internal: disconnect voice without emitting events."""
        # -- DIAGNOSTIC: force final dump --
        try:
            from .voice_diagnostics import diag
            diag.force_dump()
        except ImportError:
            try:
                from voice_diagnostics import diag
                diag.force_dump()
            except ImportError:
                pass

        if self._voice_client:
            try:
                if self._voice_client.recording:
                    self._voice_client.stop_recording()
            except Exception:
                pass
            try:
                await self._voice_client.disconnect()
            except Exception:
                pass
            self._voice_client = None

        if self._voice_sink:
            try:
                self._voice_sink.cleanup()
            except Exception:
                pass
            self._voice_sink = None

        self._player_map.clear()

    def update_player_map(self, player_map: Dict[int, int]):
        """Update Discord user -> slot mapping without reconnecting."""
        self._player_map = player_map.copy()
        if self._voice_sink:
            self._voice_sink.processors.clear()
            for user_id, slot_data in self._player_map.items():
                if isinstance(slot_data, tuple):
                    slot_idx, multiplier = slot_data
                else:
                    slot_idx, multiplier = slot_data, 2.5
                self._voice_sink.register_player(
                    user_id, slot_idx, adaptive_multiplier=multiplier)

    def get_voice_channels(self) -> list:
        """Get all voice channels the bot can see."""
        channels = []
        if not self.client:
            return channels
        for guild in self.client.guilds:
            for channel in guild.voice_channels:
                channels.append({
                    "id": channel.id,
                    "name": channel.name,
                    "guild": guild.name,
                    "member_count": len(channel.members),
                    "members": [
                        {"id": m.id, "name": m.display_name}
                        for m in channel.members
                        if m.id != self.client.user.id
                    ],
                })
        return channels

    async def _process_commands(self):
        """Process commands from the main thread."""
        while True:
            try:
                cmd, args = self._command_queue.get_nowait()
            except queue.Empty:
                break

            if cmd == "join_voice":
                await self.join_voice_channel(args["channel_id"], args["player_map"])
            elif cmd == "leave_voice":
                await self.leave_voice_channel()
            elif cmd == "update_player_map":
                self.update_player_map(args["player_map"])
            elif cmd == "get_voice_channels":
                channels = self.get_voice_channels()
                self.event_queue.put(("voice_channels", channels))

    async def _command_loop(self):
        """Background task that checks for commands from the main thread."""
        while self._running:
            await self._process_commands()
            await asyncio.sleep(0.1)


# ---------------------------------------------------------------------------
# Qt Bridge (main thread interface)
# ---------------------------------------------------------------------------

class DiscordBridge(QObject):
    """Bridges Discord bot events to the Qt main thread."""

    # Signals -- existing
    connection_changed = pyqtSignal(bool, str)    # connected, info
    dice_roll = pyqtSignal(object)                # DiceRollEvent
    voice_state = pyqtSignal(object)              # VoiceStateEvent
    command_received = pyqtSignal(object)          # CommandEvent
    error_occurred = pyqtSignal(str)

    # Signals -- voice receive
    player_audio_update = pyqtSignal(int, float, str, float)  # slot_index, rms, vowel, threshold
    voice_connected = pyqtSignal(dict)                  # channel info
    voice_disconnected = pyqtSignal()
    voice_channels_updated = pyqtSignal(list)           # list of channel dicts

    def __init__(self, parent=None):
        super().__init__(parent)
        self._event_queue = queue.Queue()
        self._bot_runner = None
        self._bot_thread = None
        self._connected = False
        self._voice_active = False

        # Poll queue every 50ms
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_events)

    @property
    def is_connected(self):
        return self._connected

    @property
    def is_voice_active(self):
        return self._voice_active

    def connect(self, token: str, roll_channel_id: int = 0, guild_id: int = 0):
        """Start the Discord bot in a background thread."""
        if not DISCORD_AVAILABLE:
            self.error_occurred.emit(
                "discord.py not installed.\n"
                "Run: pip install discord.py[voice]")
            self.connection_changed.emit(False, "Library not installed")
            return

        if self._connected:
            self.disconnect()

        self._event_queue = queue.Queue()
        self._bot_runner = _DiscordBotRunner(
            token=token,
            event_queue=self._event_queue,
            roll_channel_id=roll_channel_id,
            guild_id=guild_id,
        )

        self._bot_thread = threading.Thread(
            target=self._bot_runner.run,
            daemon=True,
            name="discord-bot"
        )
        self._bot_thread.start()
        self._poll_timer.start(50)
        self.connection_changed.emit(False, "Connecting...")

    def disconnect(self):
        """Stop the Discord bot."""
        self._poll_timer.stop()
        if self._bot_runner:
            self._bot_runner.stop()
            self._bot_runner = None
        if self._bot_thread and self._bot_thread.is_alive():
            self._bot_thread.join(timeout=3)
            if self._bot_thread.is_alive():
                print("Warning: Discord thread did not stop cleanly")
        self._bot_thread = None
        self._connected = False
        self._voice_active = False
        self.connection_changed.emit(False, "Disconnected")

    # ------------------------------------------------------------------
    # Voice receive control
    # ------------------------------------------------------------------

    def join_voice(self, channel_id: int, player_map: Dict[int, int]):
        """Request the bot to join a voice channel and start receiving audio."""
        if not self._connected or not self._bot_runner:
            self.error_occurred.emit("Connect to Discord first")
            return
        if not VOICE_RECEIVE_AVAILABLE:
            self.error_occurred.emit(
                "Voice receive not available.\n"
                "Install: pip install py-cord[voice]")
            return
        self._bot_runner._command_queue.put(
            ("join_voice", {"channel_id": channel_id, "player_map": player_map}))

    def leave_voice(self):
        """Request the bot to leave the voice channel."""
        if self._bot_runner:
            self._bot_runner._command_queue.put(("leave_voice", None))

    def update_player_map(self, player_map: Dict[int, int]):
        """Update Discord user -> slot mapping without reconnecting."""
        if self._bot_runner:
            self._bot_runner._command_queue.put(
                ("update_player_map", {"player_map": player_map}))

    def request_voice_channels(self):
        """Request the list of voice channels the bot can see."""
        if self._bot_runner:
            self._bot_runner._command_queue.put(("get_voice_channels", None))

    # ------------------------------------------------------------------
    # Event polling
    # ------------------------------------------------------------------

    def _poll_events(self):
        """Drain the event queue and emit signals (runs on main thread)."""
        while True:
            try:
                event_type, data = self._event_queue.get_nowait()
            except queue.Empty:
                break

            if event_type == "connected":
                self._connected = True
                info = data
                self.connection_changed.emit(
                    True,
                    f"{info['bot_name']} -- {info['guild_count']} server(s)")

            elif event_type == "dice_roll":
                self.dice_roll.emit(data)

            elif event_type == "voice_state":
                self.voice_state.emit(data)

            elif event_type == "command":
                self.command_received.emit(data)

            elif event_type == "player_audio":
                slot_index, rms, vowel, threshold = data
                self.player_audio_update.emit(slot_index, rms, vowel, threshold)

            elif event_type == "voice_connected":
                self._voice_active = True
                self.voice_connected.emit(data)

            elif event_type == "voice_disconnected":
                self._voice_active = False
                self.voice_disconnected.emit()

            elif event_type == "voice_channels":
                self.voice_channels_updated.emit(data)

            elif event_type == "error":
                self._connected = False
                self.error_occurred.emit(str(data))
                self.connection_changed.emit(False, f"Error: {data}")
