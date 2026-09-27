import logging
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Asset, EventAsset, LifeEvent, LifePeriod, MemoryEntry
from app.services.directory import (
    assign_recorder_person,
    sync_memory_people,
    sync_memory_places,
)
from app.services.image_metadata import extract_and_apply_image_metadata
from app.services.periods import (
    ensure_event_asset_link,
    get_or_create_period_for_memory,
)


logger = logging.getLogger("memoir.life_hierarchy")
DOCUMENT_STORAGE_DIR = Path(os.getenv("DOCUMENT_STORAGE_DIR", "/data/documents"))


def _sync_document_asset_image_metadata(memory: MemoryEntry, asset: Asset) -> None:
    if asset.kind != "photo" or not memory.document_filename:
        return

    document_path = DOCUMENT_STORAGE_DIR / memory.document_filename
    if not document_path.exists():
        return

    try:
        file_bytes = document_path.read_bytes()
    except OSError as exc:
        logger.warning(
            "Could not read image asset bytes for memory %s: %s", memory.id, exc
        )
        return

    if not file_bytes:
        return

    extract_and_apply_image_metadata(asset, file_bytes, memory.document_content_type)


def _has_reliable_memory_date(memory: MemoryEntry) -> bool:
    if memory.date_year or memory.date_decade or memory.estimated_date_sort:
        return True
    precision = (memory.date_precision or "").strip().lower()
    return precision in {"day", "month", "year", "decade", "approximate"}


def _find_canonical_event_from_memory_assets(
    db: Session, memory: MemoryEntry
) -> tuple[LifeEvent | None, list[int]]:
    """Return the preferred linked event for this memory's assets and those asset ids."""
    memory_asset_ids = [
        row[0]
        for row in (
            db.query(Asset.id).filter(Asset.legacy_memory_id == memory.id).all()
        )
    ]
    if not memory_asset_ids:
        return None, []

    linked_events = (
        db.query(LifeEvent)
        .join(EventAsset, EventAsset.event_id == LifeEvent.id)
        .filter(EventAsset.asset_id.in_(memory_asset_ids))
        .distinct()
        .order_by(LifeEvent.created_at.asc(), LifeEvent.id.asc())
        .all()
    )
    if not linked_events:
        return None, memory_asset_ids

    asset_period_ids = {
        row[0]
        for row in (
            db.query(Asset.period_id)
            .filter(Asset.id.in_(memory_asset_ids), Asset.period_id.isnot(None))
            .all()
        )
    }
    if asset_period_ids:
        for candidate in linked_events:
            if candidate.period_id in asset_period_ids:
                return candidate, memory_asset_ids

    return linked_events[0], memory_asset_ids


def _should_auto_create_event_for_memory(
    memory: MemoryEntry,
    existing_event: LifeEvent | None,
    canonical_asset_event: LifeEvent | None,
) -> bool:
    if existing_event is not None:
        return True
    if canonical_asset_event is not None:
        return False

    # For new document/photo memories with unknown timing, keep the asset unlinked
    # so it lands in the Unlinked Asset Inbox for manual event assignment.
    if (
        memory.document_filename
        and not memory.audio_filename
        and not _has_reliable_memory_date(memory)
    ):
        return False

    return True


def sync_life_hierarchy_for_memory(db: Session, memory: MemoryEntry) -> None:
    event = db.query(LifeEvent).filter(LifeEvent.legacy_memory_id == memory.id).first()
    canonical_asset_event, memory_asset_ids = _find_canonical_event_from_memory_assets(
        db, memory
    )

    if (
        event is not None
        and canonical_asset_event is not None
        and event.id != canonical_asset_event.id
    ):
        # This memory is already represented by assets linked to a different event.
        # Clear the duplicate legacy pointer and remove duplicate asset links from
        # the auto-created event so the memory only appears under one event/period.
        db.query(EventAsset).filter(
            EventAsset.event_id == event.id,
            EventAsset.asset_id.in_(memory_asset_ids),
        ).delete(synchronize_session=False)
        event.legacy_memory_id = None
        event = canonical_asset_event
    elif event is None and canonical_asset_event is not None:
        event = canonical_asset_event

    period = None
    should_create_event = _should_auto_create_event_for_memory(
        memory, event, canonical_asset_event
    )

    if not event and should_create_event:
        period = get_or_create_period_for_memory(db, memory)
        event_title = (memory.event_description or "").strip() or f"Memory {memory.id}"
        if len(event_title) > 180:
            event_title = event_title[:180].rstrip()

        event = LifeEvent(
            period_id=period.id,
            title=event_title,
            description=memory.transcript,
            event_date_text=memory.estimated_date_text,
            event_date_sort=memory.estimated_date_sort,
            date_precision=memory.date_precision,
            date_year=memory.date_year,
            date_month=memory.date_month,
            date_day=memory.date_day,
            date_decade=memory.date_decade,
            legacy_memory_id=memory.id,
        )
        db.add(event)
        db.flush()
    elif event and event.period_id is not None:
        period = event.period
    elif event:
        # Recovery path: if all periods were removed, repopulate inferred structure
        # so legacy events remain visible in the timeline after restart.
        has_any_period = db.query(LifePeriod.id).first() is not None
        if not has_any_period:
            period = get_or_create_period_for_memory(db, memory)
            event.period_id = period.id

    # If a legacy-linked event exists with period_id=None, keep it unassigned
    # unless there are no periods at all (startup recovery case handled above).

    if event is not None and event.legacy_memory_id == memory.id:
        # Keep event timeline metadata synchronized with the source memory.
        event.event_date_text = memory.estimated_date_text
        event.event_date_sort = memory.estimated_date_sort
        event.event_end_date_sort = memory.estimated_end_date_sort
        event.date_precision = memory.date_precision
        event.date_year = memory.date_year
        event.date_month = memory.date_month
        event.date_day = memory.date_day
        event.date_decade = memory.date_decade

    if memory.audio_filename:
        audio_asset = (
            db.query(Asset)
            .filter(Asset.legacy_memory_id == memory.id, Asset.kind == "audio")
            .first()
        )
        if not audio_asset:
            audio_asset = Asset(
                period_id=(period.id if period else None),
                kind="audio",
                storage_filename=memory.audio_filename,
                original_filename=memory.audio_filename,
                content_type=memory.audio_content_type,
                size_bytes=memory.audio_size_bytes,
                text_excerpt=(memory.transcript or "").strip()[:1200] or None,
                notes=f"Audio recording with transcript from legacy memory {memory.id}.",
                legacy_memory_id=memory.id,
            )
            db.add(audio_asset)
            db.flush()
        else:
            if period is not None and audio_asset.period_id != period.id:
                audio_asset.period_id = period.id
            if not audio_asset.text_excerpt and memory.transcript:
                audio_asset.text_excerpt = memory.transcript[:1200]

        if event is not None:
            ensure_event_asset_link(db, event, audio_asset, relation_type="recording")

    if memory.document_filename:
        asset_kind = (
            "photo"
            if (memory.document_content_type or "").startswith("image/")
            else "document"
        )
        document_asset = (
            db.query(Asset)
            .filter(Asset.legacy_memory_id == memory.id, Asset.kind == asset_kind)
            .first()
        )
        if not document_asset:
            document_asset = Asset(
                period_id=(period.id if period else None),
                kind=asset_kind,
                storage_filename=memory.document_filename,
                original_filename=memory.document_original_filename,
                content_type=memory.document_content_type,
                size_bytes=memory.document_size_bytes,
                text_excerpt=(memory.transcript or "").strip()[:1200] or None,
                notes=f"Backfilled from legacy memory {memory.id}.",
                legacy_memory_id=memory.id,
            )
            db.add(document_asset)
            db.flush()
        elif period is not None and document_asset.period_id != period.id:
            document_asset.period_id = period.id

        _sync_document_asset_image_metadata(memory, document_asset)

        if event is not None:
            ensure_event_asset_link(db, event, document_asset)


def backfill_normalized_directory(db: Session) -> None:
    for memory in db.query(MemoryEntry).all():
        recorder_name = memory.recorder_name
        if not recorder_name and memory.recorder_person:
            recorder_name = memory.recorder_person.name
        assign_recorder_person(db, memory, recorder_name)
        sync_memory_people(db, memory, memory.referenced_people)
        sync_memory_places(db, memory, memory.referenced_locations)

    db.commit()


def backfill_life_hierarchy(db: Session) -> None:
    memories = db.query(MemoryEntry).order_by(MemoryEntry.created_at.asc()).all()

    for memory in memories:
        sync_life_hierarchy_for_memory(db, memory)

    db.commit()
