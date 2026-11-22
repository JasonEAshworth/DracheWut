# Source art

Art from the 2012-2013 project that the game does not load yet. The files the game uses are in
`drachewut/assets/`.

| Folder | Contents | Source |
| --- | --- | --- |
| `class-sprites/` | Attack sheets for the four classes, and `vlad/` walking frames | Reiner's Tilesets |
| `monsters/` | Walk, attack, and death sheets for about 50 monsters | Reiner's Tilesets |
| `concept/` | Zone concept paintings | The ETGG 1802 team |
| `environment/` | Trees, bushes, houses, troughs, and overlay tests | Mixed; not recorded |
| `tilesets/` | Larger tileset versions, tile configs, and `tiles.zip` (PSD sources) | The ETGG 1802 team |
| `sound/` | Class ability and monster sounds (WAV) | Not recorded |

Sprite sheets are 8 rows (one per direction) of 96 x 96 frames; death sheets for some
monsters use 128 x 128. See `drachewut/player.py` for the row order.

Several monster names shared one sprite sheet in 2013. The copies were removed in 2026; these
names map to the kept sheet:

| Name in 2013 | Sheet now |
| --- | --- |
| greenSpider | beetle |
| dragonF | furyclaw |
| mole128 (Attack, Death) | rat |
| orc128 / orc96Walking | ogre |
| pigRun | pigWalk |
| wolfMove | wolfWalk |
