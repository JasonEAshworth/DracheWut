# Python Pygame Game

An unfinished multiplayer top-down dungeon crawler built in Python 2.7 with Pygame, inspired
by Realm of the Mad God. A personal project that is partially playable.

## What's implemented

- **Client** (`trunk/main_client_app.py`): login / account-creation UI, arrow-key movement, a
  camera that follows the player across the world, and in-game chat
- **World and maps** (`world.py`): tile-based level loading with collision (blocking, damage,
  slow, and warp tiles), camera culling, and overlays
- **Map editor** (`Map_Editor/`): create, load, and save tile maps with a palette and grid
- **Player:** 8-directional sprite animation, health / experience / leveling, and a
  ranged-attack framework
- **Networking** (`networking_start/`): a UDP client/server handshake, login/auth, heartbeat
  pings, and player-state serialization

## What's incomplete

The server app is largely stubbed, enemy AI / combat and bullet damage are only partly wired
up, sound is unused, and some asset paths are broken. The entry point is
`trunk/main_client_app.py`, which runs with default test credentials and needs no server.

## Run

Requires Python 2.7 and Pygame (it predates Python 3).

## License

My original game code is [MIT licensed](LICENSE). The **art and sound assets are from Realm
of the Mad God** (the sprite names match its creatures and classes); they are copyright their
respective owners, are NOT covered by the MIT license, and should not be reused or
redistributed.
