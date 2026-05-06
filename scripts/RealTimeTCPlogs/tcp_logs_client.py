from __future__ import annotations

import json
import socket
from typing import Any, Dict, Optional


class TcpLogsClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 5051, timeout: float = 2.0):
        self.host = str(host)
        self.port = int(port)
        self.timeout = float(timeout)
        self._sock: Optional[socket.socket] = None

    def connect(self):
        if self._sock is None:
            self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        return self

    def close(self):
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def send(self, payload: Dict[str, Any]):
        if self._sock is None:
            self.connect()
        wire = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        self._sock.sendall(wire)  # type: ignore[union-attr]

    def ping(self, request_id: str = "ping"):
        self.send({"type": "ping", "request_id": request_id})

    def set_position(self, carrier_id: int, position, event_id: Optional[int] = None):
        msg: Dict[str, Any] = {
            "type": "set_position",
            "carrier_id": int(carrier_id),
            "position": [float(position[0]), float(position[1]), float(position[2])],
        }
        if event_id is not None:
            msg["event_id"] = int(event_id)
        self.send(msg)

    def move_path(self, carrier_id: int, path, duration: float, event_id: Optional[int] = None):
        msg: Dict[str, Any] = {
            "type": "move_path",
            "carrier_id": int(carrier_id),
            "path": [[float(p[0]), float(p[1]), float(p[2])] for p in path],
            "duration": float(duration),
        }
        if event_id is not None:
            msg["event_id"] = int(event_id)
        self.send(msg)

    def set_visibility(self, carrier_id: int, visible: bool, event_id: Optional[int] = None):
        msg: Dict[str, Any] = {
            "type": "set_visibility",
            "carrier_id": int(carrier_id),
            "visible": bool(visible),
        }
        if event_id is not None:
            msg["event_id"] = int(event_id)
        self.send(msg)

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc, tb):
        self.close()
