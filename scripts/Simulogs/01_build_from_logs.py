from pathlib import Path
import csv
import json
import sys
from pxr import Usd, UsdGeom, Gf

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from marker_layout import resolve_layout_markers

BASE_USD = PROJECT_ROOT / "3d" / "layout" / "modelbuffer.usd"
CARRIER_USD = PROJECT_ROOT / "3d" / "layout" / "carrier.usd"
OUTPUT_USD = PROJECT_ROOT / "3d" / "Simulogs" / "modelbuffer_build.usd"
LAYOUT_JSON = Path(__file__).resolve().with_name("production_layout_simulogs.json")
LOGS_CSV = Path(__file__).resolve().parent / "CSV" / "logs.csv"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return resolve_layout_markers(json.load(f), PROJECT_ROOT)


def get_palette_ids(csv_path: Path):
    ids = set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if "carrier_id" not in (reader.fieldnames or []):
            raise ValueError("Le CSV doit contenir la colonne 'carrier_id'")
        for row in reader:
            value = str(row["carrier_id"]).strip()
            if value:
                ids.add(int(float(value)))
    return sorted(ids)


def ensure_world(stage: Usd.Stage):
    if not stage.GetPrimAtPath("/World").IsValid():
        UsdGeom.Xform.Define(stage, "/World")


def remove_if_exists(stage: Usd.Stage, prim_path: str):
    if stage.GetPrimAtPath(prim_path).IsValid():
        stage.RemovePrim(prim_path)


def get_or_create_translate_op(xformable: UsdGeom.Xformable):
    for op in xformable.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            return op
    return xformable.AddTranslateOp()


def get_or_create_scale_op(xformable: UsdGeom.Xformable):
    for op in xformable.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeScale:
            return op
    return xformable.AddScaleOp()


def create_palette_template(stage: Usd.Stage, config: dict):
    UsdGeom.Scope.Define(stage, "/World/Prototypes")

    template_path = config["palette_template"]["prototype_path"]
    template_xform = UsdGeom.Xform.Define(stage, template_path)
    UsdGeom.Imageable(template_xform.GetPrim()).MakeInvisible()

    asset_path = PROJECT_ROOT / config["palette_template"].get("asset_path", CARRIER_USD.relative_to(PROJECT_ROOT))
    if not asset_path.exists():
        raise FileNotFoundError(f"Carrier USD not found: {asset_path}")
    carrier_xform = UsdGeom.Xform.Define(stage, f"{template_path}/Geometry")
    carrier_xform.GetPrim().GetReferences().ClearReferences()
    carrier_xform.GetPrim().GetReferences().AddReference(asset_path.as_posix())

    return template_path


def create_palette_instances(stage: Usd.Stage, template_path: str, palette_ids, config: dict):
    UsdGeom.Scope.Define(stage, "/World/Palettes")

    initial_pos = config["palette_template"]["initial_position"]
    scale = config["palette_template"]["scale"]
    instance_prefix = config["palette_template"]["instance_prefix"]

    for palette_id in palette_ids:
        prim_path = f"{instance_prefix}{palette_id}"
        xform = UsdGeom.Xform.Define(stage, prim_path)
        prim = xform.GetPrim()

        prim.GetReferences().ClearReferences()
        prim.GetReferences().AddInternalReference(template_path)

        translate_op = get_or_create_translate_op(UsdGeom.Xformable(prim))
        scale_op = get_or_create_scale_op(UsdGeom.Xformable(prim))

        translate_op.Set(Gf.Vec3d(*initial_pos))
        scale_op.Set(Gf.Vec3d(*scale))

        print(f"Palette créée: {prim_path}")


def main():
    config = load_json(LAYOUT_JSON)
    palette_ids = get_palette_ids(LOGS_CSV)

    stage = Usd.Stage.Open(str(BASE_USD))
    if not stage:
        raise RuntimeError(f"Impossible d'ouvrir le fichier USD de base: {BASE_USD}")

    ensure_world(stage)
    remove_if_exists(stage, "/World/Palettes")
    remove_if_exists(stage, "/World/Prototypes")

    template_path = create_palette_template(stage, config)
    create_palette_instances(stage, template_path, palette_ids, config)

    OUTPUT_USD.parent.mkdir(parents=True, exist_ok=True)
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
    stage.Export(str(OUTPUT_USD))

    print(f"Scène exportée: {OUTPUT_USD}")


if __name__ == "__main__":
    main()
