from __future__ import annotations

from datetime import datetime, time as datetime_time

import cv2
from PIL import Image, ImageTk

from .config import resolve_project_path


def timestamp_label() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def save_snapshot(frame, folder: str, prefix: str) -> str:
    folder_path = resolve_project_path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_{safe_timestamp()}.jpg"
    path = folder_path / filename
    cv2.imwrite(str(path), frame)
    return str(path)


def sanitize_name(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in name.strip())
    return cleaned or "nouvelle_personne"


def parse_time_value(value: str) -> datetime_time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return datetime.strptime("00:00", "%H:%M").time()


def is_time_in_window(start_value: str, end_value: str, current: datetime_time | None = None) -> bool:
    current = current or datetime.now().time()
    start = parse_time_value(start_value)
    end = parse_time_value(end_value)
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def create_preview_image(frame_rgb, target_width: int, target_height: int):
    image = Image.fromarray(frame_rgb)
    resampling = getattr(Image, "Resampling", Image)
    image.thumbnail((target_width, target_height), resampling.LANCZOS)

    background = Image.new("RGB", (target_width, target_height), (2, 6, 23))
    offset_x = max(0, (target_width - image.width) // 2)
    offset_y = max(0, (target_height - image.height) // 2)
    background.paste(image, (offset_x, offset_y))
    return ImageTk.PhotoImage(image=background)
