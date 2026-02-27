"""
SRD 5.1 monster stat blocks for the bestiary autocomplete.

Only stores name, default HP, AC, and DEX modifier (for initiative).
These are Open Game License content -- free to include.

Format: (name, hp, ac, dex_modifier, token_color)
Token colors are thematic defaults for auto-generated circular tokens.
"""

SRD_MONSTERS = [
    # -- Beasts & Animals --
    ("Bat", 1, 12, 2, "#554433"),
    ("Cat", 2, 12, 2, "#aa8855"),
    ("Giant Rat", 7, 12, 2, "#665544"),
    ("Wolf", 11, 13, 2, "#777777"),
    ("Dire Wolf", 37, 14, 2, "#555555"),
    ("Giant Spider", 26, 14, 3, "#2a2a2a"),
    ("Brown Bear", 34, 11, 0, "#8B4513"),
    ("Giant Eagle", 26, 13, 3, "#aa8844"),
    ("Warhorse", 19, 11, 1, "#886644"),
    ("Giant Scorpion", 52, 15, 1, "#664422"),
    ("Giant Constrictor Snake", 60, 12, 2, "#556b2f"),

    # -- Humanoid --
    ("Bandit", 11, 12, 1, "#886644"),
    ("Bandit Captain", 65, 15, 2, "#aa7744"),
    ("Berserker", 67, 13, 1, "#884422"),
    ("Commoner", 4, 10, 0, "#888888"),
    ("Cultist", 9, 12, 1, "#553366"),
    ("Cult Fanatic", 33, 13, 2, "#663377"),
    ("Guard", 11, 16, 1, "#4466aa"),
    ("Knight", 52, 18, 0, "#6688cc"),
    ("Mage", 40, 12, 2, "#4444aa"),
    ("Noble", 9, 15, 1, "#cc9944"),
    ("Priest", 27, 13, 0, "#ddaa44"),
    ("Scout", 16, 13, 2, "#558844"),
    ("Spy", 27, 12, 2, "#444444"),
    ("Thug", 32, 11, 0, "#664422"),
    ("Veteran", 58, 17, 1, "#557788"),
    ("Assassin", 78, 15, 3, "#222222"),
    ("Gladiator", 112, 16, 2, "#cc6644"),

    # -- Goblinoid --
    ("Goblin", 7, 15, 2, "#668844"),
    ("Goblin Boss", 21, 17, 2, "#558833"),
    ("Hobgoblin", 11, 18, 1, "#884422"),
    ("Hobgoblin Captain", 39, 17, 2, "#773311"),
    ("Bugbear", 27, 16, 2, "#885533"),
    ("Bugbear Chief", 65, 17, 2, "#774422"),

    # -- Orc --
    ("Orc", 15, 13, 1, "#556644"),
    ("Orc War Chief", 93, 16, 1, "#445533"),
    ("Orog", 42, 18, 1, "#334422"),

    # -- Undead --
    ("Skeleton", 13, 13, 2, "#d4c5a9"),
    ("Zombie", 22, 8, -2, "#556b2f"),
    ("Ghoul", 22, 12, 2, "#667766"),
    ("Ghast", 36, 13, 3, "#778877"),
    ("Shadow", 16, 12, 2, "#333344"),
    ("Specter", 22, 12, 2, "#aabbcc"),
    ("Wight", 45, 14, 2, "#889988"),
    ("Wraith", 67, 13, 3, "#334455"),
    ("Mummy", 58, 11, -1, "#c4a35a"),
    ("Vampire Spawn", 82, 15, 3, "#882222"),

    # -- Fiend --
    ("Imp", 10, 13, 3, "#993333"),
    ("Quasit", 7, 13, 3, "#994444"),
    ("Hell Hound", 45, 15, 1, "#cc3311"),

    # -- Aberration --
    ("Gibbering Mouther", 67, 9, -1, "#8a7a6a"),

    # -- Construct --
    ("Animated Armor", 33, 18, 0, "#888899"),
    ("Flying Sword", 17, 17, 2, "#9999aa"),

    # -- Dragon & Dragonkin --
    ("Kobold", 5, 12, 2, "#cc6644"),
    ("Pseudodragon", 7, 13, 2, "#cc8844"),
    ("Young White Dragon", 133, 17, 0, "#ccddee"),
    ("Young Black Dragon", 127, 18, 2, "#333333"),
    ("Young Green Dragon", 136, 18, 1, "#448844"),
    ("Young Blue Dragon", 152, 18, 0, "#4466cc"),
    ("Young Red Dragon", 178, 18, 0, "#cc2222"),
    ("Adult White Dragon", 200, 18, 0, "#ddeeff"),
    ("Adult Black Dragon", 195, 19, 2, "#222222"),
    ("Adult Green Dragon", 207, 19, 1, "#336633"),
    ("Adult Blue Dragon", 225, 19, 0, "#3355bb"),
    ("Adult Red Dragon", 256, 19, 0, "#aa1111"),

    # -- Giant --
    ("Ogre", 59, 11, -1, "#7a6a4f"),
    ("Half-Ogre", 30, 12, 0, "#6a5a3f"),
    ("Troll", 84, 15, 1, "#556B2F"),
    ("Hill Giant", 105, 13, -1, "#8a7a55"),
    ("Stone Giant", 126, 17, 2, "#888888"),
    ("Frost Giant", 138, 15, -1, "#6688aa"),
    ("Fire Giant", 162, 18, -1, "#cc4422"),

    # -- Monstrosity --
    ("Mimic", 58, 12, 1, "#8B7355"),
    ("Owlbear", 59, 13, 1, "#8B6914"),
    ("Basilisk", 52, 15, -1, "#556644"),
    ("Manticore", 68, 14, 3, "#aa6644"),
    ("Griffon", 59, 12, 2, "#cc9944"),
    ("Hydra", 172, 15, 1, "#446644"),
    ("Wyvern", 110, 13, 0, "#556655"),

    # -- Ooze --
    ("Gelatinous Cube", 84, 6, -4, "#aaddaa"),
    ("Gray Ooze", 22, 8, -2, "#888888"),
    ("Ochre Jelly", 45, 8, -2, "#cc9933"),
    ("Black Pudding", 85, 7, -3, "#222222"),

    # -- Elemental --
    ("Fire Elemental", 102, 13, 3, "#ff6622"),
    ("Water Elemental", 114, 14, 2, "#3366aa"),
    ("Air Elemental", 90, 15, 4, "#aaccdd"),
    ("Earth Elemental", 126, 17, -1, "#886633"),
]
