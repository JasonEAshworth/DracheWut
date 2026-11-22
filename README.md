# Drache Wut

A top-down multiplayer dungeon crawler made with Python and pygame in 2012-2013 as a team project
for ETGG 1802. It was inspired by Realm of the Mad God. It was never finished, but you can play
it: pick a class and explore the world through its portals, alone or with friends over a LAN.

**Play in the browser:** https://jasoneashworth.github.io/DracheWut/ (single player)

## What works

- Title, login, and account screens, plus a **Play** button for single-player with a class
  choice: Mage, Cleric, Thief, or Warrior.
- 23 tile maps. From the hub, portals lead to the forest, glacier, sea, wasteland, Doom's Path,
  and the zones behind them. Lava tiles close the volcano portal in the hub, as in the original
  map.
- Walls block movement. Damage tiles hurt; at zero health the character falls and respawns.
- Multiplayer over UDP: accounts, login, shared positions, and chat.
- A map editor for the `.map` files.

Not done, as in 2013: enemies, combat, abilities, inventory, and sound. The map files already
list enemies and spawn points, and the monster sprites are in `art/monsters/`.

## Run it

You need Python 3.10 or later.

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -e .
drache-wut                      # or: python -m drachewut
```

Controls: arrow keys move, Enter opens and sends chat, Esc goes back to the title (and quits
from the title).

### Multiplayer

```bash
drache-wut server               # UDP port 50000; add --no-window to run without the status window
```

In each client, choose **New User** (pick a class) or **Login**, then enter the server address.
Leave the address empty to use this computer. The server keeps accounts in `accounts.dat` in
its working folder. Passwords are stored as plain text, so do not reuse a real one.

### Browser build

```bash
pip install pygbag
python tools/build_web.py           # writes build/web/
python tools/build_web.py --serve   # builds and serves on http://localhost:8000
```

The browser build is single-player: browsers have no UDP sockets. If you serve `build/web/`
with another web server, open it at `127.0.0.1`, not `localhost`. pygbag treats `localhost` as
its own development server and looks for its files there.

`.github/workflows/deploy.yml` runs the tests on Linux and publishes the browser build to GitHub
Pages on every push to `master`.

### Tests

```bash
python -m unittest discover -s tests
```

## Project layout

```
drachewut/              the game
  client.py             screens, game loop, server messages
  server.py             accounts and relaying state between players
  world.py              maps, collision, portals
  player.py             classes, sprites, movement, network state
  gui.py                buttons, labels, text entry, chat log
  connection.py         non-blocking UDP messages
  assets/               fonts, GUI art, sprites, tiles, maps
web/main.py             browser entry point
tools/build_web.py      builds the browser version
tools/map_editor.py     map editor (python tools/map_editor.py)
tools/layer2sheet2.jsx  Photoshop script that turns frame layers into a sprite sheet
art/                    source art the game does not load yet
docs/                   2013 design documents and the map file format
```

## Credits and license

The code is [MIT licensed](LICENSE). The art, sound, and font are not covered by the MIT license.

- Title screen, GUI, tiles, and concept art: the 2012-2013 ETGG 1802 team.
- Character and monster sprites: [Reiner's Tilesets](https://www.reinerstilesets.de/). The
  readme inside the original sprite archive is signed by Reiner. Check his terms before reusing
  them.
- Sounds: source not recorded. The game does not play them.
- Font: BlackCastle; source not recorded.

An earlier version of this README said the art came from Realm of the Mad God. It did not;
that game was only the inspiration.
