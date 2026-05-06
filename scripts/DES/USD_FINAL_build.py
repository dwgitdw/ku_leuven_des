
from pathlib import Path
import json
import sys
from pxr import Usd, UsdGeom, UsdLux, Gf

# ====================
# CONFIGURATION
# ====================
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from marker_layout import resolve_layout_markers

BASE_PLATFORM_USD = PROJECT_ROOT / "3d" / "layout" / "model.usd"
CARRIER_USD = PROJECT_ROOT / "3d" / "layout" / "carrier.usd"
OUTPUT_SCENE_USD = PROJECT_ROOT / "3d" / "DES" / "model_build.usd"
CONFIG_JSON = Path(__file__).resolve().with_name("production_layout.json")


def load_config():
    with CONFIG_JSON.open("r", encoding="utf-8") as f:
        return resolve_layout_markers(json.load(f), PROJECT_ROOT)


CONFIG = load_config()


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


def create_palette_template(stage: Usd.Stage):
    UsdGeom.Scope.Define(stage, "/World/Prototypes")

    template_path = CONFIG["palette_template"]["prototype_path"]
    template_xform = UsdGeom.Xform.Define(stage, template_path)

    # Prototype hidden on purpose, instances stay visible.
    UsdGeom.Imageable(template_xform.GetPrim()).MakeInvisible()

    if not CARRIER_USD.exists():
        raise FileNotFoundError(f"Carrier USD not found: {CARRIER_USD}")

    carrier_asset = CARRIER_USD.as_posix()
    carrier_xform = UsdGeom.Xform.Define(stage, f"{template_path}/Geometry")
    carrier_xform.GetPrim().GetReferences().ClearReferences()
    carrier_xform.GetPrim().GetReferences().AddReference(carrier_asset)

    return template_path


def create_palette_instances(stage: Usd.Stage, template_path: str, num_palettes: int):
    UsdGeom.Scope.Define(stage, "/World/Palettes")

    base_pos = CONFIG["palette_template"]["initial_position"]
    scale = CONFIG["palette_template"]["scale"]
    prefix = CONFIG["palette_template"]["instance_prefix"]

    for i in range(1, num_palettes + 1):
        path = f"{prefix}{i}"
        xform = UsdGeom.Xform.Define(stage, path)
        prim = xform.GetPrim()

        prim.GetReferences().ClearReferences()
        prim.GetReferences().AddInternalReference(template_path)

        # Force instances visible even if prototype is hidden.
        UsdGeom.Imageable(prim).MakeVisible()

        translate = get_or_create_translate_op(UsdGeom.Xformable(prim))
        scale_op = get_or_create_scale_op(UsdGeom.Xformable(prim))

        # Spacing cohérent avec le JSON.
        offset = (i - 1) * CONFIG["palette_template"].get("initial_spacing", 5.0)
        pos = (base_pos[0] - offset, base_pos[1], base_pos[2])

        translate.Set(Gf.Vec3d(*pos))
        scale_op.Set(Gf.Vec3d(*scale))


def create_lights(stage: Usd.Stage):
    remove_if_exists(stage, "/World/Lights")
    UsdGeom.Scope.Define(stage, "/World/Lights")

    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
    dome.CreateIntensityAttr(300.0)

    key = UsdLux.SphereLight.Define(stage, "/World/Lights/Key")
    key.CreateIntensityAttr(40000.0)
    key.CreateRadiusAttr(25.0)
    UsdGeom.Xformable(key).AddTranslateOp().Set(Gf.Vec3d(-250.0, 450.0, 700.0))


def main():
    stage = Usd.Stage.Open(str(BASE_PLATFORM_USD))
    if not stage:
        raise RuntimeError(f"Impossible d'ouvrir le fichier USD de base: {BASE_PLATFORM_USD}")

    ensure_world(stage)

    # Deterministic rebuild.
    remove_if_exists(stage, "/World/Palettes")
    remove_if_exists(stage, "/World/Prototypes")
    remove_if_exists(stage, "/World/Lights")

    template = create_palette_template(stage)
    create_palette_instances(stage, template, CONFIG["simulation_params"]["num_palettes"])
    create_lights(stage)

    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
    OUTPUT_SCENE_USD.parent.mkdir(parents=True, exist_ok=True)
    stage.Export(str(OUTPUT_SCENE_USD))
    print(f"Scene exported: {OUTPUT_SCENE_USD}")


if __name__ == "__main__":
    main()
