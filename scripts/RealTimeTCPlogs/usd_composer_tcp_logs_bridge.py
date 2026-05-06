"""
TCP bridge for RealTimeTCPlogs.

Run inside USD Composer Script Editor:
    import RealTimeTCPlogs.usd_composer_tcp_logs_bridge as rtlogs
    rtlogs.start_tcp_bridge(host="127.0.0.1", port=5051)
"""

from __future__ import annotations

import json
import queue
import socketserver
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Dict, Optional, Tuple


Vec3 = Tuple[float, float, float]
CARRIER_USD = Path(__file__).resolve().parents[2] / "3d" / "layout" / "carrier.usd"
CARRIER_SCALE = (0.15, 0.15, 0.15)
ROOT_SCOPE = "/World/RealTimeTCPlogs"
CARRIER_SCOPE = f"{ROOT_SCOPE}/Carriers"
PROTOTYPE_SCOPE = f"{ROOT_SCOPE}/Prototypes"
CARRIER_TEMPLATE_PATH = f"{PROTOTYPE_SCOPE}/Carrier_Template"
CARRIER_PREFIX = f"{CARRIER_SCOPE}/Carrier_"


def _point3(values) -> Vec3:
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise ValueError(f"Invalid 3D position: {values}")
    return (float(values[0]), float(values[1]), float(values[2]))


def _path3(values) -> Tuple[Vec3, ...]:
    if not isinstance(values, (list, tuple)) or len(values) < 2:
        raise ValueError(f"Invalid path points: {values}")
    return tuple(_point3(v) for v in values)


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


def _carrier_path(msg: dict) -> str:
    prim_path = str(msg.get("prim_path") or "").strip()
    if prim_path:
        return prim_path
    carrier_id = msg.get("carrier_id", msg.get("palette_id"))
    if carrier_id is None:
        raise ValueError("Message requires 'carrier_id' or 'prim_path'.")
    return f"{CARRIER_PREFIX}{int(carrier_id)}"


def _ensure_translate_op(prim):
    from pxr import UsdGeom

    xformable = UsdGeom.Xformable(prim)
    for op in xformable.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            return op
    return xformable.AddTranslateOp()


@dataclass
class _ActivePath:
    prim_path: str
    points: Tuple[Vec3, ...]
    segment_lengths: Tuple[float, ...]
    total_length: float
    start_ts: float
    duration: float
    segment_durations: Optional[Tuple[float, ...]] = None


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
                    bridge._received_count += 1
                    if bridge.debug and bridge._received_count <= 20:
                        bridge._log(
                            f"Received #{bridge._received_count}: "
                            f"type={msg.get('type')} carrier={msg.get('carrier_id')} event_id={msg.get('event_id')}"
                        )
                    bridge._inbox.put(msg)
                except Exception as exc:
                    bridge._log(f"Invalid message from {client}: {exc}")
        finally:
            bridge._log(f"Client disconnected: {client}")


class _ThreadingTcpServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


class TcpLogsBridge:
    def __init__(self, host: str = "127.0.0.1", port: int = 5051, debug: bool = False):
        self.host = str(host)
        self.port = int(port)
        self.debug = bool(debug)
        self._inbox: "queue.Queue[dict]" = queue.Queue()
        self._server: Optional[_ThreadingTcpServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._update_sub = None
        self._active_paths: Dict[str, _ActivePath] = {}
        self._pending_messages: Dict[str, Deque[dict]] = {}
        self._last_event_id: Dict[str, int] = {}
        self._received_count = 0
        self._handled_count = 0
        self._last_debug_ts = 0.0
        self._running = False

    def _log(self, text: str):
        print(f"[RealTimeTCPlogs-Bridge] {text}")

    def _get_stage(self):
        import omni.usd

        return omni.usd.get_context().get_stage()

    def _ensure_scopes(self, stage):
        from pxr import UsdGeom

        for path in (ROOT_SCOPE, PROTOTYPE_SCOPE, CARRIER_SCOPE):
            if not stage.GetPrimAtPath(path).IsValid():
                UsdGeom.Xform.Define(stage, path)

    def _ensure_template(self, stage):
        from pxr import UsdGeom

        prim = stage.GetPrimAtPath(CARRIER_TEMPLATE_PATH)
        if prim.IsValid():
            return

        template = UsdGeom.Xform.Define(stage, CARRIER_TEMPLATE_PATH)
        UsdGeom.Imageable(template.GetPrim()).MakeInvisible()

        if not CARRIER_USD.exists():
            raise FileNotFoundError(f"Carrier USD not found: {CARRIER_USD}")
        carrier_xform = UsdGeom.Xform.Define(stage, f"{CARRIER_TEMPLATE_PATH}/Geometry")
        carrier_xform.GetPrim().GetReferences().ClearReferences()
        carrier_xform.GetPrim().GetReferences().AddReference(CARRIER_USD.as_posix())

    def _ensure_carrier(self, prim_path: str) -> bool:
        if not str(prim_path).startswith(CARRIER_PREFIX):
            return False

        from pxr import Gf, UsdGeom

        stage = self._get_stage()
        if not stage:
            self._log("No opened stage in USD Composer.")
            return False

        prim = stage.GetPrimAtPath(prim_path)
        if prim.IsValid():
            return True

        self._ensure_scopes(stage)
        self._ensure_template(stage)

        xform = UsdGeom.Xform.Define(stage, prim_path)
        prim = xform.GetPrim()
        prim.GetReferences().ClearReferences()
        prim.GetReferences().AddInternalReference(CARRIER_TEMPLATE_PATH)
        UsdGeom.Imageable(prim).MakeVisible()
        _ensure_translate_op(prim).Set(Gf.Vec3d(0.0, 0.0, 0.0))
        UsdGeom.Xformable(prim).AddScaleOp().Set(Gf.Vec3d(*CARRIER_SCALE))
        self._log(f"Auto-created carrier prim: {prim_path}")
        return True

    def _set_position(self, prim_path: str, pos: Vec3) -> bool:
        from pxr import Gf

        stage = self._get_stage()
        if not stage:
            self._log("No opened stage in USD Composer.")
            return False
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            self._ensure_carrier(prim_path)
            prim = stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                self._log(f"Prim not found: {prim_path}")
                return False
        _ensure_translate_op(prim).Set(Gf.Vec3d(*pos))
        if self.debug:
            now = time.monotonic()
            if now - self._last_debug_ts >= 1.0:
                self._last_debug_ts = now
                self._log(
                    f"Applied position: {prim_path} -> "
                    f"({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f}); active_paths={len(self._active_paths)}"
                )
        return True

    def _set_visibility(self, prim_path: str, visible: bool) -> bool:
        from pxr import UsdGeom

        stage = self._get_stage()
        if not stage:
            self._log("No opened stage in USD Composer.")
            return False
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            self._ensure_carrier(prim_path)
            prim = stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
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
            self._ensure_carrier(prim_path)
            prim = stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                return None
        for op in UsdGeom.Xformable(prim).GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                vec = op.Get()
                return (float(vec[0]), float(vec[1]), float(vec[2]))
        return (0.0, 0.0, 0.0)

    def _enqueue_path(self, prim_path: str, points: Tuple[Vec3, ...], duration: float):
        if duration <= 0:
            self._active_paths.pop(prim_path, None)
            self._set_position(prim_path, points[-1])
            return

        from_pos = self._get_current_pos(prim_path)
        if from_pos is None:
            return
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
            self._set_position(prim_path, path_points[-1])
            return

        self._active_paths[prim_path] = _ActivePath(
            prim_path=prim_path,
            points=tuple(path_points),
            segment_lengths=tuple(seg_lengths),
            total_length=float(total),
            start_ts=time.monotonic(),
            duration=max(0.001, float(duration)),
        )

    def _enqueue_timed_path(self, prim_path: str, raw_segments):
        if not isinstance(raw_segments, (list, tuple)) or not raw_segments:
            raise ValueError("move_timed_path requires a non-empty 'segments' list.")

        points = []
        durations = []
        for raw_segment in raw_segments:
            if not isinstance(raw_segment, dict):
                raise ValueError("Each timed segment must be an object.")
            segment_path = list(_path3(raw_segment.get("path")))
            segment_duration = max(0.0, float(raw_segment.get("duration", 0.0)))
            if len(segment_path) < 2:
                continue

            if not points:
                points.append(segment_path[0])
            elif _distance(points[-1], segment_path[0]) > 1e-6:
                segment_path[0] = points[-1]

            lengths = []
            total = 0.0
            for i in range(len(segment_path) - 1):
                seg_len = _distance(segment_path[i], segment_path[i + 1])
                lengths.append(seg_len)
                total += seg_len

            for i, seg_len in enumerate(lengths):
                if total > 1e-9:
                    step_duration = segment_duration * (seg_len / total)
                else:
                    step_duration = segment_duration / max(1, len(lengths))
                points.append(segment_path[i + 1])
                durations.append(max(0.001, float(step_duration)))

        if len(points) < 2:
            return

        from_pos = self._get_current_pos(prim_path)
        if from_pos is None:
            return
        if _distance(from_pos, points[0]) > 1e-6:
            points[0] = from_pos

        segment_lengths = []
        total_length = 0.0
        for i in range(len(points) - 1):
            seg_len = _distance(points[i], points[i + 1])
            segment_lengths.append(seg_len)
            total_length += seg_len

        total_duration = sum(durations)
        if total_duration <= 0:
            self._set_position(prim_path, points[-1])
            return

        self._active_paths[prim_path] = _ActivePath(
            prim_path=prim_path,
            points=tuple(points),
            segment_lengths=tuple(segment_lengths),
            total_length=float(total_length),
            start_ts=time.monotonic(),
            duration=max(0.001, float(total_duration)),
            segment_durations=tuple(durations),
        )
        if self.debug:
            self._log(f"Queued timed path: {prim_path}, points={len(points)}, duration={total_duration:.3f}s")

    def _queue_or_start_motion(self, prim_path: str, msg: dict):
        if prim_path in self._active_paths:
            self._pending_messages.setdefault(prim_path, deque()).append(dict(msg))
            if self.debug:
                self._log(
                    f"Queued behind active move: {prim_path}, "
                    f"type={msg.get('type')}, pending={len(self._pending_messages[prim_path])}"
                )
            return
        self._start_motion_message(prim_path, msg)

    def _start_motion_message(self, prim_path: str, msg: dict):
        msg_type = str(msg.get("type") or "set_position").strip().lower()

        if msg_type == "set_position":
            self._active_paths.pop(prim_path, None)
            self._set_position(prim_path, _point3(msg.get("position")))
            return

        if msg_type == "move_path":
            self._enqueue_path(prim_path, _path3(msg.get("path")), float(msg.get("duration", 0.25)))
            return

        if msg_type == "move_timed_path":
            self._enqueue_timed_path(prim_path, msg.get("segments"))
            return

        if msg_type == "move_linear":
            current = self._get_current_pos(prim_path)
            target = _point3(msg.get("to"))
            if current is None:
                current = target
            self._enqueue_path(prim_path, (current, target), float(msg.get("duration", 0.25)))
            return

        if msg_type == "set_visibility":
            self._set_visibility(prim_path, _bool_value(msg.get("visible"), True))
            return

        self._log(f"Unsupported message type: {msg_type}")

    def _start_next_pending(self, prim_path: str):
        while prim_path not in self._active_paths:
            pending = self._pending_messages.get(prim_path)
            if not pending:
                self._pending_messages.pop(prim_path, None)
                return

            msg = pending.popleft()
            if not pending:
                self._pending_messages.pop(prim_path, None)

            try:
                self._start_motion_message(prim_path, msg)
            except Exception as exc:
                self._log(f"Pending message failed: {exc}; msg={msg}")

    def _handle_message(self, msg: dict):
        msg_type = str(msg.get("type") or "set_position").strip().lower()
        if msg_type == "ping":
            self._log(f"pong request_id={msg.get('request_id')}")
            return

        prim_path = _carrier_path(msg)
        self._handled_count += 1
        if self.debug and self._handled_count <= 20:
            self._log(f"Handling #{self._handled_count}: type={msg_type} prim={prim_path}")
        raw_event_id = msg.get("event_id")
        if raw_event_id is not None:
            event_id = int(raw_event_id)
            last = self._last_event_id.get(prim_path)
            if last is not None and event_id <= last:
                return
            self._last_event_id[prim_path] = event_id

        if msg_type == "set_visibility":
            self._set_visibility(prim_path, _bool_value(msg.get("visible"), True))
            return

        self._queue_or_start_motion(prim_path, msg)

    def _advance_paths(self):
        now = time.monotonic()
        finished = []
        for prim_path, path in list(self._active_paths.items()):
            alpha = (now - path.start_ts) / path.duration
            if alpha >= 1.0:
                self._set_position(prim_path, path.points[-1])
                finished.append(prim_path)
                continue

            if path.segment_durations:
                elapsed = now - path.start_ts
                walked_time = 0.0
                current = path.points[-1]
                for i, segment_duration in enumerate(path.segment_durations):
                    if walked_time + segment_duration >= elapsed:
                        local = 0.0 if segment_duration <= 1e-12 else (elapsed - walked_time) / segment_duration
                        local = max(0.0, min(1.0, local))
                        a = path.points[i]
                        b = path.points[i + 1]
                        current = (
                            a[0] + (b[0] - a[0]) * local,
                            a[1] + (b[1] - a[1]) * local,
                            a[2] + (b[2] - a[2]) * local,
                        )
                        break
                    walked_time += segment_duration
                self._set_position(prim_path, current)
                continue

            dist_target = path.total_length * max(0.0, min(1.0, alpha))
            walked = 0.0
            current = path.points[-1]
            for i, seg_len in enumerate(path.segment_lengths):
                if walked + seg_len >= dist_target:
                    local = 0.0 if seg_len <= 1e-12 else (dist_target - walked) / seg_len
                    a = path.points[i]
                    b = path.points[i + 1]
                    current = (
                        a[0] + (b[0] - a[0]) * local,
                        a[1] + (b[1] - a[1]) * local,
                        a[2] + (b[2] - a[2]) * local,
                    )
                    break
                walked += seg_len
            self._set_position(prim_path, current)

        for prim_path in finished:
            self._active_paths.pop(prim_path, None)
            self._start_next_pending(prim_path)

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
                self._log(f"Message failed: {exc}; msg={msg}")
            count += 1
        self._advance_paths()

    def start(self):
        if self._running:
            return self
        import omni.kit.app

        self._server = _ThreadingTcpServer((self.host, self.port), _LineJsonHandler)
        self._server.bridge = self  # type: ignore[attr-defined]
        self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._server_thread.start()

        stream = omni.kit.app.get_app().get_update_event_stream()
        self._update_sub = stream.create_subscription_to_pop(self._on_update, name="RealTimeTCPlogs Bridge")
        self._running = True
        self._log(f"Listening on tcp://{self.host}:{self.port}")
        return self

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
        self._active_paths.clear()
        self._pending_messages.clear()
        self._last_event_id.clear()
        self._running = False
        self._log("Stopped")

    def status(self) -> dict:
        return {
            "running": self._running,
            "host": self.host,
            "port": self.port,
            "active_paths": len(self._active_paths),
            "pending_messages": sum(len(items) for items in self._pending_messages.values()),
            "tracked_event_ids": len(self._last_event_id),
            "received_messages": self._received_count,
            "handled_messages": self._handled_count,
            "queued_messages": self._inbox.qsize(),
            "debug": self.debug,
        }


_BRIDGE: Optional[TcpLogsBridge] = None


def start_tcp_bridge(host: str = "127.0.0.1", port: int = 5051, debug: bool = False) -> TcpLogsBridge:
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = TcpLogsBridge(host=host, port=port, debug=debug)
    else:
        _BRIDGE.debug = bool(debug)
    return _BRIDGE.start()


def stop_tcp_bridge():
    global _BRIDGE
    if _BRIDGE is not None:
        _BRIDGE.stop()
        _BRIDGE = None


def bridge_status() -> dict:
    if _BRIDGE is None:
        return {"running": False, "host": "127.0.0.1", "port": 5051}
    return _BRIDGE.status()


def bridge_self_test(carrier_id: int = 999, duration: float = 8.0):
    """Create one carrier and move it visibly without using TCP or logs."""
    bridge = start_tcp_bridge()
    start = (0.0, 0.0, 900.0)
    end = (1200.0, 0.0, 900.0)
    prim_path = f"{CARRIER_PREFIX}{int(carrier_id)}"
    bridge._set_position(prim_path, start)
    bridge._set_visibility(prim_path, True)
    bridge._enqueue_path(prim_path, (start, end), float(duration))
    bridge._log(f"Self-test moving carrier {carrier_id}: {start} -> {end} in {float(duration):.1f}s")
    return bridge.status()
