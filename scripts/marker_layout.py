from pathlib import Path
from typing import Any, Dict


MARKER_PREFIX = "marker:"
MARKER_ROOT = "/World/Markers"
MARKER_ROOT_CANDIDATES = (
    "/World/Markers",
    "/model/Markers",
    "/Markers",
)


def _import_usd():
    try:
        from pxr import Usd, UsdGeom  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on USD Python env
        raise RuntimeError(
            "Cannot resolve marker layout because pxr.Usd is unavailable. "
            "Run this script from the USD Composer / Omniverse Python environment, "
            "or generate a coordinate layout before running it."
        ) from exc
    return Usd, UsdGeom


def _marker_prim_path(marker_name: str) -> str:
    name = str(marker_name).strip()
    if name.startswith(MARKER_PREFIX):
        name = name[len(MARKER_PREFIX) :]
    if name.startswith("/World/Markers/"):
        return name
    if name.startswith("/"):
        return name
    return f"{MARKER_ROOT}/{name}"


def _project_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root / path


def _find_marker_roots(stage) -> list:
    roots = []
    for root_path in MARKER_ROOT_CANDIDATES:
        prim = stage.GetPrimAtPath(root_path)
        if prim and prim.IsValid():
            roots.append(root_path)
    if roots:
        return roots

    for prim in stage.Traverse():
        if prim.GetName() == "Markers":
            roots.append(str(prim.GetPath()))
    return roots


def load_marker_positions(stage_path: Path) -> Dict[str, list]:
    Usd, UsdGeom = _import_usd()
    stage = Usd.Stage.Open(str(stage_path))
    if not stage:
        raise RuntimeError(f"Cannot open marker stage: {stage_path}")

    marker_roots = _find_marker_roots(stage)
    if not marker_roots:
        raise RuntimeError(
            "Marker root not found in stage. Expected one of: "
            + ", ".join(MARKER_ROOT_CANDIDATES)
        )

    positions: Dict[str, list] = {}
    for prim in stage.Traverse():
        path = str(prim.GetPath())
        matching_root = None
        for root_path in marker_roots:
            if path.startswith(f"{root_path}/"):
                matching_root = root_path
                break
        if not matching_root:
            continue
        xformable = UsdGeom.Xformable(prim)
        if not xformable:
            continue
        matrix = xformable.ComputeLocalToWorldTransform(0)
        translation = matrix.ExtractTranslation()
        relative = path[len(f"{matching_root}/") :]
        value = [float(translation[0]), float(translation[1]), float(translation[2])]
        positions[relative] = value
        positions[path] = value
        positions[prim.GetName()] = value
    return positions


def resolve_marker_value(value: Any, marker_positions: Dict[str, list]) -> Any:
    if isinstance(value, str) and value.startswith(MARKER_PREFIX):
        marker_name = value[len(MARKER_PREFIX) :]
        full_path = _marker_prim_path(marker_name)
        relative = full_path[len(f"{MARKER_ROOT}/") :] if full_path.startswith(f"{MARKER_ROOT}/") else marker_name
        if relative in marker_positions:
            return marker_positions[relative]
        if full_path in marker_positions:
            return marker_positions[full_path]
        raise KeyError(f"Marker not found: {value} ({full_path})")

    if isinstance(value, list):
        return [resolve_marker_value(item, marker_positions) for item in value]

    if isinstance(value, dict):
        return {
            key: resolve_marker_value(item, marker_positions)
            for key, item in value.items()
            if key != "marker_stage"
        }

    return value


def resolve_layout_markers(layout: dict, project_root: Path) -> dict:
    marker_stage = layout.get("marker_stage")
    if not marker_stage:
        return layout
    stage_path = _project_path(project_root, str(marker_stage))
    marker_positions = load_marker_positions(stage_path)
    return resolve_marker_value(layout, marker_positions)
