"""
TCP realtime bridge for USD Composer with named places.

Run inside USD Composer Script Editor:
    import RealtimeTCP.usd_composer_tcp_realtime_bridge as rt
    rt.start_tcp_bridge(host="127.0.0.1", port=5050)

Main protocol (NDJSON, one JSON per line):
{"type":"set_place","palette_id":1,"place":"DEPOT_IN"}
{"type":"move_to_place","palette_id":1,"place":"POSTE_1_ENTRY","duration":1.0}
{"type":"set_visibility","palette_id":1,"visible":true}
"""

from __future__ import annotations

import json
import queue
import socketserver
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple


Vec3 = Tuple[float, float, float]
PLACES_FILE = Path(__file__).with_name("places.json")
CARRIER_USD = Path(__file__).resolve().parents[2] / "3d" / "layout" / "carrier.usd"
CARRIER_SCALE = (0.15, 0.15, 0.15)
PALETTE_SCOPE = "/World/Palettes"
PROTOTYPE_SCOPE = "/World/Prototypes"
PALETTE_TEMPLATE_PATH = f"{PROTOTYPE_SCOPE}/Palette_Template"
PALETTE_PREFIX = f"{PALETTE_SCOPE}/Palette_"


def _point3(values) -> Vec3:
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise ValueError(f"Invalid 3D position: {values}")
    return (float(values[0]), float(values[1]), float(values[2]))


def _path3(values) -> Tuple[Vec3, ...]:
    if not isinstance(values, (list, tuple)) or len(values) < 2:
        raise ValueError(f"Invalid path points: {values}")
    points = tuple(_point3(v) for v in values)
    if len(points) < 2:
        raise ValueError("Path requires at least 2 points.")
    return points


def _distance(a: Vec3, b: Vec3) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def _bool_value(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _palette_path(msg: dict) -> str:
    prim_path = str(msg.get("prim_path") or "").strip()
    if prim_path:
        return prim_path
    palette_id = msg.get("palette_id")
    if palette_id is None:
        raise ValueError("Message requires 'palette_id' or 'prim_path'.")
    return f"/World/Palettes/Palette_{int(palette_id)}"


def _ensure_translate_op(prim):
    from pxr import UsdGeom

    xformable = UsdGeom.Xformable(prim)
    for op in xformable.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            return op
    return xformable.AddTranslateOp()


@dataclass
class _ActiveMove:
    prim_path: str
    start_pos: Vec3
    end_pos: Vec3
    start_ts: float
    duration: float


@dataclass
class _ActivePath:
    prim_path: str
    points: Tuple[Vec3, ...]
    segment_lengths: Tuple[float, ...]
    total_length: float
    start_ts: float
    duration: float


class _LineJsonHandler(socketserver.StreamRequestHandler):
    def handle(self):
        bridge = self.server.bridge  # type: ignore[attr-defined]
        client = f"{self.client_address[0]}:{self.client_address[1]}"
        bridge._log(f"Client connected: {client}")
        try:
            while True:
                line = self.rfile.readline()
                if not line:
                    break

                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue

                try:
                    msg = json.loads(text)
                    if not isinstance(msg, dict):
                        raise ValueError("JSON message must be an object")
                    bridge._inbox.put(msg)
                except Exception as exc:
                    bridge._log(f"Invalid message from {client}: {exc}")
        finally:
            bridge._log(f"Client disconnected: {client}")


class _ThreadingTcpServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


class TcpRealtimeBridge:
    def __init__(self, host: str = "127.0.0.1", port: int = 5050, places_path: Optional[str] = None):
        self.host = str(host)
        self.port = int(port)
        self.places_path = Path(places_path) if places_path else PLACES_FILE
        self.places: Dict[str, Vec3] = {}
        self.zones: Dict[str, Dict[str, Vec3]] = {}
        self._inbox: "queue.Queue[dict]" = queue.Queue()
        self._server: Optional[_ThreadingTcpServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._update_sub = None
        self._active_moves: Dict[str, _ActiveMove] = {}
        self._active_paths: Dict[str, _ActivePath] = {}
        self._last_event_id: Dict[str, int] = {}
        self._last_sim_time: Dict[str, float] = {}
        self._running = False
        self._load_places()

    def _log(self, text: str):
        print(f"[TCP-Bridge] {text}")

    def _load_places(self):
        if not self.places_path.exists():
            self.places = {}
            self.zones = {}
            self._log(f"No places file found: {self.places_path}. Direct coordinate messages remain supported.")
            return
        raw_text = self.places_path.read_text(encoding="utf-8").strip()
        data = json.loads(raw_text) if raw_text else {}
        places: Dict[str, Vec3] = {}
        zones: Dict[str, Dict[str, Vec3]] = {}

        raw_zones = data.get("zones")
        if isinstance(raw_zones, dict):
            for zone_name, raw_zone in raw_zones.items():
                if not isinstance(raw_zone, dict):
                    continue
                zone: Dict[str, Vec3] = {}
                for field in ("entry", "buffer", "processing", "exit"):
                    if field in raw_zone and raw_zone[field] is not None:
                        pos = _point3(raw_zone[field])
                        zone[field] = pos
                        # Compatibility aliases.
                        key_legacy = f"{str(zone_name).upper()}_{field.upper()}"
                        places[key_legacy] = pos
                        key_dot = f"{zone_name}.{field}"
                        places[key_dot] = pos
                zones[str(zone_name)] = zone

        raw_places = data.get("places")
        if isinstance(raw_places, dict):
            for name, coords in raw_places.items():
                places[str(name)] = _point3(coords)

        if not places and not zones:
            self.places = {}
            self.zones = {}
            self._log("places.json contains no places/zones. Direct coordinate messages remain supported.")
            return

        self.zones = zones
        self.places = places
        self._log(
            f"Loaded {len(self.zones)} zones and {len(self.places)} place aliases from {self.places_path}"
        )

    def reload_places(self):
        self._load_places()

    def _resolve_target_position(self, msg: dict, key_position: str, key_place: str) -> Vec3:
        if key_position in msg and msg.get(key_position) is not None:
            return _point3(msg.get(key_position))
        place_name = str(msg.get(key_place) or "").strip()
        if not place_name:
            raise ValueError(f"Message requires '{key_place}' or '{key_position}'")
        if "." in place_name:
            zone_name, field = place_name.split(".", 1)
            zone = self.zones.get(zone_name)
            if zone and field in zone:
                return zone[field]
        if place_name not in self.places:
            raise ValueError(f"Unknown place: {place_name}")
        return self.places[place_name]

    def _get_stage(self):
        import omni.usd

        return omni.usd.get_context().get_stage()

    def _ensure_world_scopes(self, stage):
        from pxr import UsdGeom

        if not stage.GetPrimAtPath("/World").IsValid():
            UsdGeom.Xform.Define(stage, "/World")
        if not stage.GetPrimAtPath(PROTOTYPE_SCOPE).IsValid():
            UsdGeom.Scope.Define(stage, PROTOTYPE_SCOPE)
        if not stage.GetPrimAtPath(PALETTE_SCOPE).IsValid():
            UsdGeom.Scope.Define(stage, PALETTE_SCOPE)

    def _ensure_palette_template(self, stage):
        from pxr import UsdGeom

        prim = stage.GetPrimAtPath(PALETTE_TEMPLATE_PATH)
        if prim.IsValid():
            return

        template_xform = UsdGeom.Xform.Define(stage, PALETTE_TEMPLATE_PATH)
        UsdGeom.Imageable(template_xform.GetPrim()).MakeInvisible()

        if not CARRIER_USD.exists():
            raise FileNotFoundError(f"Carrier USD not found: {CARRIER_USD}")

        carrier_xform = UsdGeom.Xform.Define(stage, f"{PALETTE_TEMPLATE_PATH}/Geometry")
        carrier_xform.GetPrim().GetReferences().ClearReferences()
        carrier_xform.GetPrim().GetReferences().AddReference(CARRIER_USD.as_posix())

    def _ensure_palette_prim(self, prim_path: str, initial_position: Optional[Vec3] = None) -> bool:
        if not str(prim_path).startswith(PALETTE_PREFIX):
            return False

        from pxr import Gf, UsdGeom

        stage = self._get_stage()
        if not stage:
            self._log("No opened stage in USD Composer.")
            return False

        prim = stage.GetPrimAtPath(prim_path)
        if prim.IsValid():
            return True

        self._ensure_world_scopes(stage)
        self._ensure_palette_template(stage)

        xform = UsdGeom.Xform.Define(stage, prim_path)
        prim = xform.GetPrim()
        prim.GetReferences().ClearReferences()
        prim.GetReferences().AddInternalReference(PALETTE_TEMPLATE_PATH)
        UsdGeom.Imageable(prim).MakeVisible()

        start_pos = initial_position if initial_position is not None else (0.0, 0.0, 0.0)
        _ensure_translate_op(UsdGeom.Xformable(prim)).Set(Gf.Vec3d(*start_pos))
        for op in UsdGeom.Xformable(prim).GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeScale:
                op.Set(Gf.Vec3d(*CARRIER_SCALE))
                break
        else:
            UsdGeom.Xformable(prim).AddScaleOp().Set(Gf.Vec3d(*CARRIER_SCALE))

        self._log(f"Auto-created palette prim: {prim_path}")
        return True

    def _set_position(self, prim_path: str, pos: Vec3) -> bool:
        from pxr import Gf

        stage = self._get_stage()
        if not stage:
            self._log("No opened stage in USD Composer.")
            return False
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            self._ensure_palette_prim(prim_path, initial_position=pos)
            prim = stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                self._log(f"Prim not found: {prim_path}")
                return False
        _ensure_translate_op(prim).Set(Gf.Vec3d(*pos))
        return True

    def _set_visibility(self, prim_path: str, visible: bool) -> bool:
        from pxr import UsdGeom

        stage = self._get_stage()
        if not stage:
            self._log("No opened stage in USD Composer.")
            return False
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            self._ensure_palette_prim(prim_path)
            prim = stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                self._log(f"Prim not found: {prim_path}")
                return False

        imageable = UsdGeom.Imageable(prim)
        if visible:
            imageable.MakeVisible()
        else:
            imageable.MakeInvisible()
        return True

    def _get_current_pos(self, prim_path: str) -> Optional[Vec3]:
        from pxr import UsdGeom

        stage = self._get_stage()
        if not stage:
            return None
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            return None

        xform = UsdGeom.Xformable(prim)
        for op in xform.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                vec = op.Get()
                return (float(vec[0]), float(vec[1]), float(vec[2]))
        return (0.0, 0.0, 0.0)

    def _enqueue_linear_move(self, prim_path: str, to_pos: Vec3, duration: float):
        from_pos = self._get_current_pos(prim_path)
        if from_pos is None:
            self._log(f"Cannot start move, prim missing: {prim_path}")
            return
        duration = max(0.001, float(duration))
        self._active_paths.pop(prim_path, None)
        self._active_moves[prim_path] = _ActiveMove(
            prim_path=prim_path,
            start_pos=from_pos,
            end_pos=to_pos,
            start_ts=time.monotonic(),
            duration=duration,
        )

    def _resolve_duration(self, msg: dict, default: float = 0.25) -> float:
        duration = float(msg.get("duration", default))
        duration_scale = float(msg.get("duration_scale", 1.0))
        return max(0.001, duration * duration_scale)

    def _enqueue_path_move(self, prim_path: str, points: Tuple[Vec3, ...], duration: float):
        if duration <= 0:
            self._active_moves.pop(prim_path, None)
            self._active_paths.pop(prim_path, None)
            self._set_position(prim_path, points[-1])
            return

        from_pos = self._get_current_pos(prim_path)
        if from_pos is None:
            from_pos = points[0]
            self._set_position(prim_path, from_pos)

        path_points = points
        if _distance(from_pos, path_points[0]) > 1e-6:
            path_points = (from_pos,) + path_points

        seg_lengths = []
        total = 0.0
        for i in range(len(path_points) - 1):
            seg = _distance(path_points[i], path_points[i + 1])
            seg_lengths.append(seg)
            total += seg

        if total <= 1e-9:
            self._active_moves.pop(prim_path, None)
            self._active_paths.pop(prim_path, None)
            self._set_position(prim_path, path_points[-1])
            return

        self._active_moves.pop(prim_path, None)
        self._active_paths[prim_path] = _ActivePath(
            prim_path=prim_path,
            points=tuple(path_points),
            segment_lengths=tuple(seg_lengths),
            total_length=float(total),
            start_ts=time.monotonic(),
            duration=max(0.001, float(duration)),
        )

    def _handle_message(self, msg: dict):
        msg_type = str(msg.get("type") or "set_place").strip().lower()

        if msg_type == "ping":
            req = msg.get("request_id")
            self._log(f"pong request_id={req}")
            return

        if msg_type == "reload_places":
            self.reload_places()
            return

        prim_path = _palette_path(msg)

        # Drop out-of-order messages when event_id is provided by producer.
        raw_event_id = msg.get("event_id")
        if raw_event_id is not None:
            event_id = int(raw_event_id)
            last = self._last_event_id.get(prim_path)
            if last is not None and event_id <= last:
                return
            self._last_event_id[prim_path] = event_id

        raw_sim_time = msg.get("sim_time")
        if raw_sim_time is not None:
            sim_time = float(raw_sim_time)
            last_sim = self._last_sim_time.get(prim_path)
            if last_sim is not None and sim_time < last_sim - 1e-9:
                return
            self._last_sim_time[prim_path] = sim_time

        if msg_type in ("set_place", "set_position"):
            pos = self._resolve_target_position(msg, key_position="position", key_place="place")
            self._active_moves.pop(prim_path, None)
            self._active_paths.pop(prim_path, None)
            self._set_position(prim_path, pos)
            return

        if msg_type in ("move_to_place", "move_linear"):
            to_pos = self._resolve_target_position(msg, key_position="to", key_place="place")
            duration = self._resolve_duration(msg, default=0.25)
            self._enqueue_linear_move(prim_path, to_pos, duration)
            return

        if msg_type == "move_path":
            points = _path3(msg.get("path"))
            duration = self._resolve_duration(msg, default=0.25)
            self._enqueue_path_move(prim_path, points, duration)
            return

        if msg_type == "set_visibility":
            visible = _bool_value(msg.get("visible"), True)
            self._set_visibility(prim_path, visible)
            return

        self._log(f"Unsupported message type: {msg_type}")

    def _advance_moves(self):
        now = time.monotonic()
        finished = []
        for prim_path, move in list(self._active_moves.items()):
            alpha = (now - move.start_ts) / move.duration
            if alpha >= 1.0:
                self._set_position(prim_path, move.end_pos)
                finished.append(prim_path)
                continue

            alpha = max(0.0, min(1.0, alpha))
            current = (
                move.start_pos[0] + (move.end_pos[0] - move.start_pos[0]) * alpha,
                move.start_pos[1] + (move.end_pos[1] - move.start_pos[1]) * alpha,
                move.start_pos[2] + (move.end_pos[2] - move.start_pos[2]) * alpha,
            )
            self._set_position(prim_path, current)

        for prim_path in finished:
            self._active_moves.pop(prim_path, None)

    def _advance_paths(self):
        now = time.monotonic()
        finished = []

        for prim_path, path in list(self._active_paths.items()):
            alpha = (now - path.start_ts) / path.duration
            if alpha >= 1.0:
                self._set_position(prim_path, path.points[-1])
                finished.append(prim_path)
                continue

            alpha = max(0.0, min(1.0, alpha))
            dist_target = path.total_length * alpha
            walked = 0.0
            current = path.points[-1]

            for i, seg_len in enumerate(path.segment_lengths):
                if seg_len <= 1e-12:
                    walked += seg_len
                    continue
                if walked + seg_len >= dist_target:
                    local_alpha = (dist_target - walked) / seg_len
                    a = path.points[i]
                    b = path.points[i + 1]
                    current = (
                        a[0] + (b[0] - a[0]) * local_alpha,
                        a[1] + (b[1] - a[1]) * local_alpha,
                        a[2] + (b[2] - a[2]) * local_alpha,
                    )
                    break
                walked += seg_len

            self._set_position(prim_path, current)

        for prim_path in finished:
            self._active_paths.pop(prim_path, None)

    def _on_update(self, _event):
        max_per_frame = 200
        count = 0
        while count < max_per_frame:
            try:
                msg = self._inbox.get_nowait()
            except queue.Empty:
                break

            try:
                self._handle_message(msg)
            except Exception as exc:
                self._log(f"Message handling error: {exc}; msg={msg}")
            count += 1

        if self._active_moves:
            self._advance_moves()
        if self._active_paths:
            self._advance_paths()

    def start(self):
        if self._running:
            self._log(f"Already running on {self.host}:{self.port}")
            return

        import omni.kit.app

        self._server = _ThreadingTcpServer((self.host, self.port), _LineJsonHandler)
        self._server.bridge = self  # type: ignore[attr-defined]
        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            name="UsdComposerTcpBridge",
            daemon=True,
        )
        self._server_thread.start()

        stream = omni.kit.app.get_app().get_update_event_stream()
        self._update_sub = stream.create_subscription_to_pop(
            self._on_update,
            name="UsdComposerTcpBridgeUpdate",
        )

        self._running = True
        self._log(f"Listening on tcp://{self.host}:{self.port}")

    def stop(self):
        if not self._running:
            return

        if self._update_sub is not None:
            self._update_sub = None
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._server_thread is not None:
            self._server_thread.join(timeout=1.0)
            self._server_thread = None

        self._active_moves.clear()
        self._active_paths.clear()
        self._last_event_id.clear()
        self._last_sim_time.clear()
        self._running = False
        self._log("Stopped")

    def status(self) -> dict:
        return {
            "running": self._running,
            "host": self.host,
            "port": self.port,
            "places_path": str(self.places_path),
            "zones_count": len(self.zones),
            "places_count": len(self.places),
            "queued_messages": self._inbox.qsize(),
            "active_moves": len(self._active_moves),
            "active_paths": len(self._active_paths),
            "tracked_event_ids": len(self._last_event_id),
            "tracked_sim_times": len(self._last_sim_time),
        }


_BRIDGE: Optional[TcpRealtimeBridge] = None


def start_tcp_bridge(host: str = "127.0.0.1", port: int = 5050, places_path: Optional[str] = None) -> TcpRealtimeBridge:
    global _BRIDGE
    if _BRIDGE is not None:
        _BRIDGE.stop()
    _BRIDGE = TcpRealtimeBridge(host=host, port=port, places_path=places_path)
    _BRIDGE.start()
    return _BRIDGE


def stop_tcp_bridge():
    global _BRIDGE
    if _BRIDGE is not None:
        _BRIDGE.stop()
        _BRIDGE = None


def bridge_status() -> dict:
    if _BRIDGE is None:
        return {
            "running": False,
            "host": None,
            "port": None,
            "places_path": None,
            "zones_count": 0,
            "places_count": 0,
            "queued_messages": 0,
            "active_moves": 0,
            "active_paths": 0,
            "tracked_event_ids": 0,
            "tracked_sim_times": 0,
        }
    return _BRIDGE.status()


def reload_places():
    if _BRIDGE is None:
        raise RuntimeError("Bridge is not started.")
    _BRIDGE.reload_places()
