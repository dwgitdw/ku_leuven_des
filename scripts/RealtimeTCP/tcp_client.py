"""
TCP client helpers for named-place realtime messages.
"""

from __future__ import annotations

import json
import socket
from typing import Any, Dict, Optional


class TcpRealtimeClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 5050, timeout: float = 2.0):
        self.host = host
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

    def set_place(self, palette_id: int, place: str, prim_path: Optional[str] = None):
        msg: Dict[str, Any] = {"type": "set_place", "palette_id": int(palette_id), "place": str(place)}
        if prim_path:
            msg["prim_path"] = str(prim_path)
        self.send(msg)

    def move_to_place(self, palette_id: int, place: str, duration: float = 0.25, prim_path: Optional[str] = None):
        msg: Dict[str, Any] = {
            "type": "move_to_place",
            "palette_id": int(palette_id),
            "place": str(place),
            "duration": float(duration),
        }
        if prim_path:
            msg["prim_path"] = str(prim_path)
        self.send(msg)

    def set_visibility(self, palette_id: int, visible: bool, prim_path: Optional[str] = None):
        msg: Dict[str, Any] = {"type": "set_visibility", "palette_id": int(palette_id), "visible": bool(visible)}
        if prim_path:
            msg["prim_path"] = str(prim_path)
        self.send(msg)

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc, tb):
        self.close()

