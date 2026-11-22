"""Screen-based GUI: image buttons, labels, text entries, and a chat log.

Original design by Rock G Bolton (ETGG 1802).
"""

from __future__ import annotations

import pygame

from .paths import asset

GREEN_KEY = (0, 255, 0)


def image(*parts: str) -> pygame.Surface:
    return pygame.image.load(asset("gui", *parts)).convert_alpha()


def stone_button(label: str, font: pygame.font.Font) -> tuple[pygame.Surface, ...]:
    """Three button states (normal, hover, pressed) in the style of the
    painted Login button, with a new label. The art has its text baked in,
    so the face is rebuilt from plain stone first."""
    states = []
    for n in (1, 2, 3):
        base = image("Login", f"button_login_{n}.png")
        w, h = base.get_size()
        face = base.copy()
        # Clean stone from the left of the face, mirrored and tiled across
        # where the old label was.
        strip = base.subsurface((10, 6, 12, h - 12)).copy()
        flipped = pygame.transform.flip(strip, True, False)
        x, flip = 22, False
        while x < w - 22:
            face.blit(flipped if flip else strip, (x, 6), (0, 0, min(12, w - 22 - x), h - 12))
            x += 12
            flip = not flip
        text = _gold_text(label, font)
        face.blit(text, ((w - text.get_width()) // 2, (h - text.get_height()) // 2 + (1 if n == 3 else 0)))
        states.append(face)
    return tuple(states)


def _gold_text(label: str, font: pygame.font.Font) -> pygame.Surface:
    fill = font.render(label, True, (240, 192, 80))
    shade = font.render(label, True, (52, 30, 8))
    out = pygame.Surface((fill.get_width() + 4, fill.get_height() + 4), pygame.SRCALPHA)
    for dx in (0, 1, 2, 3, 4):
        for dy in (0, 1, 2, 3, 4):
            if (dx, dy) != (2, 2):
                out.blit(shade, (dx, dy))
    out.blit(fill, (2, 2))
    return out


class GUIManager:
    def __init__(self, start_screen: str = "title"):
        self.elementCategories: dict[str, list] = {}
        self.currentGroup = start_screen
        self.font = None
        self.focus = None

    def group(self, name: str) -> list:
        return self.elementCategories.setdefault(name, [])

    def setFont(self, font):
        self.font = font

    # -- building ------------------------------------------------------------

    def createButton(self, ID, group_name, pos, bg_img, bg_mousedover_img, bg_pressed_img, colorkey=GREEN_KEY):
        b = Button(ID, pos, bg_img, bg_mousedover_img, bg_pressed_img, colorkey)
        self.group(group_name).append(b)
        return b

    def createTextEntry(self, ID, group_name, pos, width, font, bg_color, text_color, secret=False):
        e = TextEntry(ID, pos, width, font, bg_color, text_color, secret)
        self.group(group_name).append(e)
        return e

    def createTextList(self, ID, group_name, pos, width, font, max_number, bg_color, text_color):
        t = TextList(ID, pos, width, font, max_number, bg_color, text_color)
        self.group(group_name).append(t)
        return t

    def createLabel(self, ID, group_name, pos, bg_img, colorkey=GREEN_KEY):
        surf = bg_img if isinstance(bg_img, pygame.Surface) else image(*bg_img.split("/"))
        label = Label(ID, pos, surf, colorkey)
        self.group(group_name).append(label)
        return label

    # -- events --------------------------------------------------------------

    def show(self, name: str):
        if name != self.currentGroup:
            self.currentGroup = name
            self.set_focus(None)

    def entries(self) -> list:
        return [e for e in self.group(self.currentGroup) if isinstance(e, TextEntry)]

    def set_focus(self, entry):
        if self.focus is not None:
            self.focus.isfocused = False
        self.focus = entry
        if entry is not None:
            entry.isfocused = True

    def onKeyEvent(self, keyType, key, mod):
        if keyType != pygame.KEYDOWN:
            return
        if key == pygame.K_TAB:
            entries = self.entries()
            if entries:
                i = entries.index(self.focus) if self.focus in entries else -1
                step = -1 if mod & pygame.KMOD_SHIFT else 1
                self.set_focus(entries[(i + step) % len(entries)])
        elif self.focus is not None:
            self.focus.gotKeyEvt(keyType, key, mod)

    def onTextInput(self, text: str):
        if self.focus is not None:
            self.focus.insert(text)

    def onMouse(self, mouseType, button, pos):
        """Forward a mouse event to the element under the cursor. Returns the
        ID of a button pressed with the left button, else None."""
        hit_id = None
        if mouseType == pygame.MOUSEBUTTONDOWN:
            self.set_focus(None)
        for e in self.group(self.currentGroup):
            inside = e.rect().collidepoint(pos)
            if inside:
                e.gotMouseEvt(mouseType, button)
                if isinstance(e, TextEntry) and mouseType == pygame.MOUSEBUTTONDOWN:
                    self.set_focus(e)
                elif isinstance(e, Button) and button == 1 and mouseType == pygame.MOUSEBUTTONDOWN:
                    hit_id = e.ID
            else:
                e.gotMouseEvt(None, button)
        return hit_id

    # -- per frame -----------------------------------------------------------

    def update(self, dtime):
        for e in self.group(self.currentGroup):
            e.update(dtime)

    def render(self, surface):
        for e in self.group(self.currentGroup):
            e.redraw()
            surface.blit(e.surf, e.pos)


class GuiElement:
    def __init__(self, ID, pos, surf):
        self.ID = ID
        self.pos = pos
        self.surf = surf

    def rect(self) -> pygame.Rect:
        return pygame.Rect(self.pos, self.surf.get_size())

    def redraw(self):
        pass

    def gotMouseEvt(self, mouseType, button):
        pass

    def gotKeyEvt(self, keyType, key, mod):
        pass

    def update(self, dtime):
        pass


class Button(GuiElement):
    def __init__(self, ID, pos, bg_img, bg_mousedover_img, bg_pressed_img, colorkey=GREEN_KEY):
        if not isinstance(ID, int):
            raise ValueError(f"Button ID must be an int, got {ID!r}")
        for s in (bg_img, bg_mousedover_img, bg_pressed_img):
            s.set_colorkey(colorkey)
        self.images = (bg_img, bg_mousedover_img, bg_pressed_img)
        self.pressed = False
        self.mouse_over = False
        self.visible = True
        super().__init__(ID, tuple(pos), bg_img)

    def rect(self):
        return super().rect() if self.visible else pygame.Rect(0, 0, 0, 0)

    def redraw(self):
        normal, hover, pressed = self.images
        self.surf = pressed if self.pressed else hover if self.mouse_over else normal
        if not self.visible:
            self.surf = pygame.Surface((0, 0))

    def gotMouseEvt(self, mouseType, button):
        if mouseType == pygame.MOUSEBUTTONDOWN and button == 1:
            self.pressed = True
        elif mouseType == pygame.MOUSEBUTTONUP and button == 1:
            self.pressed = False
        elif mouseType == pygame.MOUSEMOTION:
            self.mouse_over = True
        else:
            self.mouse_over = False
            self.pressed = False


class Label(GuiElement):
    def __init__(self, ID, pos, bg_img, colorkey=GREEN_KEY):
        surf = pygame.Surface(bg_img.get_size())
        surf.fill(colorkey)
        surf.set_colorkey(colorkey)
        surf.blit(bg_img, (0, 0))
        super().__init__(ID, tuple(pos), surf)


class TextEntry(GuiElement):
    def __init__(self, ID, pos, width, font, bg_color, text_color, secret=False):
        self.font = font
        self.width = width
        self.bg_color = bg_color
        self.text_color = text_color
        self.secret = secret
        self.current_str = ""
        self.caret = 0
        self.isfocused = False
        self.blink = 0.0
        super().__init__(ID, tuple(pos), pygame.Surface((width, font.get_linesize())))
        self.redraw()

    def shown(self) -> str:
        return "*" * len(self.current_str) if self.secret else self.current_str

    def insert(self, text: str):
        # ':' '<' '>' frame the network protocol, so they cannot be typed.
        text = "".join(ch for ch in text if ch not in ":<>")
        if not text or self.font.size(self.shown() + text)[0] > self.width - 4:
            return
        s = self.current_str
        self.current_str = s[:self.caret] + text + s[self.caret:]
        self.caret += len(text)

    def gotKeyEvt(self, keyType, key, mod):
        s = self.current_str
        if key == pygame.K_BACKSPACE and self.caret > 0:
            self.current_str = s[:self.caret - 1] + s[self.caret:]
            self.caret -= 1
        elif key == pygame.K_DELETE:
            self.current_str = s[:self.caret] + s[self.caret + 1:]
        elif key == pygame.K_LEFT:
            self.caret = max(self.caret - 1, 0)
        elif key == pygame.K_RIGHT:
            self.caret = min(self.caret + 1, len(s))
        elif key == pygame.K_HOME:
            self.caret = 0
        elif key == pygame.K_END:
            self.caret = len(s)

    def clear(self):
        self.current_str = ""
        self.caret = 0

    def update(self, dtime):
        self.blink = (self.blink + dtime) % 1.0

    def redraw(self):
        self.surf.fill(self.bg_color)
        self.surf.blit(self.font.render(self.shown(), True, self.text_color), (2, 0))
        if self.isfocused and self.blink < 0.5:
            x = 2 + self.font.size(self.shown()[:self.caret])[0]
            pygame.draw.line(self.surf, self.text_color, (x, 2), (x, self.surf.get_height() - 3))


class TextList(GuiElement):
    """Scrolling chat log, newest line at the bottom."""

    VISIBLE_LINES = 10

    def __init__(self, ID, pos, width, font, max_number, bg_color, text_color):
        self.font = font
        self.width = width
        self.max_number = max_number
        self.bg_color = bg_color
        self.text_color = text_color
        self.lines: list[str] = []
        surf = pygame.Surface((width, font.get_linesize() * self.VISIBLE_LINES), pygame.SRCALPHA)
        super().__init__(ID, tuple(pos), surf)

    def addTextdraw(self, text: str):
        # Wrap long lines to the box width.
        words, line = text.split(" "), ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if self.font.size(candidate)[0] > self.width - 8 and line:
                self.lines.append(line)
                line = word
            else:
                line = candidate
        self.lines.append(line)
        del self.lines[:-self.max_number]

    def redraw(self):
        self.surf.fill((0, 0, 0, 0))
        if not self.lines:
            return
        h = self.font.get_linesize()
        shown = self.lines[-self.VISIBLE_LINES:]
        top = (self.VISIBLE_LINES - len(shown)) * h
        backdrop = pygame.Surface((self.width, len(shown) * h), pygame.SRCALPHA)
        backdrop.fill((0, 0, 0, 110))
        self.surf.blit(backdrop, (0, top))
        for i, line in enumerate(shown):
            self.surf.blit(self.font.render(line, True, self.text_color), (4, top + i * h))
