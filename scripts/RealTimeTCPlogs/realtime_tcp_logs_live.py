from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from RealTimeTCPlogs.tcp_logs_client import TcpLogsClient
except Exception:
    from tcp_logs_client import TcpLogsClient  # type: ignore


Vec3 = Tuple[float, float, float]
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from marker_layout import resolve_layout_markers

CONFIG_JSON = SCRIPT_DIR / "realtimetcp_logs_config.json"
CSV_COLUMNS = [
    "carrier_id",
    "origin_id",
    "event_type",
    "destination_id",
    "start_time",
    "processing_time",
    "end_time",
    "task_id",
    "details",
]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return resolve_layout_markers(json.load(f), PROJECT_ROOT)


def resolve_project_path(value: str, base: Path = PROJECT_ROOT) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return base / path


def parse_time_to_seconds(value) -> float:
    text = str(value or "").strip()
    if text == "" or text.lower() == "nan":
        return 0.0
    if ":" in text:
        h, m, s = text.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    return float(text)


def safe_int(value) -> Optional[int]:
    text = str(value or "").strip()
    if text == "" or text.lower() == "nan":
        return None
    return int(float(text))


def point3(values) -> Vec3:
    if len(values) != 3:
        raise ValueError(f"Invalid 3D point: {values}")
    return (float(values[0]), float(values[1]), float(values[2]))


def distance(a: Vec3, b: Vec3) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def interpolate(a: Vec3, b: Vec3, t: float) -> Vec3:
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def dedupe(points: Iterable[Vec3]) -> List[Vec3]:
    out: List[Vec3] = []
    for raw in points:
        p = tuple(float(v) for v in raw)
        if not out or distance(out[-1], p) > 1e-9:
            out.append(p)  # type: ignore[arg-type]
    return out


@dataclass
class LogEvent:
    carrier_id: int
    origin_id: Optional[int]
    event_type: str
    destination_id: Optional[int]
    start_s: float
    end_s: float
    task_id: str
    details: str
    next_event_type: str = ""
    next_destination_id: Optional[int] = None

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end_s - self.start_s)


def parse_log_event(row: dict) -> LogEvent:
    missing = [name for name in CSV_COLUMNS if name not in row]
    if missing:
        raise ValueError(f"Missing CSV columns: {missing}")

    start_s = parse_time_to_seconds(row["start_time"])
    processing_s = parse_time_to_seconds(row["processing_time"])
    end_s = parse_time_to_seconds(row["end_time"])
    if end_s < start_s or (end_s == start_s and processing_s > 0):
        end_s = start_s + processing_s

    return LogEvent(
        carrier_id=int(float(str(row["carrier_id"]).strip())),
        origin_id=safe_int(row["origin_id"]),
        event_type=str(row["event_type"]).strip().upper(),
        destination_id=safe_int(row["destination_id"]),
        start_s=start_s,
        end_s=end_s,
        task_id=str(row["task_id"]).strip(),
        details=str(row["details"]).strip(),
        next_event_type=str(row.get("_next_event_type", "")).strip().upper(),
        next_destination_id=safe_int(row.get("_next_destination_id", "")),
    )


class LayoutResolver:
    def __init__(self, config: dict):
        self.resource_map = {int(k): str(v) for k, v in config["resource_map"].items()}
        self.workstations = config["workstations"]
        self.routes = {str(k): [point3(p) for p in v] for k, v in config["routes"].items()}
        self.transfers = {
            name: {
                "from": point3(transfer["from"]),
                "to": point3(transfer["to"]),
                "duration": float(transfer["duration"]),
            }
            for name, transfer in config.get("transfers", {}).items()
        }
        sim_params = config.get("simulation_params", {})
        self.initial_position = point3(config["palette_template"]["initial_position"])
        self.path_sample_step = float(sim_params.get("path_sample_step", 12.0))
        self.max_points_per_motion = int(sim_params.get("max_keys_per_motion", 80))
        self.micro_move_seconds = float(sim_params.get("micro_move_seconds", 0.10))

    def station_name(self, resource_id: int) -> str:
        return self.resource_map[int(resource_id)]

    def station(self, resource_id: int) -> dict:
        return self.workstations[self.station_name(resource_id)]

    def entry(self, resource_id: int) -> Vec3:
        return point3(self.station(resource_id)["entry"])

    def buffer(self, resource_id: int) -> Vec3:
        station = self.station(resource_id)
        if "buffer" in station:
            return point3(station["buffer"])
        return self.entry(resource_id)

    def processing(self, resource_id: int) -> Vec3:
        return point3(self.station(resource_id)["processing"])

    def exit(self, resource_id: int) -> Vec3:
        return point3(self.station(resource_id)["exit"])

    def transfer_for_segment(self, start_pos: Vec3, end_pos: Vec3):
        for name, transfer in self.transfers.items():
            if distance(start_pos, transfer["from"]) <= 1e-6 and distance(end_pos, transfer["to"]) <= 1e-6:
                return name, transfer
        return None, None

    def timed_segments_for_path(self, waypoints: List[Vec3], duration_seconds: float):
        path = dedupe(waypoints)
        if len(path) <= 1:
            return [], max(0.0, float(duration_seconds))

        requested_duration = max(0.0, float(duration_seconds))
        fixed_total = 0.0
        normal_total = 0.0
        segment_meta = []
        for i in range(len(path) - 1):
            start_pos = path[i]
            end_pos = path[i + 1]
            transfer_name, transfer = self.transfer_for_segment(start_pos, end_pos)
            if transfer:
                seg_duration = float(transfer["duration"])
                fixed_total += seg_duration
                segment_meta.append((start_pos, end_pos, seg_duration, True, transfer_name))
            else:
                seg_dist = distance(start_pos, end_pos)
                normal_total += seg_dist
                segment_meta.append((start_pos, end_pos, seg_dist, False, None))

        effective_duration = max(requested_duration, fixed_total)
        if fixed_total > requested_duration + 1e-6:
            print(
                "WARNING: log transport shorter than fixed transfer duration; "
                f"using {effective_duration:.3f}s instead of {requested_duration:.3f}s."
            )
        normal_budget = max(0.0, effective_duration - fixed_total)

        segments = []
        for start_pos, end_pos, value, is_transfer, transfer_name in segment_meta:
            if is_transfer:
                step_duration = float(value)
            elif normal_total > 1e-9:
                step_duration = normal_budget * (float(value) / normal_total)
            else:
                step_duration = 0.0
            segments.append({
                "path": [start_pos, end_pos],
                "duration": step_duration,
                "transfer": transfer_name,
            })
        return segments, effective_duration

    def explicit_path(self, resource_id: int, name: str, fallback: List[Vec3]) -> List[Vec3]:
        station = self.station(resource_id)
        if name in station and station[name]:
            return [point3(p) for p in station[name]]
        return fallback

    def buffer_slots(self, resource_id: int) -> List[Vec3]:
        station = self.station(resource_id)
        if "buffer_path" in station and station["buffer_path"]:
            return [point3(p) for p in station["buffer_path"]]
        return [self.buffer(resource_id)]

    def queue_slot_for_rank(self, resource_id: int, rank_zero_based: int) -> Tuple[int, Vec3]:
        slots = self.buffer_slots(resource_id)
        idx = max(0, len(slots) - 1 - rank_zero_based)
        return idx, slots[idx]

    def entry_to_buffer_path(self, resource_id: int, slot_index: int) -> List[Vec3]:
        slots = self.buffer_slots(resource_id)
        slot_index = min(max(0, slot_index), len(slots) - 1)
        target = slots[slot_index]
        base = self.explicit_path(resource_id, "entry_to_buffer", [self.entry(resource_id), slots[0]])

        path = []
        for point in base:
            path.append(point)
            if distance(point, target) <= 1e-6:
                return dedupe(path)

        start_idx = -1
        for i, slot in enumerate(slots):
            if path and distance(path[-1], slot) <= 1e-6:
                start_idx = i
                break
        if start_idx < 0:
            path.append(slots[0])
            start_idx = 0

        step = 1 if start_idx <= slot_index else -1
        for i in range(start_idx + step, slot_index + step, step):
            if path[-1] != slots[i]:
                path.append(slots[i])
        return dedupe(path)

    def buffer_to_processing_path(self, resource_id: int, slot_index: int) -> List[Vec3]:
        slots = self.buffer_slots(resource_id)
        slot_index = min(max(0, slot_index), len(slots) - 1)
        slot = slots[slot_index]
        explicit = self.station(resource_id).get("buffer_to_processing")
        if explicit:
            return dedupe([slot] + [point3(p) for p in explicit if point3(p) != slot])
        return dedupe([slot, self.processing(resource_id)])

    def entry_to_processing_path(self, resource_id: int) -> List[Vec3]:
        return dedupe(self.explicit_path(resource_id, "entry_to_processing", [self.entry(resource_id), self.processing(resource_id)]))

    def processing_to_buffer_path(self, resource_id: int, slot_index: int) -> List[Vec3]:
        slots = self.buffer_slots(resource_id)
        slot_index = min(max(0, slot_index), len(slots) - 1)
        explicit = self.station(resource_id).get("processing_to_buffer")
        if explicit:
            target = slots[slot_index]
            path = [self.processing(resource_id)] + [point3(p) for p in explicit]
            for i, point in enumerate(path):
                if distance(point, target) <= 1e-6:
                    return dedupe(path[: i + 1])
            if path[-1] != target:
                path.append(target)
            return dedupe(path)
        return dedupe([self.processing(resource_id), slots[slot_index]])

    def route_between_stations(self, origin_id: Optional[int], destination_id: int) -> List[Vec3]:
        origin_key = "START" if origin_id is None else str(origin_id)
        route = self.routes.get(f"{origin_key}->{destination_id}")
        if route:
            return dedupe(route)
        start_pos = self.initial_position if origin_id is None else self.exit(origin_id)
        return dedupe([start_pos, self.entry(destination_id)])

    def transport_to_processing_path(
        self,
        current_position: Vec3,
        origin_id: Optional[int],
        destination_id: int,
    ) -> List[Vec3]:
        path: List[Vec3] = [current_position]
        if origin_id is not None and distance(current_position, self.processing(origin_id)) < 1e-6:
            for p in self.explicit_path(origin_id, "processing_to_exit", [self.processing(origin_id), self.exit(origin_id)]):
                if distance(path[-1], p) > 1e-6:
                    path.append(p)
        for p in self.route_between_stations(origin_id, destination_id):
            if distance(path[-1], p) > 1e-6:
                path.append(p)
        for p in self.entry_to_processing_path(destination_id):
            if distance(path[-1], p) > 1e-6:
                path.append(p)
        return self.sample_route(path)

    def transport_to_entry_path(
        self,
        current_position: Vec3,
        origin_id: Optional[int],
        destination_id: int,
    ) -> List[Vec3]:
        path: List[Vec3] = [current_position]
        if origin_id is not None and distance(current_position, self.processing(origin_id)) < 1e-6:
            for p in self.explicit_path(origin_id, "processing_to_exit", [self.processing(origin_id), self.exit(origin_id)]):
                if distance(path[-1], p) > 1e-6:
                    path.append(p)
        for p in self.route_between_stations(origin_id, destination_id):
            if distance(path[-1], p) > 1e-6:
                path.append(p)
        entry = self.entry(destination_id)
        if distance(path[-1], entry) > 1e-6:
            path.append(entry)
        return self.sample_route(path)

    def sample_route(self, route: List[Vec3]) -> List[Vec3]:
        route = dedupe(route)
        if len(route) <= 1:
            return route
        sampled = [route[0]]
        for i in range(len(route) - 1):
            a = route[i]
            b = route[i + 1]
            seg_len = distance(a, b)
            if seg_len <= 1e-9:
                continue
            if self.transfer_for_segment(a, b)[1]:
                sampled.append(b)
                continue
            sub_count = int(seg_len // self.path_sample_step)
            for j in range(1, sub_count + 1):
                sampled.append(interpolate(a, b, j / (sub_count + 1)))
            sampled.append(b)
        sampled = dedupe(sampled)
        if len(sampled) > self.max_points_per_motion:
            mandatory_points = []
            for a, b in zip(route, route[1:]):
                if self.transfer_for_segment(a, b)[1]:
                    mandatory_points.extend([a, b])
            mandatory_indices = {
                idx
                for idx, point in enumerate(sampled)
                if idx in (0, len(sampled) - 1)
                or any(distance(point, required) <= 1e-6 for required in mandatory_points)
            }
            reduced_indices = set(mandatory_indices)
            last = len(sampled) - 1
            for k in range(self.max_points_per_motion):
                idx = round(k * last / (self.max_points_per_motion - 1))
                reduced_indices.add(idx)
            reduced = [sampled[idx] for idx in sorted(reduced_indices)]
            sampled = dedupe(reduced)
        return sampled


class MessageSink:
    def __init__(
        self,
        host: str,
        port: int,
        timeout: float,
        dry_run: bool = False,
        print_messages: bool = False,
        audit_log: Optional[Path] = None,
    ):
        self.dry_run = bool(dry_run)
        self.print_messages = bool(print_messages)
        self.client = None if self.dry_run else TcpLogsClient(host, port, timeout=timeout)
        self.audit_fh = None
        if audit_log:
            audit_log.parent.mkdir(parents=True, exist_ok=True)
            self.audit_fh = audit_log.open("w", encoding="utf-8", newline="\n")

    def connect(self):
        if self.client is not None:
            self.client.connect()

    def send(self, payload: dict):
        if self.print_messages:
            print(json.dumps(payload, separators=(",", ":")))
        if self.audit_fh is not None:
            self.audit_fh.write(json.dumps({"wall_time": time.time(), "msg": payload}, separators=(",", ":")) + "\n")
            self.audit_fh.flush()
        if self.client is not None:
            try:
                self.client.send(payload)
            except OSError:
                self.client.close()
                self.client.connect()
                self.client.send(payload)

    def close(self):
        if self.client is not None:
            self.client.close()
        if self.audit_fh is not None:
            self.audit_fh.close()
            self.audit_fh = None


class LiveLogMapper:
    def __init__(self, layout: dict, sink: MessageSink, duration_scale: float = 1.0):
        self.resolver = LayoutResolver(layout)
        self.sink = sink
        self.duration_scale = float(duration_scale)
        self.positions: Dict[int, Vec3] = {}
        self.seeded = set()
        self.queue_active: Dict[int, List[Tuple[float, int, int]]] = defaultdict(list)
        self.event_seq = 0

    def _next_event_id(self) -> int:
        self.event_seq += 1
        return self.event_seq

    def _send(self, payload: dict):
        payload["event_id"] = self._next_event_id()
        self.sink.send(payload)

    def _seed_carrier(self, carrier_id: int):
        if carrier_id in self.seeded:
            return
        self.positions[carrier_id] = self.resolver.initial_position
        self._send({
            "type": "set_position",
            "carrier_id": int(carrier_id),
            "position": list(self.resolver.initial_position),
        })
        self._send({"type": "set_visibility", "carrier_id": int(carrier_id), "visible": True})
        self.seeded.add(carrier_id)

    def _move_or_set(self, carrier_id: int, path: List[Vec3], duration: float):
        path = dedupe(path)
        if not path:
            return
        if len(path) == 1 or duration <= 0:
            self._send({"type": "set_position", "carrier_id": carrier_id, "position": list(path[-1])})
        else:
            self._send({
                "type": "move_path",
                "carrier_id": carrier_id,
                "path": [list(p) for p in path],
                "duration": max(0.001, float(duration)),
            })
        self.positions[carrier_id] = path[-1]

    def _move_timed_or_set(self, carrier_id: int, timed_segments):
        segments = list(timed_segments or [])
        if not segments:
            return
        final_pos = tuple(segments[-1]["path"][-1])
        total_sim_duration = sum(max(0.0, float(segment["duration"])) for segment in segments)
        has_transfer = any(segment.get("transfer") for segment in segments)
        if total_sim_duration <= 0 and not has_transfer:
            self._send({"type": "set_position", "carrier_id": carrier_id, "position": list(final_pos)})
            self.positions[carrier_id] = final_pos
            return

        payload_segments = []
        for segment in segments:
            path = dedupe(segment["path"])
            if len(path) < 2:
                continue
            payload_segments.append({
                "path": [list(p) for p in path],
                "duration": max(0.001, self._wall_duration(float(segment["duration"]))),
                "sim_duration": max(0.0, float(segment["duration"])),
                "transfer": segment.get("transfer"),
            })

        if not payload_segments:
            self._send({"type": "set_position", "carrier_id": carrier_id, "position": list(final_pos)})
        else:
            self._send({
                "type": "move_timed_path",
                "carrier_id": carrier_id,
                "segments": payload_segments,
            })
        self.positions[carrier_id] = final_pos

    def _wall_duration(self, seconds: float) -> float:
        return max(0.0, float(seconds) * self.duration_scale)

    def _micro_duration(self, event: LogEvent) -> float:
        if event.duration_s <= 0:
            return self._wall_duration(self.resolver.micro_move_seconds)
        return self._wall_duration(min(event.duration_s, max(self.resolver.micro_move_seconds, event.duration_s * 0.25)))

    def _assign_queue_slot(self, event: LogEvent) -> int:
        assert event.destination_id is not None
        active = [
            (end_s, carrier_id, slot)
            for end_s, carrier_id, slot in self.queue_active[event.destination_id]
            if end_s > event.start_s and carrier_id != event.carrier_id
        ]
        used = {slot for _, _, slot in active}
        rank = 0
        while True:
            slot_index, _ = self.resolver.queue_slot_for_rank(event.destination_id, rank)
            if slot_index not in used:
                break
            rank += 1
        active.append((event.end_s, event.carrier_id, slot_index))
        self.queue_active[event.destination_id] = active
        return slot_index

    def _remove_from_queue(self, destination_id: int, carrier_id: int):
        self.queue_active[destination_id] = [
            item for item in self.queue_active[destination_id] if item[1] != carrier_id
        ]

    def process(self, event: LogEvent):
        self._seed_carrier(event.carrier_id)
        current = self.positions.get(event.carrier_id, self.resolver.initial_position)

        if event.event_type == "TRANSPORT":
            if event.destination_id is None:
                return
            if event.next_event_type == "QUEUE" and event.next_destination_id == event.destination_id:
                path = self.resolver.transport_to_entry_path(current, event.origin_id, event.destination_id)
            else:
                path = self.resolver.transport_to_processing_path(current, event.origin_id, event.destination_id)
            timed_segments, _effective_duration = self.resolver.timed_segments_for_path(path, event.duration_s)
            self._move_timed_or_set(event.carrier_id, timed_segments)
            return

        if event.destination_id is None:
            return

        if event.event_type == "QUEUE":
            slot_index = self._assign_queue_slot(event)
            target = self.resolver.buffer_slots(event.destination_id)[slot_index]
            if event.duration_s <= 0 and distance(current, target) > 1e-6:
                return
            if distance(current, self.resolver.entry(event.destination_id)) < 1e-6:
                path = self.resolver.entry_to_buffer_path(event.destination_id, slot_index)
            elif event.origin_id == event.destination_id and distance(current, self.resolver.processing(event.destination_id)) < 1e-6:
                path = self.resolver.processing_to_buffer_path(event.destination_id, slot_index)
            else:
                path = [current, target]
            self._move_or_set(event.carrier_id, path, self._wall_duration(event.duration_s))
            return

        if event.event_type == "PROCESSING":
            self._remove_from_queue(event.destination_id, event.carrier_id)
            target = self.resolver.processing(event.destination_id)
            if event.duration_s <= 0 and distance(current, target) > 1e-6:
                return
            slots = self.resolver.buffer_slots(event.destination_id)
            if any(distance(current, slot) < 1e-6 for slot in slots):
                slot_index = min(range(len(slots)), key=lambda i: distance(current, slots[i]))
                path = self.resolver.buffer_to_processing_path(event.destination_id, slot_index)
            elif distance(current, self.resolver.entry(event.destination_id)) < 1e-6:
                path = self.resolver.entry_to_processing_path(event.destination_id)
            else:
                path = [current, target]
            self._move_or_set(event.carrier_id, path, self._micro_duration(event))
            return

        self._send({"type": "set_position", "carrier_id": event.carrier_id, "position": list(current)})


class CsvLogFollower:
    def __init__(
        self,
        path: Path,
        poll_interval: float,
        drain_existing: bool,
        idle_timeout: Optional[float],
        max_events: Optional[int],
        replay_timing: bool = False,
        replay_scale: float = 1.0,
    ):
        self.path = Path(path)
        self.poll_interval = float(poll_interval)
        self.drain_existing = bool(drain_existing)
        self.idle_timeout = idle_timeout
        self.max_events = max_events
        self.replay_timing = bool(replay_timing)
        self.replay_scale = max(0.0, float(replay_scale))

    def ensure_file(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() or self.path.stat().st_size == 0:
            self.path.write_text(",".join(CSV_COLUMNS) + "\n", encoding="utf-8")

    @staticmethod
    def _carrier_key(row: dict) -> str:
        return str(row.get("carrier_id", "")).strip()

    @staticmethod
    def _is_transport(row: dict) -> bool:
        return str(row.get("event_type", "")).strip().upper() == "TRANSPORT"

    @staticmethod
    def _attach_next_event(row: dict, next_row: dict):
        row["_next_event_type"] = str(next_row.get("event_type", "")).strip().upper()
        row["_next_destination_id"] = str(next_row.get("destination_id", "")).strip()

    @staticmethod
    def _row_start_seconds(row: dict) -> float:
        return parse_time_to_seconds(row.get("start_time", "0"))

    @staticmethod
    def _row_end_seconds(row: dict) -> float:
        start_s = CsvLogFollower._row_start_seconds(row)
        processing_s = parse_time_to_seconds(row.get("processing_time", "0"))
        end_s = parse_time_to_seconds(row.get("end_time", "0"))
        if end_s < start_s or (end_s == start_s and processing_s > 0):
            return start_s + processing_s
        return end_s

    def rows(self):
        self.ensure_file()
        with self.path.open("r", encoding="utf-8-sig", newline="") as f:
            header = f.readline()
            if not header:
                raise ValueError(f"CSV log has no header: {self.path}")
            fieldnames = next(csv.reader([header]))
            missing = [name for name in CSV_COLUMNS if name not in fieldnames]
            if missing:
                raise ValueError(f"CSV log missing columns {missing}: {self.path}")

            if self.drain_existing:
                rows = []
                for source_index, line in enumerate(f):
                    if not line.strip():
                        continue
                    reader = csv.DictReader([header, line])
                    rows.append((source_index, next(reader)))

                rows.sort(
                    key=lambda item: (
                        self._row_start_seconds(item[1]),
                        self._row_end_seconds(item[1]),
                        item[0],
                    )
                )
                ordered_rows = [row for _, row in rows]

                for i, row in enumerate(ordered_rows):
                    for next_row in ordered_rows[i + 1:]:
                        if self._carrier_key(next_row) == self._carrier_key(row):
                            self._attach_next_event(row, next_row)
                            break

                replay_start_wall: Optional[float] = None
                replay_start_log: Optional[float] = None
                for count, row in enumerate(ordered_rows):
                    if self.max_events is not None and count >= self.max_events:
                        break
                    if self.replay_timing:
                        log_start = parse_time_to_seconds(row.get("start_time", "0"))
                        if replay_start_wall is None:
                            replay_start_wall = time.monotonic()
                            replay_start_log = log_start
                        target_wall = replay_start_wall + max(0.0, log_start - float(replay_start_log)) * self.replay_scale
                        while True:
                            wait_s = target_wall - time.monotonic()
                            if wait_s <= 0:
                                break
                            time.sleep(min(wait_s, self.poll_interval))
                    yield row
                return

            count = 0
            pending_transport_by_carrier: Dict[str, dict] = {}
            if not self.drain_existing:
                f.seek(0, 2)

            last_activity = time.monotonic()
            while True:
                line = f.readline()
                if not line:
                    if self.idle_timeout is not None and time.monotonic() - last_activity >= self.idle_timeout:
                        for pending in list(pending_transport_by_carrier.values()):
                            if self.max_events is not None and count >= self.max_events:
                                break
                            yield pending
                            count += 1
                        pending_transport_by_carrier.clear()
                        break
                    time.sleep(self.poll_interval)
                    continue
                last_activity = time.monotonic()
                if not line.strip():
                    continue
                reader = csv.DictReader([header, line])
                row = next(reader)

                carrier_key = self._carrier_key(row)
                current_start_s = self._row_start_seconds(row)
                for pending_key, pending in list(pending_transport_by_carrier.items()):
                    if pending_key == carrier_key:
                        continue
                    if self._row_end_seconds(pending) < current_start_s - 1e-9:
                        yield pending
                        count += 1
                        pending_transport_by_carrier.pop(pending_key, None)
                        if self.max_events is not None and count >= self.max_events:
                            break
                if self.max_events is not None and count >= self.max_events:
                    break

                pending = pending_transport_by_carrier.pop(carrier_key, None)
                if pending is not None:
                    self._attach_next_event(pending, row)
                    yield pending
                    count += 1
                    if self.max_events is not None and count >= self.max_events:
                        break

                if self._is_transport(row) and carrier_key:
                    pending_transport_by_carrier[carrier_key] = row
                    continue

                yield row
                count += 1
                if self.max_events is not None and count >= self.max_events:
                    break


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live log-driven TCP sender for USD Composer.")
    parser.add_argument("--config", default=str(CONFIG_JSON), help="RealTimeTCPlogs config JSON.")
    parser.add_argument("--layout", default="", help="Override layout JSON.")
    parser.add_argument("--logs", default="", help="CSV log file to follow.")
    parser.add_argument("--host", default="", help="TCP bridge host.")
    parser.add_argument("--port", type=int, default=0, help="TCP bridge port.")
    parser.add_argument("--timeout", type=float, default=0.0, help="TCP connection timeout.")
    parser.add_argument("--duration-scale", type=float, default=None, help="Scale log durations to wall-clock durations.")
    parser.add_argument("--poll-interval", type=float, default=None, help="CSV follow polling interval.")
    parser.add_argument("--drain-existing", action="store_true", help="Process existing CSV rows first. Debug only; default waits for new rows.")
    parser.add_argument("--replay-timing", action="store_true", help="When draining existing rows, wait according to CSV start_time.")
    parser.add_argument("--replay-scale", type=float, default=None, help="Scale CSV start_time waits for --replay-timing. Example: 0.1 is 10x faster.")
    parser.add_argument("--idle-timeout", type=float, default=None, help="Stop after this many idle seconds.")
    parser.add_argument("--max-events", type=int, default=None, help="Stop after N processed rows.")
    parser.add_argument("--dry-run", action="store_true", help="Do not open TCP; useful for tests.")
    parser.add_argument("--print-messages", action="store_true", help="Print outgoing JSON messages.")
    parser.add_argument("--audit-log", default="", help="Optional NDJSON copy of outgoing messages.")
    return parser


def main():
    args = build_parser().parse_args()
    config_path = resolve_project_path(args.config)
    config = load_json(config_path)

    layout_path = resolve_project_path(args.layout or config["layout"])
    logs_path = resolve_project_path(args.logs or config["logs"]["path"])
    composer_stage = resolve_project_path(config.get("composer_stage", "3d/RealTimeTCPlogs/modelbuffer.usd"))
    tcp_cfg = config.get("tcp", {})
    runtime_cfg = config.get("runtime", {})
    logs_cfg = config.get("logs", {})

    host = args.host or tcp_cfg.get("host", "127.0.0.1")
    port = int(args.port or tcp_cfg.get("port", 5051))
    timeout = float(args.timeout or tcp_cfg.get("timeout", 2.0))
    duration_scale = float(args.duration_scale if args.duration_scale is not None else runtime_cfg.get("duration_scale", 1.0))
    replay_scale = float(args.replay_scale if args.replay_scale is not None else duration_scale)
    poll_interval = float(args.poll_interval if args.poll_interval is not None else logs_cfg.get("poll_interval", 0.1))
    audit_log = resolve_project_path(args.audit_log) if args.audit_log else None

    print("RealTimeTCPlogs live log sender")
    print(f"Layout: {layout_path}")
    print(f"Logs: {logs_path}")
    print(f"Composer stage expected: {composer_stage}")
    print(f"TCP: {host}:{port}")
    if args.drain_existing and args.replay_timing:
        print(f"Mode: replay existing rows with CSV timing (scale={replay_scale})")
    else:
        print("Mode: follow new CSV rows in real time" if not args.drain_existing else "Mode: drain existing rows then follow (debug)")

    layout = load_json(layout_path)
    follower = CsvLogFollower(
        logs_path,
        poll_interval=poll_interval,
        drain_existing=args.drain_existing,
        idle_timeout=args.idle_timeout,
        max_events=args.max_events,
        replay_timing=args.replay_timing,
        replay_scale=replay_scale,
    )
    sink = MessageSink(
        host=host,
        port=port,
        timeout=timeout,
        dry_run=args.dry_run,
        print_messages=args.print_messages,
        audit_log=audit_log,
    )
    mapper = LiveLogMapper(layout, sink, duration_scale=duration_scale)

    processed = 0
    try:
        sink.connect()
        for row in follower.rows():
            event = parse_log_event(row)
            mapper.process(event)
            processed += 1
            print(
                f"sent live log event #{processed}: "
                f"carrier={event.carrier_id} type={event.event_type} dest={event.destination_id}"
            )
    finally:
        sink.close()

    print(f"RealTimeTCPlogs stopped after {processed} event(s).")


if __name__ == "__main__":
    main()
