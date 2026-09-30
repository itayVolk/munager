from __future__ import annotations

import socket
import struct
import threading
import queue
import traceback
from typing import Callable

# A queued callback runs on the Tk main thread via pump().
_Callback = Callable[[], None]
# A data listener receives one complete binary message.
DataListener = Callable[[bytes], None]
# A connection listener receives a newly-accepted socket.
ConnListener = Callable[["LengthSocket"], None]

_dispatch: "queue.Queue[_Callback]" = queue.Queue()


def pump() -> None:
    """Call from the Tk main loop to run queued socket callbacks safely."""
    while True:
        try:
            fn = _dispatch.get_nowait()
        except queue.Empty:
            break
        try:
            fn()
        except Exception:
            traceback.print_exc()


def _later(fn: _Callback) -> None:
    _dispatch.put(fn)


class LengthSocket:
    """Length-prefixed BINARY message socket.

    Only raw ``bytes`` may be sent; encode via ``munager_proto.encode``.
    """

    def __init__(self, sock: socket.socket) -> None:
        self.sock: socket.socket = sock
        self._listeners: list[DataListener] = []
        self._closed: bool = False
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()

    def on(self, event: str, listener: DataListener) -> None:
        if event == "data":
            self._listeners.append(listener)

    def write(self, data: bytes) -> None:
        """Send one framed message. Binary only — no str accepted."""
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError(
                "LengthSocket.write expects bytes; "
                "encode with munager_proto.encode() first")
        try:
            self.sock.sendall(struct.pack("<I", len(data)) + bytes(data))
        except OSError:
            self.destroy()

    def _reader(self) -> None:
        buf = b""
        want = 4
        state = "length"
        try:
            while not self._closed:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while len(buf) >= want:
                    if state == "length":
                        want = struct.unpack("<I", buf[:4])[0]
                        buf = buf[4:]
                        state = "data"
                    else:
                        msg = buf[:want]
                        buf = buf[want:]
                        want = 4
                        state = "length"
                        for listener in list(self._listeners):
                            _later(lambda fn=listener, msg=msg: fn(msg))
        except OSError:
            pass
        finally:
            self.destroy()

    def destroy(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.sock.close()
        except OSError:
            pass


class Server:
    def __init__(self, connection_listener: ConnListener) -> None:
        self._cb: ConnListener = connection_listener

    def listen(self, port: int, host: str) -> "Server":
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, int(port)))
        srv.listen(200)

        def accept_loop() -> None:
            while True:
                try:
                    conn, _ = srv.accept()
                except OSError:
                    break
                ls = LengthSocket(conn)
                _later(lambda ls=ls: self._cb(ls))

        threading.Thread(target=accept_loop, daemon=True).start()
        return self


def connect(port: int, host: str) -> LengthSocket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, int(port)))
    return LengthSocket(sock)


def local_ip() -> str:
    """Best-effort primary IPv4, mirroring SysGetIPAddresses()[1]."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = str(s.getsockname()[0])
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def all_ipv4() -> list[str]:
    """All local IPv4 addresses, hotspot-range addresses first."""
    addrs: set[str] = set()
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            addr = info[4][0]
            if isinstance(addr, str):
                addr = addr.strip()
                addrs.add(addr)
    except OSError:
        pass
    try:
        addrs.add(local_ip())
    except Exception:
        pass
    addrs.discard("127.0.0.1")

    def rank(ip: str) -> int:
        if ip.startswith("192.168.137."):
            return 0
        if ip.startswith("192.168."):
            return 1
        if ip.startswith("10."):
            return 2
        if ip.startswith("172."):
            return 3
        return 4

    return sorted(addrs, key=rank)
