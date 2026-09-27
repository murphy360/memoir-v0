"""Unknown face grouping and curation operations.

This service owns deterministic unknown-face grouping based on face crop
fingerprints plus bulk curation actions (assign/create/merge/split).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional
from uuid import uuid4

import cv2
import numpy as np
from sqlalchemy.orm import Session

from app.models import AssetFace, EventAsset, Person, UnknownFaceGroup
from app.services.directory import get_or_create_person


def compute_face_fingerprint(
    image_bytes: bytes,
    *,
    bbox_x: float,
    bbox_y: float,
    bbox_w: float,
    bbox_h: float,
) -> Optional[str]:
    """Return a deterministic 64-bit average-hash fingerprint for one face crop."""
    if not image_bytes:
        return None

    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if frame is None:
        return None

    height, width = frame.shape[:2]
    if width <= 0 or height <= 0:
        return None

    x1 = max(0, min(width - 1, int(round(bbox_x * width))))
    y1 = max(0, min(height - 1, int(round(bbox_y * height))))
    x2 = max(x1 + 1, min(width, int(round((bbox_x + bbox_w) * width))))
    y2 = max(y1 + 1, min(height, int(round((bbox_y + bbox_h) * height))))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    # Average hash gives a stable, lightweight grouping key for visually-similar crops.
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
    mean_value = float(resized.mean())
    bits = (resized >= mean_value).flatten()

    value = 0
    for bit in bits:
        value = (value << 1) | int(bool(bit))
    return f"{value:016x}"


def reconcile_unknown_face_groups_for_asset(db: Session, asset_id: int) -> None:
    """Attach unknown faces of one asset to stable groups based on face fingerprints."""
    faces = db.query(AssetFace).filter(AssetFace.asset_id == asset_id).all()
    if not faces:
        return

    affected_group_ids: set[int] = set()

    for face in faces:
        if face.unknown_face_group_id is not None:
            affected_group_ids.add(face.unknown_face_group_id)

        should_group = (
            face.person_id is None
            and not face.compreface_subject
            and bool(face.face_fingerprint)
        )
        if not should_group:
            face.unknown_face_group_id = None
            continue

        existing_group = (
            db.query(UnknownFaceGroup)
            .filter(UnknownFaceGroup.fingerprint == face.face_fingerprint)
            .first()
        )
        if not existing_group:
            existing_group = UnknownFaceGroup(
                fingerprint=face.face_fingerprint or uuid4().hex
            )
            db.add(existing_group)
            db.flush()

        face.unknown_face_group_id = existing_group.id
        affected_group_ids.add(existing_group.id)

    _refresh_group_representatives(db, affected_group_ids)
    _delete_empty_groups(db, affected_group_ids)


def list_unknown_face_groups_for_event(db: Session, event_id: int) -> list[dict]:
    """Return unknown-face groups for one event with members for rapid curation."""
    rows = (
        db.query(AssetFace)
        .join(EventAsset, EventAsset.asset_id == AssetFace.asset_id)
        .filter(
            EventAsset.event_id == event_id,
            AssetFace.person_id.is_(None),
            AssetFace.unknown_face_group_id.isnot(None),
        )
        .order_by(AssetFace.unknown_face_group_id.asc(), AssetFace.id.asc())
        .all()
    )
    if not rows:
        return []

    by_group: dict[int, list[AssetFace]] = defaultdict(list)
    for row in rows:
        if row.unknown_face_group_id is not None:
            by_group[row.unknown_face_group_id].append(row)

    groups = (
        db.query(UnknownFaceGroup)
        .filter(UnknownFaceGroup.id.in_(list(by_group.keys())))
        .all()
    )
    group_map = {group.id: group for group in groups}

    payload: list[dict] = []
    for group_id, faces in by_group.items():
        group = group_map.get(group_id)
        if not group:
            continue
        payload.append(
            {
                "group_id": group.id,
                "fingerprint": group.fingerprint,
                "status": group.status,
                "representative_face_id": group.representative_face_id,
                "face_count": len(faces),
                "members": [
                    {
                        "face_id": face.id,
                        "asset_id": face.asset_id,
                        "asset_download_url": face.asset.download_url
                        if face.asset
                        else "",
                        "bbox_x": face.bbox_x,
                        "bbox_y": face.bbox_y,
                        "bbox_w": face.bbox_w,
                        "bbox_h": face.bbox_h,
                        "confidence": face.confidence,
                    }
                    for face in faces
                ],
            }
        )

    payload.sort(key=lambda item: item["face_count"], reverse=True)
    return payload


def assign_unknown_group_to_person(
    db: Session, group_id: int, person_id: int
) -> UnknownFaceGroup:
    """Assign all unknown faces in a group to an existing person."""
    group = db.get(UnknownFaceGroup, group_id)
    if not group:
        raise ValueError("group_not_found")

    person = db.get(Person, person_id)
    if not person:
        raise ValueError("person_not_found")

    for face in list(group.faces):
        face.person_id = person.id
        face.unknown_face_group_id = None

    group.status = "resolved"
    group.representative_face_id = None
    return group


def create_person_from_unknown_group(
    db: Session, group_id: int, name: str
) -> tuple[UnknownFaceGroup, Person]:
    """Create (or reuse) a person and assign all faces from one unknown group."""
    group = db.get(UnknownFaceGroup, group_id)
    if not group:
        raise ValueError("group_not_found")

    person = get_or_create_person(db, name)
    if not person:
        raise ValueError("invalid_person_name")

    for face in list(group.faces):
        face.person_id = person.id
        face.unknown_face_group_id = None

    group.status = "resolved"
    group.representative_face_id = None
    return group, person


def merge_unknown_face_groups(
    db: Session, source_group_id: int, into_group_id: int
) -> UnknownFaceGroup:
    """Move faces from source group into target group and delete emptied source."""
    source = db.get(UnknownFaceGroup, source_group_id)
    target = db.get(UnknownFaceGroup, into_group_id)
    if not source or not target:
        raise ValueError("group_not_found")
    if source.id == target.id:
        raise ValueError("cannot_merge_same_group")

    for face in list(source.faces):
        face.unknown_face_group_id = target.id

    _refresh_group_representatives(db, {source.id, target.id})
    _delete_empty_groups(db, {source.id})
    return target


def split_unknown_face_group(
    db: Session, source_group_id: int, face_ids: list[int]
) -> UnknownFaceGroup:
    """Move selected face ids from a source group into a newly created group."""
    source = db.get(UnknownFaceGroup, source_group_id)
    if not source:
        raise ValueError("group_not_found")

    selected_faces = (
        db.query(AssetFace)
        .filter(
            AssetFace.id.in_(face_ids),
            AssetFace.unknown_face_group_id == source_group_id,
        )
        .all()
    )
    if not selected_faces:
        raise ValueError("no_faces_selected")

    split_group = UnknownFaceGroup(
        # Split groups are operator decisions; use synthetic fingerprint to keep uniqueness.
        fingerprint=uuid4().hex,
        status="open",
    )
    db.add(split_group)
    db.flush()

    for face in selected_faces:
        face.unknown_face_group_id = split_group.id

    _refresh_group_representatives(db, {source.id, split_group.id})
    _delete_empty_groups(db, {source.id})
    return split_group


def _refresh_group_representatives(db: Session, group_ids: set[int]) -> None:
    if not group_ids:
        return

    groups = (
        db.query(UnknownFaceGroup)
        .filter(UnknownFaceGroup.id.in_(list(group_ids)))
        .all()
    )
    for group in groups:
        candidate_faces = [face for face in group.faces if face.person_id is None]
        if not candidate_faces:
            group.representative_face_id = None
            continue

        candidate_faces.sort(
            key=lambda face: (
                face.confidence if face.confidence is not None else -1.0,
                -face.id,
            ),
            reverse=True,
        )
        group.representative_face_id = candidate_faces[0].id
        group.status = "open"


def _delete_empty_groups(db: Session, group_ids: set[int]) -> None:
    if not group_ids:
        return

    groups = (
        db.query(UnknownFaceGroup)
        .filter(UnknownFaceGroup.id.in_(list(group_ids)))
        .all()
    )
    for group in groups:
        has_faces = any(face.unknown_face_group_id == group.id for face in group.faces)
        if not has_faces:
            db.delete(group)
