"""Tile maps: loading, drawing, collision, and warps between zones."""

from __future__ import annotations

import configparser
from dataclasses import dataclass

import pygame

from .paths import asset

TILE_SIZE = 64

# Tile effects, from the flags in master.con.
NONE = 0
BLOCK = 1
WARP = 2
DAMAGE = 3
SLOW = 4

START_MAP = "hub.map"


class TileDbase:
    """Tile codes (a00, b30, ...) mapped to their tileset cell and flags."""

    def __init__(self, path: str = asset("tiles", "master.con")):
        config = configparser.ConfigParser()
        if not config.read(path):
            raise FileNotFoundError(path)
        self.cells: dict[str, tuple[int, int]] = {}
        self.effects: dict[str, int] = {}
        for code in config.sections():
            section = config[code]
            if "tile" in section:
                x, y = (int(v) for v in section["tile"].split(","))
                self.cells[code] = (x, y)
            # getboolean, not a truthiness test: "block = False" is a
            # non-empty string, so the 2013 check made the damage tile a wall.
            if section.getboolean("block", False):
                self.effects[code] = BLOCK
            elif section.getboolean("warp", False):
                self.effects[code] = WARP
            elif section.getboolean("damage", False):
                self.effects[code] = DAMAGE
            elif section.getboolean("slow", False):
                self.effects[code] = SLOW

    def effect(self, code: str | None) -> int:
        # Off the map, or a code the tileset does not define: treat as a wall.
        if code is None or code not in self.cells:
            return BLOCK
        return self.effects.get(code, NONE)


@dataclass
class Warp:
    row: int
    col: int
    target: str
    dest: tuple[int, int] | None  # pixel position in the target map


def _lines(conf: configparser.SectionProxy, key: str) -> list[str]:
    return [line.strip() for line in conf.get(key, "").split("\n") if line.strip()]


class GameMap:
    """One .map file: a grid of 3-character tile codes plus warps and spawns."""

    def __init__(self, name: str):
        self.name = name
        conf = configparser.ConfigParser()
        if not conf.read(asset("maps", name)):
            raise FileNotFoundError(f"map {name!r} not found")
        level = conf["level"]

        # Tile rows are plain alphanumeric codes; stop at anything else.
        rows = []
        for r in (r.strip() for r in level["map"].split("\n")):
            if not r:
                continue
            if not r.isalnum():
                break
            rows.append(r)
        width = max(len(r) // 3 for r in rows)
        self.grid = []
        for r in rows:
            codes = [r[i:i + 3] for i in range(0, len(r) - 2, 3)]
            # A few maps have a row one tile short; repeat its last tile.
            codes += [codes[-1]] * (width - len(codes))
            self.grid.append(codes)
        self.cols = width
        self.rows = len(self.grid)
        self.pixel_width = self.cols * TILE_SIZE
        self.pixel_height = self.rows * TILE_SIZE

        pos = _lines(level, "pos")
        self.start = tuple(int(v) for v in pos[-1].split(":")[:2]) if pos else None

        # Warp lines are row:col:target[:destX:destY], as the map-editor notes
        # describe. The 2013 loader read them as col:row and ignored the
        # destination, so most portals never fired.
        self.warps: list[Warp] = []
        for line in _lines(level, "warps"):
            parts = line.split(":")
            dest = None
            if len(parts) >= 5 and parts[3] and parts[4]:
                dest = (int(parts[3]), int(parts[4]))
            self.warps.append(Warp(int(parts[0]), int(parts[1]), parts[2], dest))

        # Enemy data is not used yet; keep it for when spawning is written.
        self.enemies = [line.split(":") for line in _lines(level, "enemies")]
        self.spawns = [tuple(int(v) for v in line.split(":")[:2])
                       for line in _lines(level, "enemyspawn")]

    def code_at(self, x: float, y: float) -> str | None:
        col, row = int(x // TILE_SIZE), int(y // TILE_SIZE)
        if 0 <= row < self.rows and 0 <= col < self.cols:
            return self.grid[row][col]
        return None

    def warp_at(self, row: int, col: int) -> Warp | None:
        for w in self.warps:
            if (w.row, w.col) == (row, col):
                return w
        # Fallback for the few entries written in col:row order.
        for w in self.warps:
            if (w.col, w.row) == (row, col):
                return w
        return None

    def center(self) -> tuple[int, int]:
        return self.pixel_width // 2, self.pixel_height // 2


class Zone:
    """The map the player is in, plus the camera that follows them."""

    def __init__(self, map_name: str = START_MAP, view_size=(1280, 704),
                 tileset: str = "tilesetDay"):
        self.tiles = TileDbase()
        self.view_width, self.view_height = view_size
        self.tileset_name = tileset
        self._tile_images = None
        self.camera = [0.0, 0.0]
        self.map = GameMap(map_name)
        # A warp fires when the player steps onto a portal, not while they
        # stand on one. Arriving on the destination portal must not bounce
        # them straight back.
        self.warp_armed = False

    # -- loading -------------------------------------------------------------

    def _load_tiles(self):
        image = pygame.image.load(asset("tiles", self.tileset_name + ".png")).convert_alpha()
        w, h = image.get_size()
        return [[image.subsurface((x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE))
                 for y in range(h // TILE_SIZE)]
                for x in range(w // TILE_SIZE)]

    def enter(self, map_name: str, dest: tuple[int, int] | None = None) -> tuple[float, float]:
        """Load a map and return where the player arrives."""
        came_from = self.map.name
        self.map = GameMap(map_name)
        self.warp_armed = False
        back = next((w for w in self.map.warps if w.target == came_from), None)
        if dest:
            x, y = dest
        elif self.map.start:
            x, y = self.map.start
        elif back:
            x, y = self._tile_center(back.row, back.col)
        else:
            x, y = self.map.center()
        x = min(max(x, TILE_SIZE // 2), self.map.pixel_width - TILE_SIZE // 2)
        y = min(max(y, TILE_SIZE // 2), self.map.pixel_height - TILE_SIZE // 2)
        x, y = self._nearest_open(x, y)
        # A few destinations are sealed pockets with no way out. Arrive on
        # the portal back instead; the player can walk off it.
        if back and self.map.warps and not self._reaches_portal(x, y):
            x, y = self._tile_center(back.row, back.col)
        return x, y

    @staticmethod
    def _tile_center(row: int, col: int) -> tuple[float, float]:
        return float(col * TILE_SIZE + TILE_SIZE // 2), float(row * TILE_SIZE + TILE_SIZE // 2)

    def _reaches_portal(self, x: float, y: float) -> bool:
        m = self.map
        if self.tile_effect(x, y) == BLOCK:
            return False
        start = (int(y // TILE_SIZE), int(x // TILE_SIZE))
        seen, todo = {start}, [start]
        while todo:
            r, c = todo.pop()
            for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if (nr, nc) in seen or not (0 <= nr < m.rows and 0 <= nc < m.cols):
                    continue
                effect = self.tiles.effect(m.grid[nr][nc])
                if effect == WARP:
                    return True
                if effect != BLOCK:
                    seen.add((nr, nc))
                    todo.append((nr, nc))
        return False

    def _nearest_open(self, x: float, y: float) -> tuple[float, float]:
        """Move a point off a wall. Some warp destinations land inside one."""
        if self.tile_effect(x, y) != BLOCK:
            return float(x), float(y)
        m = self.map
        col0, row0 = int(x // TILE_SIZE), int(y // TILE_SIZE)
        for ring in range(1, 8):
            best = None
            for r in range(row0 - ring, row0 + ring + 1):
                for c in range(col0 - ring, col0 + ring + 1):
                    if max(abs(r - row0), abs(c - col0)) != ring:
                        continue
                    if not (0 <= r < m.rows and 0 <= c < m.cols):
                        continue
                    if self.tiles.effect(m.grid[r][c]) in (BLOCK, WARP):
                        continue
                    d = (r - row0) ** 2 + (c - col0) ** 2
                    if best is None or d < best[0]:
                        best = (d, r, c)
            if best:
                _, r, c = best
                return float(c * TILE_SIZE + TILE_SIZE // 2), float(r * TILE_SIZE + TILE_SIZE // 2)
        return float(x), float(y)

    def spawn_point(self) -> tuple[float, float]:
        x, y = self.map.start or self.map.center()
        return float(x), float(y)

    # -- camera and drawing --------------------------------------------------

    def follow(self, x: float, y: float):
        """Center the camera on a point, clamped to the map edges."""
        m = self.map
        cx = x - self.view_width / 2
        cy = y - self.view_height / 2
        cx = min(max(cx, 0), max(m.pixel_width - self.view_width, 0))
        cy = min(max(cy, 0), max(m.pixel_height - self.view_height, 0))
        # Maps smaller than the window are drawn centered.
        if m.pixel_width < self.view_width:
            cx = -(self.view_width - m.pixel_width) / 2
        if m.pixel_height < self.view_height:
            cy = -(self.view_height - m.pixel_height) / 2
        self.camera = [cx, cy]

    def render(self, surf: pygame.Surface):
        if self._tile_images is None:
            # Loaded once. The 2013 code re-read the tileset every frame.
            self._tile_images = self._load_tiles()
        m = self.map
        cx, cy = int(self.camera[0]), int(self.camera[1])
        first_col, first_row = max(cx // TILE_SIZE, 0), max(cy // TILE_SIZE, 0)
        last_col = min((cx + self.view_width) // TILE_SIZE + 1, m.cols)
        last_row = min((cy + self.view_height) // TILE_SIZE + 1, m.rows)
        for row in range(first_row, last_row):
            for col in range(first_col, last_col):
                cell = self.tiles.cells.get(m.grid[row][col])
                if cell is None:
                    continue
                surf.blit(self._tile_images[cell[0]][cell[1]],
                          (col * TILE_SIZE - cx, row * TILE_SIZE - cy))

    # -- movement ------------------------------------------------------------

    def collide(self, x: float, y: float, radius: float = 8.0) -> tuple[float, float]:
        """Push a circle out of any blocking tile around it."""
        m = self.map
        for _ in range(2):  # a second pass settles corners
            col, row = int(x // TILE_SIZE), int(y // TILE_SIZE)
            for r in range(row - 1, row + 2):
                for c in range(col - 1, col + 2):
                    code = m.grid[r][c] if 0 <= r < m.rows and 0 <= c < m.cols else None
                    if self.tiles.effect(code) != BLOCK:
                        continue
                    left, top = c * TILE_SIZE, r * TILE_SIZE
                    nx = min(max(x, left), left + TILE_SIZE)
                    ny = min(max(y, top), top + TILE_SIZE)
                    dx, dy = x - nx, y - ny
                    dist2 = dx * dx + dy * dy
                    if dist2 >= radius * radius:
                        continue
                    if dist2 == 0:
                        # Center inside the tile: leave by the nearest edge.
                        exits = [(x - left, -1, 0), (left + TILE_SIZE - x, 1, 0),
                                 (y - top, 0, -1), (top + TILE_SIZE - y, 0, 1)]
                        d, ex, ey = min(exits)
                        x += ex * (d + radius)
                        y += ey * (d + radius)
                    else:
                        dist = dist2 ** 0.5
                        push = radius - dist
                        x += dx / dist * push
                        y += dy / dist * push
        return x, y

    def tile_effect(self, x: float, y: float) -> int:
        return self.tiles.effect(self.map.code_at(x, y))

    def check_warp(self, x: float, y: float) -> tuple[float, float] | None:
        """Return the arrival point if the player just stepped onto a portal."""
        on_portal = self.tile_effect(x, y) == WARP
        if not on_portal:
            self.warp_armed = True
            return None
        if not self.warp_armed:
            return None
        warp = self.map.warp_at(int(y // TILE_SIZE), int(x // TILE_SIZE))
        if warp is None:
            return None
        return self.enter(warp.target, warp.dest)
