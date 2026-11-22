"""Drache Wut game client: title screens, the game world, and server messages."""

from __future__ import annotations

import asyncio
import random
import sys

import pygame

from . import TITLE, world
from .gui import GUIManager, image, stone_button
from .paths import asset
from .player import CLASSES, Player

SCREEN_SIZE = (1280, 704)
FPS = 60
DAMAGE_PER_SECOND = 30.0   # health lost per second on a damage tile
SLOW_FACTOR = 0.5          # speed multiplier on a slow tile
WEB = sys.platform == "emscripten"   # running in the browser via pygbag

# Button IDs. The values come from the 2013 client.
TO_TITLE, TO_LOGIN, TO_NEW_USER = -1, 2, 5
PICK_MAGE, PICK_CLERIC, PICK_THIEF, PICK_WARRIOR = 12, 13, 14, 15
SUBMIT_LOGIN, SUBMIT_NEW_USER = 16, 17
TO_CHOOSE_CLASS, START_OFFLINE = 20, 21
CLASS_BUTTONS = {PICK_MAGE: "Mage", PICK_CLERIC: "Cleric", PICK_THIEF: "Thief", PICK_WARRIOR: "Warrior"}
CLASS_POSITIONS = {"Mage": (200, 200), "Cleric": (200, 500), "Thief": (1000, 200), "Warrior": (1000, 500)}


def random_name(n: int = 6) -> str:
    return "".join(random.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(n)).title()


class Application:
    """All game state. Talks to the server through a Connection when online."""

    def __init__(self, screen: pygame.Surface | None = None):
        self.screen = screen or pygame.display.set_mode(SCREEN_SIZE)
        pygame.display.set_caption(TITLE)
        pygame.key.start_text_input()
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(asset("fonts", "BlackCastle.ttf"), 20)
        self.hud_font = pygame.font.Font(asset("fonts", "BlackCastle.ttf"), 26)
        self.connection = None
        self.remoteIP = None
        self.remotePort = None
        self.uname = ""
        self.password = ""
        self.offline = False
        self.gameState = "title"
        self.players: dict[int, Player] = {}
        self.playerID = None
        self.classstr = None
        self.map = world.Zone(view_size=SCREEN_SIZE)
        self.running = True
        # Arrow keys pressed since the last update. A tap shorter than one
        # frame would otherwise not move the player (it happens on slow
        # frames, e.g. a browser tab in the background).
        self.tapped: set[int] = set()
        self.initGUI()

    # -- setup ---------------------------------------------------------------

    def initGUI(self):
        g = self.GUIManager = GUIManager("title")
        g.setFont(self.font)
        font = self.font

        def button(ID, group, pos, folder, stem, states=(1, 2, 3)):
            imgs = [image(folder, f"{stem}_{n}.png") for n in states]
            return g.createButton(ID, group, pos, *imgs)

        def entry(group, pos, secret=False):
            return g.createTextEntry(0, group, pos, 225, font, (255, 255, 255), (0, 0, 0), secret)

        def menu_button(group):
            button(TO_TITLE, group, (1150, 0), "Menu", "button_menu")

        def title_backdrop(group):
            g.createLabel(0, group, (0, 0), "gui_title.png")

        play = stone_button("Play", pygame.font.Font(asset("fonts", "BlackCastle.ttf"), 26))

        # Title
        title_backdrop("title")
        if WEB:
            # No sockets in the browser: offline play only.
            g.createButton(TO_CHOOSE_CLASS, "title", (550, 300), *play)
        else:
            button(TO_LOGIN, "title", (550, 300), "Login", "button_login")
            button(TO_NEW_USER, "title", (550, 375), "New_User", "button_newUser")
            g.createButton(TO_CHOOSE_CLASS, "title", (550, 450), *play)

        # Login
        title_backdrop("login")
        g.createLabel(0, "login", (500, 250), "gui_username.png")
        g.createLabel(0, "login", (500, 350), "gui_password.png")
        g.createLabel(0, "login", (500, 450), "gui_ipaddress.png")
        self.login_user = entry("login", (510, 303))
        self.login_pass = entry("login", (510, 403), secret=True)
        self.login_ip = entry("login", (510, 503))
        button(SUBMIT_LOGIN, "login", (560, 550), "Login", "button_login")
        menu_button("login")

        for group, panel, pos, back in (
            ("login_failure", "gui_login_fail.png", (415, 250), TO_LOGIN),
            ("login_busy", "gui_login_busy.png", (415, 200), TO_LOGIN),
            ("new_account_failure", "gui_new_user_fail.png", (415, 200), TO_NEW_USER),
            ("new_account_busy", "gui_new_user_busy.png", (415, 200), TO_NEW_USER),
        ):
            title_backdrop(group)
            g.createLabel(0, group, pos, panel)
            button(back, group, (560, 550), "Ok", "button_ok")
            menu_button(group)

        # New account
        title_backdrop("New_user")
        g.createLabel(0, "New_user", (500, 200), "gui_username.png")
        g.createLabel(0, "New_user", (500, 300), "gui_password.png")
        g.createLabel(0, "New_user", (500, 400), "gui_confirm.png")
        g.createLabel(0, "New_user", (500, 500), "gui_ipaddress.png")
        self.new_user = entry("New_user", (510, 253))
        self.new_pass = entry("New_user", (510, 353), secret=True)
        self.new_confirm = entry("New_user", (510, 453), secret=True)
        self.new_ip = entry("New_user", (510, 553))
        button(SUBMIT_NEW_USER, "New_user", (560, 600), "Create", "button_create", (1, 2, 1))
        self._class_buttons("New_user")
        menu_button("New_user")

        # Offline class choice
        title_backdrop("choose_class")
        self._class_buttons("choose_class")
        g.createButton(START_OFFLINE, "choose_class", (576, 560), *play)
        menu_button("choose_class")

        # In game: chat entry and log
        self.chat_entry = g.createTextEntry(0, "Game", (0, 680), 500, font, (255, 255, 255), (0, 0, 0))
        self.chat_log = g.createTextList(0, "Game", (0, 440), 500, font, 50, (0, 0, 0), (255, 255, 255))

        title_backdrop("credits")
        g.createLabel(0, "credits", (200, 100), "credits.png", (255, 255, 255))
        menu_button("credits")

    def _class_buttons(self, group):
        files = {"Mage": "Mage.png", "Cleric": "cleric.png", "Thief": "Thief.png", "Warrior": "Warrior.png"}
        for ID, name in CLASS_BUTTONS.items():
            img = image(files[name])
            self.GUIManager.createButton(ID, group, CLASS_POSITIONS[name], img, img, img)

    def setState(self, state: str):
        self.gameState = state
        self.GUIManager.show(state)

    # -- offline play --------------------------------------------------------

    def startOffline(self):
        self.offline = True
        self.uname = random_name()
        self.playerID = 0
        self.map = world.Zone(view_size=SCREEN_SIZE)
        p = Player(self.uname, self.classstr or "Cleric")
        p.posX, p.posY = self.map.spawn_point()
        self.players = {0: p}
        self.chat_log.lines.clear()
        self.chat_log.addTextdraw(f"Welcome to {TITLE}, {self.uname} the {p.Pclass}.")
        self.chat_log.addTextdraw("Arrow keys move. Walk onto a portal to travel.")
        self.setState("Game")

    # -- per frame -----------------------------------------------------------

    def update(self, dT: float):
        self.updateGame(dT)
        self.GUIManager.update(dT)
        self.updateConnection()

    def updateGame(self, dT: float):
        me = self.players.get(self.playerID)
        if self.gameState != "Game" or me is None:
            return

        typing = self.GUIManager.focus is self.chat_entry
        keys = pygame.key.get_pressed()

        def down(key):
            return keys[key] or key in self.tapped

        dx = dy = 0
        if not typing and not me.dead:
            dx = down(pygame.K_RIGHT) - down(pygame.K_LEFT)
            dy = down(pygame.K_DOWN) - down(pygame.K_UP)
        self.tapped.clear()
        me.set_move(dx, dy)

        effect = self.map.tile_effect(me.posX, me.posY)
        me.speed_factor = SLOW_FACTOR if effect == world.SLOW else 1.0
        for p in self.players.values():
            p.update(dT)

        # The 2013 client computed the wall push-out and then dropped it, so
        # walls did not block.
        me.posX, me.posY = self.map.collide(me.posX, me.posY)

        if self.map.tile_effect(me.posX, me.posY) == world.DAMAGE:
            was_alive = not me.dead
            me.hurt(DAMAGE_PER_SECOND * dT)
            if was_alive and me.dead:
                self.chat_log.addTextdraw("You have fallen.")
        if me.respawn_due():
            me.respawn(*self.map.spawn_point())
            self.map.warp_armed = False

        arrival = self.map.check_warp(me.posX, me.posY)
        if arrival:
            me.posX, me.posY = arrival
            zone = self.map.map.name.removesuffix(".map")
            self.chat_log.addTextdraw(f"You enter {zone}.")

        self.map.follow(me.posX, me.posY)

    def updateConnection(self):
        if self.connection is None:
            return
        self.connection.update()
        if not self.connection.getActive():
            return
        self.handleServerMessages()
        self.connection.checkForDeadConnection(self.remoteIP, self.remotePort)
        me = self.players.get(self.playerID)
        if me is not None:
            s = me.serialize(0)
            if s:
                self.send("<UPDATE:" + s + ">")

    # -- drawing -------------------------------------------------------------

    def render(self):
        surf = self.screen
        if self.gameState == "Game":
            surf.fill((0, 0, 0))
            self.map.render(surf)
            for pid, p in self.players.items():
                if pid != self.playerID:
                    p.render(surf, self.map.camera)
            if self.playerID in self.players:
                self.players[self.playerID].render(surf, self.map.camera)
            self.renderHud(surf)
        self.GUIManager.render(surf)
        if self.gameState in ("New_user", "choose_class") and self.classstr:
            x, y = CLASS_POSITIONS[self.classstr]
            pygame.draw.rect(surf, (240, 192, 80), (x - 6, y - 6, 76, 76), 3, border_radius=6)
        if self.gameState == "choose_class":
            self._caption(surf, "Choose your class", 640, 470)
            if self.classstr:
                self._caption(surf, self.classstr, 640, 515)
        pygame.display.flip()

    def _caption(self, surf, text, cx, cy):
        shade = self.hud_font.render(text, True, (40, 24, 6))
        fill = self.hud_font.render(text, True, (240, 192, 80))
        r = fill.get_rect(center=(cx, cy))
        surf.blit(shade, r.move(2, 2))
        surf.blit(fill, r)

    def renderHud(self, surf):
        me = self.players.get(self.playerID)
        if me is None:
            return
        zone = self.map.map.name.removesuffix(".map")
        lines = [f"{me.Pname} the {me.Pclass}", f"Health {int(me.cur_health)} / {int(me.max_health)}", f"Zone: {zone}"]
        for i, text in enumerate(lines):
            surf.blit(self.font.render(text, True, (0, 0, 0)), (12, 10 + i * 24))
            surf.blit(self.font.render(text, True, (255, 236, 180)), (10, 8 + i * 24))
        hint = "Arrows move   Enter chats   Esc returns to the title"
        img = self.font.render(hint, True, (255, 255, 255))
        surf.blit(img, (SCREEN_SIZE[0] - img.get_width() - 10, SCREEN_SIZE[1] - img.get_height() - 6))

    # -- input ---------------------------------------------------------------

    def processInput(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.shutdown()
            elif e.type == pygame.KEYDOWN:
                self.keyDown(e.key, e.mod)
            elif e.type == pygame.TEXTINPUT:
                self.GUIManager.onTextInput(e.text)
            elif e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
                self.mouseMessage(e.type, getattr(e, "button", None), e.pos)

    def keyDown(self, key, mod):
        if key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
            self.tapped.add(key)
        if key == pygame.K_ESCAPE:
            if self.gameState == "title":
                if not WEB:
                    self.shutdown()
            else:
                self.leaveGame()
            return
        if key == pygame.K_RETURN and self.gameState == "Game":
            if self.GUIManager.focus is self.chat_entry:
                self.sendChat(self.chat_entry.current_str.strip())
                self.chat_entry.clear()
                self.GUIManager.set_focus(None)
            else:
                self.GUIManager.set_focus(self.chat_entry)
            return
        self.GUIManager.onKeyEvent(pygame.KEYDOWN, key, mod)

    def sendChat(self, text: str):
        if not text:
            return
        if self.offline or self.connection is None:
            self.chat_log.addTextdraw(f"{self.uname}: {text}")
        else:
            self.send(f"<CHAT:msg={text}:uname={self.uname}>")

    def mouseMessage(self, eventType, button, pos):
        hit = self.GUIManager.onMouse(eventType, button, pos)
        if eventType != pygame.MOUSEBUTTONDOWN or hit is None:
            return
        if hit == TO_TITLE:
            self.leaveGame()
        elif hit == TO_LOGIN:
            self.setState("login")
        elif hit == TO_NEW_USER:
            self.setState("New_user")
        elif hit in CLASS_BUTTONS:
            self.classstr = CLASS_BUTTONS[hit]
        elif hit == TO_CHOOSE_CLASS:
            self.setState("choose_class")
        elif hit == START_OFFLINE:
            self.startOffline()
        elif hit == SUBMIT_LOGIN:
            self.connectToServer(self.login_user.current_str, self.login_pass.current_str,
                                 self.classstr, False, self.login_ip.current_str)
        elif hit == SUBMIT_NEW_USER:
            if self.new_pass.current_str != self.new_confirm.current_str:
                self.setState("new_account_failure")
            else:
                self.connectToServer(self.new_user.current_str, self.new_pass.current_str,
                                     self.classstr, True, self.new_ip.current_str)

    def leaveGame(self):
        self._disconnect()
        self.players = {}
        self.playerID = None
        self.offline = False
        self.setState("title")

    # -- networking ----------------------------------------------------------

    def send(self, msg: str):
        self.connection.sendMessage(msg, (self.remoteIP, self.remotePort), True)

    def connectToServer(self, uname, passW, class_string, createAccount, remoteIP, remotePort=None):
        from .connection import DEFAULT_PORT, Connection  # not available in the browser

        uname, passW = uname.strip(), passW.strip()
        failure = "new_account_failure" if createAccount else "login_failure"
        # The server ignores empty fields, so the client used to wait forever.
        if not uname or not passW or len(uname) >= 32 or len(passW) >= 32:
            self.setState(failure)
            return
        self.uname, self.password = uname, passW
        self.class_string = class_string or "Cleric"
        self.remoteIP = remoteIP.strip() or "127.0.0.1"
        self.remotePort = remotePort or DEFAULT_PORT
        if self.connection is None:
            self.connection = Connection()
            self.connection.createSocket(0)
        if createAccount:
            msg = f"<NEW_ACCOUNT:uname={uname}:pass={passW}:class={self.class_string}>"
        else:
            msg = f"<LOGIN:uname={uname}:pass={passW}:class={self.class_string}>"
        print(f"Connecting to {self.remoteIP}:{self.remotePort}")
        self.send(msg)
        self.connection.setPingEnable(True)
        self.setState("new_account_busy" if createAccount else "login_busy")

    def handleServerMessages(self):
        for msg, _addr in self.connection.getNewMessages():
            opcode = msg.split(":")[0]
            handler = {
                "NEW_ACCOUNT_ACK": self._onNewAccountAck,
                "LOGIN_ACK": self._onLoginAck,
                "FULL_UPDATE_ACK": self._onFullUpdate,
                "HEARTBEAT": self._onHeartbeat,
                "PLAYER_JOINED": self._onPlayerJoined,
                "PLAYER_LEFT": self._onPlayerLeft,
                "PING": lambda m: self.send("<PING_ACK>"),
                "PING_ACK": lambda m: None,
                "QUIT_ACK": lambda m: self.connection.kill(),
                "CHAT": self._onChat,
            }.get(opcode)
            if handler is None:
                self.connection.logMessage(f"Unhandled opcode {opcode!r}", 1)
            else:
                handler(msg)

    @staticmethod
    def _fields(msg: str) -> dict[str, str]:
        return dict(f.split("=", 1) for f in msg.split(":")[1:] if "=" in f)

    @staticmethod
    def _split_players(msg: str) -> dict[int, str]:
        """Split "OP:ID=1:k=v:...:ID=2:k=v" into {1: "k=v:...", 2: "k=v"}."""
        out, current, fields = {}, None, []
        for f in msg.split(":")[1:]:
            if f.startswith("ID="):
                if current is not None:
                    out[current] = ":".join(fields)
                current, fields = int(f[3:]), []
            else:
                fields.append(f)
        if current is not None:
            out[current] = ":".join(fields)
        return out

    def _onNewAccountAck(self, msg):
        f = self._fields(msg)
        if f.get("accepted") == "T":
            # Account made: log in with it.
            self.send(f"<LOGIN:uname={self.uname}:pass={self.password}:class={self.class_string}>")
        else:
            self.setState("new_account_failure")

    def _onLoginAck(self, msg):
        parts = msg.split(":")
        f = self._fields(msg)
        accepted = f.get("accepted")
        if accepted == "F":
            self.setState("login_failure")
        elif accepted == "B":
            self.setState("login_busy")
        elif accepted == "T" and "ID" in f:
            self.playerID = int(f["ID"])
            self.connection.setID(self.playerID)
            me = Player(self.uname, self.class_string)
            me.deserialize(":".join(parts[3:]))
            self.map = world.Zone(view_size=SCREEN_SIZE)
            me.posX, me.posY = self.map.spawn_point()
            self.players = {self.playerID: me}
            self.chat_log.lines.clear()
            self.chat_log.addTextdraw(f"Connected to {self.remoteIP} as {self.uname}.")
            self.setState("Game")
            self.send("<FULL_UPDATE>")

    def _onFullUpdate(self, msg):
        data = self._split_players(msg)
        for pid, s in data.items():
            if pid == self.playerID:
                continue  # we are the authority on our own position
            if pid not in self.players:
                self.players[pid] = Player("???")
            self.players[pid].deserialize(s)
        for pid in [p for p in self.players if p not in data and p != self.playerID]:
            del self.players[pid]

    def _onHeartbeat(self, msg):
        for pid, s in self._split_players(msg).items():
            if pid != self.playerID and pid in self.players:
                self.players[pid].deserialize(s)

    def _onPlayerJoined(self, msg):
        for pid, s in self._split_players(msg).items():
            if pid != self.playerID and pid not in self.players:
                self.players[pid] = Player("???")
                self.players[pid].deserialize(s)
                self.chat_log.addTextdraw(f"{self.players[pid].Pname} joined.")

    def _onPlayerLeft(self, msg):
        pid = int(self._fields(msg).get("ID", -1))
        if pid in self.players and pid != self.playerID:
            self.chat_log.addTextdraw(f"{self.players[pid].Pname} left.")
            del self.players[pid]

    def _onChat(self, msg):
        f = self._fields(msg)
        self.chat_log.addTextdraw(f"{f.get('uname', '?')}: {f.get('msg', '')}")

    # -- main loop -----------------------------------------------------------

    def _disconnect(self):
        if self.connection is not None:
            if self.remoteIP and self.connection.getActive():
                self.send("<QUIT>")
            self.connection.close()
        self.connection = None

    def shutdown(self):
        self._disconnect()
        self.running = False

    async def main(self):
        while self.running:
            dT = min(self.clock.tick(FPS) / 1000.0, 0.1)
            self.processInput()
            if not self.running:
                break
            self.update(dT)
            self.render()
            await asyncio.sleep(0)  # yields to the browser under pygbag
        pygame.quit()


def run():
    pygame.init()
    app = Application()
    asyncio.run(app.main())
