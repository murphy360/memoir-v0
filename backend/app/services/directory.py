"""Directory service logic for people/places normalization and linking.

This module owns directory CRUD helpers plus people merge behavior that keeps
memory links, face links, aliases, and CompreFace subject linkage consistent.
"""

import json
import logging
import os
from typing import Optional
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models import (
    Asset,
    AssetFace,
    EventAsset,
    LifeEvent,
    MemoryEntry,
    MemoryPerson,
    MemoryPlace,
    Person,
    PersonAlias,
    Place,
)
from app.schemas import DirectoryEntryResponse
from app.services.periods import normalize_directory_name


logger = logging.getLogger("memoir.directory")
_COMPREFACE_BASE_URL = (os.getenv("COMPREFACE_BASE_URL") or "").strip().rstrip("/")


def _normalized_compreface_subject(subject: Optional[str]) -> Optional[str]:
    normalized = (subject or "").strip()
    return normalized or None


def _build_compreface_subject_url(subject: Optional[str]) -> Optional[str]:
    normalized = _normalized_compreface_subject(subject)
    if not normalized or not _COMPREFACE_BASE_URL:
        return None
    return f"{_COMPREFACE_BASE_URL}/api/v1/recognition/subjects/{quote(normalized)}"


def _merge_person_aliases(db: Session, source: Person, target: Person) -> None:
    existing_aliases = {alias.alias.casefold() for alias in target.aliases}

    for alias in source.aliases:
        normalized_alias = normalize_directory_name(alias.alias)
        if not normalized_alias:
            continue
        alias_key = normalized_alias.casefold()
        if alias_key == target.name.casefold() or alias_key in existing_aliases:
            continue
        db.add(PersonAlias(person_id=target.id, alias=normalized_alias))
        existing_aliases.add(alias_key)

    source_name_key = source.name.casefold()
    if (
        source_name_key != target.name.casefold()
        and source_name_key not in existing_aliases
    ):
        db.add(PersonAlias(person_id=target.id, alias=source.name))


def merge_people_records(db: Session, source: Person, target: Person) -> None:
    """Merge one source person into a target person with CompreFace linkage integrity.

    Rules:
    - A person may exist without a CompreFace link.
    - At most one person may hold a given non-null CompreFace subject link.
    - When both people have different links, the target link is preserved.
    """
    _merge_person_aliases(db, source, target)

    for memory in db.query(MemoryEntry).all():
        if memory.recorder_person_id == source.id:
            assign_recorder_person(db, memory, target.name)

        already_linked = any(
            link.person_id == target.id for link in memory.people_links
        )
        has_source_link = any(
            link.person_id == source.id for link in memory.people_links
        )

        if has_source_link:
            for link in list(memory.people_links):
                if link.person_id == source.id:
                    memory.people_links.remove(link)
                    db.delete(link)
            if not already_linked:
                memory.people_links.append(
                    MemoryPerson(person_id=target.id, role="mentioned")
                )
            memory.people_json = json.dumps(memory.referenced_people)

    source_faces = db.query(AssetFace).filter(AssetFace.person_id == source.id).all()
    for face in source_faces:
        face.person_id = target.id

    source_subject = _normalized_compreface_subject(source.compreface_subject_id)
    target_subject = _normalized_compreface_subject(target.compreface_subject_id)

    if source_subject and not target_subject:
        target.compreface_subject_id = source_subject
        target_subject = source_subject

    if (
        source_subject
        and target_subject
        and source_subject.casefold() != target_subject.casefold()
    ):
        subject_faces = (
            db.query(AssetFace)
            .filter(AssetFace.compreface_subject == source_subject)
            .all()
        )
        for face in subject_faces:
            face.compreface_subject = target_subject

        from app.services.faces import delete_compreface_subject

        try:
            delete_compreface_subject(source_subject)
        except Exception as exc:  # pragma: no cover - fail-open sync to upstream
            logger.warning(
                "Failed to remove merged source CompreFace subject %s: %s",
                source_subject,
                exc,
            )

    source.compreface_subject_id = None


def detach_person_compreface_link(db: Session, person: Person) -> None:
    """Remove one person's CompreFace link and clear matching local face subject labels.

    This is used when a person record is deleted/split and no 1:1 link should
    remain for that removed person identity.
    """
    subject = _normalized_compreface_subject(person.compreface_subject_id)
    if not subject:
        return

    subject_faces = (
        db.query(AssetFace).filter(AssetFace.compreface_subject == subject).all()
    )
    for face in subject_faces:
        face.compreface_subject = None

    from app.services.faces import delete_compreface_subject

    try:
        delete_compreface_subject(subject)
    except Exception as exc:  # pragma: no cover - fail-open sync to upstream
        logger.warning(
            "Failed to delete CompreFace subject %s during person removal: %s",
            subject,
            exc,
        )

    person.compreface_subject_id = None


def get_or_create_person(db: Session, raw_name: Optional[str]) -> Optional[Person]:
    name = normalize_directory_name(raw_name)
    if not name:
        return None

    for person in db.query(Person).all():
        if person.name.casefold() == name.casefold():
            if person.name != name:
                person.name = name
            return person

    alias_row = db.query(PersonAlias).filter(PersonAlias.alias.ilike(name)).first()
    if alias_row:
        return alias_row.person

    person = Person(name=name)
    db.add(person)
    db.flush()
    return person


def expand_person_names(db: Session, raw_name: Optional[str]) -> list[Person]:
    name = normalize_directory_name(raw_name)
    if not name:
        return []

    for person in db.query(Person).all():
        if person.name.casefold() == name.casefold():
            return [person]

    alias_rows = db.query(PersonAlias).filter(PersonAlias.alias.ilike(name)).all()
    if alias_rows:
        seen: set[int] = set()
        resolved: list[Person] = []
        for row in alias_rows:
            if row.person_id not in seen:
                seen.add(row.person_id)
                resolved.append(row.person)
        return resolved

    person = Person(name=name)
    db.add(person)
    db.flush()
    return [person]


def get_or_create_place(db: Session, raw_name: Optional[str]) -> Optional[Place]:
    name = normalize_directory_name(raw_name)
    if not name:
        return None

    for place in db.query(Place).all():
        if place.name.casefold() == name.casefold():
            if place.name != name:
                place.name = name
            return place

    place = Place(name=name)
    db.add(place)
    db.flush()
    return place


def sync_memory_people(db: Session, memory: MemoryEntry, names: list[str]) -> None:
    ordered_people: list[Person] = []
    seen_keys: set[str] = set()

    for raw_name in names:
        for person in expand_person_names(db, raw_name):
            key = person.name.casefold()
            if key in seen_keys:
                continue
            seen_keys.add(key)
            ordered_people.append(person)

    existing_links = {link.person_id: link for link in memory.people_links}
    desired_ids = {person.id for person in ordered_people}

    for link in list(memory.people_links):
        if link.person_id not in desired_ids:
            memory.people_links.remove(link)
            db.delete(link)

    for person in ordered_people:
        if person.id not in existing_links:
            memory.people_links.append(
                MemoryPerson(person_id=person.id, role="mentioned")
            )

    memory.people_json = json.dumps([person.name for person in ordered_people])


def sync_memory_places(db: Session, memory: MemoryEntry, names: list[str]) -> None:
    ordered_places: list[Place] = []
    seen_keys: set[str] = set()

    for raw_name in names:
        place = get_or_create_place(db, raw_name)
        if not place:
            continue
        key = place.name.casefold()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        ordered_places.append(place)

    existing_links = {link.place_id: link for link in memory.place_links}
    desired_ids = {place.id for place in ordered_places}

    for link in list(memory.place_links):
        if link.place_id not in desired_ids:
            memory.place_links.remove(link)
            db.delete(link)

    for place in ordered_places:
        if place.id not in existing_links:
            memory.place_links.append(MemoryPlace(place_id=place.id))

    memory.locations_json = json.dumps([place.name for place in ordered_places])


def assign_recorder_person(
    db: Session, memory: MemoryEntry, raw_name: Optional[str]
) -> None:
    person = get_or_create_person(db, raw_name)
    if not person:
        memory.recorder_person = None
        memory.recorder_person_id = None
        memory.recorder_name = None
        return

    memory.recorder_person = person
    memory.recorder_person_id = person.id
    memory.recorder_name = person.name


def build_directory_response(
    name: str,
    item_id: int,
    memory_count: int,
    photo_count: int = 0,
    aliases: Optional[list[str]] = None,
    avatar_download_url: Optional[str] = None,
    compreface_subject_id: Optional[str] = None,
    compreface_subject_url: Optional[str] = None,
) -> DirectoryEntryResponse:
    return DirectoryEntryResponse(
        id=item_id,
        name=name,
        memory_count=memory_count,
        photo_count=photo_count,
        aliases=aliases or [],
        avatar_download_url=avatar_download_url,
        compreface_subject_id=_normalized_compreface_subject(compreface_subject_id),
        compreface_subject_url=(
            compreface_subject_url
            or _build_compreface_subject_url(compreface_subject_id)
        ),
    )


def list_people_directory(db: Session) -> list[DirectoryEntryResponse]:
    memories = db.query(MemoryEntry).all()
    counts: dict[int, set[int]] = {}
    photo_counts: dict[int, set[int]] = {}

    for memory in memories:
        if memory.recorder_person_id is not None:
            counts.setdefault(memory.recorder_person_id, set()).add(memory.id)
        for link in memory.people_links:
            counts.setdefault(link.person_id, set()).add(memory.id)

    # Track distinct photo assets tagged to each person.
    tagged_photo_rows = (
        db.query(AssetFace.person_id, AssetFace.asset_id)
        .join(Asset, Asset.id == AssetFace.asset_id)
        .filter(AssetFace.person_id.isnot(None), Asset.kind == "photo")
        .all()
    )
    for person_id, asset_id in tagged_photo_rows:
        if person_id is None:
            continue
        photo_counts.setdefault(person_id, set()).add(asset_id)

    # Pick one avatar photo per person using their most recent assigned face.
    avatars_by_person_id: dict[int, str] = {}
    face_rows = (
        db.query(AssetFace)
        .join(Asset, Asset.id == AssetFace.asset_id)
        .filter(AssetFace.person_id.isnot(None), Asset.kind == "photo")
        .order_by(AssetFace.created_at.desc(), AssetFace.id.desc())
        .all()
    )
    for face in face_rows:
        person_id = face.person_id
        if person_id is None or person_id in avatars_by_person_id:
            continue
        if face.asset:
            avatars_by_person_id[person_id] = face.asset.download_url

    people = db.query(Person).order_by(Person.name.asc()).all()
    return [
        build_directory_response(
            person.name,
            person.id,
            len(counts.get(person.id, set())),
            len(photo_counts.get(person.id, set())),
            [alias.alias for alias in person.aliases],
            avatars_by_person_id.get(person.id),
            person.compreface_subject_id,
        )
        for person in people
    ]


def list_places_directory(db: Session) -> list[DirectoryEntryResponse]:
    counts: dict[int, set[int]] = {}

    for memory in db.query(MemoryEntry).all():
        for link in memory.place_links:
            counts.setdefault(link.place_id, set()).add(memory.id)

    places = db.query(Place).order_by(Place.name.asc()).all()
    return [
        build_directory_response(place.name, place.id, len(counts.get(place.id, set())))
        for place in places
    ]


def update_memory_json_from_links(memory: MemoryEntry) -> None:
    memory.people_json = json.dumps(memory.referenced_people)
    memory.locations_json = json.dumps(memory.referenced_locations)


def person_memory_ids(db: Session, person_id: int) -> set[int]:
    """Collect memory ids where the person is recorder or referenced."""
    memory_ids: set[int] = set()
    for memory in db.query(MemoryEntry).all():
        if memory.recorder_person_id == person_id:
            memory_ids.add(memory.id)
            continue
        if any(link.person_id == person_id for link in memory.people_links):
            memory_ids.add(memory.id)
    return memory_ids


def list_person_memories(db: Session, person_id: int) -> list[MemoryEntry]:
    """Return person-linked memories in timeline order for the details page."""
    ids = person_memory_ids(db, person_id)
    if not ids:
        return []
    return (
        db.query(MemoryEntry)
        .filter(MemoryEntry.id.in_(ids))
        .order_by(
            MemoryEntry.estimated_date_sort.is_(None),
            MemoryEntry.estimated_date_sort.asc(),
            MemoryEntry.estimated_end_date_sort.asc().nulls_last(),
            MemoryEntry.created_at.desc(),
        )
        .all()
    )


def list_person_events(db: Session, person_id: int) -> list[LifeEvent]:
    """Return events associated through legacy memory links or face-tagged assets."""
    memory_ids = person_memory_ids(db, person_id)
    event_ids: set[int] = set()

    if memory_ids:
        legacy_events = (
            db.query(LifeEvent.id)
            .filter(
                LifeEvent.legacy_memory_id.isnot(None),
                LifeEvent.legacy_memory_id.in_(memory_ids),
            )
            .all()
        )
        event_ids.update(event_id for (event_id,) in legacy_events)

    face_event_ids = (
        db.query(EventAsset.event_id)
        .join(AssetFace, AssetFace.asset_id == EventAsset.asset_id)
        .filter(AssetFace.person_id == person_id)
        .all()
    )
    event_ids.update(event_id for (event_id,) in face_event_ids)

    if not event_ids:
        return []

    return (
        db.query(LifeEvent)
        .filter(LifeEvent.id.in_(event_ids))
        .order_by(
            LifeEvent.event_date_sort.is_(None),
            LifeEvent.event_date_sort.asc(),
            LifeEvent.created_at.asc(),
        )
        .all()
    )


def list_person_assets(db: Session, person_id: int) -> list[Asset]:
    """Return distinct photo assets where this person is face-tagged."""
    direct_asset_ids = {
        asset_id
        for (asset_id,) in db.query(AssetFace.asset_id)
        .filter(AssetFace.person_id == person_id)
        .all()
    }

    event_asset_ids = {
        asset_id
        for (asset_id,) in (
            db.query(EventAsset.asset_id)
            .join(AssetFace, AssetFace.asset_id == EventAsset.asset_id)
            .filter(AssetFace.person_id == person_id)
            .all()
        )
    }

    asset_ids = direct_asset_ids.union(event_asset_ids)
    if not asset_ids:
        return []

    return (
        db.query(Asset)
        .filter(Asset.id.in_(asset_ids), Asset.kind == "photo")
        .order_by(Asset.captured_at.desc().nulls_last(), Asset.created_at.desc())
        .all()
    )
