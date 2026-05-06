from pathlib import Path
import csv
import json
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from pxr import Usd, UsdGeom, Gf, UsdLux

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from marker_layout import resolve_layout_markers

SCENE_USD = PROJECT_ROOT / "3d" / "Simulogs" / "modelbuffer_build.usd"
OUTPUT_USD = PROJECT_ROOT / "3d" / "Simulogs" / "modelbuffer_replay.usd"
LAYOUT_JSON = Path(__file__).resolve().with_name("production_layout_simulogs.json")
LOGS_CSV = Path(__file__).resolve().parent / "CSV" / "logs.csv"

Vec3 = Tuple[float, float, float]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return resolve_layout_markers(json.load(f), PROJECT_ROOT)


def parse_time_to_seconds(value) -> float:
    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return 0.0
    if ":" in text:
        h, m, s = text.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    return float(text)


def safe_int(value) -> Optional[int]:
    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return None
    return int(float(text))


def point3(values) -> Vec3:
    if len(values) != 3:
        raise ValueError(f"Coordonnées invalides: {values}")
    return (float(values[0]), float(values[1]), float(values[2]))


def distance(a: Vec3, b: Vec3) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def interpolate(a: Vec3, b: Vec3, t: float) -> Vec3:
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))  # type: ignore[return-value]


def ensure_translate_op(prim):
    xformable = UsdGeom.Xformable(prim)
    for op in xformable.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            return op
    return xformable.AddTranslateOp()


class LayoutResolver:
    def __init__(self, config: dict):
        self.resource_map = {int(k): v for k, v in config["resource_map"].items()}
        self.workstations = config["workstations"]
        self.routes = {k: [point3(p) for p in v] for k, v in config["routes"].items()}
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
        self.timeline_fps = float(sim_params.get("timeline_fps", 24.0))
        self.path_sample_step = float(sim_params.get("path_sample_step", 12.0))
        self.max_keys_per_motion = int(sim_params.get("max_keys_per_motion", 120))
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

    def timed_points_for_path(self, waypoints: List[Vec3], start_seconds: float, end_seconds: float) -> List[Tuple[float, Vec3]]:
        path = self._dedupe(waypoints)
        if not path:
            return []
        if len(path) == 1:
            return [(float(start_seconds), path[-1]), (float(end_seconds), path[-1])]

        duration = max(0.0, float(end_seconds) - float(start_seconds))
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

        effective_duration = max(duration, fixed_total)
        if fixed_total > duration + 1e-6:
            print(
                "WARNING: log transport shorter than fixed transfer duration; "
                f"using {effective_duration:.3f}s instead of {duration:.3f}s."
            )
        normal_budget = max(0.0, effective_duration - fixed_total)

        current_time = float(start_seconds)
        timed = [(current_time, path[0])]
        for _start_pos, end_pos, value, is_transfer, _transfer_name in segment_meta:
            if is_transfer:
                step_duration = float(value)
            elif normal_total > 1e-9:
                step_duration = normal_budget * (float(value) / normal_total)
            else:
                step_duration = 0.0
            current_time += step_duration
            timed.append((current_time, end_pos))

        target_end = float(start_seconds) + effective_duration
        if current_time < target_end - 1e-6:
            timed.append((target_end, path[-1]))
        return timed

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
        # rank 0 = plus proche du process, rangs suivants = plus en arrière dans la file
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
                return self._dedupe(path)

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
        return self._dedupe(path)

    def buffer_to_processing_path(self, resource_id: int, slot_index: int) -> List[Vec3]:
        slots = self.buffer_slots(resource_id)
        slot_index = min(max(0, slot_index), len(slots) - 1)
        slot = slots[slot_index]
        explicit = self.station(resource_id).get("buffer_to_processing")
        if explicit:
            return self._dedupe([slot] + [point3(p) for p in explicit if tuple(point3(p)) != tuple(slot)])
        return self._dedupe([slot, self.processing(resource_id)])

    def entry_to_processing_path(self, resource_id: int) -> List[Vec3]:
        return self._dedupe(self.explicit_path(resource_id, "entry_to_processing", [self.entry(resource_id), self.processing(resource_id)]))

    def processing_to_exit_path(self, resource_id: int) -> List[Vec3]:
        return self._dedupe(self.explicit_path(resource_id, "processing_to_exit", [self.processing(resource_id), self.exit(resource_id)]))

    def processing_to_buffer_path(self, resource_id: int, slot_index: int) -> List[Vec3]:
        slots = self.buffer_slots(resource_id)
        slot_index = min(max(0, slot_index), len(slots) - 1)
        station = self.station(resource_id)
        explicit = station.get("processing_to_buffer")
        if explicit:
            target = slots[slot_index]
            path = [self.processing(resource_id)] + [point3(p) for p in explicit]
            for i, point in enumerate(path):
                if distance(point, target) <= 1e-6:
                    return self._dedupe(path[: i + 1])
            if path[-1] != target:
                path.append(target)
            return self._dedupe(path)
        return self._dedupe([self.processing(resource_id), slots[slot_index]])

    def route_between_stations(self, origin_id: Optional[int], destination_id: int) -> List[Vec3]:
        origin_key = "START" if origin_id is None else str(origin_id)
        key = f"{origin_key}->{destination_id}"
        route = self.routes.get(key)
        if route:
            return self._dedupe(route)

        start_pos = self.initial_position if origin_id is None else self.exit(origin_id)
        return self._dedupe([start_pos, self.entry(destination_id)])

    def transport_path(
        self,
        current_position: Vec3,
        origin_id: Optional[int],
        destination_id: int,
        arrival_mode: str,
        queue_slot_index: int = 0,
    ) -> List[Vec3]:
        path: List[Vec3] = [current_position]

        if origin_id is not None:
            origin_processing = self.processing(origin_id)
            origin_exit = self.exit(origin_id)

            # Si on est encore au process, il faut sortir du poste avant de prendre la route globale.
            if distance(current_position, origin_processing) < 1e-6:
                for p in self.processing_to_exit_path(origin_id):
                    if distance(path[-1], p) > 1e-6:
                        path.append(p)
            elif distance(current_position, origin_exit) < 1e-6:
                pass

        for p in self.route_between_stations(origin_id, destination_id):
            if distance(path[-1], p) > 1e-6:
                path.append(p)

        if arrival_mode == "PROCESSING":
            branch = self.entry_to_processing_path(destination_id)
        elif arrival_mode == "QUEUE":
            branch = [self.entry(destination_id)]
        else:
            branch = [self.entry(destination_id)]

        for p in branch:
            if distance(path[-1], p) > 1e-6:
                path.append(p)

        return self.sample_route(path)

    def sample_route(self, route: List[Vec3]) -> List[Vec3]:
        route = self._dedupe(route)
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

        sampled = self._dedupe(sampled)
        if len(sampled) > self.max_keys_per_motion:
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
            for k in range(self.max_keys_per_motion):
                idx = round(k * last / (self.max_keys_per_motion - 1))
                reduced_indices.add(idx)
            reduced = [sampled[idx] for idx in sorted(reduced_indices)]
            sampled = self._dedupe(reduced)
        return sampled

    @staticmethod
    def _dedupe(points: List[Vec3]) -> List[Vec3]:
        out: List[Vec3] = []
        for p in points:
            p = tuple(float(v) for v in p)
            if not out or distance(out[-1], p) > 1e-9:
                out.append(p)
        return out


def load_events(csv_path: Path) -> List[dict]:
    required = {
        "carrier_id", "origin_id", "event_type", "destination_id",
        "start_time", "processing_time", "end_time", "task_id", "details"
    }
    events = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Colonnes CSV manquantes: {sorted(missing)}")

        for row in reader:
            start_s = parse_time_to_seconds(row["start_time"])
            processing_s = parse_time_to_seconds(row["processing_time"])
            end_s = parse_time_to_seconds(row["end_time"])
            if end_s < start_s:
                end_s = start_s + processing_s
            if end_s == start_s and processing_s > 0:
                end_s = start_s + processing_s

            events.append({
                "carrier_id": int(float(row["carrier_id"])),
                "origin_id": safe_int(row["origin_id"]),
                "destination_id": safe_int(row["destination_id"]),
                "event_type": str(row["event_type"]).strip().upper(),
                "start_s": start_s,
                "end_s": end_s,
                "task_id": str(row["task_id"]).strip(),
                "details": str(row["details"]).strip(),
            })

    events.sort(key=lambda e: (e["carrier_id"], e["start_s"], e["end_s"], e["task_id"], e["event_type"]))
    return events


def assign_queue_slots(events: List[dict], resolver: LayoutResolver) -> Dict[int, int]:
    by_station: Dict[int, List[Tuple[int, dict]]] = defaultdict(list)
    for idx, event in enumerate(events):
        if event["event_type"] == "QUEUE" and event["destination_id"] is not None:
            by_station[event["destination_id"]].append((idx, event))

    slot_map: Dict[int, int] = {}
    for destination_id, station_events in by_station.items():
        station_events.sort(key=lambda x: (x[1]["start_s"], x[1]["end_s"], x[0]))
        active: List[Tuple[float, int]] = []
        for idx, event in station_events:
            active = [(end_t, rank) for end_t, rank in active if end_t > event["start_s"]]
            used_ranks = {rank for _, rank in active}
            chosen_rank = 0
            while chosen_rank in used_ranks:
                chosen_rank += 1
            active.append((event["end_s"], chosen_rank))
            slot_index, _ = resolver.queue_slot_for_rank(destination_id, chosen_rank)
            slot_map[idx] = slot_index
    return slot_map


class OmniverseBridge:
    def __init__(self, usd_path: Path, fps: float):
        self.stage = Usd.Stage.Open(str(usd_path))
        if not self.stage:
            raise RuntimeError(f"Impossible d'ouvrir la scène USD: {usd_path}")
        self.fps = fps
        self.keyframes: Dict[int, List[Tuple[float, Vec3]]] = {}
        self.last_positions: Dict[int, Vec3] = {}

    def sec_to_tc(self, seconds: float) -> float:
        return float(seconds) * self.fps

    def add_keyframe_seconds(self, palette_id: int, position: Vec3, time_seconds: float):
        pos = tuple(float(v) for v in position)
        tc = self.sec_to_tc(time_seconds)
        self.keyframes.setdefault(palette_id, []).append((tc, pos))
        self.last_positions[palette_id] = pos

    def get_last_position(self, palette_id: int) -> Optional[Vec3]:
        return self.last_positions.get(palette_id)

    def add_hold_seconds(self, palette_id: int, position: Vec3, start_seconds: float, end_seconds: float):
        self.add_keyframe_seconds(palette_id, position, start_seconds)
        self.add_keyframe_seconds(palette_id, position, end_seconds)

    def add_path_seconds(self, palette_id: int, waypoints: List[Vec3], start_seconds: float, end_seconds: float):
        duration = max(0.0, end_seconds - start_seconds)
        if not waypoints:
            return
        waypoints = LayoutResolver._dedupe(waypoints)
        if len(waypoints) == 1 or duration <= 0:
            self.add_hold_seconds(palette_id, waypoints[-1], start_seconds, end_seconds)
            return

        cumulative = [0.0]
        total = 0.0
        for i in range(len(waypoints) - 1):
            total += distance(waypoints[i], waypoints[i + 1])
            cumulative.append(total)

        if total <= 1e-9:
            self.add_hold_seconds(palette_id, waypoints[-1], start_seconds, end_seconds)
            return

        for i, pos in enumerate(waypoints):
            alpha = cumulative[i] / total
            t = start_seconds + alpha * duration
            self.add_keyframe_seconds(palette_id, pos, t)

    def add_timed_path_seconds(self, palette_id: int, timed_points: List[Tuple[float, Vec3]]):
        if not timed_points:
            return
        for seconds, pos in timed_points:
            self.add_keyframe_seconds(palette_id, pos, seconds)

    def ensure_good_light(self):
        light_path = "/World/SimulogsKeyLight"
        if self.stage.GetPrimAtPath(light_path).IsValid():
            self.stage.RemovePrim(light_path)
        light = UsdLux.SphereLight.Define(self.stage, light_path)
        light.CreateIntensityAttr(30000.0)
        light.CreateRadiusAttr(75.0)
        light.CreateExposureAttr(1.0)
        xform = UsdGeom.Xformable(light.GetPrim())
        xform.AddTranslateOp().Set(Gf.Vec3d(-250.0, 350.0, 650.0))

    def ensure_palettes_visible(self):
        palettes_scope = self.stage.GetPrimAtPath("/World/Palettes")
        if not palettes_scope.IsValid():
            return
        for child in palettes_scope.GetChildren():
            UsdGeom.Imageable(child).MakeVisible()

    def apply_animation(self, output_usd: Path):
        self.stage.SetFramesPerSecond(self.fps)
        self.stage.SetTimeCodesPerSecond(self.fps)
        self.stage.SetStartTimeCode(0)
        self.ensure_good_light()
        self.ensure_palettes_visible()

        max_tc = 0.0
        for palette_id, keyframes in self.keyframes.items():
            prim_path = f"/World/Palettes/Palette_{palette_id}"
            prim = self.stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                print(f"ERROR: {prim_path} introuvable")
                continue

            translate_op = ensure_translate_op(prim)
            keyframes.sort(key=lambda x: (x[0], x[1]))

            deduped: List[Tuple[float, Vec3]] = []
            seen_times = set()
            for tc, pos in keyframes:
                rounded = round(tc, 6)
                if rounded in seen_times:
                    deduped[-1] = (tc, pos)
                else:
                    seen_times.add(rounded)
                    deduped.append((tc, pos))

            for tc, pos in deduped:
                translate_op.Set(Gf.Vec3d(*pos), time=tc)
                max_tc = max(max_tc, tc)

        self.stage.SetEndTimeCode(max_tc)
        output_usd.parent.mkdir(parents=True, exist_ok=True)
        output_usd.parent.mkdir(parents=True, exist_ok=True)
        self.stage.Export(str(output_usd))
        replay_seconds = max_tc / self.fps if self.fps > 0 else 0.0
        print(f"Replay duration from USD timeline: {replay_seconds:.3f}s")
        print(f"Animated USD saved: {output_usd}")


def next_event_same_carrier(events: List[dict], index: int) -> Tuple[Optional[dict], Optional[int]]:
    carrier_id = events[index]["carrier_id"]
    for j in range(index + 1, len(events)):
        if events[j]["carrier_id"] == carrier_id:
            return events[j], j
    return None, None


def movement_budget(start_s: float, end_s: float, resolver: LayoutResolver) -> float:
    duration = max(0.0, end_s - start_s)
    if duration <= 0:
        return 0.0
    return min(duration, max(resolver.micro_move_seconds, duration * 0.25))


def main():
    config = load_json(LAYOUT_JSON)
    resolver = LayoutResolver(config)
    events = load_events(LOGS_CSV)
    if events:
        csv_start = min(e["start_s"] for e in events)
        csv_end = max(e["end_s"] for e in events)
        print(f"CSV makespan: {csv_end - csv_start:.3f}s (start={csv_start:.3f}, end={csv_end:.3f})")
    queue_slot_by_event_index = assign_queue_slots(events, resolver)
    bridge = OmniverseBridge(SCENE_USD, resolver.timeline_fps)

    for carrier_id in sorted({e["carrier_id"] for e in events}):
        bridge.add_keyframe_seconds(carrier_id, resolver.initial_position, 0.0)

    carrier_available: Dict[int, float] = defaultdict(float)

    for idx, event in enumerate(events):
        carrier_id = event["carrier_id"]
        event_type = event["event_type"]
        origin_id = event["origin_id"]
        destination_id = event["destination_id"]
        scheduled_start_t = event["start_s"]
        scheduled_end_t = event["end_s"]
        event_duration = max(0.0, scheduled_end_t - scheduled_start_t)
        start_t = max(scheduled_start_t, carrier_available[carrier_id])
        end_t = start_t + event_duration
        current = bridge.get_last_position(carrier_id) or resolver.initial_position

        if event_type == "TRANSPORT":
            if destination_id is None:
                carrier_available[carrier_id] = max(carrier_available[carrier_id], end_t)
                continue
            next_event, next_idx = next_event_same_carrier(events, idx)
            arrival_mode = "PROCESSING"
            queue_slot_index = 0
            if next_event and next_event.get("destination_id") == destination_id:
                if next_event["event_type"] == "QUEUE":
                    arrival_mode = "QUEUE"
                    queue_slot_index = queue_slot_by_event_index.get(next_idx, 0)
                elif next_event["event_type"] == "PROCESSING":
                    arrival_mode = "PROCESSING"

            path = resolver.transport_path(
                current_position=current,
                origin_id=origin_id,
                destination_id=destination_id,
                arrival_mode=arrival_mode,
                queue_slot_index=queue_slot_index,
            )
            timed_points = resolver.timed_points_for_path(path, start_t, end_t)
            if timed_points:
                end_t = max(seconds for seconds, _ in timed_points)
            bridge.add_timed_path_seconds(carrier_id, timed_points)
            carrier_available[carrier_id] = max(carrier_available[carrier_id], end_t)
            continue

        if destination_id is None:
            carrier_available[carrier_id] = max(carrier_available[carrier_id], end_t)
            continue

        if event_type == "QUEUE":
            slot_index = queue_slot_by_event_index.get(idx, 0)
            target = resolver.buffer_slots(destination_id)[min(slot_index, len(resolver.buffer_slots(destination_id)) - 1)]
            budget = max(0.0, end_t - start_t)
            if budget <= 0 and distance(current, target) > 1e-6:
                bridge.add_hold_seconds(carrier_id, current, start_t, end_t)
                carrier_available[carrier_id] = max(carrier_available[carrier_id], end_t)
                continue
            if distance(current, target) > 1e-6 and budget > 0:
                if origin_id == destination_id and distance(current, resolver.processing(destination_id)) < 1e-6:
                    move_path = resolver.processing_to_buffer_path(destination_id, slot_index)
                elif distance(current, resolver.entry(destination_id)) < 1e-6:
                    move_path = resolver.entry_to_buffer_path(destination_id, slot_index)
                else:
                    move_path = [current, target]
                bridge.add_path_seconds(carrier_id, move_path, start_t, start_t + budget)
                bridge.add_hold_seconds(carrier_id, target, start_t + budget, end_t)
            else:
                bridge.add_hold_seconds(carrier_id, target, start_t, end_t)
            carrier_available[carrier_id] = max(carrier_available[carrier_id], end_t)
            continue

        if event_type == "PROCESSING":
            target = resolver.processing(destination_id)
            budget = movement_budget(start_t, end_t, resolver)
            if budget <= 0 and distance(current, target) > 1e-6:
                bridge.add_hold_seconds(carrier_id, current, start_t, end_t)
                carrier_available[carrier_id] = max(carrier_available[carrier_id], end_t)
                continue
            if distance(current, target) > 1e-6 and budget > 0:
                slot_index = queue_slot_by_event_index.get(idx - 1, 0)
                if origin_id == destination_id and distance(current, resolver.buffer_slots(destination_id)[min(slot_index, len(resolver.buffer_slots(destination_id)) - 1)]) < 1e-6:
                    move_path = resolver.buffer_to_processing_path(destination_id, slot_index)
                elif distance(current, resolver.entry(destination_id)) < 1e-6:
                    move_path = resolver.entry_to_processing_path(destination_id)
                else:
                    move_path = [current, target]
                bridge.add_path_seconds(carrier_id, move_path, start_t, start_t + budget)
                bridge.add_hold_seconds(carrier_id, target, start_t + budget, end_t)
            else:
                bridge.add_hold_seconds(carrier_id, target, start_t, end_t)
            carrier_available[carrier_id] = max(carrier_available[carrier_id], end_t)
            continue

        # Sécurité : pour un type non géré, on reste immobile.
        bridge.add_hold_seconds(carrier_id, current, start_t, end_t)
        carrier_available[carrier_id] = max(carrier_available[carrier_id], end_t)

    bridge.apply_animation(OUTPUT_USD)


if __name__ == "__main__":
    main()
