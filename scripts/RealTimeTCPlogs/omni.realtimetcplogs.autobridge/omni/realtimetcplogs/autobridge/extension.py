from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Optional

import carb
import omni.ext


class RealTimeTcpLogsAutoBridgeExtension(omni.ext.IExt):
    def __init__(self):
        super().__init__()
        self._bridge_module: Optional[ModuleType] = None

    def _load_bridge_module(self) -> ModuleType:
        bridge_path = Path(__file__).resolve().parents[4] / "usd_composer_tcp_logs_bridge.py"
        if not bridge_path.exists():
            raise FileNotFoundError(f"Bridge file not found: {bridge_path}")

        module_name = "realtimetcplogs_runtime_bridge"
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
        enabled = settings.get("/exts/omni.realtimetcplogs.autobridge/enabled")
        if enabled is False:
            carb.log_info("[RealTimeTCPlogs-AutoBridge] Extension loaded but disabled by setting.")
            return

        host = settings.get("/exts/omni.realtimetcplogs.autobridge/host") or "127.0.0.1"
        port = int(settings.get("/exts/omni.realtimetcplogs.autobridge/port") or 5051)

        try:
            self._bridge_module = self._load_bridge_module()
            self._bridge_module.start_tcp_bridge(host=host, port=port)
            carb.log_info(f"[RealTimeTCPlogs-AutoBridge] Started on tcp://{host}:{port}")
        except Exception as exc:
            carb.log_error(f"[RealTimeTCPlogs-AutoBridge] Startup failed: {exc}")

    def on_shutdown(self):
        if self._bridge_module is None:
            return
        try:
            self._bridge_module.stop_tcp_bridge()
            carb.log_info("[RealTimeTCPlogs-AutoBridge] Stopped.")
        except Exception as exc:
            carb.log_error(f"[RealTimeTCPlogs-AutoBridge] Shutdown failed: {exc}")
