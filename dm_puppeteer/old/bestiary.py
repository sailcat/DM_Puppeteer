"""
Bestiary Manager -- monster/NPC library with autocomplete search.

Combines SRD monsters with custom entries and usage history.
Powers the monster search field in the DM Combat tab.
"""

from typing import Optional

from .models import AppState, BestiaryEntry

try:
    from .srd_bestiary import SRD_MONSTERS
except ImportError:
    try:
        from srd_bestiary import SRD_MONSTERS
    except ImportError:
        SRD_MONSTERS = []


class BestiaryManager:
    """Manages the monster/NPC library for encounter building.

    Combines three sources:
    - SRD monsters (built-in, ~90 common D&D monsters)
    - Custom entries (user-created, persisted in state.json)
    - Usage history (tracks how often each monster is used)

    Search results are ranked by: exact prefix > fuzzy match,
    with frequently-used entries boosted to the top.
    """

    def __init__(self, state: AppState):
        self.state = state
        self._all_entries: list[BestiaryEntry] = []
        self._load()

    def _load(self):
        """Build the combined entry list from SRD + custom."""
        self._all_entries = []

        # Load SRD monsters
        for name, hp, ac, dex_mod, color in SRD_MONSTERS:
            entry = BestiaryEntry(
                name=name,
                hp_default=hp,
                ac=ac,
                initiative_modifier=dex_mod,
                token_color=color,
                source="srd",
            )
            self._all_entries.append(entry)

        # Merge custom entries (overwrite SRD if same name, add if new)
        srd_names_lower = {e.name.lower() for e in self._all_entries}
        for custom in self.state.bestiary:
            # Check if this overrides an SRD entry
            if custom.name.lower() in srd_names_lower:
                # Replace the SRD entry with the custom one
                for i, existing in enumerate(self._all_entries):
                    if existing.name.lower() == custom.name.lower():
                        # Preserve usage count from custom
                        self._all_entries[i] = custom
                        break
            else:
                self._all_entries.append(custom)

    def search(self, query: str, limit: int = 10) -> list[BestiaryEntry]:
        """Search the bestiary with ranked autocomplete.

        Ranking priority:
        1. Exact name match (case-insensitive)
        2. Name starts with query (prefix match)
        3. Query appears anywhere in name (substring match)

        Within each tier, results are sorted by:
        - times_used (descending) -- frequently used monsters first
        - alphabetical (ascending) -- tiebreaker
        """
        if not query or not query.strip():
            # No query -- return most recently used, then alphabetical
            sorted_all = sorted(
                self._all_entries,
                key=lambda e: (-e.times_used, e.name.lower()))
            return sorted_all[:limit]

        query_lower = query.strip().lower()
        exact = []
        prefix = []
        substring = []

        for entry in self._all_entries:
            name_lower = entry.name.lower()
            if name_lower == query_lower:
                exact.append(entry)
            elif name_lower.startswith(query_lower):
                prefix.append(entry)
            elif query_lower in name_lower:
                substring.append(entry)

        # Sort each tier by usage count then name
        sort_key = lambda e: (-e.times_used, e.name.lower())
        exact.sort(key=sort_key)
        prefix.sort(key=sort_key)
        substring.sort(key=sort_key)

        results = exact + prefix + substring
        return results[:limit]

    def get_entry(self, name: str) -> Optional[BestiaryEntry]:
        """Get a specific entry by exact name (case-insensitive)."""
        name_lower = name.lower()
        for entry in self._all_entries:
            if entry.name.lower() == name_lower:
                return entry
        return None

    def add_custom(self, entry: BestiaryEntry):
        """Add a new custom monster to the library and persist it."""
        entry.source = "custom"
        # Check if it already exists
        existing = self.get_entry(entry.name)
        if existing:
            # Update existing entry
            idx = self._all_entries.index(existing)
            self._all_entries[idx] = entry
            # Update in state.bestiary too
            for i, b in enumerate(self.state.bestiary):
                if b.name.lower() == entry.name.lower():
                    self.state.bestiary[i] = entry
                    return
        # New entry
        self._all_entries.append(entry)
        self.state.bestiary.append(entry)

    def remove_custom(self, name: str):
        """Remove a custom entry. SRD entries cannot be removed."""
        name_lower = name.lower()
        entry = self.get_entry(name)
        if not entry or entry.source == "srd":
            return
        self._all_entries = [
            e for e in self._all_entries if e.name.lower() != name_lower]
        self.state.bestiary = [
            e for e in self.state.bestiary if e.name.lower() != name_lower]

    def record_usage(self, name: str):
        """Bump usage count when a monster is added to combat.
        This makes frequently-used monsters appear higher in search results."""
        name_lower = name.lower()
        for entry in self._all_entries:
            if entry.name.lower() == name_lower:
                entry.times_used += 1
                # If it's an SRD entry that was used, save a custom copy
                # so the usage count persists across sessions
                if entry.source == "srd":
                    entry.source = "custom"
                    self.state.bestiary.append(entry)
                break

    def get_all_names(self) -> list[str]:
        """Return all monster names for QCompleter."""
        return sorted(set(e.name for e in self._all_entries))

    @property
    def entry_count(self) -> int:
        """Total number of entries (SRD + custom)."""
        return len(self._all_entries)

    @property
    def custom_count(self) -> int:
        """Number of custom entries only."""
        return len([e for e in self._all_entries if e.source == "custom"])
