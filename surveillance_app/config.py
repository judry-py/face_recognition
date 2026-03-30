from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
ENV_PATH = PROJECT_ROOT / ".env"
SUPPORTED_EXTENSIONS = (".jpg", ".jpeg", ".png")


@dataclass
class AppConfig:
    faces_dir: str = "known_faces"
    alerts_dir: str = "alerts"
    captures_dir: str = "captures"
    reports_dir: str = "reports"
    detections_log: str = "detections_log.csv"
    alerts_log: str = "alerts_log.csv"
    camera_index: int = 0
    tolerance: float = 0.48
    scale_factor: int = 4
    process_every_n_frames: int = 2
    motion_blur_size: int = 21
    motion_threshold_value: int = 25
    min_contour_area: int = 1800
    motion_ratio_threshold: float = 0.015
    suspicious_motion_ratio: float = 0.08
    suspicious_motion_frames: int = 6
    alert_cooldown_seconds: int = 10
    unknown_alert_cooldown_seconds: int = 12
    detection_log_cooldown_seconds: int = 15
    save_unknown_snapshots: bool = True
    unknown_snapshot_cooldown_seconds: int = 20
    display_motion_boxes: bool = True
    schedule_enabled: bool = True
    surveillance_start_time: str = "00:00"
    surveillance_end_time: str = "23:59"
    night_mode_enabled: bool = True
    night_start_time: str = "19:00"
    night_end_time: str = "06:00"
    night_motion_ratio_threshold: float = 0.01
    night_suspicious_motion_ratio: float = 0.05
    alert_record_seconds: int = 15
    video_fps: int = 12
    prompt_save_unknown_face: bool = True
    auto_start_camera: bool = True
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 5000
    admin_password: str = ""
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    max_camera_index: int = 4
    person_detection_enabled: bool = True
    person_detection_every_n_frames: int = 4
    person_detection_resize_width: int = 640
    require_human_for_motion_alert: bool = True
    window_width: int = 1180
    window_height: int = 760


def resolve_project_path(path_like: str | Path) -> Path:
    path = Path(path_like)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_env_file(env_path: str | Path = ENV_PATH) -> None:
    path = resolve_project_path(env_path)
    if not path.exists():
        return

    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except Exception as exc:
        print(f"Impossible de lire {path.name} : {exc}")


def parse_env_value(raw_value: str, current_value: Any) -> Any:
    if isinstance(current_value, bool):
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(current_value, int) and not isinstance(current_value, bool):
        try:
            return int(raw_value)
        except ValueError:
            return current_value
    if isinstance(current_value, float):
        try:
            return float(raw_value)
        except ValueError:
            return current_value
    return raw_value


def apply_environment_overrides(config: AppConfig) -> AppConfig:
    for field_name in AppConfig.__dataclass_fields__:
        env_name = f"SURVEILLANCE_{field_name.upper()}"
        raw_value = os.getenv(env_name)
        if raw_value is None or raw_value == "":
            continue
        current_value = getattr(config, field_name)
        setattr(config, field_name, parse_env_value(raw_value, current_value))
    return config


def load_config(config_path: str | Path = CONFIG_PATH) -> AppConfig:
    config = AppConfig()
    load_env_file()
    config_path = resolve_project_path(config_path)

    if not config_path.exists():
        config_path.write_text(json.dumps(asdict(config), indent=2, ensure_ascii=False), encoding="utf-8")
        return apply_environment_overrides(config)

    try:
        overrides = json.loads(config_path.read_text(encoding="utf-8"))
        for key, value in overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)
    except Exception as exc:
        print(f"Impossible de lire {config_path.name}, valeurs par défaut utilisées : {exc}")

    return apply_environment_overrides(config)


def ensure_directories(config: AppConfig) -> None:
    for directory in (config.faces_dir, config.alerts_dir, config.captures_dir, config.reports_dir):
        resolve_project_path(directory).mkdir(parents=True, exist_ok=True)


def build_dashboard_url(config: AppConfig) -> str:
    return f"http://{config.dashboard_host}:{config.dashboard_port}"
