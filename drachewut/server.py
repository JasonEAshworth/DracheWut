"""Drache Wut server: accounts, logins, and relaying player state and chat."""

from __future__ import annotations

import time
from pathlib import Path

from .connection import DEFAULT_PORT, Connection
from .player import Player


class ClientInfo:
    """One remote address the server has heard from."""

    def __init__(self, ID, addr):
        self.ID = ID
        self.addr = addr
        self.ping_timer = 0.0
        self.recv_timer = time.time()
        self.recv_count = 0
        self.send_count = 0


class Server:
    """Holds the master copy of every player and relays updates.

    A heartbeat with every player's full state goes out twice a second while
    two or more players are connected.
    """

    maxDelay = 4.0       # ping a client this long after its last message
    pingFrequency = 0.5  # seconds between pings to a quiet client
    heartbeatFreq = 0.5

    def __init__(self, maxPlayers: int = 5, myPort: int = DEFAULT_PORT,
                 accounts: str | Path = "accounts.dat", log_level: int = 1):
        self.maxPlayers = maxPlayers
        self.heartbeatTimer = 0.0
        self.pendingMessages: list[tuple[int, str, tuple]] = []
        self.dbase_fname = Path(accounts)
        self.dbase: dict[str, str] = {}   # uname -> stored record
        self.clientNextID = 0
        self.clients: dict[int, ClientInfo] = {}
        self.by_addr: dict[tuple, ClientInfo] = {}
        self.players: dict[int, Player] = {}
        self.connection = Connection(log_level)
        self.connection.createSocket(myPort)
        self.log = self.connection.logMessage

    # -- account file --------------------------------------------------------
    # One line per account: the player's level-3 serialization plus :pass=...
    # Passwords are stored as plain text, as in the 2013 version. Do not reuse
    # a real password here.

    def loadDBase(self):
        self.dbase = {}
        if not self.dbase_fname.exists():
            return
        for line in self.dbase_fname.read_text().splitlines():
            line = line.strip()
            if line.startswith("uname="):
                self.dbase[line.split(":")[0].split("=", 1)[1]] = line

    def saveDBase(self):
        self.dbase_fname.write_text("".join(line + "\n" for line in self.dbase.values()))

    @staticmethod
    def _password(record: str) -> str:
        return record[record.rfind(":pass=") + 6:]

    def addToDBase(self, player: Player, password: str):
        self.dbase[player.uname] = player.serialize(3, False) + ":pass=" + password

    def updateDBase(self, player: Player):
        if player.uname in self.dbase:
            password = self._password(self.dbase[player.uname])
            self.dbase[player.uname] = player.serialize(3, False) + ":pass=" + password

    # -- receiving -----------------------------------------------------------

    def getNewMessages(self):
        for msg, addr in self.connection.getNewMessages():
            cinfo = self.by_addr.get(addr)
            if cinfo is None:
                cinfo = ClientInfo(self.clientNextID, addr)
                self.clients[cinfo.ID] = cinfo
                self.by_addr[addr] = cinfo
                self.clientNextID += 1
                self.log(f"New client #{cinfo.ID} at {addr[0]}:{addr[1]}", 1)
            cinfo.recv_timer = time.time()
            cinfo.recv_count += 1
            self.pendingMessages.append((cinfo.ID, msg, addr))

    def processPendingData(self):
        items, self.pendingMessages = self.pendingMessages, []
        for ID, msg, _addr in items:
            opcode = msg.split(":")[0]
            handler = {
                "NEW_ACCOUNT": self._onNewAccount,
                "LOGIN": self._onLogin,
                "UPDATE": self._onUpdate,
                "FULL_UPDATE": self._onFullUpdate,
                "PLAYER_LEFT": self._onPlayerLeft,
                "QUIT": self._onQuit,
                "PING": lambda m, i: self.sendMessage("<PING_ACK>", i, True),
                "PING_ACK": lambda m, i: None,
                "CHAT": self._onChat,
            }.get(opcode)
            if handler is None:
                self.log(f"Unhandled message {opcode!r} from #{ID}", 1)
            else:
                handler(msg, ID)

    @staticmethod
    def _fields(msg: str) -> dict[str, str]:
        return dict(f.split("=", 1) for f in msg.split(":")[1:] if "=" in f)

    def _onChat(self, msg, ID):
        for pid in self.players:
            self.sendMessage("<" + msg + ">", pid, True)

    def _onNewAccount(self, msg, ID):
        f = self._fields(msg)
        uname, password = f.get("uname", ""), f.get("pass", "")
        if not uname or not password:
            self.log(f"Corrupt NEW_ACCOUNT from #{ID}", 1)
            self.sendMessage("<NEW_ACCOUNT_ACK:accepted=F>", ID, True)
            return
        if uname in self.dbase:
            # The 2013 code passed the client ID where an address belongs here,
            # which crashed the server on a duplicate name.
            self.sendMessage("<NEW_ACCOUNT_ACK:accepted=F>", ID, True)
            return
        self.addToDBase(Player(uname, f.get("class", "Cleric"), load_sprites=False), password)
        self.saveDBase()
        self.sendMessage(f"<NEW_ACCOUNT_ACK:accepted=T:ID={ID}>", ID, True)

    def _onLogin(self, msg, ID):
        # The class field is optional: a returning player only sends a name
        # and password. The 2013 server required it, so logins always failed.
        f = self._fields(msg)
        uname, password = f.get("uname", ""), f.get("pass", "")
        if len(self.players) >= self.maxPlayers and ID not in self.players:
            self.sendMessage("<LOGIN_ACK:accepted=B>", ID, True)
            return
        record = self.dbase.get(uname)
        if record is None or self._password(record) != password:
            self.sendMessage("<LOGIN_ACK:accepted=F>", ID, True)
            return
        stored = record[:record.rfind(":pass=")]
        player = Player(uname, self._fields("X:" + stored).get("Pclass", "Cleric"), load_sprites=False)
        player.deserialize(stored)
        self.players[ID] = player
        self.log(f"{uname} logged in as #{ID}", 1)
        self.sendMessage(f"<LOGIN_ACK:accepted=T:ID={ID}:{player.serialize(2)}>", ID, True)
        joined = f"<PLAYER_JOINED:ID={ID}:{player.serialize(2)}>"
        for pid in self.players:
            if pid != ID:
                self.sendMessage(joined, pid, True)

    def _onUpdate(self, msg, ID):
        state = msg[len("UPDATE:"):]
        if ID in self.players:
            self.players[ID].deserialize(state)
        relay = f"<HEARTBEAT:ID={ID}:{state}>"
        for pid in self.players:
            if pid != ID:
                self.sendMessage(relay, pid, True)

    def _fullState(self) -> str:
        return "".join(f":ID={pid}:{p.serialize(2, False)}" for pid, p in self.players.items())

    def _onFullUpdate(self, msg, ID):
        self.sendMessage("<FULL_UPDATE_ACK" + self._fullState() + ">", ID, True)

    def _onPlayerLeft(self, msg, ID):
        for pid in self.players:
            if pid != ID:
                self.sendMessage(f"<PLAYER_LEFT:ID={ID}>", pid, True)

    def _onQuit(self, msg, ID):
        self.sendMessage("<QUIT_ACK>", ID, True)
        player = self.players.pop(ID, None)
        if player is not None:
            self.log(f"{player.uname} (#{ID}) left", 1)
            self.updateDBase(player)
            self.saveDBase()
            self._onPlayerLeft("PLAYER_LEFT", ID)

    # -- sending -------------------------------------------------------------

    def sendMessage(self, msg: str, ID: int, must_succeed: bool):
        client = self.clients[ID]
        client.send_count += 1
        self.connection.sendMessage(msg, client.addr, must_succeed)

    def sendHeartBeat(self, dT: float):
        if len(self.players) < 2:
            return
        self.heartbeatTimer += dT
        if self.heartbeatTimer < self.heartbeatFreq:
            return
        self.heartbeatTimer = 0.0
        beat = "<FULL_UPDATE_ACK" + self._fullState() + ">"
        for pid in self.players:
            self.sendMessage(beat, pid, False)

    def checkForDeadClients(self):
        now = time.time()
        for pid in list(self.players):
            client = self.clients[pid]
            quiet = now - client.recv_timer
            if quiet >= 2 * Server.maxDelay:
                self._onQuit("QUIT", pid)
            elif quiet >= Server.maxDelay and now - client.ping_timer >= Server.pingFrequency:
                self.sendMessage("<PING>", pid, True)
                client.ping_timer = now

    # -- main loop -----------------------------------------------------------

    def step(self, dT: float):
        self.connection.update()
        self.sendHeartBeat(dT)
        self.getNewMessages()
        self.processPendingData()
        self.checkForDeadClients()
        for p in self.players.values():
            p.update(dT)

    def drawStatus(self, screen, font):
        import pygame

        screen.fill((0, 0, 0))
        port = self.connection.getLocalPort()
        screen.blit(font.render(f"SERVER  {self.connection.getLocalIP()}:{port}   (Esc to stop)",
                                True, (255, 255, 255)), (4, 4))
        cols = [4, 40, 200, 320, 380, 440]
        heads = ["ID", "Address", "Name", "Recv", "Sent", "Quiet"]
        h = font.get_linesize()
        y = 2 * h
        for x, text in zip(cols, heads):
            screen.blit(font.render(text, True, (255, 255, 0)), (x, y))
        y += h
        for pid, p in self.players.items():
            c = self.clients[pid]
            row = [str(pid), f"{c.addr[0]}:{c.addr[1]}", p.uname, str(c.recv_count),
                   str(c.send_count), f"{time.time() - c.recv_timer:.1f}s"]
            for x, text in zip(cols, row):
                screen.blit(font.render(text, True, (100, 255, 100)), (x, y))
            y += h
        pygame.display.flip()

    def run(self, window: bool = True):
        self.loadDBase()
        print(f"Server listening on UDP port {self.connection.getLocalPort()} "
              f"({self.connection.getLocalIP()}); accounts in {self.dbase_fname.resolve()}")
        screen = font = None
        if window:
            import pygame

            pygame.display.init()
            pygame.font.init()
            pygame.display.set_caption("Drache Wut server")
            screen = pygame.display.set_mode((520, 300))
            font = pygame.font.SysFont("Courier New", 14)
        last = time.time()
        try:
            while True:
                if window:
                    import pygame

                    if any(e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE)
                           for e in pygame.event.get()):
                        break
                now = time.time()
                self.step(now - last)
                last = now
                if window:
                    self.drawStatus(screen, font)
                time.sleep(0.005)
        except KeyboardInterrupt:
            pass
        finally:
            for p in self.players.values():
                self.updateDBase(p)
            self.saveDBase()
            self.connection.kill()
            self.connection.update()
            if window:
                import pygame

                pygame.quit()
