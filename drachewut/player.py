"""Player characters: stats, sprite animation, movement, and network state."""

from __future__ import annotations

import pygame

from .paths import asset

CLASSES = ("Mage", "Warrior", "Cleric", "Thief")

# Stats from the 2013 design sheet. Movement does not use them yet.
STATS = {
    "Mage":    dict(attack=12, defense=3, speed=100, range=8, color_key=(105, 74, 46)),
    "Warrior": dict(attack=9, defense=12, speed=80, range=4, color_key=(106, 76, 48)),
    "Cleric":  dict(attack=3, defense=8, speed=100, range=12, color_key=(106, 73, 48)),
    "Thief":   dict(attack=7, defense=8, speed=150, range=3, color_key=(106, 76, 48)),
}

# walkdir: 1 = north, then clockwise to 8 = north-west.
# Sprite-sheet row for each direction.
SHEET_ROW = {1: 6, 2: 5, 3: 7, 4: 2, 5: 3, 6: 1, 7: 0, 8: 4}
# (dx, dy) of the held arrow keys -> walkdir
DIRECTION = {(0, -1): 1, (1, -1): 2, (1, 0): 3, (1, 1): 4,
             (0, 1): 5, (-1, 1): 6, (-1, 0): 7, (-1, -1): 8}

FRAME_SIZE = 96
FRAME_TIME = 0.1
WALK_SPEED = 250.0      # pixels per second
RESPAWN_TIME = 2.0      # seconds the death animation stays on screen


def load_sheet(path: str, color_key, reverse=False) -> dict[int, list[pygame.Surface]]:
    """Cut an 8-direction sprite sheet into frames: {walkdir: [frame, ...]}."""
    sheet = pygame.image.load(path).convert()
    sheet.set_colorkey(color_key)
    count = sheet.get_width() // FRAME_SIZE
    order = range(count - 1, -1, -1) if reverse else range(count)
    frames = {}
    for walkdir, row in SHEET_ROW.items():
        frames[walkdir] = []
        for j in order:
            frame = pygame.Surface((FRAME_SIZE, FRAME_SIZE), pygame.SRCALPHA)
            frame.blit(sheet, (0, 0), (j * FRAME_SIZE, row * FRAME_SIZE, FRAME_SIZE, FRAME_SIZE))
            frames[walkdir].append(frame)
    return frames


_sheet_cache: dict[tuple[str, str], dict] = {}


def class_frames(pclass: str, kind: str) -> dict[int, list[pygame.Surface]]:
    """Walk ("Other") or "Death" frames for a class, loaded once per class."""
    key = (pclass, kind)
    if key not in _sheet_cache:
        # File names are lowercase; the 2013 code relied on Windows ignoring case.
        path = asset("sprites", f"{pclass.lower()}{kind}.png")
        _sheet_cache[key] = load_sheet(path, STATS[pclass]["color_key"], reverse=(kind == "Death"))
    return _sheet_cache[key]


class Player:
    def __init__(self, uname: str, pclass: str = "Cleric", load_sprites: bool = True):
        self.uname = uname
        self.Pname = uname
        self.Pclass = pclass if pclass in STATS else "Cleric"
        self.load_sprites = load_sprites
        self.posX, self.posY = 768.0, 640.0
        self.walkdir = 5
        self.p_state = 0          # 0 standing, 1 walking
        self.move = (0, 0)
        self.speed_factor = 1.0   # slow tiles lower this
        self.max_health = 100.0
        self.cur_health = 100.0
        self.dead_time = 0.0
        self.frame = 0
        self.frame_timer = 0.0
        self.exp = 0
        self._sent = {}
        self.frames = self.death_frames = None
        self._load()

    def _load(self):
        stats = STATS[self.Pclass]
        self.attack, self.defense = stats["attack"], stats["defense"]
        self.speed, self.Range = stats["speed"], stats["range"]
        if self.load_sprites:
            self.frames = class_frames(self.Pclass, "Other")
            self.death_frames = class_frames(self.Pclass, "Death")

    @property
    def level(self) -> int:
        return min(max(self.exp // 100, 1), 50)

    @property
    def dead(self) -> bool:
        return self.cur_health <= 0

    def __str__(self):
        return f"[Player.{self.uname}.({self.posX:.0f},{self.posY:.0f}).({self.walkdir})]"

    # -- simulation ----------------------------------------------------------

    def set_move(self, dx: int, dy: int):
        self.move = (dx, dy)
        if (dx, dy) != (0, 0):
            self.walkdir = DIRECTION[(dx, dy)]
            self.p_state = 1
        else:
            self.p_state = 0

    def hurt(self, amount: float):
        if not self.dead:
            self.cur_health = max(self.cur_health - amount, 0.0)
            if self.dead:
                self.dead_time = 0.0
                self.frame = 0
                self.p_state = 0

    def update(self, dT: float):
        if self.dead:
            self.dead_time += dT
            if self.death_frames:
                last = len(self.death_frames[self.walkdir]) - 1
                self.frame = min(int(self.dead_time / FRAME_TIME), last)
            return
        if self.p_state == 1:
            dx, dy = self.move
            norm = (dx * dx + dy * dy) ** 0.5 or 1.0
            step = WALK_SPEED * self.speed_factor * dT / norm
            self.posX += dx * step
            self.posY += dy * step
            self.frame_timer += dT
            while self.frame_timer >= FRAME_TIME:
                self.frame_timer -= FRAME_TIME
                self.frame = (self.frame + 1) % 8
        else:
            self.frame = 0
            self.frame_timer = 0.0

    def respawn_due(self) -> bool:
        return self.dead and self.dead_time >= RESPAWN_TIME

    def respawn(self, x: float, y: float):
        self.posX, self.posY = x, y
        self.cur_health = self.max_health
        self.frame = 0

    # -- drawing -------------------------------------------------------------

    def render(self, surf: pygame.Surface, camera):
        if not self.frames:
            return
        frames = self.death_frames if self.dead else self.frames
        image = frames[self.walkdir][self.frame % len(frames[self.walkdir])]
        x = self.posX - image.get_width() // 2 - camera[0]
        y = self.posY - image.get_height() // 2 - camera[1]
        surf.blit(image, (x, y))
        if self.dead:
            return
        # Health bar above the sprite
        bar = pygame.Rect(int(x) + 23, int(y), 50, 10)
        pygame.draw.rect(surf, (255, 255, 255), bar, 1)
        fill = bar.inflate(-2, -2)
        fill.width = int(fill.width * self.cur_health / self.max_health)
        if fill.width > 0:
            pygame.draw.rect(surf, (220, 0, 0), fill)

    # -- network serialization -----------------------------------------------

    def serialize(self, level: int, updateOldValues: bool = True) -> str:
        """Fields as "key=value" joined by ":".

        level 0: what changed since the last call (client <-> server updates).
        level 2: everything another client needs.
        level 3: what the server stores in its account file.
        """
        if level not in (0, 1, 2, 3):
            raise ValueError("Level must be 0-3")
        full = {
            "uname": self.uname,
            "x": str(int(self.posX)),
            "y": str(int(self.posY)),
            "PState": str(self.p_state),
            "direction": str(self.walkdir),
            "Pname": self.Pname,
            "Pclass": self.Pclass,
        }
        if level == 3:
            keys = ("uname", "x", "y", "Pname", "Pclass")
        elif level == 2:
            keys = tuple(full)
        else:
            # The 2013 version never sent x/y here, so other players never
            # saw anyone move.
            keys = tuple(k for k in ("x", "y", "PState", "direction", "Pclass")
                         if self._sent.get(k) != full[k])
        s = ":".join(f"{k}={full[k]}" for k in keys)
        if updateOldValues:
            self._sent = dict(full)
        return s

    def deserialize(self, s: str):
        for field in s.split(":"):
            if "=" not in field:
                continue
            key, value = field.split("=", 1)
            if key == "PState":
                self.p_state = int(value)
            elif key == "x":
                self.posX = float(value)
            elif key == "y":
                self.posY = float(value)
            elif key == "Pname":
                self.Pname = value
            elif key == "Pclass":
                if value in STATS and value != self.Pclass:
                    self.Pclass = value
                    self._load()
            elif key == "direction":
                if value.isdigit() and int(value) in SHEET_ROW:
                    self.walkdir = int(value)
            elif key in ("uname", "pass", "class"):
                pass
            else:
                raise ValueError(f"Undefined deserialize key ({key!r})")
