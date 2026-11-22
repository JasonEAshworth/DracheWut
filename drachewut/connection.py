"""Non-blocking UDP messaging. Messages are framed as <...> blocks."""

from __future__ import annotations

import socket
import time

DEFAULT_PORT = 50000


def local_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


class Connection:
    """A sending/receiving socket polled once per frame by update()."""

    maxPacketSize = 4096
    # No message for maxDelay seconds: start pinging. No message for twice
    # that: the remote side is considered gone.
    maxDelay = 4.0
    pingFrequency = 0.5

    def __init__(self, log_level: int = 1):
        self._ID = None
        self._socket = None
        self._local_IP = local_ip()
        self._local_port = None
        self._active = False
        self._shutting_down = False
        self._recv_accum = ""
        self._recv_messages: list[tuple[str, tuple]] = []
        self._send_queue: list[tuple[str, tuple, bool]] = []
        self._recv_timer = time.time()
        self._ping_timer = 0.0
        self._ping_check = False
        # 0 startup/shutdown, 1 major, 2 medium, 3 minor, 4 pings, 5 debug
        self._log_level = log_level

    # -- state ---------------------------------------------------------------

    def kill(self):
        """Close the socket once the send queue is empty."""
        self._shutting_down = True

    def close(self):
        """Send what is queued, then close the socket now."""
        self._shutting_down = True
        for _ in range(len(self._send_queue) + 1):
            self.update()
            if not self._active:
                break
        if self._socket is not None and self._active:
            self._socket.close()
        self._active = False

    def setID(self, ID):
        self._ID = ID

    def getID(self):
        return self._ID

    def setPingEnable(self, enable: bool):
        self._ping_check = enable
        if enable:
            self._recv_timer = time.time()

    def logMessage(self, s, lvl: int = 1):
        if lvl <= self._log_level:
            print(f"[Connection #{self._ID}: {s}]")

    def getLocalIP(self) -> str:
        return self._local_IP

    def getLocalPort(self):
        return self._local_port

    def getActive(self) -> bool:
        return self._active

    def getTimeSinceLastRecv(self) -> float:
        return time.time() - self._recv_timer

    def hasSocket(self) -> bool:
        return self._socket is not None

    def createSocket(self, myPort: int, bind_ip: str = "0.0.0.0"):
        if self._socket is not None:
            raise ValueError("This Connection already has an active socket!")
        self.logMessage(f"New socket on {bind_ip}:{myPort}", 0)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(False)
        self._socket.bind((bind_ip, myPort))
        self._local_port = self._socket.getsockname()[1]
        self._active = True

    # -- messaging -----------------------------------------------------------

    def checkForDeadConnection(self, remoteIP, remotePort):
        """Ping a quiet remote side; give up on one that stays quiet."""
        if not self._ping_check:
            return
        quiet = self.getTimeSinceLastRecv()
        if quiet > 2 * Connection.maxDelay:
            self._active = False
            self.logMessage("Remote connection timed out -- shutting down.", 0)
        elif quiet > Connection.maxDelay and time.time() - self._ping_timer > Connection.pingFrequency:
            self.sendMessage("<PING>", (remoteIP, remotePort), False)
            self._ping_timer = time.time()

    def sendMessage(self, s: str, addr, must_succeed: bool):
        if not self._shutting_down:
            self._send_queue.append((s, addr, must_succeed))

    def getNewMessages(self) -> list[tuple[str, tuple]]:
        rv, self._recv_messages = self._recv_messages, []
        return rv

    def _accumulate(self, s: str, addr):
        self._recv_accum += s
        while "<" in self._recv_accum and ">" in self._recv_accum:
            start = self._recv_accum.find("<")
            end = self._recv_accum.find(">", start)
            if end < 0:
                break
            self._recv_messages.append((self._recv_accum[start + 1:end], addr))
            self._recv_accum = self._recv_accum[end + 1:]

    def update(self):
        if not self._active:
            return

        # The 2013 code matched Windows error numbers (10035, 10054), which
        # raised on other platforms. These exceptions cover all of them.
        while True:
            try:
                data, addr = self._socket.recvfrom(Connection.maxPacketSize)
            except (BlockingIOError, InterruptedError):
                break
            except (ConnectionResetError, socket.timeout):
                break  # a datagram to a closed port bounced; ignore it
            self._recv_timer = time.time()
            self._accumulate(data.decode("utf-8", "replace"), addr)

        while self._send_queue:
            msg, addr, must_succeed = self._send_queue[0]
            data = msg.encode()
            try:
                sent = self._socket.sendto(data, addr)
            except (BlockingIOError, InterruptedError):
                break
            except ConnectionResetError:
                sent = len(data)
            if sent >= len(data) or not must_succeed:
                self._send_queue.pop(0)
            else:
                break

        if self._shutting_down and not self._send_queue:
            self._active = False
            self._socket.close()
