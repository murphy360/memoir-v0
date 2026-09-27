"""Queue-like orchestration for analyzing all events under a life period."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models import LifeEvent, LifePeriod
from app.services.event_analysis import (
    collect_event_memories,
    refresh_event_summary_and_suggestion,
    research_memory_entry,
)
from app.services.photo_batch import process_event_photo_assets


TERMINAL_EVENT_STATUSES = {"completed", "skipped"}


def _event_signature(event: LifeEvent, db: Session) -> str:
    """Hash the current event analysis inputs to detect staleness."""
    assets_payload: list[dict] = []
    for link in sorted(event.linked_assets, key=lambda row: (row.asset_id, row.id)):
        asset = link.asset
        if not asset:
            continue
        assets_payload.append(
            {
                "id": asset.id,
                "kind": asset.kind,
                "title": asset.title,
                "notes": asset.notes,
                "text_excerpt": asset.text_excerpt,
                "captured_at_text": asset.captured_at_text,
                "fingerprint_sha256": asset.fingerprint_sha256,
                "legacy_memory_id": asset.legacy_memory_id,
                "created_at": asset.created_at.isoformat()
                if asset.created_at
                else None,
            }
        )

    memories_payload: list[dict] = []
    for memory in sorted(collect_event_memories(event, db), key=lambda row: row.id):
        memories_payload.append(
            {
                "id": memory.id,
                "event_description": memory.event_description,
                "transcript": memory.transcript,
                "estimated_date_text": memory.estimated_date_text,
                "date_precision": memory.date_precision,
                "date_year": memory.date_year,
                "date_month": memory.date_month,
                "date_day": memory.date_day,
                "date_decade": memory.date_decade,
                "research_summary": memory.research_summary,
                "research_queries_json": memory.research_queries_json,
                "research_sources_json": memory.research_sources_json,
                "created_at": memory.created_at.isoformat()
                if memory.created_at
                else None,
            }
        )

    payload = {
        "event": {
            "id": event.id,
            "period_id": event.period_id,
            "title": event.title,
            "description": event.description,
            "event_date_text": event.event_date_text,
            "location": event.location,
        },
        "assets": assets_payload,
        "memories": memories_payload,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _memory_needs_research(memory, force: bool) -> bool:
    if force:
        return True
    if not (memory.research_summary or "").strip():
        return True
    if not (memory.research_queries_json or "").strip():
        return True
    if not (memory.research_sources_json or "").strip():
        return True
    return False


def queue_and_process_period_event_analysis(
    db: Session,
    period: LifePeriod,
    events: list[LifeEvent],
    *,
    document_storage_dir: Path,
    force_reanalyze: bool = False,
    include_processed_photos: Optional[bool] = None,
) -> dict:
    """Analyze period events in queue order before period-level recommendations run."""
    queue_ids = [event.id for event in events]
    if include_processed_photos is None:
        include_processed_photos = force_reanalyze

    analyzed = 0
    skipped = 0
    failed = 0
    photo_assets_analyzed = 0
    memories_researched = 0

    for event_id in queue_ids:
        event = db.get(LifeEvent, event_id)
        if event is None:
            failed += 1
            continue

        now = datetime.utcnow()
        event.analysis_requested_at = now
        current_hash = _event_signature(event, db)
        unchanged = bool(
            not force_reanalyze
            and event.analysis_input_hash
            and event.analysis_input_hash == current_hash
            and event.analysis_status in TERMINAL_EVENT_STATUSES
        )
        if unchanged:
            event.analysis_status = "skipped"
            event.analysis_last_error = None
            skipped += 1
            continue

        event.analysis_status = "running"
        event.analysis_started_at = now
        event.analysis_last_error = None

        try:
            updated_photos = process_event_photo_assets(
                db,
                document_storage_dir,
                event=event,
                include_processed=include_processed_photos,
            )
            photo_assets_analyzed += len(updated_photos)

            for memory in collect_event_memories(event, db):
                if not _memory_needs_research(memory, force_reanalyze):
                    continue
                research_memory_entry(memory, document_storage_dir)
                memories_researched += 1

            refresh_event_summary_and_suggestion(db, event, auto_apply_title=False)

            event.analysis_status = "completed"
            event.analysis_last_analyzed_at = datetime.utcnow()
            event.analysis_input_hash = _event_signature(event, db)
            analyzed += 1
        except Exception as exc:
            event.analysis_status = "failed"
            event.analysis_last_error = str(exc)[:1000]
            failed += 1

    return {
        "period_id": period.id,
        "queued_event_count": len(queue_ids),
        "event_count": len(events),
        "analyzed_event_count": analyzed,
        "skipped_event_count": skipped,
        "failed_event_count": failed,
        "photo_assets_analyzed": photo_assets_analyzed,
        "memories_researched": memories_researched,
    }
