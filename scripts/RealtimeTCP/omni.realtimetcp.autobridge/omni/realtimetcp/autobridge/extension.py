from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Optional

import carb
import omni.ext


class RealtimeTcpAutoBridgeExtension(omni.ext.IExt):
    def __init__(self):
        super().__init__()
        self._bridge_module: Optional[ModuleType] = None

    def _load_bridge_module(self) -> ModuleType:
        # extension.py -> .../scripts/RealtimeTCP/omni.realtimetcp.autobridge/omni/realtimetcp/autobridge/extension.py
        # target bridge at .../scripts/RealtimeTCP/usd_composer_tcp_realtime_bridge.py
        bridge_path = Path(__file__).resolve().parents[4] / "usd_composer_tcp_realtime_bridge.py"
        if not bridge_path.exists():
            raise FileNotFoundError(f"Bridge file not found: {bridge_path}")

        module_name = "realtimetcp_runtime_bridge"
        existing = sys.modules.get(module_name)
        if existing is not None:
            return existing

        spec = importlib.util.spec_from_file_location(module_name, str(bridge_path))
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load module spec from {bridge_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[module_name] = module
        return module

    def on_startup(self, ext_id):
        settings = carb.settings.get_settings()
        enabled = settings.get("/exts/omni.realtimetcp.autobridge/enabled")
        if enabled is False:
            carb.log_info("[RealtimeTCP-AutoBridge] Extension loaded but disabled by setting.")
            return

        host = settings.get("/exts/omni.realtimetcp.autobridge/host") or "127.0.0.1"
        port = int(settings.get("/exts/omni.realtimetcp.autobridge/port") or 5050)
        places_path = settings.get("/exts/omni.realtimetcp.autobridge/places_path") or ""
        places_arg = str(places_path).strip() or None

        try:
            self._bridge_module = self._load_bridge_module()
            self._bridge_module.start_tcp_bridge(host=host, port=port, places_path=places_arg)
            carb.log_info(f"[RealtimeTCP-AutoBridge] Started on tcp://{host}:{port}")
        except Exception as exc:
            carb.log_error(f"[RealtimeTCP-AutoBridge] Startup failed: {exc}")

    def on_shutdown(self):
        if self._bridge_module is None:
            return
        try:
            self._bridge_module.stop_tcp_bridge()
            carb.log_info("[RealtimeTCP-AutoBridge] Stopped.")
        except Exception as exc:
            carb.log_error(f"[RealtimeTCP-AutoBridge] Shutdown failed: {exc}")

