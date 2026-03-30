from __future__ import annotations

import os

import cv2
import face_recognition
import numpy as np

from .config import AppConfig, SUPPORTED_EXTENSIONS, resolve_project_path

_PERSON_HOG = None


def distance_to_confidence(distance: float) -> float:
    return max(0.0, min(100.0, (1.0 - distance) * 100.0))


def list_available_cameras(max_index: int = 4) -> list[int]:
    cameras = []
    for index in range(max_index + 1):
        capture = cv2.VideoCapture(index)
        if capture.isOpened():
            cameras.append(index)
        capture.release()
    return cameras


def load_known_faces(config: AppConfig, logger=print) -> tuple[list, list]:
    known_face_encodings = []
    known_face_names = []
    files_found = 0

    logger("Chargement des visages connus...")
    faces_dir = resolve_project_path(config.faces_dir)

    for root, _, files in os.walk(faces_dir):
        for filename in files:
            if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
                continue

            files_found += 1
            filepath = os.path.join(root, filename)
            relative_root = os.path.relpath(root, faces_dir)
            person_name = relative_root.split(os.sep)[0] if relative_root not in (".", "") else os.path.splitext(filename)[0]

            try:
                image = face_recognition.load_image_file(filepath)
                encodings = face_recognition.face_encodings(image)
                if not encodings:
                    logger(f"Aucun visage détecté dans : {filename}")
                    continue
                if len(encodings) > 1:
                    logger(f"Plusieurs visages détectés dans {filename} : seul le premier sera utilisé.")

                known_face_encodings.append(encodings[0])
                known_face_names.append(person_name)
                logger(f"Visage chargé pour : {person_name} ({filename})")
            except Exception as exc:
                logger(f"Erreur lors du chargement de {filename} : {exc}")

    if files_found == 0:
        logger(f"Aucune image trouvée dans '{config.faces_dir}'. Ajoutez des photos JPG/PNG pour activer la reconnaissance.")

    logger(f"{len(known_face_encodings)} encodage(s) chargé(s) pour {len(set(known_face_names))} personne(s).")
    return known_face_encodings, known_face_names


def detect_motion(frame, previous_gray, config: AppConfig) -> tuple[float, list[tuple[int, int, int, int]], object]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (config.motion_blur_size, config.motion_blur_size), 0)

    if previous_gray is None:
        return 0.0, [], gray

    frame_delta = cv2.absdiff(previous_gray, gray)
    thresh = cv2.threshold(frame_delta, config.motion_threshold_value, 255, cv2.THRESH_BINARY)[1]
    thresh = cv2.dilate(thresh, None, iterations=2)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    motion_boxes = []
    motion_area = 0.0
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < config.min_contour_area:
            continue
        motion_area += area
        x, y, w, h = cv2.boundingRect(contour)
        motion_boxes.append((x, y, w, h))

    frame_area = float(frame.shape[0] * frame.shape[1])
    motion_ratio = motion_area / frame_area if frame_area else 0.0
    return motion_ratio, motion_boxes, gray


def recognize_faces(frame, known_face_encodings: list, known_face_names: list, config: AppConfig) -> list[dict]:
    small_frame = cv2.resize(frame, (0, 0), fx=1 / config.scale_factor, fy=1 / config.scale_factor)
    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    face_locations = face_recognition.face_locations(rgb_small_frame, model="hog")
    face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
    results = []

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        name = "Inconnu"
        confidence = 0.0
        best_distance = None

        if known_face_encodings:
            face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
            best_match_index = int(np.argmin(face_distances))
            best_distance = float(face_distances[best_match_index])
            confidence = distance_to_confidence(best_distance)
            if best_distance < config.tolerance:
                name = known_face_names[best_match_index]

        results.append(
            {
                "name": name,
                "confidence": confidence,
                "distance": best_distance,
                "top": top * config.scale_factor,
                "right": right * config.scale_factor,
                "bottom": bottom * config.scale_factor,
                "left": left * config.scale_factor,
            }
        )

    return results


def get_person_detector():
    global _PERSON_HOG
    if _PERSON_HOG is None:
        detector = cv2.HOGDescriptor()
        detector.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        _PERSON_HOG = detector
    return _PERSON_HOG


def detect_people(frame, config: AppConfig) -> list[dict]:
    if not getattr(config, "person_detection_enabled", True):
        return []

    height, width = frame.shape[:2]
    if width <= 0 or height <= 0:
        return []

    target_width = min(width, max(320, int(getattr(config, "person_detection_resize_width", 640))))
    resize_ratio = width / target_width if target_width else 1.0

    if target_width != width:
        target_height = max(1, int(height / resize_ratio))
        resized = cv2.resize(frame, (target_width, target_height))
    else:
        resized = frame

    detector = get_person_detector()
    boxes, weights = detector.detectMultiScale(resized, winStride=(8, 8), padding=(8, 8), scale=1.05)

    if len(boxes) == 0:
        return []

    flat_weights = [float(weight) for weight in np.array(weights).reshape(-1)] if len(weights) else [0.0] * len(boxes)
    nms_indices = cv2.dnn.NMSBoxes(boxes.tolist(), flat_weights, score_threshold=0.0, nms_threshold=0.35)
    if len(nms_indices) == 0:
        return []

    detections = []
    for raw_index in np.array(nms_indices).flatten():
        x, y, w, h = boxes[int(raw_index)]
        detections.append(
            {
                "left": int(x * resize_ratio),
                "top": int(y * resize_ratio),
                "right": int((x + w) * resize_ratio),
                "bottom": int((y + h) * resize_ratio),
                "confidence": flat_weights[int(raw_index)],
            }
        )

    return detections


def evaluate_suspicious_activity(
    motion_streak: int,
    motion_ratio: float,
    suspicious_threshold: float,
    unknown_present: bool,
    human_present: bool,
    config: AppConfig,
) -> tuple[bool, str]:
    if unknown_present:
        return True, "Visage inconnu détecté"

    strong_motion = motion_streak >= config.suspicious_motion_frames and motion_ratio >= suspicious_threshold
    if not strong_motion:
        return False, ""

    if human_present:
        return True, "Mouvement humain suspect détecté"

    if not getattr(config, "require_human_for_motion_alert", True):
        return True, "Mouvement suspect détecté"

    return False, ""


def draw_subtle_box(frame, left: int, top: int, right: int, bottom: int, color: tuple[int, int, int], thickness: int = 2) -> None:
    left, top, right, bottom = int(left), int(top), int(right), int(bottom)
    width = max(1, right - left)
    height = max(1, bottom - top)
    corner = max(10, min(22, width // 4, height // 4))

    cv2.line(frame, (left, top), (left + corner, top), color, thickness, cv2.LINE_AA)
    cv2.line(frame, (left, top), (left, top + corner), color, thickness, cv2.LINE_AA)

    cv2.line(frame, (right, top), (right - corner, top), color, thickness, cv2.LINE_AA)
    cv2.line(frame, (right, top), (right, top + corner), color, thickness, cv2.LINE_AA)

    cv2.line(frame, (left, bottom), (left + corner, bottom), color, thickness, cv2.LINE_AA)
    cv2.line(frame, (left, bottom), (left, bottom - corner), color, thickness, cv2.LINE_AA)

    cv2.line(frame, (right, bottom), (right - corner, bottom), color, thickness, cv2.LINE_AA)
    cv2.line(frame, (right, bottom), (right, bottom - corner), color, thickness, cv2.LINE_AA)


def draw_overlay(
    frame,
    face_results: list[dict],
    motion_boxes: list[tuple[int, int, int, int]],
    motion_ratio: float,
    suspicious: bool,
    motion_streak: int,
    known_people_count: int,
    alert_message: str,
    schedule_active: bool,
    night_mode: bool,
    recording: bool,
    config: AppConfig,
) -> None:
    for face in face_results:
        is_unknown = face["name"] == "Inconnu"
        color = (0, 170, 255) if is_unknown else (110, 215, 170)
        draw_subtle_box(frame, face["left"], face["top"], face["right"], face["bottom"], color, thickness=2)

    if config.display_motion_boxes:
        for x, y, w, h in motion_boxes:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
