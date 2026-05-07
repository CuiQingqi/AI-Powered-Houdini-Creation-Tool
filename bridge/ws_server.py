"""
Minimal WebSocket server using only Python stdlib (socket + threading).

Houdini 21's haio.py blocks asyncio on non-main threads, so we CANNOT use
asyncio or websockets library. This module implements just enough of the
WebSocket protocol (RFC 6455) for our JSON-RPC bridge.

Protocol: raw text frames, no compression, no extensions.
"""

import base64
import hashlib
import json
import logging
import socket
import struct
import threading
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("houdini_bridge.ws_server")

WS_MAGIC = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_TEXT = 0x01
OP_CLOSE = 0x08
OP_PING = 0x09
OP_PONG = 0x0A
FIN_BIT = 0x80


def _make_accept_key(key: str) -> str:
    ak = key.strip() + WS_MAGIC.decode("ascii")
    return base64.b64encode(hashlib.sha1(ak.encode("ascii")).digest()).decode("ascii")


def _read_frame(sock: socket.socket, timeout: float = 30.0) -> Optional[bytes]:
    """Read a single WebSocket frame. Returns payload bytes or None on close/error."""
    sock.settimeout(timeout)

    # Read 2-byte header
    try:
        hdr = sock.recv(2)
    except (socket.timeout, ConnectionError, OSError):
        return None
    if len(hdr) < 2:
        return None

    byte1, byte2 = hdr[0], hdr[1]
    opcode = byte1 & 0x0F

    if opcode == OP_CLOSE:
        return None
    if opcode == OP_PING:
        _send_frame(sock, OP_PONG, b"")
        return _read_frame(sock, timeout)
    if opcode == OP_PONG:
        return _read_frame(sock, timeout)

    # Payload length
    masked = (byte2 & 0x80) != 0
    length = byte2 & 0x7F

    if length == 126:
        ext = sock.recv(2)
        if len(ext) < 2:
            return None
        length = struct.unpack("!H", ext)[0]
    elif length == 127:
        ext = sock.recv(8)
        if len(ext) < 8:
            return None
        length = struct.unpack("!Q", ext)[0]

    # Mask key (client MUST mask)
    if masked:
        mask_key = sock.recv(4)
        if len(mask_key) < 4:
            return None
    else:
        mask_key = None

    # Payload
    payload = b""
    while len(payload) < length:
        chunk = sock.recv(min(length - len(payload), 65536))
        if not chunk:
            return None
        payload += chunk

    # Unmask
    if mask_key:
        payload = bytes(p ^ mask_key[i % 4] for i, p in enumerate(payload))

    return payload


def _send_frame(sock: socket.socket, opcode: int, payload: bytes) -> bool:
    """Send a WebSocket frame. Server frames are NEVER masked."""
    frame = bytes([FIN_BIT | opcode])
    length = len(payload)

    if length < 126:
        frame += bytes([length])
    elif length < 65536:
        frame += bytes([126]) + struct.pack("!H", length)
    else:
        frame += bytes([127]) + struct.pack("!Q", length)

    frame += payload

    try:
        sock.sendall(frame)
        return True
    except (ConnectionError, OSError):
        return False


class SimpleWSConnection:
    """A single WebSocket connection handled in its own thread."""

    def __init__(self, sock: socket.socket, addr: tuple, handler: Callable[[dict], dict]):
        self.sock = sock
        self.addr = addr
        self.handler = handler
        self._running = False

    def _do_handshake(self, data: bytes) -> bool:
        """Perform WebSocket upgrade handshake."""
        text = data.decode("utf-8", errors="replace")
        if "Upgrade: websocket" not in text and "upgrade: websocket" not in text.lower():
            return False

        # Extract key
        key = ""
        for line in text.split("\r\n"):
            if line.lower().startswith("sec-websocket-key:"):
                key = line.split(":", 1)[1].strip()
                break

        if not key:
            return False

        accept = _make_accept_key(key)
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n"
            "\r\n"
        )
        try:
            self.sock.sendall(response.encode("ascii"))
            return True
        except (ConnectionError, OSError):
            return False

    def run(self):
        """Main loop: handshake → read frames → dispatch → send responses."""
        self._running = True
        try:
            # Read HTTP upgrade request
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = self.sock.recv(4096)
                if not chunk:
                    return
                data += chunk
                if len(data) > 16384:
                    return

            if not self._do_handshake(data):
                return

            logger.info(f"WS client connected: {self.addr}")

            while self._running:
                payload = _read_frame(self.sock, timeout=60.0)
                if payload is None:
                    break

                try:
                    request = json.loads(payload.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

                response = self.handler(request)
                resp_json = json.dumps(response, default=str)
                if not _send_frame(self.sock, OP_TEXT, resp_json.encode("utf-8")):
                    break

        except Exception as e:
            logger.error(f"WS connection error: {e}")
        finally:
            self._running = False
            try:
                self.sock.close()
            except Exception:
                pass
            logger.info(f"WS client disconnected: {self.addr}")

    def stop(self):
        self._running = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass


class SimpleWSServer:
    """Minimal WebSocket server using socket + threading. No asyncio."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9877):
        self.host = host
        self.port = port
        self._socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._connections: List[SimpleWSConnection] = []
        self._lock = threading.Lock()
        self._handler_fn: Optional[Callable] = None

    def set_handler(self, fn: Callable[[dict], dict]):
        """Set the JSON-RPC handler function."""
        self._handler_fn = fn

    def start(self) -> bool:
        """Start listening on a daemon thread."""
        if self._running:
            return False

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._socket.bind((self.host, self.port))
            self._socket.listen(5)
            self._socket.settimeout(1.0)
        except OSError as e:
            logger.error(f"Bind failed: {e}")
            return False

        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, name="ws-server", daemon=True)
        self._thread.start()
        logger.info(f"WS server listening on ws://{self.host}:{self.port}")
        return True

    def stop(self):
        self._running = False
        with self._lock:
            for conn in self._connections:
                conn.stop()
            self._connections.clear()
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=3.0)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._connections)

    def _accept_loop(self):
        while self._running:
            try:
                client_sock, addr = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            if not self._handler_fn:
                try:
                    client_sock.close()
                except Exception:
                    pass
                continue

            conn = SimpleWSConnection(client_sock, addr, self._handler_fn)
            with self._lock:
                self._connections.append(conn)

            t = threading.Thread(target=self._run_connection, args=(conn,), daemon=True)
            t.start()

    def _run_connection(self, conn: SimpleWSConnection):
        try:
            conn.run()
        finally:
            with self._lock:
                if conn in self._connections:
                    self._connections.remove(conn)
