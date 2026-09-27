"""Face detection and event face projection helpers.

Detection is CompreFace-only. Legacy OpenCV Haar cascade detection has been
removed from the runtime path.

Face Enrollment Workflow:
  When an unknown face (compreface_subject is None) is manually assigned to a person for the first time,
  the face is automatically enrolled into a new CompreFace subject. This enables future automatic
  recognition of that person's face pattern. Subject names are kept in sync when people are renamed.
"""

from dataclasses import dataclass
import difflib
import json
import logging
import os
from typing import Any, Optional
from uuid import uuid4

import cv2
import numpy as np
import requests
from sqlalchemy.orm import Session

from app.models import Asset, AssetFace, EventAsset, Person, PersonAlias
from app.services.periods import normalize_directory_name
from app.services.unknown_face_groups import (
    compute_face_fingerprint,
    reconcile_unknown_face_groups_for_asset,
)


COMPREFACE_API_KEY = (os.getenv("COMPREFACE_API_KEY") or "").strip()
COMPREFACE_BASE_URL = (
    (os.getenv("COMPREFACE_BASE_URL") or "http://compreface-api:8080")
    .strip()
    .rstrip("/")
)
COMPREFACE_TIMEOUT_SECONDS = float(os.getenv("COMPREFACE_TIMEOUT_SECONDS", "6.0"))
COMPREFACE_DET_PROB_THRESHOLD = os.getenv(
    "COMPREFACE_DET_PROB_THRESHOLD", "0.75"
).strip()
COMPREFACE_PREDICTION_COUNT = int(os.getenv("COMPREFACE_PREDICTION_COUNT", "3"))
COMPREFACE_FACE_PLUGINS = (os.getenv("COMPREFACE_FACE_PLUGINS") or "").strip()
FACE_DETECTION_ON_INGEST = os.getenv(
    "FACE_DETECTION_ON_INGEST", "true"
).strip().lower() not in ("false", "0", "no")
COMPREFACE_AUTO_ASSIGN_ENABLED = os.getenv(
    "COMPREFACE_AUTO_ASSIGN_ENABLED", "true"
).strip().lower() not in ("false", "0", "no")
COMPREFACE_AUTO_ASSIGN_MIN_SIMILARITY = float(
    os.getenv("COMPREFACE_AUTO_ASSIGN_MIN_SIMILARITY", "0.92")
)
# Matches below this similarity are treated as unknown, regardless of what CompreFace returns.
COMPREFACE_MIN_RECOGNITION_SIMILARITY = float(
    os.getenv("COMPREFACE_MIN_RECOGNITION_SIMILARITY", "0.90")
)

logger = logging.getLogger("memoir.faces")


@dataclass
class FaceDetection:
    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float
    confidence: Optional[float] = None
    compreface_subject: Optional[str] = None
    compreface_similarity: Optional[float] = None
    compreface_gender: Optional[str] = None
    compreface_age_low: Optional[int] = None
    compreface_age_high: Optional[int] = None
    compreface_raw: Optional[dict[str, Any]] = None
    face_fingerprint: Optional[str] = None


def detect_faces_from_image(image_bytes: bytes) -> list[FaceDetection]:
    """Detect faces and return normalized bounding boxes using CompreFace only."""
    if not image_bytes:
        return []

    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if frame is None:
        return []

    height, width = frame.shape[:2]
    if width <= 0 or height <= 0:
        return []

    compreface_faces = _detect_faces_with_compreface(
        image_bytes=image_bytes,
        width=width,
        height=height,
    )
    deduped = _dedupe_overlapping_faces(compreface_faces)
    return _dedupe_subject_matches(deduped)


def _extract_face_crop_jpeg(
    image_bytes: bytes, detection: FaceDetection
) -> Optional[bytes]:
    """Extract one detected face crop as JPEG bytes from normalized bbox values."""
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if frame is None:
        return None

    height, width = frame.shape[:2]
    if width <= 0 or height <= 0:
        return None

    x1 = max(0, min(width - 1, int(round(detection.bbox_x * width))))
    y1 = max(0, min(height - 1, int(round(detection.bbox_y * height))))
    x2 = max(
        x1 + 1, min(width, int(round((detection.bbox_x + detection.bbox_w) * width)))
    )
    y2 = max(
        y1 + 1, min(height, int(round((detection.bbox_y + detection.bbox_h) * height)))
    )

    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    ok, encoded = cv2.imencode(".jpg", crop)
    if not ok:
        return None
    return encoded.tobytes()


def _auto_enroll_unknown_detections(
    image_bytes: bytes, detections: list[FaceDetection]
) -> None:
    """Create unnamed CompreFace subjects for unknown detections and enroll their crops.

    This keeps unknown identity grouping inside CompreFace, so future detections can
    resolve to the same unnamed subject without local clustering heuristics.
    """
    if not COMPREFACE_API_KEY or not COMPREFACE_BASE_URL:
        return

    for detection in detections:
        if detection.compreface_subject:
            continue

        crop_bytes = _extract_face_crop_jpeg(image_bytes, detection)
        if not crop_bytes:
            continue

        unknown_subject_name = f"unknown-{uuid4().hex[:12]}"
        try:
            subject_id = create_compreface_subject(unknown_subject_name)
            if not subject_id:
                # Some CompreFace versions return only {"subject": "..."} on create.
                # Continue with name-based enrollment and resolve id later when available.
                subject_id = find_compreface_subject_id_by_name(unknown_subject_name)
            enrolled = enroll_face_in_compreface_subject(
                unknown_subject_name, crop_bytes
            )
            if not enrolled:
                continue
            detection.compreface_subject = unknown_subject_name
        except requests.RequestException:
            # Fail-open: detection should still be stored even when enrollment fails.
            continue


def _detect_faces_with_compreface(
    *, image_bytes: bytes, width: int, height: int
) -> list[FaceDetection]:
    """Detect faces via CompreFace only; return empty list on error/unavailable."""
    if not COMPREFACE_API_KEY or not COMPREFACE_BASE_URL:
        logger.warning("CompreFace is not configured; skipping face detection.")
        return []

    try:
        response = requests.post(
            f"{COMPREFACE_BASE_URL}/api/v1/recognition/recognize",
            headers={"x-api-key": COMPREFACE_API_KEY},
            params={
                # limit = max faces returned per image (not subject matches per face).
                # Set high so large group photos are fully detected.
                "limit": 50,
                # prediction_count = max subject candidates returned per detected face.
                "prediction_count": max(1, COMPREFACE_PREDICTION_COUNT),
                "det_prob_threshold": COMPREFACE_DET_PROB_THRESHOLD,
                **(
                    {"face_plugins": COMPREFACE_FACE_PLUGINS}
                    if COMPREFACE_FACE_PLUGINS
                    else {}
                ),
                "status": "false",
                "detect_faces": "true",
            },
            files={"file": ("image.jpg", image_bytes, "image/jpeg")},
            timeout=COMPREFACE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.warning("CompreFace request failed; face detection skipped: %s", exc)
        return []
    except ValueError as exc:
        logger.warning("CompreFace JSON parse failed; face detection skipped: %s", exc)
        return []

    result_items = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result_items, list):
        return []

    faces: list[FaceDetection] = []
    for item in result_items:
        if not isinstance(item, dict):
            continue
        box = item.get("box")
        if not isinstance(box, dict):
            continue

        x_min = box.get("x_min")
        y_min = box.get("y_min")
        x_max = box.get("x_max")
        y_max = box.get("y_max")
        if None in (x_min, y_min, x_max, y_max):
            continue

        try:
            x = float(x_min)
            y = float(y_min)
            w = float(x_max) - float(x_min)
            h = float(y_max) - float(y_min)
        except (TypeError, ValueError):
            continue

        if w <= 0.0 or h <= 0.0:
            continue

        probability = box.get("probability")
        confidence: Optional[float] = None
        try:
            confidence = float(probability) if probability is not None else None
        except (TypeError, ValueError):
            confidence = None

        top_subject: Optional[str] = None
        top_similarity: Optional[float] = None
        subjects = item.get("subjects")
        if isinstance(subjects, list):
            for candidate in subjects:
                if not isinstance(candidate, dict):
                    continue
                candidate_subject = candidate.get("subject")
                candidate_similarity = candidate.get("similarity")
                if not isinstance(candidate_subject, str):
                    continue
                try:
                    similarity_value = float(candidate_similarity)
                except (TypeError, ValueError):
                    continue
                if top_similarity is None or similarity_value > top_similarity:
                    top_similarity = similarity_value
                    top_subject = candidate_subject

            # Discard low-confidence matches — treat as unknown so a new subject gets enrolled.
            if (
                top_similarity is not None
                and top_similarity < COMPREFACE_MIN_RECOGNITION_SIMILARITY
            ):
                top_subject = None

        compreface_gender: Optional[str] = None
        gender = item.get("gender")
        if isinstance(gender, dict) and isinstance(gender.get("value"), str):
            compreface_gender = str(gender.get("value"))

        compreface_age_low: Optional[int] = None
        compreface_age_high: Optional[int] = None
        age = item.get("age")
        if isinstance(age, dict):
            try:
                compreface_age_low = (
                    int(age.get("low")) if age.get("low") is not None else None
                )
            except (TypeError, ValueError):
                compreface_age_low = None
            try:
                compreface_age_high = (
                    int(age.get("high")) if age.get("high") is not None else None
                )
            except (TypeError, ValueError):
                compreface_age_high = None

        faces.append(
            FaceDetection(
                bbox_x=max(0.0, min(1.0, x / width)),
                bbox_y=max(0.0, min(1.0, y / height)),
                bbox_w=max(0.0, min(1.0, w / width)),
                bbox_h=max(0.0, min(1.0, h / height)),
                confidence=confidence,
                compreface_subject=top_subject,
                compreface_similarity=top_similarity,
                compreface_gender=compreface_gender,
                compreface_age_low=compreface_age_low,
                compreface_age_high=compreface_age_high,
                compreface_raw=item,
                face_fingerprint=compute_face_fingerprint(
                    image_bytes,
                    bbox_x=max(0.0, min(1.0, x / width)),
                    bbox_y=max(0.0, min(1.0, y / height)),
                    bbox_w=max(0.0, min(1.0, w / width)),
                    bbox_h=max(0.0, min(1.0, h / height)),
                ),
            )
        )

    return faces


def _face_iou(left: FaceDetection, right: FaceDetection) -> float:
    left_x2 = left.bbox_x + left.bbox_w
    left_y2 = left.bbox_y + left.bbox_h
    right_x2 = right.bbox_x + right.bbox_w
    right_y2 = right.bbox_y + right.bbox_h

    inter_x1 = max(left.bbox_x, right.bbox_x)
    inter_y1 = max(left.bbox_y, right.bbox_y)
    inter_x2 = min(left_x2, right_x2)
    inter_y2 = min(left_y2, right_y2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    if inter_area <= 0.0:
        return 0.0

    left_area = left.bbox_w * left.bbox_h
    right_area = right.bbox_w * right.bbox_h
    denom = left_area + right_area - inter_area
    if denom <= 0.0:
        return 0.0
    return inter_area / denom


def _dedupe_overlapping_faces(faces: list[FaceDetection]) -> list[FaceDetection]:
    if len(faces) <= 1:
        return faces

    kept: list[FaceDetection] = []
    for face in sorted(faces, key=lambda item: item.bbox_w * item.bbox_h, reverse=True):
        if any(_face_iou(face, existing) > 0.42 for existing in kept):
            continue
        kept.append(face)
    return kept


def _dedupe_subject_matches(faces: list[FaceDetection]) -> list[FaceDetection]:
    """For each recognized subject, keep only the highest-similarity match.

    If the same subject appears multiple times (e.g. a group photo where one
    person's face is detected in two positions), only the best match keeps the
    subject label. All lower-confidence duplicates are cleared to unknown so
    they surface in the unrecognized-faces inbox rather than creating false
    assignments.
    """
    # Find the highest similarity seen for each subject
    best_similarity: dict[str, float] = {}
    for face in faces:
        if face.compreface_subject and face.compreface_similarity is not None:
            current_best = best_similarity.get(face.compreface_subject)
            if current_best is None or face.compreface_similarity > current_best:
                best_similarity[face.compreface_subject] = face.compreface_similarity

    # Track which subjects have already claimed their best slot
    claimed: set[str] = set()
    result: list[FaceDetection] = []
    for face in faces:
        subject = face.compreface_subject
        if not subject:
            # Unknown face — keep as-is
            result.append(face)
        elif (
            face.compreface_similarity is not None
            and face.compreface_similarity == best_similarity.get(subject)
            and subject not in claimed
        ):
            # Best match for this subject — keep it and claim the slot
            claimed.add(subject)
            result.append(face)
        else:
            # Non-best or duplicate match — downgrade to unknown
            result.append(
                FaceDetection(
                    bbox_x=face.bbox_x,
                    bbox_y=face.bbox_y,
                    bbox_w=face.bbox_w,
                    bbox_h=face.bbox_h,
                    confidence=face.confidence,
                    compreface_subject=None,
                    compreface_similarity=None,
                    compreface_gender=face.compreface_gender,
                    compreface_age_low=face.compreface_age_low,
                    compreface_age_high=face.compreface_age_high,
                    compreface_raw=face.compreface_raw,
                    face_fingerprint=face.face_fingerprint,
                )
            )
    return result


def _resolve_person_id_for_subject(
    db: Session, subject: Optional[str]
) -> Optional[int]:
    """Resolve a CompreFace subject string to exactly one existing Person id.

    Matching checks both canonical person names and person aliases.
    Returns None when the subject is blank or maps ambiguously to multiple people.
    """
    normalized = normalize_directory_name(subject)
    if not normalized:
        return None

    key = normalized.casefold()
    candidate_ids: set[int] = set()

    for person in db.query(Person).all():
        linked_subject = (person.compreface_subject_id or "").strip()
        if linked_subject and linked_subject.casefold() == key:
            candidate_ids.add(person.id)

    for person in db.query(Person).all():
        if person.name.casefold() == key:
            candidate_ids.add(person.id)

    alias_rows = db.query(PersonAlias).filter(PersonAlias.alias.ilike(normalized)).all()
    for alias in alias_rows:
        candidate_ids.add(alias.person_id)

    if len(candidate_ids) == 1:
        return next(iter(candidate_ids))
    return None


def replace_asset_faces(
    db: Session, asset: Asset, detections: list[FaceDetection]
) -> None:
    """Replace stored face boxes for a photo asset from latest detection output."""
    for face in list(asset.faces):
        db.delete(face)

    for detection in detections:
        auto_person_id: Optional[int] = None
        if (
            COMPREFACE_AUTO_ASSIGN_ENABLED
            and detection.compreface_subject
            and detection.compreface_similarity is not None
            and detection.compreface_similarity >= COMPREFACE_AUTO_ASSIGN_MIN_SIMILARITY
        ):
            auto_person_id = _resolve_person_id_for_subject(
                db, detection.compreface_subject
            )

        db.add(
            AssetFace(
                asset_id=asset.id,
                bbox_x=detection.bbox_x,
                bbox_y=detection.bbox_y,
                bbox_w=detection.bbox_w,
                bbox_h=detection.bbox_h,
                confidence=detection.confidence,
                compreface_subject=detection.compreface_subject,
                compreface_similarity=detection.compreface_similarity,
                compreface_gender=detection.compreface_gender,
                compreface_age_low=detection.compreface_age_low,
                compreface_age_high=detection.compreface_age_high,
                compreface_raw_json=(
                    json.dumps(detection.compreface_raw)
                    if detection.compreface_raw
                    else None
                ),
                face_fingerprint=detection.face_fingerprint,
                person_id=auto_person_id,
            )
        )


def sync_asset_faces_for_photo(db: Session, asset: Asset, image_bytes: bytes) -> None:
    """Run detection for a photo asset and replace face boxes in one call."""
    detections = detect_faces_from_image(image_bytes)
    _auto_enroll_unknown_detections(image_bytes, detections)
    replace_asset_faces(db, asset, detections)
    reconcile_unknown_face_groups_for_asset(db, asset.id)


def list_faces_for_event(db: Session, event_id: int) -> list[AssetFace]:
    """Return all detected faces from photo assets linked to one event."""
    return (
        db.query(AssetFace)
        .join(Asset, Asset.id == AssetFace.asset_id)
        .join(EventAsset, EventAsset.asset_id == Asset.id)
        .filter(EventAsset.event_id == event_id)
        .order_by(AssetFace.created_at.desc(), AssetFace.id.desc())
        .all()
    )


def create_compreface_subject(name: str) -> Optional[str]:
    """Create a new subject (person) in CompreFace and return the subject UUID.

    Returns None on error or if CompreFace is not configured.
    Raises requests.RequestException on API errors.
    """
    if not COMPREFACE_API_KEY or not COMPREFACE_BASE_URL:
        logger.warning("CompreFace not configured; cannot create subject.")
        return None

    try:
        response = requests.post(
            f"{COMPREFACE_BASE_URL}/api/v1/recognition/subjects",
            headers={"x-api-key": COMPREFACE_API_KEY},
            json={"subject": name},
            timeout=COMPREFACE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        subject_id = payload.get("subject_id")
        if isinstance(subject_id, str) and subject_id:
            logger.info("Created CompreFace subject %s for %s", subject_id, name)
            return subject_id
        subject_name = payload.get("subject") if isinstance(payload, dict) else None
        if isinstance(subject_name, str) and subject_name.strip():
            logger.info(
                "Created CompreFace subject %s (subject_id not returned by API)",
                subject_name,
            )
            return None
        logger.warning(
            "CompreFace subject creation returned unexpected payload: %s", payload
        )
        return None
    except requests.RequestException as exc:
        logger.error("CompreFace subject creation failed: %s", exc)
        raise


def enroll_face_in_compreface_subject(
    subject_name: str, face_image_bytes: bytes
) -> bool:
    """Add a face sample to a CompreFace subject for enrollment.

    Returns True on success, False on error or if CompreFace is not configured.
    Raises requests.RequestException on API errors.
    """
    if not COMPREFACE_API_KEY or not COMPREFACE_BASE_URL:
        logger.warning("CompreFace not configured; cannot enroll face.")
        return False

    try:
        response = requests.post(
            f"{COMPREFACE_BASE_URL}/api/v1/recognition/faces",
            headers={"x-api-key": COMPREFACE_API_KEY},
            params={"subject": subject_name},
            files={"file": ("face.jpg", face_image_bytes, "image/jpeg")},
            timeout=COMPREFACE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        logger.info("Enrolled face into CompreFace subject %s", subject_name)
        return True
    except requests.RequestException as exc:
        logger.error("CompreFace face enrollment failed: %s", exc)
        raise


def rename_compreface_subject(subject_name: str, new_name: str) -> bool:
    """Rename a CompreFace subject by name.

    CompreFace API accepts subject names directly in the PUT endpoint.
    Returns True on success, False on error or if CompreFace is not configured.
    Raises requests.RequestException on API errors.
    """
    if not COMPREFACE_API_KEY or not COMPREFACE_BASE_URL:
        logger.warning("CompreFace not configured; cannot rename subject.")
        return False

    try:
        from urllib.parse import quote

        encoded_name = quote(subject_name)
        response = requests.put(
            f"{COMPREFACE_BASE_URL}/api/v1/recognition/subjects/{encoded_name}",
            headers={"x-api-key": COMPREFACE_API_KEY},
            json={"subject": new_name},
            timeout=COMPREFACE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        logger.info("Renamed CompreFace subject %s to %s", subject_name, new_name)
        return True
    except requests.RequestException as exc:
        logger.error("CompreFace subject rename failed: %s", exc)
        raise


def delete_compreface_subject(subject_name: str) -> bool:
    """Delete a CompreFace subject by subject name/id.

    Returns True on success, False when CompreFace is not configured.
    Raises requests.RequestException on API errors.
    """
    if not COMPREFACE_API_KEY or not COMPREFACE_BASE_URL:
        logger.warning("CompreFace not configured; cannot delete subject.")
        return False

    try:
        from urllib.parse import quote

        encoded_name = quote(subject_name)
        response = requests.delete(
            f"{COMPREFACE_BASE_URL}/api/v1/recognition/subjects/{encoded_name}",
            headers={"x-api-key": COMPREFACE_API_KEY},
            timeout=COMPREFACE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        logger.info("Deleted CompreFace subject %s", subject_name)
        return True
    except requests.RequestException as exc:
        logger.error("CompreFace subject delete failed: %s", exc)
        raise


def find_compreface_subject_id_by_name(subject_name: str) -> Optional[str]:
    """Resolve a CompreFace subject id by display name.

    CompreFace recognition responses return subject names, but rename operations
    require the subject id. This helper bridges that gap by scanning subjects.
    """
    normalized = (subject_name or "").strip()
    if not normalized:
        return None
    if not COMPREFACE_API_KEY or not COMPREFACE_BASE_URL:
        return None

    candidates = list_compreface_subjects()
    wanted = normalized.casefold()
    for candidate_name, candidate_id in candidates:
        if candidate_name.casefold() == wanted:
            return candidate_id or candidate_name
    return None


def list_compreface_subjects() -> list[tuple[str, Optional[str]]]:
    """Return CompreFace subjects as (subject_name, subject_id) tuples."""
    if not COMPREFACE_API_KEY or not COMPREFACE_BASE_URL:
        return []

    try:
        response = requests.get(
            f"{COMPREFACE_BASE_URL}/api/v1/recognition/subjects",
            headers={"x-api-key": COMPREFACE_API_KEY},
            timeout=COMPREFACE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return []

    raw_subjects = payload.get("subjects") if isinstance(payload, dict) else None
    if not isinstance(raw_subjects, list):
        return []

    subjects: list[tuple[str, Optional[str]]] = []
    for item in raw_subjects:
        if isinstance(item, str):
            normalized_name = item.strip()
            if normalized_name:
                subjects.append((normalized_name, None))
            continue
        if not isinstance(item, dict):
            continue
        name_value = item.get("subject")
        id_value = item.get("subject_id")
        if not isinstance(name_value, str):
            continue
        normalized_name = name_value.strip()
        if not normalized_name:
            continue
        normalized_id = (
            id_value.strip() if isinstance(id_value, str) and id_value.strip() else None
        )
        subjects.append((normalized_name, normalized_id))
    return subjects


def resolve_compreface_subject_name(
    subject_query: str, fallback_name: str
) -> Optional[str]:
    """Resolve best matching existing CompreFace subject name from free text.

    Matching order: exact -> case-insensitive contains -> fuzzy close match.
    """
    subjects = list_compreface_subjects()
    if not subjects:
        return None

    requested = (subject_query or "").strip() or (fallback_name or "").strip()
    if not requested:
        return None

    wanted = requested.casefold()
    subject_names = [name for name, _ in subjects]

    for name in subject_names:
        if name.casefold() == wanted:
            return name

    for name in subject_names:
        lowered = name.casefold()
        if wanted in lowered or lowered in wanted:
            return name

    close = difflib.get_close_matches(requested, subject_names, n=1, cutoff=0.70)
    if close:
        return close[0]
    return None


def link_person_to_existing_compreface_subject(
    db: Session,
    person_id: int,
    subject_query: Optional[str],
) -> Person:
    """Link one person to an existing CompreFace subject by exact/fuzzy match."""
    person = db.get(Person, person_id)
    if person is None:
        raise ValueError("person_not_found")

    subject_name = resolve_compreface_subject_name(subject_query or "", person.name)
    if not subject_name:
        raise ValueError("subject_not_found")

    subject_key = subject_name.casefold()
    existing_owner = (
        db.query(Person)
        .filter(Person.id != person.id, Person.compreface_subject_id.isnot(None))
        .all()
    )
    for owner in existing_owner:
        if (owner.compreface_subject_id or "").strip().casefold() == subject_key:
            raise ValueError("subject_already_linked")

    person.compreface_subject_id = subject_name

    linked_faces = (
        db.query(AssetFace).filter(AssetFace.compreface_subject == subject_name).all()
    )
    for face in linked_faces:
        face.person_id = person.id
        face.unknown_face_group_id = None

    return person


def assign_face_to_person(
    db: Session, face_id: int, person_id: Optional[int]
) -> AssetFace:
    """Assign a detected face to a person, or clear assignment with null.

    When assigning an unknown face (compreface_subject is None) to a person for the first time,
    automatically creates and enrolls the face in a CompreFace subject.
    """
    face = db.get(AssetFace, face_id)
    if face is None:
        raise ValueError("face_not_found")

    if person_id is None:
        face.person_id = None
        if face.asset_id:
            reconcile_unknown_face_groups_for_asset(db, face.asset_id)
        return face

    person = db.get(Person, person_id)
    if person is None:
        raise ValueError("person_not_found")

    # If this face came from an unnamed CompreFace subject, promote it to the
    # selected person's canonical name so future detections auto-match correctly.
    subject_name = (face.compreface_subject or "").strip()
    is_unknown_subject = subject_name.casefold().startswith("unknown-")
    if is_unknown_subject:
        try:
            if rename_compreface_subject(subject_name, person.name):
                person.compreface_subject_id = person.name
                related_faces = (
                    db.query(AssetFace)
                    .filter(AssetFace.compreface_subject == subject_name)
                    .all()
                )
                for related_face in related_faces:
                    related_face.compreface_subject = person.name
                    related_face.person_id = person.id
        except requests.RequestException as exc:
            logger.warning(
                "Failed to rename unknown CompreFace subject %s to %s: %s",
                subject_name,
                person.name,
                exc,
            )

    # Ensure first-time person assignments are enrolled in CompreFace.
    # This allows rapid "create person + assign" from the face row to seed
    # recognition even when a low-confidence detected subject label is present.
    if face.asset and face.asset.storage_filename and not person.compreface_subject_id:
        try:
            from app.main import DOCUMENT_STORAGE_DIR

            file_path = DOCUMENT_STORAGE_DIR / face.asset.storage_filename
            if file_path.exists():
                image_bytes = file_path.read_bytes()
                # Crop just the face region so CompreFace doesn't reject multi-face images
                face_detection = FaceDetection(
                    bbox_x=face.bbox_x,
                    bbox_y=face.bbox_y,
                    bbox_w=face.bbox_w,
                    bbox_h=face.bbox_h,
                    confidence=face.confidence or 0.0,
                )
                crop_bytes = _extract_face_crop_jpeg(image_bytes, face_detection)
                if crop_bytes:
                    # Reuse existing subject if present, otherwise create one.
                    subject_id = find_compreface_subject_id_by_name(person.name)
                    if not subject_id:
                        try:
                            subject_id = create_compreface_subject(person.name)
                        except requests.RequestException:
                            subject_id = find_compreface_subject_id_by_name(person.name)

                    # Enroll the cropped face by subject name even if subject_id is unavailable.
                    if enroll_face_in_compreface_subject(person.name, crop_bytes):
                        person.compreface_subject_id = subject_id or person.name
                        face.compreface_subject = person.name
                        logger.info(
                            "Auto-enrolled face for person %s (id=%s) to CompreFace subject %s",
                            person.name,
                            person.id,
                            person.compreface_subject_id,
                        )
        except Exception as exc:
            logger.warning(
                "Face auto-enrollment to CompreFace failed; continuing without enrollment: %s",
                exc,
            )

    face.person_id = person.id
    face.unknown_face_group_id = None
    if face.asset_id:
        reconcile_unknown_face_groups_for_asset(db, face.asset_id)
    return face


def approve_face_for_person(db: Session, face_id: int, person_id: int) -> AssetFace:
    """Approve one face-to-person match and push training data to CompreFace when possible."""
    face = assign_face_to_person(db, face_id, person_id)
    person = db.get(Person, person_id)
    if person is None:
        raise ValueError("person_not_found")

    subject_name = (person.compreface_subject_id or person.name or "").strip()
    if not subject_name or not face.asset or not face.asset.storage_filename:
        return face

    try:
        from app.main import DOCUMENT_STORAGE_DIR

        file_path = DOCUMENT_STORAGE_DIR / face.asset.storage_filename
        if not file_path.exists():
            return face

        image_bytes = file_path.read_bytes()
        crop_bytes = _extract_face_crop_jpeg(
            image_bytes,
            FaceDetection(
                bbox_x=face.bbox_x,
                bbox_y=face.bbox_y,
                bbox_w=face.bbox_w,
                bbox_h=face.bbox_h,
                confidence=face.confidence,
            ),
        )
        if crop_bytes:
            enroll_face_in_compreface_subject(subject_name, crop_bytes)
            face.compreface_subject = person.name
    except Exception as exc:
        logger.warning(
            "Face approval enrollment failed for person %s: %s", person_id, exc
        )

    return face


def rename_face_subject(db: Session, face_id: int, new_subject_name: str) -> AssetFace:
    """Rename a detected face's CompreFace subject and sync local face subject labels.

    The rename is applied in CompreFace first, then all local `asset_faces` rows that
    reference the old subject label are updated to keep future UI and assignment flows
    aligned with the external recognizer state.
    """
    face = db.get(AssetFace, face_id)
    if face is None:
        raise ValueError("face_not_found")

    current_subject = (face.compreface_subject or "").strip()
    if not current_subject:
        raise ValueError("face_has_no_subject")

    normalized_new_name = (new_subject_name or "").strip()
    if not normalized_new_name:
        raise ValueError("subject_name_required")

    if len(normalized_new_name) > 120:
        raise ValueError("subject_name_too_long")

    if normalized_new_name.casefold() == current_subject.casefold():
        return face

    try:
        rename_compreface_subject(current_subject, normalized_new_name)
    except requests.RequestException as exc:
        logger.warning(
            "Failed to rename CompreFace subject %s to %s: %s",
            current_subject,
            normalized_new_name,
            exc,
        )
        raise ValueError("compreface_rename_failed") from exc

    related_faces = (
        db.query(AssetFace)
        .filter(AssetFace.compreface_subject == current_subject)
        .all()
    )
    for related_face in related_faces:
        related_face.compreface_subject = normalized_new_name

    return face
