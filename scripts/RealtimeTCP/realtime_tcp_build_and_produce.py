from pathlib import Path
import json
import argparse
import time
import sys
from collections import deque
from typing import Dict, Optional, Tuple
import simpy
try:
    from simpy.rt import RealtimeEnvironment
except Exception:
    RealtimeEnvironment = None  # type: ignore[assignment]

try:
    from RealtimeTCP.tcp_client import TcpRealtimeClient
except Exception:
    # Allows execution as: python scripts/RealtimeTCP/realtime_tcp_build_and_produce.py
    from tcp_client import TcpRealtimeClient  # type: ignore

# ====================
# CONFIGURATION
# ====================
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from marker_layout import resolve_layout_markers

COMPOSER_STAGE_USD = PROJECT_ROOT / "3d" / "RealtimeTCP" / "model.usd"
CONFIG_JSON = SCRIPT_DIR / "production_layout_realtime.json"
FALLBACK_TIMELINE_FPS = 24.0


def load_config():
    if not CONFIG_JSON.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_JSON}")
    with CONFIG_JSON.open("r", encoding="utf-8") as f:
        return resolve_layout_markers(json.load(f), PROJECT_ROOT)


CONFIG = load_config()


# ====================
# UTILITIES
# ====================

def distance(pos1, pos2):
    return ((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2 + (pos1[2] - pos2[2]) ** 2) ** 0.5


def calculate_transport_time(waypoints, speed):
    return sum(
        duration
        for _, _, duration, _ in iter_motion_segments(waypoints, speed)
    )


def same_position(pos1, pos2, tolerance=1e-6):
    return distance(pos1, pos2) <= tolerance


def transfer_for_segment(start_pos, end_pos):
    for name, config in CONFIG.get("transfers", {}).items():
        if same_position(start_pos, tuple(config["from"])) and same_position(end_pos, tuple(config["to"])):
            return name, config
    return None, None


def segment_transport_time(start_pos, end_pos, speed):
    transfer_name, transfer_config = transfer_for_segment(start_pos, end_pos)
    if transfer_config:
        return float(transfer_config["duration"]), transfer_name
    if speed <= 0:
        raise ValueError("transport_speed must be > 0")
    return distance(start_pos, end_pos) / speed, None


def iter_motion_segments(waypoints, speed):
    path = clean_waypoints(waypoints)
    for i in range(len(path) - 1):
        start_pos = tuple(path[i])
        end_pos = tuple(path[i + 1])
        duration, transfer_name = segment_transport_time(start_pos, end_pos, speed)
        yield start_pos, end_pos, duration, transfer_name


def interpolate_position(pos1, pos2, fraction):
    return tuple(pos1[i] + (pos2[i] - pos1[i]) * fraction for i in range(3))


def clean_waypoints(waypoints):
    if not waypoints:
        return []
    cleaned = [tuple(waypoints[0])]
    for p in waypoints[1:]:
        p = tuple(p)
        if p != cleaned[-1]:
            cleaned.append(p)
    return cleaned


def split_path_with_durations(path, total_duration: float):
    cleaned = clean_waypoints(path)
    if len(cleaned) <= 1:
        return []

    total_dist = sum(distance(cleaned[i], cleaned[i + 1]) for i in range(len(cleaned) - 1))
    if total_dist <= 0:
        return []

    chunks = []
    for i in range(len(cleaned) - 1):
        start = cleaned[i]
        end = cleaned[i + 1]
        seg_dist = distance(start, end)
        if seg_dist <= 0:
            continue
        seg_duration = float(total_duration) * (seg_dist / total_dist)
        chunks.append((start, end, seg_duration))
    return chunks


class RealtimeEventLogger:
    """
    Writes simulation events as NDJSON lines:
    {"t": <sim_seconds>, "msg": {...tcp_message...}}
    """

    def __init__(self, output_path: Path):
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.output_path.open("w", encoding="utf-8", newline="\n")

    def close(self):
        if self._fh:
            self._fh.close()
            self._fh = None

    def _write(self, sim_time: float, msg: dict):
        record = {"t": float(sim_time), "msg": msg}
        self._fh.write(json.dumps(record, separators=(",", ":")) + "\n")
        self._fh.flush()

    def set_position(self, palette_id: int, position, sim_time: float, metadata: Optional[Dict] = None):
        msg = {
            "type": "set_position",
            "palette_id": int(palette_id),
            "position": [float(position[0]), float(position[1]), float(position[2])],
        }
        if metadata:
            msg.update(metadata)
        self._write(
            sim_time,
            msg,
        )

    def move_linear(
        self,
        palette_id: int,
        to_pos,
        duration: float,
        sim_time: float,
        metadata: Optional[Dict] = None,
    ):
        msg = {
            "type": "move_linear",
            "palette_id": int(palette_id),
            "to": [float(to_pos[0]), float(to_pos[1]), float(to_pos[2])],
            "duration": float(duration),
        }
        if metadata:
            msg.update(metadata)
        self._write(sim_time, msg)

    def move_path(
        self,
        palette_id: int,
        path_points,
        duration: float,
        sim_time: float,
        metadata: Optional[Dict] = None,
    ):
        msg = {
            "type": "move_path",
            "palette_id": int(palette_id),
            "path": [[float(p[0]), float(p[1]), float(p[2])] for p in path_points],
            "duration": float(duration),
        }
        if metadata:
            msg.update(metadata)
        self._write(sim_time, msg)

    def emit_path(self, palette_id: int, waypoints, start_time: float, duration: float):
        path = clean_waypoints(waypoints)
        if not path:
            return
        if len(path) == 1 or duration <= 0:
            self.set_position(palette_id, path[-1], start_time)
            return

        # Keep one atomic path event so file replay does not receive
        # future sub-segments out of order in the NDJSON stream.
        self.move_path(
            palette_id=palette_id,
            path_points=path,
            duration=duration,
            sim_time=start_time,
        )

    def seed_initial_positions(self, config: dict):
        base_pos = tuple(config["palette_template"]["initial_position"])
        spacing = config["palette_template"].get("initial_spacing", 5.0)
        num_palettes = config["simulation_params"]["num_palettes"]

        for palette_id in range(1, num_palettes + 1):
            offset = (palette_id - 1) * spacing
            pos = (base_pos[0] - offset, base_pos[1], base_pos[2])
            self.set_position(palette_id, pos, 0.0)


class LiveTcpEmitter:
    """
    Sends realtime messages to USD Composer bridge over one persistent TCP socket.
    """

    def __init__(self, host: str, port: int, timeout: float = 2.0, duration_scale: float = 1.0):
        self.host = str(host)
        self.port = int(port)
        self.timeout = float(timeout)
        self.duration_scale = float(duration_scale)
        if self.duration_scale <= 0:
            raise ValueError("duration_scale must be > 0")
        self._client = TcpRealtimeClient(self.host, self.port, timeout=self.timeout)
        self._connected = False

    def connect(self):
        if self._connected:
            return

        last_exc: Optional[Exception] = None
        for _ in range(30):
            try:
                self._client.connect()
                self._connected = True
                return
            except Exception as exc:
                last_exc = exc
                time.sleep(0.5)

        raise RuntimeError(
            f"Unable to connect to USD Composer bridge at tcp://{self.host}:{self.port}. "
            "Check that Composer is running and the RealtimeTCP Auto Bridge is ON."
        ) from last_exc

    def close(self):
        self._client.close()
        self._connected = False

    def _send(self, payload: dict):
        if not self._connected:
            self.connect()
        try:
            self._client.send(payload)
        except OSError:
            # One transparent reconnect attempt for transient socket drops.
            self.close()
            self.connect()
            self._client.send(payload)

    def _scaled_duration(self, sim_duration: float) -> float:
        return max(0.001, float(sim_duration) * self.duration_scale)

    def set_position(self, palette_id: int, position, sim_time: float, event_id: Optional[int] = None):
        payload = {
            "type": "set_position",
            "palette_id": int(palette_id),
            "position": [float(position[0]), float(position[1]), float(position[2])],
            "sim_time": float(sim_time),
        }
        if event_id is not None:
            payload["event_id"] = int(event_id)
        self._send(payload)

    def move_linear(
        self,
        palette_id: int,
        to_pos,
        duration: float,
        sim_time: float,
        event_id: Optional[int] = None,
    ):
        payload = {
            "type": "move_linear",
            "palette_id": int(palette_id),
            "to": [float(to_pos[0]), float(to_pos[1]), float(to_pos[2])],
            "duration": self._scaled_duration(duration),
            "sim_duration": float(duration),
            "sim_time": float(sim_time),
        }
        if event_id is not None:
            payload["event_id"] = int(event_id)
        self._send(payload)

    def move_path(
        self,
        palette_id: int,
        path_points,
        duration: float,
        sim_time: float,
        event_id: Optional[int] = None,
    ):
        payload = {
            "type": "move_path",
            "palette_id": int(palette_id),
            "path": [[float(p[0]), float(p[1]), float(p[2])] for p in path_points],
            "duration": self._scaled_duration(duration),
            "sim_duration": float(duration),
            "sim_time": float(sim_time),
        }
        if event_id is not None:
            payload["event_id"] = int(event_id)
        self._send(payload)


# ====================
# CONVEYOR / QUEUE GEOMETRY
# ====================

class ConveyorSegment:
    def __init__(self, env, name, config):
        self.env = env
        self.name = name
        self.waypoints = [tuple(wp) for wp in config["waypoints"]]
        self.capacity = config.get("capacity", 1)
        self.slot_spacing = config.get("slot_spacing", 10)
        self.is_queue = config.get("is_queue_zone", False)
        self.extend_after_end = config.get("extend_after_end", False)
        self.resource = simpy.Resource(env, capacity=self.capacity)

    def get_slot_position(self, slot_index):
        """
        slot 0 = queue head = end of waypoints.
        following slots go backward from the end toward the start.
        """
        if self.is_queue and len(self.waypoints) >= 2:
            slot_count = max(1, int(self.capacity))
            if slot_count <= 1 or slot_index <= 0:
                return self.waypoints[-1]
            bounded_index = min(int(slot_index), slot_count - 1)
            fraction = 1.0 - (bounded_index / (slot_count - 1))
            return interpolate_position(self.waypoints[0], self.waypoints[-1], fraction)

        if slot_index == 0:
            return self.waypoints[-1]

        offset = slot_index * self.slot_spacing

        if self.extend_after_end and len(self.waypoints) >= 2:
            p0 = self.waypoints[-2]
            p1 = self.waypoints[-1]
            vx = p1[0] - p0[0]
            vy = p1[1] - p0[1]
            vz = p1[2] - p0[2]
            norm = (vx * vx + vy * vy + vz * vz) ** 0.5
            if norm > 0:
                ux, uy, uz = vx / norm, vy / norm, vz / norm
                return (p1[0] + ux * offset, p1[1] + uy * offset, p1[2] + uz * offset)

        remaining = offset

        for i in range(len(self.waypoints) - 1, 0, -1):
            seg_length = distance(self.waypoints[i - 1], self.waypoints[i])
            if remaining <= seg_length:
                fraction = 1 - (remaining / seg_length)
                return interpolate_position(self.waypoints[i - 1], self.waypoints[i], fraction)
            remaining -= seg_length

        # If the queue exceeds the defined geometry, extend behind the spawn point.
        if len(self.waypoints) >= 2:
            p0 = self.waypoints[0]
            p1 = self.waypoints[1]
            vx = p1[0] - p0[0]
            vy = p1[1] - p0[1]
            vz = p1[2] - p0[2]
            norm = (vx * vx + vy * vy + vz * vz) ** 0.5
            if norm > 0:
                ux, uy, uz = vx / norm, vy / norm, vz / norm
                return (p0[0] - ux * remaining, p0[1] - uy * remaining, p0[2] - uz * remaining)

        return self.waypoints[0]


class MemoryBridge:
    """
    Minimal bridge used when running simulation without USD export.
    """

    def __init__(self):
        self.current_positions = {}

    def add_keyframe(self, palette_id, position, time_value):
        self.set_current_position(palette_id, position)

    def get_current_position(self, palette_id):
        return self.current_positions.get(palette_id)

    def set_current_position(self, palette_id, position):
        self.current_positions[palette_id] = tuple(float(v) for v in position)

    def add_path(self, palette_id, waypoints, start_time, duration):
        path = clean_waypoints(waypoints)
        if path:
            self.set_current_position(palette_id, path[-1])
        return start_time + max(0.0, float(duration))

    def seed_initial_positions(self):
        base_pos = tuple(CONFIG["palette_template"]["initial_position"])
        spacing = CONFIG["palette_template"].get("initial_spacing", 5.0)
        num_palettes = CONFIG["simulation_params"]["num_palettes"]

        for palette_id in range(1, num_palettes + 1):
            offset = (palette_id - 1) * spacing
            pos = (base_pos[0] - offset, base_pos[1], base_pos[2])
            self.set_current_position(palette_id, pos)


# ====================
# PRODUCTION LINE
# ====================

class ProductionLine:
    def __init__(
        self,
        env,
        bridge,
        realtime_logger: Optional[RealtimeEventLogger] = None,
        live_emitter: Optional[LiveTcpEmitter] = None,
    ):
        self.env = env
        self.bridge = bridge
        self.realtime_logger = realtime_logger
        self.live_emitter = live_emitter
        self._event_seq = 0

        self.workstations = {
            "Human": simpy.Resource(env, capacity=1),
            "Robot_1": simpy.Resource(env, capacity=1),
            "Robot_2": simpy.Resource(env, capacity=1),
        }

        self.robot_access = {
            "Robot_1": simpy.Resource(env, capacity=1),
            "Robot_2": simpy.Resource(env, capacity=1),
        }
        self.transfer_resources = {
            name: simpy.Resource(env, capacity=int(config.get("capacity", 1)))
            for name, config in CONFIG.get("transfers", {}).items()
        }

        self.segments = {
            name: ConveyorSegment(env, name, config)
            for name, config in CONFIG["conveyor_segments"].items()
        }

        self.human_infeed_segment = self._build_human_infeed_segment()
        self.human_queue = deque()
        self.human_queue_head_releasing = False
        self.human_direct_reserved_by = None
        self.robot_queue = deque()
        self.robot_queue_head_releasing = False
        self.motion_locks = {}

        self.stats = {
            "completed_palettes": 0,
            "total_cycle_times": [],
            "robot_choices": {"Robot_1": 0, "Robot_2": 0},
            "bottleneck_waits": {"HumanQueue": [], "RobotQueue": [], "Robot_1": [], "Robot_2": []},
        }

    def _next_event_id(self) -> int:
        self._event_seq += 1
        return self._event_seq

    def _build_human_infeed_segment(self):
        """
        Human queue geometry limited to the two HUMAN_QUEUE markers.
        """
        human_segment = self.segments["HUMAN_QUEUE"]

        merged_config = {
            "waypoints": human_segment.waypoints,
            "capacity": human_segment.capacity,
            "slot_spacing": human_segment.slot_spacing,
            "is_queue_zone": True,
        }
        return ConveyorSegment(self.env, "HUMAN_INFEED_QUEUE", merged_config)

    # ---------- Generic motion helpers ----------

    def get_motion_lock(self, palette_id):
        if palette_id not in self.motion_locks:
            self.motion_locks[palette_id] = simpy.Resource(self.env, capacity=1)
        return self.motion_locks[palette_id]

    def _move_along_waypoints_unlocked(self, palette_id, waypoints):
        path = clean_waypoints(waypoints)
        if not path:
            return

        if len(path) == 1:
            self.bridge.add_keyframe(palette_id, path[0], self.env.now)
            self.bridge.set_current_position(palette_id, path[0])
            if self.realtime_logger:
                self.realtime_logger.set_position(palette_id, path[0], self.env.now)
            if self.live_emitter:
                event_id = self._next_event_id()
                self.live_emitter.set_position(palette_id, path[0], self.env.now, event_id)
            return

        speed = CONFIG["simulation_params"]["transport_speed"]
        for start_pos, end_pos, duration, transfer_name in iter_motion_segments(path, speed):
            segment_path = [start_pos, end_pos]

            if transfer_name:
                transfer_resource = self.transfer_resources[transfer_name]
                with transfer_resource.request() as transfer_req:
                    yield transfer_req
                    print(f"[{self.env.now:.1f}] Palette {palette_id} -> {transfer_name} ({duration:.1f}s)")
                    if self.live_emitter:
                        self.bridge.add_path(palette_id, segment_path, self.env.now, duration)
                        event_id = self._next_event_id()
                        if self.realtime_logger:
                            self.realtime_logger.move_path(
                                palette_id=palette_id,
                                path_points=segment_path,
                                duration=duration,
                                sim_time=self.env.now,
                                metadata={"event_id": int(event_id), "sim_time": float(self.env.now)},
                            )
                        self.live_emitter.move_path(
                            palette_id=palette_id,
                            path_points=segment_path,
                            duration=duration,
                            sim_time=self.env.now,
                            event_id=event_id,
                        )
                    else:
                        self.bridge.add_path(palette_id, segment_path, self.env.now, duration)
                        if self.realtime_logger:
                            self.realtime_logger.emit_path(palette_id, segment_path, self.env.now, duration)
                    yield self.env.timeout(duration)
                    self.bridge.set_current_position(palette_id, end_pos)
            else:
                if self.live_emitter:
                    self.bridge.add_path(palette_id, segment_path, self.env.now, duration)
                    event_id = self._next_event_id()
                    if self.realtime_logger:
                        self.realtime_logger.move_path(
                            palette_id=palette_id,
                            path_points=segment_path,
                            duration=duration,
                            sim_time=self.env.now,
                            metadata={"event_id": int(event_id), "sim_time": float(self.env.now)},
                        )
                    self.live_emitter.move_path(
                        palette_id=palette_id,
                        path_points=segment_path,
                        duration=duration,
                        sim_time=self.env.now,
                        event_id=event_id,
                    )
                else:
                    self.bridge.add_path(palette_id, segment_path, self.env.now, duration)
                    if self.realtime_logger:
                        self.realtime_logger.emit_path(palette_id, segment_path, self.env.now, duration)
                yield self.env.timeout(duration)
                self.bridge.set_current_position(palette_id, end_pos)

    def move_along_waypoints(self, palette_id, waypoints):
        lock = self.get_motion_lock(palette_id)
        with lock.request() as move_req:
            yield move_req
            yield from self._move_along_waypoints_unlocked(palette_id, waypoints)

    def move_queue_palette_to_current_slot(self, palette_id, queue, segment):
        lock = self.get_motion_lock(palette_id)
        with lock.request() as move_req:
            yield move_req
            if palette_id not in queue:
                return
            target = segment.get_slot_position(list(queue).index(palette_id))
            current = self.bridge.get_current_position(palette_id)
            if current is None:
                current = target
            if tuple(current) != tuple(target):
                yield from self._move_along_waypoints_unlocked(palette_id, [tuple(current), tuple(target)])

    def move_to_point(self, palette_id, target_pos):
        current = self.bridge.get_current_position(palette_id)
        target = tuple(target_pos)

        if current is None:
            current = target

        if tuple(current) == target:
            self.bridge.add_keyframe(palette_id, target, self.env.now)
            self.bridge.set_current_position(palette_id, target)
            if self.realtime_logger:
                self.realtime_logger.set_position(palette_id, target, self.env.now)
            if self.live_emitter:
                event_id = self._next_event_id()
                self.live_emitter.set_position(palette_id, target, self.env.now, event_id)
            return

        yield self.env.process(self.move_along_waypoints(palette_id, [tuple(current), target]))

    def transport_segment(self, palette_id, segment_name):
        segment = self.segments[segment_name]
        start_pos = self.bridge.get_current_position(palette_id)
        if start_pos is None:
            start_pos = segment.waypoints[0]

        path = [tuple(start_pos)] + list(segment.waypoints)
        path = clean_waypoints(path)

        with segment.resource.request() as req:
            yield req
            print(f"[{self.env.now:.1f}] Palette {palette_id} -> {segment_name}")
            yield self.env.process(self.move_along_waypoints(palette_id, path))

    def human_station_can_accept_direct(self):
        return (
            not self.human_queue
            and not self.human_queue_head_releasing
            and self.human_direct_reserved_by is None
            and len(self.workstations["Human"].users) == 0
            and len(self.workstations["Human"].queue) == 0
        )

    def reserve_human_queue_slot(self, palette_id):
        if palette_id not in self.human_queue:
            self.human_queue.append(palette_id)
        slot_index = list(self.human_queue).index(palette_id)
        return self.human_infeed_segment.get_slot_position(slot_index)

    def transport_return_to_human_or_queue(self, palette_id, segment_name):
        segment = self.segments[segment_name]
        start_pos = self.bridge.get_current_position(palette_id)
        if start_pos is None:
            start_pos = segment.waypoints[0]

        path = [tuple(start_pos)] + list(segment.waypoints)
        if not self.human_station_can_accept_direct():
            target = self.reserve_human_queue_slot(palette_id)
            path = path[:-1] + [tuple(target)]
            print(f"[{self.env.now:.1f}] Palette {palette_id} -> {segment_name} then Human queue")
        else:
            self.human_direct_reserved_by = palette_id
            print(f"[{self.env.now:.1f}] Palette {palette_id} -> {segment_name}")

        path = clean_waypoints(path)
        with segment.resource.request() as req:
            yield req
            yield self.env.process(self.move_along_waypoints(palette_id, path))

    # ---------- Queue helpers ----------

    def shift_queue_forward(self, queue_name):
        if queue_name == "human":
            queue = self.human_queue
            segment = self.human_infeed_segment
        elif queue_name == "robot":
            queue = self.robot_queue
            segment = self.segments["QUEUE_ROBOT_AREA"]
        else:
            raise ValueError("queue_name invalide")

        move_processes = []
        for palette_id in list(queue):
            move_processes.append(self.env.process(self.move_queue_palette_to_current_slot(palette_id, queue, segment)))

        if move_processes:
            yield simpy.events.AllOf(self.env, move_processes)

    def join_queue_and_wait(self, palette_id, queue_name):
        if queue_name == "human":
            queue = self.human_queue
            segment = self.human_infeed_segment
            wait_stats_key = "HumanQueue"
        elif queue_name == "robot":
            queue = self.robot_queue
            segment = self.segments["QUEUE_ROBOT_AREA"]
            wait_stats_key = "RobotQueue"
        else:
            raise ValueError("queue_name invalide")

        queue.append(palette_id)
        slot_index = len(queue) - 1
        target = segment.get_slot_position(slot_index)
        current = self.bridge.get_current_position(palette_id)
        if current is None:
            current = segment.waypoints[0]

        # Direct entry to the current queue slot.
        yield self.env.process(self.move_along_waypoints(palette_id, [tuple(current), tuple(target)]))

        queue_enter_time = self.env.now

        while True:
            if len(queue) > 0 and queue[0] == palette_id:
                break
            yield self.env.timeout(0.2)

        wait_time = self.env.now - queue_enter_time
        if wait_time > 0:
            self.stats["bottleneck_waits"][wait_stats_key].append(wait_time)

    def choose_robot_when_available(self):
        # Strict priority: Robot_1 then Robot_2.
        robot1_free = len(self.workstations["Robot_1"].users) == 0 and len(self.robot_access["Robot_1"].users) == 0
        robot2_free = len(self.workstations["Robot_2"].users) == 0 and len(self.robot_access["Robot_2"].users) == 0

        if robot1_free:
            return "Robot_1"
        if robot2_free:
            return "Robot_2"
        return None

    # ---------- Workstations with queue reservation ----------

    def process_at_human(self, palette_id, cycle_num):
        ws_name = "Human"
        ws_config = CONFIG["workstations"][ws_name]
        process_time = ws_config["cycle_times"][cycle_num - 1]

        entry_pos = tuple(ws_config["entry"])
        processing_pos = tuple(ws_config["processing"])
        exit_pos = tuple(ws_config["exit"])

        already_in_human_queue = palette_id in self.human_queue
        has_direct_reservation = self.human_direct_reserved_by == palette_id
        from_queue = True
        human_free = (
            self.human_direct_reserved_by in (None, palette_id)
            and len(self.workstations[ws_name].users) == 0
            and len(self.workstations[ws_name].queue) == 0
        )
        if has_direct_reservation:
            from_queue = False
        elif not already_in_human_queue and not self.human_queue and not self.human_queue_head_releasing and human_free:
            self.human_direct_reserved_by = palette_id
            from_queue = False

        if already_in_human_queue:
            while self.human_queue and self.human_queue[0] != palette_id:
                yield self.env.timeout(0.2)
        elif from_queue:
            # Join the Human queue only when the station is busy or already reserved.
            yield self.env.process(self.join_queue_and_wait(palette_id, "human"))

        # Only the queue head may reserve the station and leave the queue.
        with self.workstations[ws_name].request() as req:
            yield req

            if self.human_direct_reserved_by == palette_id:
                self.human_direct_reserved_by = None

            if from_queue and self.human_queue and self.human_queue[0] == palette_id:
                self.human_queue_head_releasing = True
                self.human_queue.popleft()

            yield self.env.process(self.move_to_point(palette_id, entry_pos))

            # Shift only after the head has physically cleared the area.
            if from_queue and self.human_queue_head_releasing:
                self.human_queue_head_releasing = False
                if self.human_queue:
                    yield self.env.process(self.shift_queue_forward("human"))

            yield self.env.process(self.move_to_point(palette_id, processing_pos))

            print(f"[{self.env.now:.1f}] Palette {palette_id} - Human processing cycle {cycle_num} ({process_time}s)")
            yield self.env.timeout(process_time)

            yield self.env.process(self.move_to_point(palette_id, exit_pos))

    def process_at_robot(self, palette_id):
        from_queue = True
        chosen_robot = None

        if not self.robot_queue and not self.robot_queue_head_releasing:
            chosen_robot = self.choose_robot_when_available()
            from_queue = chosen_robot is None

        if from_queue:
            # Join the shared robot queue only when no robot is available.
            yield self.env.process(self.join_queue_and_wait(palette_id, "robot"))

            while chosen_robot is None:
                if (
                    not self.robot_queue_head_releasing
                    and self.robot_queue
                    and self.robot_queue[0] == palette_id
                ):
                    chosen_robot = self.choose_robot_when_available()
                if chosen_robot is None:
                    yield self.env.timeout(0.2)

        ws_config = CONFIG["workstations"][chosen_robot]
        process_time = ws_config["process_time"]
        entry_pos = tuple(ws_config["entry"])
        processing_pos = tuple(ws_config["processing"])
        exit_pos = tuple(ws_config["exit"])

        # Reserve immediately before leaving the queue to avoid overlaps.
        with self.robot_access[chosen_robot].request() as access_req:
            yield access_req
            with self.workstations[chosen_robot].request() as ws_req:
                yield ws_req

                if from_queue and self.robot_queue and self.robot_queue[0] == palette_id:
                    # The head logically leaves the queue, but shifting waits until
                    # it physically clears the robot critical area.
                    self.robot_queue_head_releasing = True
                    self.robot_queue.popleft()

                self.stats["robot_choices"][chosen_robot] += 1
                print(f"[{self.env.now:.1f}] Palette {palette_id} - entering {chosen_robot}")

                yield self.env.process(self.move_to_point(palette_id, entry_pos))

                # Queue shift only after the area is physically clear.
                if from_queue and self.robot_queue_head_releasing:
                    self.robot_queue_head_releasing = False
                    if self.robot_queue:
                        self.env.process(self.shift_queue_forward("robot"))

                yield self.env.process(self.move_to_point(palette_id, processing_pos))

                print(f"[{self.env.now:.1f}] Palette {palette_id} - {chosen_robot} processing ({process_time}s)")
                yield self.env.timeout(process_time)

                yield self.env.process(self.move_to_point(palette_id, exit_pos))
                print(f"[{self.env.now:.1f}] Palette {palette_id} - exited {chosen_robot}")

        return chosen_robot

    # ---------- Lifecycle ----------

    def palette_lifecycle(self, palette_id):
        start_time = self.env.now
        print(f"\nPalette {palette_id} starting lifecycle")

        for cycle in range(1, CONFIG["simulation_params"]["max_cycles"] + 1):
            print(f"\n--- Palette {palette_id} - CYCLE {cycle}/{CONFIG['simulation_params']['max_cycles']} ---")

            yield self.env.process(self.process_at_human(palette_id, cycle))

            if cycle == CONFIG["simulation_params"]["max_cycles"]:
                print(f"[{self.env.now:.1f}] Palette {palette_id} - completed all cycles")
                break

            yield self.env.process(self.transport_segment(palette_id, "HUMAN_TO_ROBOT_AREA"))
            robot_choice = yield self.env.process(self.process_at_robot(palette_id))

            return_segment = {
                "Robot_1": "ROBOT_1_RETURN",
                "Robot_2": "ROBOT_2_RETURN",
            }[robot_choice]
            yield self.env.process(self.transport_return_to_human_or_queue(palette_id, return_segment))

        total_time = self.env.now - start_time
        self.stats["completed_palettes"] += 1
        self.stats["total_cycle_times"].append(total_time)
        print(f"Palette {palette_id} FINISHED - Total time: {total_time:.1f}")

    # ---------- Statistics ----------

    def print_statistics(self):
        print("\n" + "=" * 60)
        print("SIMULATION STATISTICS")
        print("=" * 60)

        print(f"\nCompleted palettes: {self.stats['completed_palettes']}/{CONFIG['simulation_params']['num_palettes']}")

        if self.stats["total_cycle_times"]:
            avg_cycle = sum(self.stats["total_cycle_times"]) / len(self.stats["total_cycle_times"])
            print("\nCycle times:")
            print(f"   Average: {avg_cycle:.1f}")
            print(f"   Min: {min(self.stats['total_cycle_times']):.1f}")
            print(f"   Max: {max(self.stats['total_cycle_times']):.1f}")

        print("\nRobot selection:")
        for robot, count in self.stats["robot_choices"].items():
            print(f"   {robot}: {count} times")

        print("\nQueue waits:")
        for ws, waits in self.stats["bottleneck_waits"].items():
            if waits:
                avg_wait = sum(waits) / len(waits)
                print(f"   {ws}: {len(waits)} waits, avg {avg_wait:.1f}")
            else:
                print(f"   {ws}: No waits")


# ====================
# MAIN
# ====================

def main():
    parser = argparse.ArgumentParser(description="RealtimeTCP build + simulation message producer.")
    parser.add_argument(
        "--config",
        type=str,
        default=str(CONFIG_JSON),
        help="Path to production layout JSON (RealtimeTCP trajectories source).",
    )
    parser.add_argument(
        "--event-log",
        type=str,
        default="",
        help="Path to NDJSON event log for realtime TCP bridge replay.",
    )
    parser.add_argument(
        "--live-tcp",
        action="store_true",
        default=True,
        help="Send updates live to USD Composer TCP bridge while simulation runs (default).",
    )
    parser.add_argument(
        "--no-live-tcp",
        action="store_false",
        dest="live_tcp",
        help="Do not connect to USD Composer; useful for NDJSON/debug runs.",
    )
    parser.add_argument("--host", type=str, default="127.0.0.1", help="USD Composer TCP bridge host.")
    parser.add_argument("--port", type=int, default=5050, help="USD Composer TCP bridge port.")
    parser.add_argument(
        "--realtime-factor",
        type=float,
        default=None,
        help="Wall-time factor when --live-tcp is enabled (None => 1.0 wall-clock; use 1/24 to preview faster).",
    )
    parser.add_argument(
        "--until",
        type=float,
        default=3000.0,
        help="Simulation stop time in simulated seconds.",
    )
    parser.add_argument(
        "--start-all-at-once",
        action="store_true",
        help="Disable RealtimeTCP inter-arrival launch and start all palettes at t=0.",
    )
    args = parser.parse_args()

    globals()["CONFIG_JSON"] = Path(args.config)
    globals()["CONFIG"] = load_config()

    timeline_fps = float(CONFIG.get("simulation_params", {}).get("timeline_fps", FALLBACK_TIMELINE_FPS) or FALLBACK_TIMELINE_FPS)
    if args.realtime_factor is None:
        args.realtime_factor = 1.0

    if args.realtime_factor <= 0:
        raise ValueError("--realtime-factor must be > 0")
    if args.until <= 0:
        raise ValueError("--until must be > 0")

    print("=" * 60)
    print("RealtimeTCP PRODUCTION SYSTEM")
    print("=" * 60)
    print(f"Palettes: {CONFIG['simulation_params']['num_palettes']}")
    print(f"Max cycles per palette: {CONFIG['simulation_params']['max_cycles']}")
    print(f"Human cycle times: {CONFIG['workstations']['Human']['cycle_times']}")
    print(f"Layout config: {CONFIG_JSON}")
    print(f"Composer stage expected: {COMPOSER_STAGE_USD}")
    print("Build mode: live TCP seed messages")
    print(f"Timeline FPS: {timeline_fps:g}")
    print("=" * 60 + "\n")

    realtime_logger = RealtimeEventLogger(Path(args.event_log)) if args.event_log else None
    live_emitter = (
        LiveTcpEmitter(
            args.host,
            args.port,
            duration_scale=float(args.realtime_factor),
        )
        if args.live_tcp
        else None
    )

    if args.live_tcp and RealtimeEnvironment is not None:
        env = RealtimeEnvironment(factor=float(args.realtime_factor), strict=False)
        speedup = 1.0 / float(args.realtime_factor)
        print(
            "Live TCP mode on "
            f"tcp://{args.host}:{args.port} "
            f"(realtime factor={args.realtime_factor:.6f}, speedup x{speedup:.2f} vs simulated seconds)"
        )
    else:
        if args.live_tcp and RealtimeEnvironment is None:
            raise RuntimeError(
                "RealtimeEnvironment unavailable. "
                "Install/use SimPy with realtime support or disable --live-tcp."
            )
        env = simpy.Environment()

    bridge = MemoryBridge()
    bridge.seed_initial_positions()
    if realtime_logger:
        realtime_logger.seed_initial_positions(CONFIG)
        print(f"Realtime event log: {Path(args.event_log)}")

    if live_emitter:
        live_emitter.connect()
        print("Sending live build seed messages to USD Composer...")
        base_pos = tuple(CONFIG["palette_template"]["initial_position"])
        spacing = CONFIG["palette_template"].get("initial_spacing", 5.0)
        num_palettes = CONFIG["simulation_params"]["num_palettes"]
        for palette_id in range(1, num_palettes + 1):
            offset = (palette_id - 1) * spacing
            pos = (base_pos[0] - offset, base_pos[1], base_pos[2])
            # Seed without event_id so first lifecycle events are never dropped.
            live_emitter.set_position(palette_id, pos, sim_time=0.0)

    production = ProductionLine(
        env,
        bridge,
        realtime_logger=realtime_logger,
        live_emitter=live_emitter,
    )

    inter_arrival = float(CONFIG.get("simulation_params", {}).get("inter_arrival_time", 0.0) or 0.0)
    num_palettes = int(CONFIG["simulation_params"]["num_palettes"])
    if args.start_all_at_once or inter_arrival <= 0:
        launch_mode = "all-at-once"
        for palette_id in range(1, num_palettes + 1):
            env.process(production.palette_lifecycle(palette_id))
    else:
        launch_mode = f"inter-arrival={inter_arrival:g}s"
        for palette_id in range(1, num_palettes + 1):
            start_delay = (palette_id - 1) * inter_arrival

            def launch_palette(pid: int, delay: float):
                yield env.timeout(delay)
                yield env.process(production.palette_lifecycle(pid))

            env.process(launch_palette(palette_id, start_delay))

    print(f"Launch mode: {launch_mode}")

    env.run(until=float(args.until))
    production.print_statistics()
    if realtime_logger:
        realtime_logger.close()
    if live_emitter:
        live_emitter.close()


if __name__ == "__main__":
    main()
