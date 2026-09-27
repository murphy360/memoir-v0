import dataclasses
import hashlib
import json
import logging
import os
from io import BytesIO
from pathlib import Path
from datetime import date, datetime
from typing import Optional

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, ensure_schema_migrations, get_db
from app.models import (
    Asset,
    AssetFace,
    Base,
    EventAsset,
    LifeEpic,
    LifeEvent,
    LifePeriod,
    LifeThread,
    MemoryEntry,
    MemoryPerson,
    MemoryPlace,
    Person,
    PersonAlias,
    Place,
    Question,
    Setting,
    UnknownFaceGroup,
)
from app.schemas import (
    AnalyzeLifePeriodRequest,
    AssetResponse,
    AssignFacePersonRequest,
    CreateLifeEpicRequest,
    EventFaceResponse,
    AddAliasRequest,
    ApprovePersonFaceRequest,
    AnswerQuestionRequest,
    CreatePersonQuickMemoryRequest,
    CreateLifeEventRequest,
    CreateLifePeriodRequest,
    CreateLifeThreadRequest,
    CreateDirectoryEntryRequest,
    LifeEpicResponse,
    DirectoryEntryResponse,
    LifeEventResponse,
    LifePeriodAnalysisResponse,
    LifePeriodResponse,
    LifeThreadResponse,
    MergeLifeEventRequest,
    MergeUnknownFaceGroupRequest,
    LinkAssetToEventRequest,
    LinkPersonComprefaceRequest,
    MemoryResponse,
    MergePersonRequest,
    QuestionResponse,
    RenameFaceSubjectRequest,
    UpdateLifeEpicRequest,
    UpdateAssetRequest,
    UpdateLifeEventRequest,
    UpdateLifePeriodRequest,
    UpdateLifeThreadRequest,
    MergePeriodsRequest,
    PersonActivityResponse,
    PersonContactResponse,
    PersonDetailResponse,
    SettingsResponse,
    SplitPersonRequest,
    SplitUnknownFaceGroupRequest,
    UnknownFaceGroupResponse,
    UpdateDirectoryEntryRequest,
    UpdateMemoryRequest,
    UpdatePersonContactRequest,
    UpdateMemoryRecorderRequest,
    UpdateSettingRequest,
    AssignUnknownFaceGroupRequest,
    CreatePersonFromUnknownFaceGroupRequest,
)
from app.services.audio_storage import save_audio_file
from app.services.document_storage import save_document_file
from app.services.gemini_client import (
    extract_metadata_with_gemini_function_call,
    research_memory_details,
    suggest_event_edit_from_context,
)
from app.services.gemini_client import extract_text_from_document
from app.services.image_metadata import (
    compress_photo_for_storage,
    extract_and_apply_image_metadata,
)
from app.services.geocoding import backfill_asset_location_names
from app.services.faces import (
    approve_face_for_person,
    assign_face_to_person,
    link_person_to_existing_compreface_subject,
    list_faces_for_event,
    rename_face_subject,
    sync_asset_faces_for_photo,
)
from app.services.unknown_face_groups import (
    assign_unknown_group_to_person,
    reconcile_unknown_face_groups_for_asset,
    create_person_from_unknown_group,
    list_unknown_face_groups_for_event,
    merge_unknown_face_groups,
    split_unknown_face_group,
)
from app.services.directory import (
    assign_recorder_person,
    build_directory_response,
    detach_person_compreface_link,
    get_or_create_person,
    get_or_create_place,
    list_person_assets,
    list_person_events,
    list_person_memories,
    list_people_directory,
    list_places_directory,
    merge_people_records,
    sync_memory_people,
    sync_memory_places,
    update_memory_json_from_links,
)
from app.services.life_hierarchy import (
    backfill_life_hierarchy,
    backfill_normalized_directory,
    sync_life_hierarchy_for_memory,
)
from app.services.event_analysis import (
    collect_event_memories,
    event_research_source_memory_id,
    extract_questions_from_research,
    refresh_event_summary_and_suggestion,
    research_memory_entry,
)
from app.services.memory_ingest import analyze_memory_audio
from app.services.periods import (
    apply_epic_updates,
    apply_event_updates,
    apply_period_updates,
    analyze_period,
    build_asset_response,
    build_epic_response,
    build_event_response,
    build_period_response,
    build_thread_response,
    ensure_event_asset_link,
    normalize_directory_name,
    normalize_period_title,
    period_asset_count_from_events,
    refresh_period_summary,
    unique_period_slug,
    unique_thread_slug,
)
from app.services.period_analysis_pipeline import (
    queue_and_process_period_event_analysis,
)
from app.services.photo_batch import (
    QueuedPhotoUpload,
    analyze_photo_assets_stream,
    enqueue_photo_uploads,
    get_photo_queue_size,
    process_events_photo_assets,
    process_queued_photo_uploads,
    process_single_photo_asset,
)
from app.services.questions import (
    add_unique_pending_questions,
    normalize_question_text,
    seed_initial_questions,
)
from app.services.gemini_client import generate_insightful_questions
from app.services.memory_analysis import (
    build_sort_date,
    fallback_metadata_from_transcript,
    generate_questions_from_memory,
)
from app.services.date_normalization import (
    clean_date_text,
    parse_text_date_range,
    resolve_start_end_dates,
)


def _generate_questions(transcript: str, event_description: str, metadata) -> list[str]:
    """Generate follow-up questions, using Gemini for insightful content questions."""
    questions = generate_questions_from_memory(transcript, event_description, metadata)
    # If only the generic 'what happened just before' fallback fired, use Gemini instead
    if len(questions) == 1 and questions[0].startswith("You shared:"):
        gemini_questions = generate_insightful_questions(
            transcript, event_description, metadata
        )
        if gemini_questions:
            return gemini_questions
    return questions


logger = logging.getLogger("memoir.api")
AUDIO_STORAGE_DIR = Path(os.getenv("AUDIO_STORAGE_DIR", "/data/audio"))
DOCUMENT_STORAGE_DIR = Path(os.getenv("DOCUMENT_STORAGE_DIR", "/data/documents"))


app = FastAPI(title="Memoir API", version="0.1.0")

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    logger.info("=== APP STARTUP ===")
    logger.info(
        "Registered models: %s", [table for table in Base.metadata.tables.keys()]
    )
    logger.info("Creating tables...")
    Base.metadata.create_all(bind=engine)
    logger.info(
        "Tables after create_all: %s", [table for table in Base.metadata.tables.keys()]
    )
    AUDIO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    DOCUMENT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Running schema migrations...")
    ensure_schema_migrations()
    logger.info("Schema migrations complete")
    db = SessionLocal()
    try:
        backfill_normalized_directory(db)
        backfill_life_hierarchy(db)
        backfill_sortable_dates(db)
        db.commit()
        backfill_asset_location_names(db)
        seed_initial_questions(db)
    finally:
        db.close()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def root() -> dict:
    return {"service": "memoir-api", "health": "/api/health"}


def derive_asset_title(filename: Optional[str]) -> Optional[str]:
    candidate = (filename or "").strip()
    if not candidate:
        return None
    stem = Path(candidate).stem.strip() or candidate
    return stem[:180]


def backfill_sortable_dates(db: Session) -> None:
    for period in db.query(LifePeriod).all():
        start_sort, end_sort = resolve_start_end_dates(
            period.start_date_text, period.end_date_text
        )
        period.start_sort = start_sort
        period.end_sort = end_sort

    for epic in db.query(LifeEpic).all():
        start_sort, end_sort = resolve_start_end_dates(
            epic.start_date_text, epic.end_date_text
        )
        epic.start_sort = start_sort
        epic.end_sort = end_sort

    for event in db.query(LifeEvent).all():
        start_sort, end_sort = parse_text_date_range(event.event_date_text)
        if event.date_precision:
            start_sort = (
                build_sort_date(
                    event.date_precision,
                    event.date_year,
                    event.date_month,
                    event.date_day,
                    event.date_decade,
                )
                or start_sort
            )
        event.event_date_sort = start_sort
        event.event_end_date_sort = end_sort or start_sort

    for memory in db.query(MemoryEntry).all():
        start_sort, end_sort = parse_text_date_range(memory.estimated_date_text)
        if memory.date_precision:
            start_sort = (
                build_sort_date(
                    memory.date_precision,
                    memory.date_year,
                    memory.date_month,
                    memory.date_day,
                    memory.date_decade,
                )
                or start_sort
            )
        memory.estimated_date_sort = start_sort
        memory.estimated_end_date_sort = end_sort or start_sort

    for asset in db.query(Asset).all():
        if asset.captured_at is not None:
            asset.captured_end_at = asset.captured_at


@app.get("/api/threads", response_model=list[LifeThreadResponse])
def list_threads(db: Session = Depends(get_db)) -> list[LifeThreadResponse]:
    threads = db.query(LifeThread).order_by(LifeThread.created_at.asc()).all()
    return [build_thread_response(thread) for thread in threads]


@app.post("/api/threads", response_model=LifeThreadResponse)
def create_thread(
    body: CreateLifeThreadRequest, db: Session = Depends(get_db)
) -> LifeThreadResponse:
    title = normalize_period_title(body.title)
    if not title:
        raise HTTPException(status_code=400, detail="Thread title is required")

    thread = LifeThread(
        title=title,
        slug=unique_thread_slug(db, title),
        summary=(body.summary or None),
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return build_thread_response(thread)


@app.patch("/api/threads/{thread_id}", response_model=LifeThreadResponse)
def update_thread(
    thread_id: int, body: UpdateLifeThreadRequest, db: Session = Depends(get_db)
) -> LifeThreadResponse:
    thread = db.get(LifeThread, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if body.title is not None:
        clean_title = normalize_period_title(body.title)
        if not clean_title:
            raise HTTPException(status_code=400, detail="Thread title cannot be empty")
        thread.title = clean_title
        thread.slug = unique_thread_slug(db, clean_title, existing_id=thread.id)

    if "summary" in body.model_fields_set:
        thread.summary = (body.summary or "").strip()[:2000] or None

    db.commit()
    db.refresh(thread)
    return build_thread_response(thread)


@app.delete("/api/threads/{thread_id}", status_code=204)
def delete_thread(thread_id: int, db: Session = Depends(get_db)) -> None:
    thread = db.get(LifeThread, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    # Detach events and epics from thread before deleting
    db.query(LifeEvent).filter(LifeEvent.thread_id == thread_id).update(
        {"thread_id": None}
    )
    db.query(LifeEpic).filter(LifeEpic.thread_id == thread_id).update(
        {"thread_id": None}
    )
    db.delete(thread)
    db.commit()


@app.get("/api/periods", response_model=list[LifePeriodResponse])
def list_periods(db: Session = Depends(get_db)) -> list[LifePeriodResponse]:
    periods = (
        db.query(LifePeriod)
        .order_by(LifePeriod.start_sort.asc().nulls_last(), LifePeriod.created_at.asc())
        .all()
    )
    return [build_period_response(period) for period in periods]


@app.patch("/api/periods/{period_id}", response_model=LifePeriodResponse)
def update_period(
    period_id: int, body: UpdateLifePeriodRequest, db: Session = Depends(get_db)
) -> LifePeriodResponse:
    period = db.get(LifePeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Period not found")

    apply_period_updates(db, period, body)

    db.commit()
    db.refresh(period)
    return build_period_response(period)


@app.delete("/api/periods/{period_id}", status_code=204)
def delete_period(period_id: int, db: Session = Depends(get_db)) -> None:
    period = db.get(LifePeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Period not found")

    # Detach events and assets from the period before deleting
    db.query(LifeEvent).filter(LifeEvent.period_id == period_id).update(
        {"period_id": None}
    )
    db.query(Asset).filter(Asset.period_id == period_id).update({"period_id": None})
    db.delete(period)
    db.commit()


@app.post("/api/periods/{period_id}/merge", status_code=204)
def merge_period(
    period_id: int, body: MergePeriodsRequest, db: Session = Depends(get_db)
) -> None:
    source = db.get(LifePeriod, period_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source period not found")
    target = db.get(LifePeriod, body.into_period_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target period not found")
    if source.id == target.id:
        raise HTTPException(status_code=400, detail="Cannot merge a period into itself")

    # Move events and assets from source → target
    db.query(LifeEvent).filter(LifeEvent.period_id == source.id).update(
        {"period_id": target.id}
    )
    db.query(Asset).filter(Asset.period_id == source.id).update(
        {"period_id": target.id}
    )
    db.delete(source)
    db.commit()
    # Refresh the target summary now that it has more content
    db.refresh(target)
    refresh_period_summary(db, target, force=False)
    db.commit()


@app.post("/api/periods", response_model=LifePeriodResponse)
def create_period(
    body: CreateLifePeriodRequest, db: Session = Depends(get_db)
) -> LifePeriodResponse:
    title = normalize_period_title(body.title)
    if not title:
        raise HTTPException(status_code=400, detail="Period title is required")

    period = LifePeriod(
        title=title,
        slug=unique_period_slug(db, title),
        start_date_text=clean_date_text(body.start_date_text),
        end_date_text=clean_date_text(body.end_date_text),
        summary=body.summary,
    )
    period.start_sort, period.end_sort = resolve_start_end_dates(
        period.start_date_text, period.end_date_text
    )
    db.add(period)
    db.commit()
    db.refresh(period)
    return build_period_response(period)


@app.get("/api/periods/{period_id}/events", response_model=list[LifeEventResponse])
def list_period_events(
    period_id: int, db: Session = Depends(get_db)
) -> list[LifeEventResponse]:
    period = db.get(LifePeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Period not found")

    events = (
        db.query(LifeEvent)
        .filter(LifeEvent.period_id == period_id)
        .order_by(
            LifeEvent.event_date_sort.is_(None),
            LifeEvent.event_date_sort.asc(),
            LifeEvent.created_at.asc(),
        )
        .all()
    )
    return [build_event_response(event) for event in events]


@app.get("/api/periods/{period_id}/epics", response_model=list[LifeEpicResponse])
def list_period_epics(
    period_id: int, db: Session = Depends(get_db)
) -> list[LifeEpicResponse]:
    period = db.get(LifePeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Period not found")

    epics = (
        db.query(LifeEpic)
        .filter(LifeEpic.period_id == period_id)
        .order_by(
            LifeEpic.start_sort.is_(None),
            LifeEpic.start_sort.asc(),
            LifeEpic.created_at.asc(),
        )
        .all()
    )
    return [build_epic_response(epic) for epic in epics]


@app.get("/api/epics", response_model=list[LifeEpicResponse])
def list_epics(
    period_id: Optional[int] = None, db: Session = Depends(get_db)
) -> list[LifeEpicResponse]:
    query = db.query(LifeEpic)
    if period_id is not None:
        query = query.filter(LifeEpic.period_id == period_id)
    epics = query.order_by(
        LifeEpic.start_sort.is_(None),
        LifeEpic.start_sort.asc(),
        LifeEpic.created_at.asc(),
    ).all()
    return [build_epic_response(epic) for epic in epics]


@app.post("/api/epics", response_model=LifeEpicResponse)
def create_epic(
    body: CreateLifeEpicRequest, db: Session = Depends(get_db)
) -> LifeEpicResponse:
    period = db.get(LifePeriod, body.period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Period not found")

    title = normalize_directory_name(body.title)
    if not title:
        raise HTTPException(status_code=400, detail="Epic title is required")

    epic = LifeEpic(
        period_id=period.id,
        title=title,
        description=body.description,
        weight=body.weight,
        start_date_text=clean_date_text(body.start_date_text),
        end_date_text=clean_date_text(body.end_date_text),
    )
    epic.start_sort, epic.end_sort = resolve_start_end_dates(
        epic.start_date_text, epic.end_date_text
    )
    db.add(epic)
    db.commit()
    db.refresh(epic)
    return build_epic_response(epic)


@app.patch("/api/epics/{epic_id}", response_model=LifeEpicResponse)
def update_epic(
    epic_id: int, body: UpdateLifeEpicRequest, db: Session = Depends(get_db)
) -> LifeEpicResponse:
    epic = db.get(LifeEpic, epic_id)
    if not epic:
        raise HTTPException(status_code=404, detail="Epic not found")

    apply_epic_updates(db, epic, body)

    db.commit()
    db.refresh(epic)
    return build_epic_response(epic)


@app.delete("/api/epics/{epic_id}", status_code=204)
def delete_epic(epic_id: int, db: Session = Depends(get_db)) -> None:
    epic = db.get(LifeEpic, epic_id)
    if not epic:
        raise HTTPException(status_code=404, detail="Epic not found")
    # Detach events from epic before deleting
    db.query(LifeEvent).filter(LifeEvent.epic_id == epic_id).update({"epic_id": None})
    db.delete(epic)
    db.commit()


@app.post("/api/periods/{period_id}/analyze", response_model=LifePeriodAnalysisResponse)
def analyze_life_period(
    period_id: int,
    body: AnalyzeLifePeriodRequest = Body(default=AnalyzeLifePeriodRequest()),
    db: Session = Depends(get_db),
) -> LifePeriodAnalysisResponse:
    period = db.get(LifePeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Period not found")

    events = (
        db.query(LifeEvent)
        .filter(LifeEvent.period_id == period.id)
        .order_by(
            LifeEvent.event_date_sort.is_(None),
            LifeEvent.event_date_sort.asc(),
            LifeEvent.created_at.asc(),
        )
        .all()
    )

    pipeline_stats = queue_and_process_period_event_analysis(
        db,
        period,
        events,
        document_storage_dir=DOCUMENT_STORAGE_DIR,
        force_reanalyze=body.reanalyze_events,
    )
    db.commit()
    db.refresh(period)

    events = (
        db.query(LifeEvent)
        .filter(LifeEvent.period_id == period.id)
        .order_by(
            LifeEvent.event_date_sort.is_(None),
            LifeEvent.event_date_sort.asc(),
            LifeEvent.created_at.asc(),
        )
        .all()
    )
    analysis = analyze_period(
        period,
        events,
        period_asset_count_from_events(events),
        pipeline_stats=pipeline_stats,
    )

    if (
        body.apply_dates
        and analysis.recommended_start_date_text
        and analysis.recommended_end_date_text
    ):
        period.start_date_text = analysis.recommended_start_date_text
        period.end_date_text = analysis.recommended_end_date_text
        period.start_sort, period.end_sort = resolve_start_end_dates(
            period.start_date_text, period.end_date_text
        )

    if body.apply_title and analysis.recommended_titles:
        period.title = analysis.recommended_titles[0]
        period.slug = unique_period_slug(
            db, analysis.recommended_titles[0], existing_id=period.id
        )

    if body.apply_title_text:
        clean = body.apply_title_text.strip()[:160]
        if clean:
            period.title = clean
            period.slug = unique_period_slug(db, clean, existing_id=period.id)

    if body.regenerate_summary:
        refresh_period_summary(db, period, force=True)

    if body.apply_dates or body.apply_title or body.regenerate_summary:
        db.commit()
        db.refresh(period)
        events = (
            db.query(LifeEvent)
            .filter(LifeEvent.period_id == period.id)
            .order_by(
                LifeEvent.event_date_sort.is_(None),
                LifeEvent.event_date_sort.asc(),
                LifeEvent.created_at.asc(),
            )
            .all()
        )

    return analyze_period(
        period,
        events,
        period_asset_count_from_events(events),
        pipeline_stats=pipeline_stats,
    )


@app.post("/api/events", response_model=LifeEventResponse)
def create_event(
    body: CreateLifeEventRequest, db: Session = Depends(get_db)
) -> LifeEventResponse:
    title = normalize_directory_name(body.title)
    if not title:
        raise HTTPException(status_code=400, detail="Event title is required")

    period_id = body.period_id
    epic_id = body.epic_id

    period: Optional[LifePeriod] = None
    epic: Optional[LifeEpic] = None
    if period_id is not None:
        period = db.get(LifePeriod, period_id)
        if not period:
            raise HTTPException(status_code=404, detail="Period not found")

    if epic_id is not None:
        epic = db.get(LifeEpic, epic_id)
        if not epic:
            raise HTTPException(status_code=404, detail="Epic not found")
        if period_id is not None and epic.period_id != period_id:
            raise HTTPException(
                status_code=400, detail="Epic does not belong to the provided period"
            )
        period_id = epic.period_id

    if period_id is None:
        raise HTTPException(
            status_code=400, detail="Event requires period_id or epic_id"
        )

    parsed_event_start, parsed_event_end = parse_text_date_range(body.event_date_text)
    if parsed_event_start is not None and parsed_event_end is None:
        parsed_event_end = parsed_event_start

    event = LifeEvent(
        period_id=period_id,
        epic_id=epic_id,
        title=title,
        description=body.description,
        weight=body.weight,
        location=body.location,
        event_date_text=body.event_date_text,
        date_precision=body.date_precision,
        date_year=body.date_year,
        date_month=body.date_month,
        date_day=body.date_day,
        date_decade=body.date_decade,
        event_date_sort=(
            build_sort_date(
                body.date_precision,
                body.date_year,
                body.date_month,
                body.date_day,
                body.date_decade,
            )
            or parsed_event_start
        ),
        event_end_date_sort=parsed_event_end,
    )
    db.add(event)
    # Period summary refresh is deferred — triggered explicitly via "Analyze Period".
    db.commit()
    db.refresh(event)
    return build_event_response(event)


@app.get("/api/events", response_model=list[LifeEventResponse])
def list_events(
    period_id: Optional[int] = None, db: Session = Depends(get_db)
) -> list[LifeEventResponse]:
    query = db.query(LifeEvent)
    if period_id is not None:
        query = query.filter(LifeEvent.period_id == period_id)
    events = query.order_by(
        LifeEvent.event_date_sort.is_(None),
        LifeEvent.event_date_sort.asc(),
        LifeEvent.created_at.asc(),
    ).all()
    return [build_event_response(event) for event in events]


@app.patch("/api/events/{event_id}", response_model=LifeEventResponse)
def update_event(
    event_id: int, body: UpdateLifeEventRequest, db: Session = Depends(get_db)
) -> LifeEventResponse:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    apply_event_updates(db, event, body)

    db.commit()
    db.refresh(event)
    return build_event_response(event)


@app.post("/api/events/{event_id}/merge", response_model=LifeEventResponse)
def merge_event(
    event_id: int,
    body: MergeLifeEventRequest,
    db: Session = Depends(get_db),
) -> LifeEventResponse:
    source = db.get(LifeEvent, event_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source event not found")

    target = db.get(LifeEvent, body.into_event_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target event not found")

    if source.id == target.id:
        raise HTTPException(status_code=400, detail="Cannot merge an event into itself")

    for link in list(source.linked_assets):
        exists = any(
            existing.asset_id == link.asset_id for existing in target.linked_assets
        )
        if not exists:
            db.add(
                EventAsset(
                    event_id=target.id,
                    asset_id=link.asset_id,
                    relation_type=link.relation_type,
                )
            )

    if not target.description and source.description:
        target.description = source.description
    if not target.event_date_text and source.event_date_text:
        target.event_date_text = source.event_date_text
        target.event_date_sort = source.event_date_sort
        target.event_end_date_sort = source.event_end_date_sort
        target.date_precision = source.date_precision
        target.date_year = source.date_year
        target.date_month = source.date_month
        target.date_day = source.date_day
        target.date_decade = source.date_decade
    if target.period_id is None and source.period_id is not None:
        target.period_id = source.period_id
    if target.legacy_memory_id is None and source.legacy_memory_id is not None:
        target.legacy_memory_id = source.legacy_memory_id

    target_period = db.get(LifePeriod, target.period_id) if target.period_id else None
    source_period = db.get(LifePeriod, source.period_id) if source.period_id else None
    refresh_period_summary(db, target_period)
    if source_period and (not target_period or source_period.id != target_period.id):
        refresh_period_summary(db, source_period)

    db.delete(source)
    db.commit()
    db.refresh(target)
    return build_event_response(target)


@app.delete("/api/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)) -> dict:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    period = db.get(LifePeriod, event.period_id) if event.period_id else None
    db.delete(event)
    refresh_period_summary(db, period)
    db.commit()
    return {"status": "deleted", "event_id": event_id}


@app.get("/api/events/{event_id}/assets", response_model=list[AssetResponse])
def list_event_assets(
    event_id: int, db: Session = Depends(get_db)
) -> list[AssetResponse]:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    assets = [link.asset for link in event.linked_assets if link.asset]
    return [build_asset_response(asset) for asset in assets]


def _build_event_face_response(face: AssetFace) -> EventFaceResponse:
    asset = face.asset
    person = face.person
    return EventFaceResponse(
        id=face.id,
        asset_id=face.asset_id,
        asset_title=(asset.title if asset else None)
        or (asset.original_filename if asset else None),
        asset_download_url=(asset.download_url if asset else ""),
        bbox_x=face.bbox_x,
        bbox_y=face.bbox_y,
        bbox_w=face.bbox_w,
        bbox_h=face.bbox_h,
        confidence=face.confidence,
        compreface_subject=face.compreface_subject,
        compreface_similarity=face.compreface_similarity,
        compreface_gender=face.compreface_gender,
        compreface_age_low=face.compreface_age_low,
        compreface_age_high=face.compreface_age_high,
        compreface_raw=face.compreface_raw,
        person_id=person.id if person else None,
        person_name=person.name if person else None,
    )


def _build_unknown_face_group_response(
    db: Session, group_id: int
) -> UnknownFaceGroupResponse:
    group = db.get(UnknownFaceGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Unknown face group not found")

    face_rows = (
        db.query(AssetFace)
        .filter(AssetFace.unknown_face_group_id == group_id)
        .order_by(AssetFace.id.asc())
        .all()
    )
    return UnknownFaceGroupResponse(
        group_id=group_id,
        fingerprint=group.fingerprint,
        status=group.status,
        representative_face_id=group.representative_face_id,
        face_count=len(face_rows),
        members=[
            {
                "face_id": face.id,
                "asset_id": face.asset_id,
                "asset_download_url": face.asset.download_url if face.asset else "",
                "bbox_x": face.bbox_x,
                "bbox_y": face.bbox_y,
                "bbox_w": face.bbox_w,
                "bbox_h": face.bbox_h,
                "confidence": face.confidence,
            }
            for face in face_rows
        ],
    )


@app.get("/api/events/{event_id}/faces", response_model=list[EventFaceResponse])
def list_event_faces(
    event_id: int, db: Session = Depends(get_db)
) -> list[EventFaceResponse]:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    faces = list_faces_for_event(db, event_id)
    return [_build_event_face_response(face) for face in faces if face.asset]


@app.get("/api/faces/{face_id}/thumbnail")
def get_face_thumbnail(
    face_id: int,
    size: int = 96,
    padding: float = 0.35,
    db: Session = Depends(get_db),
) -> Response:
    """Return a cropped thumbnail image for a detected face."""
    face = db.get(AssetFace, face_id)
    if not face:
        raise HTTPException(status_code=404, detail="Face not found")

    asset = face.asset
    if not asset or not asset.storage_filename:
        raise HTTPException(status_code=404, detail="Source photo not found")

    content_type = (asset.content_type or "").lower()
    if asset.kind != "photo" and not content_type.startswith("image/"):
        raise HTTPException(
            status_code=400, detail="Face thumbnail is only available for photo assets"
        )

    bounded_size = max(32, min(512, size))
    bounded_padding = max(0.0, min(1.5, padding))

    image_path = DOCUMENT_STORAGE_DIR / asset.storage_filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Source photo file not found")

    try:
        with Image.open(image_path) as image:
            image = image.convert("RGB")
            width, height = image.size

            x = max(0.0, min(1.0, face.bbox_x))
            y = max(0.0, min(1.0, face.bbox_y))
            w = max(0.0001, min(1.0, face.bbox_w))
            h = max(0.0001, min(1.0, face.bbox_h))

            left = int(max(0, (x - (w * bounded_padding)) * width))
            top = int(max(0, (y - (h * bounded_padding)) * height))
            right = int(min(width, (x + w + (w * bounded_padding)) * width))
            bottom = int(min(height, (y + h + (h * bounded_padding)) * height))

            if right <= left:
                right = min(width, left + 1)
            if bottom <= top:
                bottom = min(height, top + 1)

            cropped = image.crop((left, top, right, bottom))
            cropped.thumbnail((bounded_size, bounded_size), Image.LANCZOS)

            buffer = BytesIO()
            cropped.save(buffer, format="JPEG", quality=88)
            return Response(
                content=buffer.getvalue(),
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=86400"},
            )
    except UnidentifiedImageError as exc:
        raise HTTPException(
            status_code=415, detail="Source file is not a readable image"
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail="Could not render face thumbnail"
        ) from exc


@app.get(
    "/api/events/{event_id}/unknown-face-groups",
    response_model=list[UnknownFaceGroupResponse],
)
def list_event_unknown_face_groups(
    event_id: int, db: Session = Depends(get_db)
) -> list[UnknownFaceGroupResponse]:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return [
        UnknownFaceGroupResponse(**payload)
        for payload in list_unknown_face_groups_for_event(db, event_id)
    ]


@app.post(
    "/api/unknown-face-groups/{group_id}/assign-person",
    response_model=UnknownFaceGroupResponse,
)
def assign_unknown_face_group(
    group_id: int,
    body: AssignUnknownFaceGroupRequest,
    db: Session = Depends(get_db),
) -> UnknownFaceGroupResponse:
    try:
        assign_unknown_group_to_person(db, group_id, body.person_id)
    except ValueError as exc:
        if str(exc) == "group_not_found":
            raise HTTPException(
                status_code=404, detail="Unknown face group not found"
            ) from exc
        if str(exc) == "person_not_found":
            raise HTTPException(status_code=404, detail="Person not found") from exc
        raise HTTPException(
            status_code=400, detail="Could not assign unknown face group"
        ) from exc

    db.commit()
    return _build_unknown_face_group_response(db, group_id)


@app.post(
    "/api/unknown-face-groups/{group_id}/create-person",
    response_model=DirectoryEntryResponse,
)
def create_person_from_unknown_group_route(
    group_id: int,
    body: CreatePersonFromUnknownFaceGroupRequest,
    db: Session = Depends(get_db),
) -> DirectoryEntryResponse:
    try:
        _, person = create_person_from_unknown_group(db, group_id, body.name)
    except ValueError as exc:
        if str(exc) == "group_not_found":
            raise HTTPException(
                status_code=404, detail="Unknown face group not found"
            ) from exc
        raise HTTPException(
            status_code=400, detail="Could not create person from unknown face group"
        ) from exc

    db.commit()
    return build_directory_response(person.name, person.id, 0)


@app.post(
    "/api/unknown-face-groups/{group_id}/merge", response_model=UnknownFaceGroupResponse
)
def merge_unknown_face_group_route(
    group_id: int,
    body: MergeUnknownFaceGroupRequest,
    db: Session = Depends(get_db),
) -> UnknownFaceGroupResponse:
    try:
        target = merge_unknown_face_groups(db, group_id, body.into_group_id)
    except ValueError as exc:
        if str(exc) == "group_not_found":
            raise HTTPException(
                status_code=404, detail="Unknown face group not found"
            ) from exc
        if str(exc) == "cannot_merge_same_group":
            raise HTTPException(
                status_code=400, detail="Cannot merge a group into itself"
            ) from exc
        raise HTTPException(
            status_code=400, detail="Could not merge unknown face groups"
        ) from exc

    db.commit()
    return _build_unknown_face_group_response(db, target.id)


@app.post(
    "/api/unknown-face-groups/{group_id}/split", response_model=UnknownFaceGroupResponse
)
def split_unknown_face_group_route(
    group_id: int,
    body: SplitUnknownFaceGroupRequest,
    db: Session = Depends(get_db),
) -> UnknownFaceGroupResponse:
    try:
        split_group = split_unknown_face_group(db, group_id, body.face_ids)
    except ValueError as exc:
        if str(exc) == "group_not_found":
            raise HTTPException(
                status_code=404, detail="Unknown face group not found"
            ) from exc
        if str(exc) == "no_faces_selected":
            raise HTTPException(
                status_code=400, detail="No faces selected to split"
            ) from exc
        raise HTTPException(
            status_code=400, detail="Could not split unknown face group"
        ) from exc

    db.commit()
    return _build_unknown_face_group_response(db, split_group.id)


@app.post("/api/faces/{face_id}/assign-person", response_model=EventFaceResponse)
def assign_event_face_person(
    face_id: int,
    body: AssignFacePersonRequest,
    db: Session = Depends(get_db),
) -> EventFaceResponse:
    try:
        face = assign_face_to_person(db, face_id, body.person_id)
    except ValueError as exc:
        if str(exc) == "face_not_found":
            raise HTTPException(status_code=404, detail="Face not found") from exc
        if str(exc) == "person_not_found":
            raise HTTPException(status_code=404, detail="Person not found") from exc
        raise HTTPException(status_code=400, detail="Could not assign face") from exc

    db.commit()
    db.refresh(face)
    return _build_event_face_response(face)


@app.post("/api/faces/{face_id}/rename-subject", response_model=EventFaceResponse)
def rename_event_face_subject(
    face_id: int,
    body: RenameFaceSubjectRequest,
    db: Session = Depends(get_db),
) -> EventFaceResponse:
    try:
        face = rename_face_subject(db, face_id, body.new_subject_name)
    except ValueError as exc:
        code = str(exc)
        if code == "face_not_found":
            raise HTTPException(status_code=404, detail="Face not found") from exc
        if code == "face_has_no_subject":
            raise HTTPException(
                status_code=400, detail="Face has no CompreFace subject"
            ) from exc
        if code == "subject_name_required":
            raise HTTPException(
                status_code=400, detail="New subject name is required"
            ) from exc
        if code == "subject_name_too_long":
            raise HTTPException(
                status_code=400, detail="New subject name is too long"
            ) from exc
        if code == "compreface_rename_failed":
            raise HTTPException(
                status_code=502,
                detail="Failed to rename CompreFace subject in upstream service",
            ) from exc
        raise HTTPException(
            status_code=400, detail="Could not rename CompreFace subject"
        ) from exc

    db.commit()
    db.refresh(face)
    return _build_event_face_response(face)


@app.delete("/api/faces/{face_id}", status_code=204)
def delete_event_face(face_id: int, db: Session = Depends(get_db)) -> None:
    face = db.get(AssetFace, face_id)
    if not face:
        raise HTTPException(status_code=404, detail="Face not found")
    asset_id = face.asset_id
    db.delete(face)
    db.flush()
    reconcile_unknown_face_groups_for_asset(db, asset_id)
    db.commit()


@app.post("/api/assets/{asset_id}/sync-faces", response_model=list[EventFaceResponse])
def sync_asset_faces(
    asset_id: int, db: Session = Depends(get_db)
) -> list[EventFaceResponse]:
    """Trigger face detection on a single photo asset on demand."""
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.kind != "photo":
        raise HTTPException(status_code=400, detail="Asset is not a photo")
    if not asset.storage_filename:
        raise HTTPException(status_code=400, detail="Asset has no stored file")
    file_path = DOCUMENT_STORAGE_DIR / asset.storage_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Asset file not found on disk")
    image_bytes = file_path.read_bytes()
    sync_asset_faces_for_photo(db, asset, image_bytes)
    db.commit()
    faces = db.query(AssetFace).filter(AssetFace.asset_id == asset_id).all()
    return [_build_event_face_response(face) for face in faces]


@app.post("/api/events/{event_id}/summarize", response_model=LifeEventResponse)
def summarize_event(event_id: int, db: Session = Depends(get_db)) -> LifeEventResponse:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Process any photo assets that haven't been analyzed yet so their
    # text_excerpt, title, and place data are available for the summary.
    process_events_photo_assets(
        db,
        DOCUMENT_STORAGE_DIR,
        event_id=event_id,
        include_processed=False,
    )
    db.flush()

    refresh_event_summary_and_suggestion(db, event, auto_apply_title=False)

    db.commit()
    db.refresh(event)
    return build_event_response(event)


@app.post("/api/events/{event_id}/research", response_model=LifeEventResponse)
def research_event(event_id: int, db: Session = Depends(get_db)) -> LifeEventResponse:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    memories = collect_event_memories(event, db)
    assets = [link.asset for link in event.linked_assets if link.asset]

    transcript_sections: list[str] = [f"Event title: {event.title}"]
    if event.description:
        transcript_sections.append(f"Event description: {event.description}")

    for memory in memories:
        transcript_sections.append(f"Memory: {memory.event_description}")
        transcript_sections.append(memory.transcript or "")

    for asset in assets:
        asset_title = asset.title or asset.original_filename or f"Asset {asset.id}"
        transcript_sections.append(f"Asset: {asset_title}")
        if asset.notes:
            transcript_sections.append(f"Notes: {asset.notes}")
        if asset.text_excerpt:
            transcript_sections.append(f"Extracted text: {asset.text_excerpt}")
        if asset.captured_at_text:
            transcript_sections.append(f"Captured at: {asset.captured_at_text}")

    combined_transcript = "\n\n".join(
        section for section in transcript_sections if section.strip()
    )[:20000]
    people = sorted(
        {name for memory in memories for name in memory.referenced_people if name}
    )
    locations = sorted(
        {name for memory in memories for name in memory.referenced_locations if name}
    )

    research = research_memory_details(
        transcript=combined_transcript,
        event_description=event.title,
        estimated_date_text=event.event_date_text,
        referenced_locations=locations,
        referenced_people=people,
        document_bytes=None,
        document_mime_type=None,
    )

    event.research_summary = research.summary
    event.research_queries_json = json.dumps(research.queries)
    event.research_sources_json = json.dumps(
        [{"title": source.title, "url": source.url} for source in research.sources]
    )
    suggestion = suggest_event_edit_from_context(
        analysis_text=research.summary,
        current_title=event.title,
        current_event_date_text=event.event_date_text,
        current_description=event.description,
    )
    event.research_suggested_edit_json = (
        json.dumps(dataclasses.asdict(suggestion)) if suggestion else None
    )

    source_memory_id = event_research_source_memory_id(event, memories)
    if source_memory_id is not None:
        add_unique_pending_questions(
            db,
            extract_questions_from_research(research.summary),
            source_memory_id,
        )

    db.commit()
    db.refresh(event)
    return build_event_response(event)


@app.post(
    "/api/events/{event_id}/apply-research-suggestion", response_model=LifeEventResponse
)
def apply_event_research_suggestion(
    event_id: int, db: Session = Depends(get_db)
) -> LifeEventResponse:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not event.research_suggested_edit_json:
        raise HTTPException(status_code=404, detail="No pending suggestion")

    suggestion = json.loads(event.research_suggested_edit_json)
    if isinstance(suggestion, dict):
        next_title = (suggestion.get("title") or "").strip()
        next_date_text = (suggestion.get("event_date_text") or "").strip()
        next_description = (suggestion.get("description") or "").strip()

        if next_title:
            event.title = next_title[:180]
        if next_date_text:
            event.event_date_text = next_date_text[:100]
            parsed_start, parsed_end = parse_text_date_range(event.event_date_text)
            if parsed_start is not None and parsed_end is None:
                parsed_end = parsed_start
            event.event_date_sort = parsed_start
            event.event_end_date_sort = parsed_end
        if next_description:
            event.description = next_description[:1200]

    event.research_suggested_edit_json = None
    db.commit()
    db.refresh(event)
    return build_event_response(event)


@app.post(
    "/api/events/{event_id}/dismiss-research-suggestion",
    response_model=LifeEventResponse,
)
def dismiss_event_research_suggestion(
    event_id: int, db: Session = Depends(get_db)
) -> LifeEventResponse:
    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.research_suggested_edit_json = None
    db.commit()
    db.refresh(event)
    return build_event_response(event)


@app.get("/api/assets/unlinked", response_model=list[AssetResponse])
def list_unlinked_assets(db: Session = Depends(get_db)) -> list[AssetResponse]:
    assets = (
        db.query(Asset)
        .order_by(
            Asset.captured_at.is_(None),
            Asset.captured_at.asc(),
            Asset.created_at.desc(),
        )
        .all()
    )
    unlinked = [asset for asset in assets if not asset.event_links]
    return [build_asset_response(asset) for asset in unlinked]


@app.post("/api/assets", response_model=AssetResponse)
async def upload_asset(
    file: UploadFile = File(...),
    kind: str = Form("document"),
    period_id: Optional[int] = Form(None),
    event_id: Optional[int] = Form(None),
    notes: Optional[str] = Form(None),
    captured_at_text: Optional[str] = Form(None),
    db: Session = Depends(get_db),
) -> AssetResponse:
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Asset file is empty")

    if period_id is not None and not db.get(LifePeriod, period_id):
        raise HTTPException(status_code=404, detail="Period not found")

    event: Optional[LifeEvent] = None
    if event_id is not None:
        event = db.get(LifeEvent, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

    normalized_kind = (kind or "document").strip().lower()[:20]
    if normalized_kind == "audio" or (file.content_type or "").startswith("audio/"):
        storage_filename, content_type, size_bytes, stored_bytes = save_audio_file(
            file, file_bytes, AUDIO_STORAGE_DIR
        )
        original_filename = file.filename
        fingerprint = hashlib.sha256(stored_bytes).hexdigest()
        normalized_kind = "audio"
    else:
        # For images, compress before writing to disk; EXIF extraction uses original bytes
        storage_bytes = file_bytes
        storage_content_type = (file.content_type or "").split(";")[
            0
        ].strip().lower() or None
        if storage_content_type and storage_content_type.startswith("image/"):
            storage_bytes, storage_content_type = compress_photo_for_storage(
                file_bytes, storage_content_type
            )
        (
            storage_filename,
            content_type,
            size_bytes,
            original_filename,
        ) = save_document_file(file, storage_bytes, DOCUMENT_STORAGE_DIR)
        if storage_content_type:
            content_type = storage_content_type
        fingerprint = hashlib.sha256(file_bytes).hexdigest()

    asset = Asset(
        period_id=period_id,
        kind=normalized_kind,
        title=derive_asset_title(original_filename),
        storage_filename=storage_filename,
        original_filename=original_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        fingerprint_sha256=fingerprint,
        notes=notes,
    )
    if normalized_kind != "audio":
        extract_and_apply_image_metadata(
            asset, file_bytes, content_type, skip_geocoding=True
        )
        captured_text_override = clean_date_text(captured_at_text)
        if captured_text_override:
            start_date, end_date = parse_text_date_range(captured_text_override)
            if start_date is None:
                raise HTTPException(
                    status_code=400,
                    detail="Could not parse captured date text override",
                )
            resolved_end_date = end_date or start_date
            asset.captured_at_text = captured_text_override
            asset.captured_at = datetime.combine(start_date, datetime.min.time())
            asset.captured_end_at = datetime.combine(
                resolved_end_date, datetime.min.time()
            )

    db.add(asset)
    db.flush()

    # Face detection and period summary are deferred — run "Process Event Photos" after upload.
    # sync_asset_faces_for_photo is intentionally skipped here to keep uploads fast.

    if event:
        db.add(
            EventAsset(event_id=event.id, asset_id=asset.id, relation_type="evidence")
        )

    db.commit()
    db.refresh(asset)
    return build_asset_response(asset)


@app.post("/api/assets/photos/queue")
async def queue_photo_assets(
    files: list[UploadFile] = File(...),
    period_id: Optional[int] = Form(None),
    event_id: Optional[int] = Form(None),
    notes: Optional[str] = Form(None),
    auto_process: bool = Form(False),
    db: Session = Depends(get_db),
) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    if period_id is not None and not db.get(LifePeriod, period_id):
        raise HTTPException(status_code=404, detail="Period not found")

    if event_id is not None and not db.get(LifeEvent, event_id):
        raise HTTPException(status_code=404, detail="Event not found")

    queued_items: list[QueuedPhotoUpload] = []
    for file in files:
        file_bytes = await file.read()
        if not file_bytes:
            continue

        content_type = (file.content_type or "").split(";")[0].strip().lower()
        if not content_type.startswith("image/"):
            raise HTTPException(
                status_code=415,
                detail=(
                    f"Unsupported file type '{content_type}'. "
                    "Photo batch queue accepts images only"
                ),
            )

        queued_items.append(
            QueuedPhotoUpload(
                filename=(file.filename or "photo"),
                content_type=content_type,
                file_bytes=file_bytes,
                period_id=period_id,
                event_id=event_id,
                notes=notes,
            )
        )

    if not queued_items:
        raise HTTPException(status_code=400, detail="No non-empty photo files provided")

    queue_size = enqueue_photo_uploads(queued_items)

    if not auto_process:
        return {
            "queued_count": len(queued_items),
            "queue_size": queue_size,
            "processed_count": 0,
            "assets": [],
        }

    assets = process_queued_photo_uploads(db, DOCUMENT_STORAGE_DIR)
    db.commit()
    for asset in assets:
        db.refresh(asset)

    return {
        "queued_count": len(queued_items),
        "queue_size": get_photo_queue_size(),
        "processed_count": len(assets),
        "assets": [
            build_asset_response(asset).model_dump(mode="json") for asset in assets
        ],
    }


@app.post("/api/assets/photos/queue/process", response_model=list[AssetResponse])
def process_photo_asset_queue(
    max_items: Optional[int] = Body(default=None, embed=True),
    db: Session = Depends(get_db),
) -> list[AssetResponse]:
    assets = process_queued_photo_uploads(db, DOCUMENT_STORAGE_DIR, max_items=max_items)
    if not assets:
        return []

    db.commit()
    for asset in assets:
        db.refresh(asset)
    return [build_asset_response(asset) for asset in assets]


@app.get("/api/assets/analyze-stream")
def stream_analyze_assets(
    asset_ids: Optional[str] = None,
    event_id: Optional[int] = None,
    include_processed: bool = False,
) -> StreamingResponse:
    """SSE endpoint: streams per-photo analysis progress (geocoding -> faces -> gemini).

    Provide either:
    - asset_ids: comma-separated list of asset IDs
    - event_id: resolve all photo assets linked to this event (respects include_processed)
    """
    if asset_ids:
        ids = [int(x.strip()) for x in asset_ids.split(",") if x.strip().isdigit()]
    elif event_id is not None:
        with SessionLocal() as _db:
            event = _db.get(LifeEvent, event_id)
            if not event:
                raise HTTPException(status_code=404, detail="Event not found")
            ids = [
                link.asset.id
                for link in event.linked_assets
                if link.asset
                and link.asset.kind == "photo"
                and link.asset.storage_filename
                and (include_processed or not (link.asset.text_excerpt or "").strip())
            ]
    else:
        raise HTTPException(status_code=400, detail="Provide asset_ids or event_id")

    if not ids:

        def _empty():
            yield f"data: {json.dumps({'type': 'complete', 'photos_processed': 0})}\n\n"

        return StreamingResponse(
            _empty(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def generate():
        db = SessionLocal()
        try:
            yield from analyze_photo_assets_stream(db, DOCUMENT_STORAGE_DIR, ids)
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        finally:
            db.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/assets/photos/process-events")
def process_photo_assets_by_event(
    event_id: Optional[int] = Body(default=None, embed=True),
    include_processed: bool = Body(default=False, embed=True),
    max_events: Optional[int] = Body(default=None, embed=True),
    max_items_per_event: Optional[int] = Body(default=None, embed=True),
    db: Session = Depends(get_db),
) -> dict:
    if event_id is not None and not db.get(LifeEvent, event_id):
        raise HTTPException(status_code=404, detail="Event not found")

    result = process_events_photo_assets(
        db,
        DOCUMENT_STORAGE_DIR,
        event_id=event_id,
        include_processed=include_processed,
        max_events=max_events,
        max_items_per_event=max_items_per_event,
    )
    db.commit()
    return result


@app.post("/api/assets/{asset_id}/process-photo")
def process_single_photo(
    asset_id: int,
    include_processed: bool = Body(default=True, embed=True),
    db: Session = Depends(get_db),
) -> dict:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.kind != "photo":
        raise HTTPException(status_code=400, detail="Asset is not a photo")

    processed, suggested_title = process_single_photo_asset(
        db,
        DOCUMENT_STORAGE_DIR,
        asset=asset,
        include_processed=include_processed,
        force_faces=True,
    )
    if not processed:
        raise HTTPException(
            status_code=400, detail="Photo asset could not be processed"
        )

    db.commit()
    db.refresh(asset)
    return {
        "asset_id": asset.id,
        "processed": True,
        "has_text_excerpt": bool((asset.text_excerpt or "").strip()),
        "face_count": len(asset.faces),
        "has_gps": asset.gps_latitude is not None and asset.gps_longitude is not None,
        "exif_place_name": asset.exif_place_name,
        "reverse_geocode_location_name": asset.reverse_geocode_location_name,
        "analyzed_place_name": asset.analyzed_place_name,
        "location_name": asset.location_name,
        "captured_at_text": asset.captured_at_text,
        "gemini_suggested_title": asset.gemini_suggested_title,
        "suggested_title": suggested_title,
    }


@app.post("/api/assets/{asset_id}/link-event/{event_id}", response_model=AssetResponse)
def link_asset_to_event(
    asset_id: int,
    event_id: int,
    body: LinkAssetToEventRequest,
    db: Session = Depends(get_db),
) -> AssetResponse:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    event = db.get(LifeEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    existing = (
        db.query(EventAsset)
        .filter(EventAsset.asset_id == asset_id, EventAsset.event_id == event_id)
        .first()
    )
    if not existing:
        db.add(
            EventAsset(
                event_id=event_id,
                asset_id=asset_id,
                relation_type=(body.relation_type or "evidence")[:30],
            )
        )
        period = db.get(LifePeriod, event.period_id) if event.period_id else None
        refresh_period_summary(db, period)
        db.commit()
        db.refresh(asset)

    return build_asset_response(asset)


@app.patch("/api/assets/{asset_id}", response_model=AssetResponse)
def update_asset(
    asset_id: int, body: UpdateAssetRequest, db: Session = Depends(get_db)
) -> AssetResponse:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if "title" in body.model_fields_set:
        clean_title = body.title.strip() if body.title is not None else None
        asset.title = clean_title or None

    if "notes" in body.model_fields_set:
        clean_notes = body.notes.strip() if body.notes is not None else None
        asset.notes = clean_notes or None

    if "captured_at_text" in body.model_fields_set:
        cleaned_captured_text = clean_date_text(body.captured_at_text)
        if not cleaned_captured_text:
            asset.captured_at_text = None
            asset.captured_at = None
            asset.captured_end_at = None
        else:
            start_date, end_date = parse_text_date_range(cleaned_captured_text)
            if start_date is None:
                raise HTTPException(
                    status_code=400, detail="Could not parse captured date text"
                )
            resolved_end_date = end_date or start_date
            asset.captured_at_text = cleaned_captured_text
            asset.captured_at = datetime.combine(start_date, datetime.min.time())
            asset.captured_end_at = datetime.combine(
                resolved_end_date, datetime.min.time()
            )

    db.commit()
    db.refresh(asset)
    return build_asset_response(asset)


@app.delete("/api/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: int, db: Session = Depends(get_db)) -> None:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    storage_dir = AUDIO_STORAGE_DIR if asset.kind == "audio" else DOCUMENT_STORAGE_DIR
    file_path = storage_dir / asset.storage_filename if asset.storage_filename else None

    db.delete(asset)
    db.commit()

    if file_path and file_path.exists():
        try:
            file_path.unlink()
        except OSError:
            logger.warning("Could not delete file for asset %s", asset_id)


@app.get("/api/assets/{asset_id}/download")
def download_asset(
    asset_id: int, download: bool = True, db: Session = Depends(get_db)
) -> FileResponse:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    storage_dir = AUDIO_STORAGE_DIR if asset.kind == "audio" else DOCUMENT_STORAGE_DIR
    file_path = storage_dir / asset.storage_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Asset file missing from storage")

    filename = asset.original_filename or asset.storage_filename
    disposition = "attachment" if download else "inline"
    return FileResponse(
        path=file_path,
        media_type=(asset.content_type or "application/octet-stream"),
        filename=filename,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@app.get("/api/memories", response_model=list[MemoryResponse])
def list_memories(db: Session = Depends(get_db)) -> list[MemoryEntry]:
    memories = (
        db.query(MemoryEntry)
        .order_by(
            MemoryEntry.estimated_date_sort.is_(None),
            MemoryEntry.estimated_date_sort.asc(),
            MemoryEntry.estimated_end_date_sort.asc().nulls_last(),
            MemoryEntry.date_recorded.desc().nulls_last(),
            MemoryEntry.created_at.desc(),
        )
        .all()
    )
    return memories


@app.get("/api/people", response_model=list[DirectoryEntryResponse])
def list_people(db: Session = Depends(get_db)) -> list[DirectoryEntryResponse]:
    return list_people_directory(db)


@app.get("/api/people/{person_id}", response_model=PersonDetailResponse)
def get_person_details(
    person_id: int, db: Session = Depends(get_db)
) -> PersonDetailResponse:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    directory_row = next(
        (row for row in list_people_directory(db) if row.id == person_id), None
    )
    memories = list_person_memories(db, person_id)
    events = list_person_events(db, person_id)

    return PersonDetailResponse(
        id=person.id,
        name=person.name,
        aliases=[alias.alias for alias in person.aliases],
        memory_count=(directory_row.memory_count if directory_row else len(memories)),
        event_count=len(events),
        photo_count=(directory_row.photo_count if directory_row else 0),
        avatar_download_url=(
            directory_row.avatar_download_url if directory_row else None
        ),
        compreface_subject_id=person.compreface_subject_id,
        compreface_subject_url=(
            directory_row.compreface_subject_url if directory_row else None
        ),
        contact=PersonContactResponse(
            phone=person.phone,
            email=person.email,
            address=person.address,
            notes=person.notes,
            birthday_text=person.birthday_text,
        ),
    )


@app.patch("/api/people/{person_id}/contact", response_model=PersonDetailResponse)
def update_person_contact(
    person_id: int,
    body: UpdatePersonContactRequest,
    db: Session = Depends(get_db),
) -> PersonDetailResponse:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    if "phone" in body.model_fields_set:
        person.phone = (body.phone or "").strip() or None
    if "email" in body.model_fields_set:
        person.email = (body.email or "").strip() or None
    if "address" in body.model_fields_set:
        person.address = (body.address or "").strip() or None
    if "notes" in body.model_fields_set:
        person.notes = (body.notes or "").strip() or None
    if "birthday_text" in body.model_fields_set:
        person.birthday_text = clean_date_text(body.birthday_text)

    db.commit()
    return get_person_details(person_id, db)


@app.get("/api/people/{person_id}/activity", response_model=PersonActivityResponse)
def get_person_activity(
    person_id: int, db: Session = Depends(get_db)
) -> PersonActivityResponse:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    memories = list_person_memories(db, person_id)
    events = list_person_events(db, person_id)
    assets = list_person_assets(db, person_id)

    return PersonActivityResponse(
        memories=[MemoryResponse.model_validate(memory) for memory in memories],
        events=[build_event_response(event) for event in events],
        assets=[build_asset_response(asset) for asset in assets],
    )


@app.post("/api/people/{person_id}/memories/quick", response_model=MemoryResponse)
def create_person_quick_memory(
    person_id: int,
    body: CreatePersonQuickMemoryRequest,
    db: Session = Depends(get_db),
) -> MemoryEntry:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    text_value = (body.text or "").strip()
    if not text_value:
        raise HTTPException(status_code=400, detail="Memory text is required")

    clean_estimated_date = clean_date_text(body.estimated_date_text)
    estimated_start, estimated_end = parse_text_date_range(clean_estimated_date)

    memory = MemoryEntry(
        transcript=text_value,
        event_description=text_value[:180],
        estimated_date_text=clean_estimated_date,
        estimated_date_sort=estimated_start,
        estimated_end_date_sort=estimated_end or estimated_start,
        recorder_name=person.name,
        recorder_person_id=person.id,
        emotional_tone="neutral",
        follow_up_question="Would you like to add more detail about this person?",
        date_recorded=datetime.utcnow().date(),
    )
    db.add(memory)
    db.flush()

    sync_memory_people(db, memory, [person.name])

    db.commit()
    db.refresh(memory)
    return memory


@app.post(
    "/api/people/{person_id}/faces/{face_id}/approve", response_model=EventFaceResponse
)
def approve_person_face(
    person_id: int,
    face_id: int,
    body: ApprovePersonFaceRequest,
    db: Session = Depends(get_db),
) -> EventFaceResponse:
    if body.person_id != person_id:
        raise HTTPException(status_code=400, detail="Person id mismatch")

    try:
        face = approve_face_for_person(db, face_id, person_id)
    except ValueError as exc:
        if str(exc) == "face_not_found":
            raise HTTPException(status_code=404, detail="Face not found") from exc
        if str(exc) == "person_not_found":
            raise HTTPException(status_code=404, detail="Person not found") from exc
        raise HTTPException(status_code=400, detail="Could not approve face") from exc

    db.commit()
    db.refresh(face)
    return _build_event_face_response(face)


@app.get(
    "/api/people/{person_id}/faces/suggested", response_model=list[EventFaceResponse]
)
def list_person_suggested_faces(
    person_id: int, db: Session = Depends(get_db)
) -> list[EventFaceResponse]:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    subject_candidates = {
        value.casefold()
        for value in [person.compreface_subject_id, person.name]
        if (value or "").strip()
    }
    if not subject_candidates:
        return []

    candidate_faces = (
        db.query(AssetFace)
        .join(Asset, Asset.id == AssetFace.asset_id)
        .filter(
            Asset.kind == "photo",
            AssetFace.person_id.is_(None),
            AssetFace.compreface_subject.isnot(None),
        )
        .order_by(
            AssetFace.compreface_similarity.desc().nulls_last(),
            AssetFace.created_at.desc(),
        )
        .all()
    )

    return [
        _build_event_face_response(face)
        for face in candidate_faces
        if (face.compreface_subject or "").strip().casefold() in subject_candidates
    ]


@app.post("/api/people", response_model=DirectoryEntryResponse)
def create_person(
    body: CreateDirectoryEntryRequest, db: Session = Depends(get_db)
) -> DirectoryEntryResponse:
    person = get_or_create_person(db, body.name)
    if not person:
        raise HTTPException(status_code=400, detail="Person name is required")
    db.commit()
    return build_directory_response(person.name, person.id, 0)


@app.patch("/api/people/{person_id}", response_model=DirectoryEntryResponse)
def rename_person(
    person_id: int,
    body: UpdateDirectoryEntryRequest,
    db: Session = Depends(get_db),
) -> DirectoryEntryResponse:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    name = normalize_directory_name(body.name)
    if not name:
        raise HTTPException(status_code=400, detail="Person name is required")

    for existing in db.query(Person).all():
        if existing.id != person.id and existing.name.casefold() == name.casefold():
            raise HTTPException(status_code=409, detail="Person name already exists")

    person.name = name

    # Sync CompreFace subject name if this person has one
    if person.compreface_subject_id:
        from app.services.faces import rename_compreface_subject

        try:
            rename_compreface_subject(person.compreface_subject_id, name)
        except Exception as exc:
            logger.warning(
                "Failed to rename CompreFace subject %s: %s",
                person.compreface_subject_id,
                exc,
            )

    for memory in db.query(MemoryEntry).all():
        if memory.recorder_person_id == person.id:
            memory.recorder_name = person.name
        if any(link.person_id == person.id for link in memory.people_links):
            memory.people_json = json.dumps(memory.referenced_people)

    db.commit()
    return build_directory_response(
        person.name,
        person.id,
        len(
            {
                memory.id
                for memory in db.query(MemoryEntry).all()
                if memory.recorder_person_id == person.id
                or any(link.person_id == person.id for link in memory.people_links)
            }
        ),
    )


@app.post("/api/people/{person_id}/merge", response_model=DirectoryEntryResponse)
def merge_person(
    person_id: int,
    body: MergePersonRequest,
    db: Session = Depends(get_db),
) -> DirectoryEntryResponse:
    source = db.get(Person, person_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source person not found")

    target = db.get(Person, body.into_person_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target person not found")

    if source.id == target.id:
        raise HTTPException(
            status_code=400, detail="Cannot merge a person into themselves"
        )

    merge_people_records(db, source, target)
    db.delete(source)
    db.commit()
    db.refresh(target)

    updated = next((p for p in list_people_directory(db) if p.id == target.id), None)
    if updated:
        return updated
    return build_directory_response(target.name, target.id, 0)


@app.post(
    "/api/people/{person_id}/link-compreface", response_model=DirectoryEntryResponse
)
def link_person_compreface(
    person_id: int,
    body: LinkPersonComprefaceRequest,
    db: Session = Depends(get_db),
) -> DirectoryEntryResponse:
    try:
        person = link_person_to_existing_compreface_subject(
            db, person_id, body.subject_name
        )
    except ValueError as exc:
        code = str(exc)
        if code == "person_not_found":
            raise HTTPException(status_code=404, detail="Person not found") from exc
        if code == "subject_not_found":
            raise HTTPException(
                status_code=404, detail="No matching CompreFace subject found"
            ) from exc
        if code == "subject_already_linked":
            raise HTTPException(
                status_code=409,
                detail="CompreFace subject is already linked to another person",
            ) from exc
        raise HTTPException(
            status_code=400, detail="Could not link person to CompreFace"
        ) from exc

    db.commit()
    db.refresh(person)

    updated = next((p for p in list_people_directory(db) if p.id == person.id), None)
    if updated:
        return updated
    return build_directory_response(person.name, person.id, 0)


@app.post("/api/people/{person_id}/split", response_model=list[DirectoryEntryResponse])
def split_person(
    person_id: int,
    body: SplitPersonRequest,
    db: Session = Depends(get_db),
) -> list[DirectoryEntryResponse]:
    source = db.get(Person, person_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source person not found")

    new_names = [normalize_directory_name(n) for n in body.new_names]
    new_names = [n for n in new_names if n]
    if not new_names:
        raise HTTPException(status_code=400, detail="At least one new name is required")

    source_name = source.name

    # Create (or locate) each new person
    new_people: list[Person] = []
    for name in new_names:
        p = get_or_create_person(db, name)
        if p:
            new_people.append(p)
    db.flush()

    # Reassign memory links from source to all new people
    for memory in db.query(MemoryEntry).all():
        if memory.recorder_person_id == source.id:
            # Recorder is ambiguous after split — clear it
            memory.recorder_person = None
            memory.recorder_person_id = None
            memory.recorder_name = None

        has_source_link = any(
            link.person_id == source.id for link in memory.people_links
        )
        if has_source_link:
            for link in list(memory.people_links):
                if link.person_id == source.id:
                    memory.people_links.remove(link)
                    db.delete(link)
            for new_person in new_people:
                already_linked = any(
                    link.person_id == new_person.id for link in memory.people_links
                )
                if not already_linked:
                    memory.people_links.append(
                        MemoryPerson(person_id=new_person.id, role="mentioned")
                    )
            memory.people_json = json.dumps(memory.referenced_people)

    # Add the old name as an alias on each new person
    if body.keep_alias:
        for new_person in new_people:
            already_has_alias = any(
                a.alias.casefold() == source_name.casefold() for a in new_person.aliases
            )
            if not already_has_alias:
                db.add(PersonAlias(person_id=new_person.id, alias=source_name))

    detach_person_compreface_link(db, source)

    db.delete(source)
    db.commit()

    return list_people_directory(db)


@app.post("/api/people/{person_id}/aliases", response_model=DirectoryEntryResponse)
def add_person_alias(
    person_id: int,
    body: AddAliasRequest,
    db: Session = Depends(get_db),
) -> DirectoryEntryResponse:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    alias = normalize_directory_name(body.alias)
    if not alias:
        raise HTTPException(status_code=400, detail="Alias text is required")

    # Check alias isn't already a person name
    for p in db.query(Person).all():
        if p.id != person_id and p.name.casefold() == alias.casefold():
            raise HTTPException(
                status_code=409, detail="That name belongs to another person"
            )

    # Check not already present for this person
    if any(a.alias.casefold() == alias.casefold() for a in person.aliases):
        db.commit()  # no-op, just return current state
    else:
        db.add(PersonAlias(person_id=person_id, alias=alias))
        db.commit()
        db.refresh(person)

    directory = list_people_directory(db)
    entry = next((e for e in directory if e.id == person_id), None)
    return entry or build_directory_response(person.name, person.id, 0)


@app.delete("/api/people/{person_id}/aliases/{alias}")
def remove_person_alias(
    person_id: int,
    alias: str,
    db: Session = Depends(get_db),
) -> dict:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    row = next(
        (a for a in person.aliases if a.alias.casefold() == alias.casefold()),
        None,
    )
    if row:
        db.delete(row)
        db.commit()

    return {"status": "deleted", "alias": alias, "person_id": person_id}


@app.delete("/api/people/{person_id}")
def delete_person(person_id: int, db: Session = Depends(get_db)) -> dict:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    for memory in db.query(MemoryEntry).all():
        if memory.recorder_person_id == person.id:
            memory.recorder_person = None
            memory.recorder_person_id = None
            memory.recorder_name = None

        removed = False
        for link in list(memory.people_links):
            if link.person_id == person.id:
                memory.people_links.remove(link)
                db.delete(link)
                removed = True
        if removed:
            update_memory_json_from_links(memory)

    detach_person_compreface_link(db, person)

    db.delete(person)
    db.commit()
    return {"status": "deleted", "person_id": person_id}


@app.get("/api/compreface/subjects", response_model=list[str])
def list_compreface_subjects_endpoint() -> list[str]:
    """List all available CompreFace subjects for linking to people."""
    from app.services.faces import list_compreface_subjects

    subjects = list_compreface_subjects()
    return [name for name, _ in subjects]


@app.get("/api/places", response_model=list[DirectoryEntryResponse])
def list_places(db: Session = Depends(get_db)) -> list[DirectoryEntryResponse]:
    return list_places_directory(db)


@app.post("/api/places", response_model=DirectoryEntryResponse)
def create_place(
    body: CreateDirectoryEntryRequest, db: Session = Depends(get_db)
) -> DirectoryEntryResponse:
    place = get_or_create_place(db, body.name)
    if not place:
        raise HTTPException(status_code=400, detail="Place name is required")
    db.commit()
    return build_directory_response(place.name, place.id, 0)


@app.patch("/api/places/{place_id}", response_model=DirectoryEntryResponse)
def rename_place(
    place_id: int,
    body: UpdateDirectoryEntryRequest,
    db: Session = Depends(get_db),
) -> DirectoryEntryResponse:
    place = db.get(Place, place_id)
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    name = normalize_directory_name(body.name)
    if not name:
        raise HTTPException(status_code=400, detail="Place name is required")

    for existing in db.query(Place).all():
        if existing.id != place.id and existing.name.casefold() == name.casefold():
            raise HTTPException(status_code=409, detail="Place name already exists")

    place.name = name
    for memory in db.query(MemoryEntry).all():
        if any(link.place_id == place.id for link in memory.place_links):
            memory.locations_json = json.dumps(memory.referenced_locations)

    db.commit()
    return build_directory_response(
        place.name,
        place.id,
        len(
            {
                memory.id
                for memory in db.query(MemoryEntry).all()
                if any(link.place_id == place.id for link in memory.place_links)
            }
        ),
    )


@app.delete("/api/places/{place_id}")
def delete_place(place_id: int, db: Session = Depends(get_db)) -> dict:
    place = db.get(Place, place_id)
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    for memory in db.query(MemoryEntry).all():
        removed = False
        for link in list(memory.place_links):
            if link.place_id == place.id:
                memory.place_links.remove(link)
                db.delete(link)
                removed = True
        if removed:
            update_memory_json_from_links(memory)

    db.delete(place)
    db.commit()
    return {"status": "deleted", "place_id": place_id}


@app.get("/api/memories/{memory_id}/audio")
def get_memory_audio(memory_id: int, db: Session = Depends(get_db)) -> FileResponse:
    memory = db.get(MemoryEntry, memory_id)
    if not memory or not memory.audio_filename:
        raise HTTPException(status_code=404, detail="Audio not found")

    file_path = AUDIO_STORAGE_DIR / memory.audio_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file missing from storage")

    return FileResponse(
        path=file_path,
        media_type=(memory.audio_content_type or "application/octet-stream"),
        filename=memory.audio_filename,
    )


@app.get("/api/memories/{memory_id}/document")
def get_memory_document(
    memory_id: int, download: bool = False, db: Session = Depends(get_db)
) -> FileResponse:
    memory = db.get(MemoryEntry, memory_id)
    if not memory or not memory.document_filename:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = DOCUMENT_STORAGE_DIR / memory.document_filename
    if not file_path.exists():
        raise HTTPException(
            status_code=404, detail="Document file missing from storage"
        )

    filename = memory.document_original_filename or memory.document_filename
    disposition = "attachment" if download else "inline"
    return FileResponse(
        path=file_path,
        media_type=(memory.document_content_type or "application/octet-stream"),
        filename=filename,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@app.post("/api/memories", response_model=MemoryResponse)
async def create_memory(
    audio: UploadFile = File(...),
    event_id: Optional[int] = Form(None),
    related_asset_id: Optional[int] = Form(None),
    quick_capture: bool = Form(False),
    db: Session = Depends(get_db),
) -> MemoryEntry:
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio payload is empty")

    audio_filename, audio_content_type, audio_size_bytes, mp3_bytes = save_audio_file(
        audio, audio_bytes, AUDIO_STORAGE_DIR
    )

    related_asset: Optional[Asset] = None
    if related_asset_id is not None:
        related_asset = db.get(Asset, related_asset_id)
        if not related_asset:
            raise HTTPException(status_code=404, detail="Related asset not found")
        content_type = (related_asset.content_type or "").lower()
        if related_asset.kind != "photo" and not content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Related asset must be a photo")
        if event_id is None:
            raise HTTPException(
                status_code=400,
                detail="event_id is required when related_asset_id is provided",
            )

    transcription_enabled = os.getenv("TRANSCRIPTION_ENABLED", "true").lower() == "true"

    (
        transcript,
        event_description,
        estimated_date_sort,
        estimated_date_text,
        emotional_tone,
        follow_up_question,
        metadata,
    ) = analyze_memory_audio(audio_filename, mp3_bytes, transcription_enabled)
    parsed_memory_start, parsed_memory_end = parse_text_date_range(estimated_date_text)
    if parsed_memory_start is not None and parsed_memory_end is None:
        parsed_memory_end = parsed_memory_start

    entry = MemoryEntry(
        transcript=transcript,
        event_description=event_description,
        estimated_date_text=estimated_date_text,
        estimated_date_sort=estimated_date_sort or parsed_memory_start,
        estimated_end_date_sort=parsed_memory_end,
        date_recorded=date.today(),
        date_precision=metadata.date_precision,
        date_year=metadata.date_year,
        date_month=metadata.date_month,
        date_day=metadata.date_day,
        date_decade=metadata.date_decade,
        recorder_name=metadata.recorder_name,
        people_json=json.dumps(metadata.people),
        locations_json=json.dumps(metadata.locations),
        emotional_tone=emotional_tone,
        follow_up_question=follow_up_question,
        audio_filename=audio_filename,
        audio_content_type=audio_content_type,
        audio_size_bytes=audio_size_bytes,
    )
    db.add(entry)
    db.flush()
    assign_recorder_person(db, entry, metadata.recorder_name)
    sync_memory_people(db, entry, metadata.people)
    sync_memory_places(db, entry, metadata.locations)

    if event_id is not None:
        # Narration is being recorded directly for a specific event.
        # Skip sync_life_hierarchy_for_memory (which would create an unwanted
        # second event) and instead create the audio asset + link it manually.
        target_event = db.query(LifeEvent).filter(LifeEvent.id == event_id).first()
        if not target_event:
            raise HTTPException(status_code=404, detail="Event not found")

        if related_asset:
            ensure_event_asset_link(
                db, target_event, related_asset, relation_type="evidence"
            )
            related_asset.legacy_memory_id = entry.id
        else:
            conflicting_asset = (
                db.query(Asset).filter(Asset.legacy_memory_id == entry.id).first()
            )
            if conflicting_asset and conflicting_asset.kind != "audio":
                conflicting_asset.legacy_memory_id = None
                db.flush()

            audio_asset = (
                db.query(Asset)
                .filter(Asset.legacy_memory_id == entry.id, Asset.kind == "audio")
                .first()
            )
            if not audio_asset:
                audio_asset = Asset(
                    period_id=target_event.period_id,
                    kind="audio",
                    title=derive_asset_title(audio_filename),
                    storage_filename=audio_filename,
                    original_filename=audio_filename,
                    content_type=audio_content_type,
                    size_bytes=audio_size_bytes,
                    text_excerpt=(transcript or "").strip()[:1200] or None,
                    notes=f"Audio narration for event: {target_event.title}",
                    legacy_memory_id=entry.id,
                )
                db.add(audio_asset)
                db.flush()
            ensure_event_asset_link(
                db, target_event, audio_asset, relation_type="recording"
            )
    else:
        sync_life_hierarchy_for_memory(db, entry)
        auto_event = (
            db.query(LifeEvent).filter(LifeEvent.legacy_memory_id == entry.id).first()
        )
        if auto_event:
            refresh_event_summary_and_suggestion(db, auto_event, auto_apply_title=True)

    db.commit()
    db.refresh(entry)

    if transcription_enabled and transcript not in (
        "Transcription failed.",
        "Transcription disabled.",
    ):
        try:
            add_unique_pending_questions(
                db,
                _generate_questions(transcript, event_description, metadata),
                entry.id,
            )
            db.commit()
        except Exception as exc:
            logger.warning(
                "Could not generate questions for memory %s: %s", entry.id, exc
            )

    return entry


SUPPORTED_DOCUMENT_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
    "text/plain",
}

_EXTENSION_TO_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".txt": "text/plain",
}


@app.post("/api/memories/document", response_model=MemoryResponse)
async def create_memory_from_document(
    file: UploadFile = File(...),
    event_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
) -> MemoryEntry:
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Document file is empty")

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in SUPPORTED_DOCUMENT_MIME_TYPES:
        ext = Path(file.filename or "").suffix.lower()
        content_type = _EXTENSION_TO_MIME.get(ext, content_type)

    if content_type not in SUPPORTED_DOCUMENT_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{content_type}'. "
                "Supported: PDF, JPEG, PNG, GIF, WEBP, TXT"
            ),
        )

    transcript = extract_text_from_document(
        file.filename or "document", file_bytes, content_type
    )

    (
        document_filename,
        document_content_type,
        document_size_bytes,
        document_original_filename,
    ) = save_document_file(file, file_bytes, DOCUMENT_STORAGE_DIR)

    metadata = extract_metadata_with_gemini_function_call(transcript)
    if metadata is None:
        metadata = fallback_metadata_from_transcript(transcript)

    emotional_tone = "neutral"
    event_description = f"Document analysis: {document_original_filename}"
    follow_up_question = (
        "What additional factual details should be captured from this document?"
    )

    document_start, document_end = parse_text_date_range(metadata.date_text)
    if document_start is not None and document_end is None:
        document_end = document_start

    entry = MemoryEntry(
        transcript=transcript,
        event_description=event_description,
        estimated_date_text=metadata.date_text,
        estimated_date_sort=metadata.sort_date or document_start,
        estimated_end_date_sort=document_end,
        date_recorded=date.today(),
        date_precision=metadata.date_precision,
        date_year=metadata.date_year,
        date_month=metadata.date_month,
        date_day=metadata.date_day,
        date_decade=metadata.date_decade,
        recorder_name=metadata.recorder_name,
        people_json=json.dumps(metadata.people),
        locations_json=json.dumps(metadata.locations),
        emotional_tone=emotional_tone,
        follow_up_question=follow_up_question,
        audio_filename=None,
        audio_content_type=None,
        audio_size_bytes=None,
        document_filename=document_filename,
        document_original_filename=document_original_filename,
        document_content_type=document_content_type,
        document_size_bytes=document_size_bytes,
    )
    db.add(entry)
    db.flush()
    assign_recorder_person(db, entry, metadata.recorder_name)
    sync_memory_people(db, entry, metadata.people)
    sync_memory_places(db, entry, metadata.locations)

    if event_id is not None:
        target_event = db.query(LifeEvent).filter(LifeEvent.id == event_id).first()
        if not target_event:
            raise HTTPException(status_code=404, detail="Event not found")

        asset_kind = (
            "photo"
            if (document_content_type or "").startswith("image/")
            else "document"
        )
        conflicting_asset = (
            db.query(Asset).filter(Asset.legacy_memory_id == entry.id).first()
        )
        if conflicting_asset and conflicting_asset.kind != asset_kind:
            conflicting_asset.legacy_memory_id = None
            db.flush()

        document_asset = Asset(
            period_id=target_event.period_id,
            kind=asset_kind,
            title=derive_asset_title(document_original_filename or ""),
            storage_filename=document_filename,
            original_filename=document_original_filename,
            content_type=document_content_type,
            size_bytes=document_size_bytes,
            text_excerpt=(transcript or "").strip()[:1200] or None,
            notes=f"Uploaded to event: {target_event.title}",
            legacy_memory_id=entry.id,
        )
        db.add(document_asset)
        db.flush()
        if asset_kind == "photo" and document_filename:
            doc_path = DOCUMENT_STORAGE_DIR / document_filename
            if doc_path.exists():
                try:
                    extract_and_apply_image_metadata(
                        document_asset, doc_path.read_bytes(), document_content_type
                    )
                except Exception:
                    pass
        ensure_event_asset_link(db, target_event, document_asset)
        if target_event.legacy_memory_id is None:
            target_event.legacy_memory_id = entry.id
    else:
        sync_life_hierarchy_for_memory(db, entry)

    db.commit()
    db.refresh(entry)

    return entry


@app.post("/api/memories/{memory_id}/reanalyze", response_model=MemoryResponse)
def reanalyze_memory(memory_id: int, db: Session = Depends(get_db)) -> MemoryEntry:
    memory = db.get(MemoryEntry, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    # --- Document memory reanalysis ---
    if memory.document_filename and not memory.audio_filename:
        file_path = DOCUMENT_STORAGE_DIR / memory.document_filename
        if not file_path.exists():
            raise HTTPException(
                status_code=404, detail="Document file missing from storage"
            )

        file_bytes = file_path.read_bytes()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Stored document is empty")

        content_type = memory.document_content_type or "application/octet-stream"
        transcript = extract_text_from_document(
            memory.document_original_filename or memory.document_filename,
            file_bytes,
            content_type,
        )

        metadata = extract_metadata_with_gemini_function_call(transcript)
        if metadata is None:
            metadata = fallback_metadata_from_transcript(transcript)

        memory.transcript = transcript
        memory.estimated_date_text = metadata.date_text
        parsed_memory_start, parsed_memory_end = parse_text_date_range(
            memory.estimated_date_text
        )
        if parsed_memory_start is not None and parsed_memory_end is None:
            parsed_memory_end = parsed_memory_start
        memory.estimated_date_sort = metadata.sort_date or parsed_memory_start
        memory.estimated_end_date_sort = parsed_memory_end
        memory.date_precision = metadata.date_precision
        memory.date_year = metadata.date_year
        memory.date_month = metadata.date_month
        memory.date_day = metadata.date_day
        memory.date_decade = metadata.date_decade
        memory.people_json = json.dumps(metadata.people)
        memory.locations_json = json.dumps(metadata.locations)
        memory.research_summary = None
        memory.research_sources_json = None
        memory.research_queries_json = None
        if not memory.recorder_person_id and not memory.recorder_name:
            assign_recorder_person(db, memory, metadata.recorder_name)
        sync_memory_people(db, memory, metadata.people)
        sync_memory_places(db, memory, metadata.locations)
        sync_life_hierarchy_for_memory(db, memory)

        db.commit()
        db.refresh(memory)
        return memory

    # --- Audio memory reanalysis ---
    if not memory.audio_filename:
        raise HTTPException(
            status_code=400,
            detail="Memory has no stored audio or document to reanalyze",
        )

    file_path = AUDIO_STORAGE_DIR / memory.audio_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file missing from storage")

    mp3_bytes = file_path.read_bytes()
    if not mp3_bytes:
        raise HTTPException(status_code=400, detail="Stored audio is empty")

    transcription_enabled = os.getenv("TRANSCRIPTION_ENABLED", "true").lower() == "true"
    (
        transcript,
        event_description,
        estimated_date_sort,
        estimated_date_text,
        emotional_tone,
        follow_up_question,
        metadata,
    ) = analyze_memory_audio(memory.audio_filename, mp3_bytes, transcription_enabled)

    memory.transcript = transcript
    memory.event_description = event_description
    memory.estimated_date_text = estimated_date_text
    parsed_memory_start, parsed_memory_end = parse_text_date_range(
        memory.estimated_date_text
    )
    if parsed_memory_start is not None and parsed_memory_end is None:
        parsed_memory_end = parsed_memory_start
    memory.estimated_date_sort = estimated_date_sort or parsed_memory_start
    memory.estimated_end_date_sort = parsed_memory_end
    memory.emotional_tone = emotional_tone
    memory.follow_up_question = follow_up_question
    memory.research_summary = None
    memory.research_sources_json = None
    memory.research_queries_json = None
    memory.date_precision = metadata.date_precision
    memory.date_year = metadata.date_year
    memory.date_month = metadata.date_month
    memory.date_day = metadata.date_day
    memory.date_decade = metadata.date_decade
    if not memory.recorder_person_id and not memory.recorder_name:
        assign_recorder_person(db, memory, metadata.recorder_name)
    sync_memory_people(db, memory, metadata.people)
    sync_memory_places(db, memory, metadata.locations)

    db.query(Question).filter(
        Question.source_memory_id == memory.id,
        Question.status == "pending",
    ).delete(synchronize_session=False)

    if transcription_enabled and transcript not in (
        "Transcription failed.",
        "Transcription disabled.",
    ):
        add_unique_pending_questions(
            db,
            _generate_questions(transcript, event_description, metadata),
            memory.id,
        )

    db.commit()
    db.refresh(memory)
    return memory


@app.post("/api/memories/{memory_id}/research", response_model=MemoryResponse)
def research_memory(memory_id: int, db: Session = Depends(get_db)) -> MemoryEntry:
    memory = db.get(MemoryEntry, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    research_memory_entry(memory, DOCUMENT_STORAGE_DIR)

    db.commit()
    db.refresh(memory)

    # Extract follow-up questions from the 'Questions worth exploring' section
    # already present in the research summary, rather than making a redundant Gemini call
    follow_up_questions = extract_questions_from_research(memory.research_summary or "")
    logger.info(
        "Extracted %d questions from research summary", len(follow_up_questions)
    )
    for question_text in follow_up_questions:
        logger.info("Adding question: %s", question_text[:80])
        db.add(
            Question(text=question_text, source_memory_id=memory_id, status="pending")
        )
    db.commit()

    return memory


@app.post(
    "/api/memories/{memory_id}/apply-research-suggestion", response_model=MemoryResponse
)
def apply_research_suggestion(
    memory_id: int, db: Session = Depends(get_db)
) -> MemoryEntry:
    memory = db.get(MemoryEntry, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    if not memory.research_suggested_metadata_json:
        raise HTTPException(status_code=404, detail="No pending suggestion")

    suggestion = json.loads(memory.research_suggested_metadata_json)
    memory.estimated_date_text = (
        suggestion.get("estimated_date_text") or memory.estimated_date_text
    )
    memory.date_precision = suggestion.get("date_precision") or memory.date_precision
    memory.date_year = suggestion.get("date_year")
    memory.date_month = suggestion.get("date_month")
    memory.date_day = suggestion.get("date_day")
    memory.date_decade = suggestion.get("date_decade")
    parsed_memory_start, parsed_memory_end = parse_text_date_range(
        memory.estimated_date_text
    )
    if parsed_memory_start is not None and parsed_memory_end is None:
        parsed_memory_end = parsed_memory_start
    memory.estimated_date_sort = (
        build_sort_date(
            memory.date_precision,
            memory.date_year,
            memory.date_month,
            memory.date_day,
            memory.date_decade,
        )
        or parsed_memory_start
    )
    memory.estimated_end_date_sort = parsed_memory_end
    memory.research_suggested_metadata_json = None
    db.commit()
    db.refresh(memory)
    return memory


@app.post(
    "/api/memories/{memory_id}/dismiss-research-suggestion",
    response_model=MemoryResponse,
)
def dismiss_research_suggestion(
    memory_id: int, db: Session = Depends(get_db)
) -> MemoryEntry:
    memory = db.get(MemoryEntry, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    memory.research_suggested_metadata_json = None
    db.commit()
    db.refresh(memory)
    return memory


@app.patch("/api/memories/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: int, body: UpdateMemoryRequest, db: Session = Depends(get_db)
) -> MemoryEntry:
    memory = db.get(MemoryEntry, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    if "event_description" in body.model_fields_set:
        next_value = (body.event_description or "").strip()
        if not next_value:
            raise HTTPException(status_code=400, detail="Memory title cannot be empty")
        memory.event_description = next_value[:240]

    if "estimated_date_text" in body.model_fields_set:
        memory.estimated_date_text = clean_date_text(body.estimated_date_text)
        parsed_memory_start, parsed_memory_end = parse_text_date_range(
            memory.estimated_date_text
        )
        if parsed_memory_start is not None and parsed_memory_end is None:
            parsed_memory_end = parsed_memory_start
        memory.estimated_date_sort = parsed_memory_start
        memory.estimated_end_date_sort = parsed_memory_end
        # Date edits should immediately propagate to linked life hierarchy records.
        sync_life_hierarchy_for_memory(db, memory)

    db.commit()
    db.refresh(memory)
    return memory


@app.patch("/api/memories/{memory_id}/recorder", response_model=MemoryResponse)
def update_memory_recorder(
    memory_id: int,
    body: UpdateMemoryRecorderRequest = Body(...),
    db: Session = Depends(get_db),
) -> MemoryEntry:
    memory = db.get(MemoryEntry, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    if body.person_id is not None:
        person = db.get(Person, body.person_id)
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        assign_recorder_person(db, memory, person.name)
    else:
        assign_recorder_person(db, memory, body.recorder_name)

    db.commit()
    db.refresh(memory)
    return memory


@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: int, db: Session = Depends(get_db)) -> dict:
    memory = db.get(MemoryEntry, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    file_path = (
        AUDIO_STORAGE_DIR / memory.audio_filename if memory.audio_filename else None
    )
    document_path = (
        DOCUMENT_STORAGE_DIR / memory.document_filename
        if memory.document_filename
        else None
    )
    db.query(Question).filter(Question.source_memory_id == memory.id).delete(
        synchronize_session=False
    )
    db.query(Question).filter(Question.answer_memory_id == memory.id).update(
        {Question.answer_memory_id: None},
        synchronize_session=False,
    )
    db.query(MemoryPerson).filter(MemoryPerson.memory_id == memory.id).delete(
        synchronize_session=False
    )
    db.query(MemoryPlace).filter(MemoryPlace.memory_id == memory.id).delete(
        synchronize_session=False
    )
    db.delete(memory)
    db.commit()

    if file_path and file_path.exists():
        try:
            file_path.unlink()
        except OSError:
            logger.warning("Could not delete audio file for memory %s", memory_id)

    if document_path and document_path.exists():
        try:
            document_path.unlink()
        except OSError:
            logger.warning("Could not delete document file for memory %s", memory_id)

    return {"status": "deleted", "memory_id": memory_id}


@app.get("/api/questions", response_model=list[QuestionResponse])
def list_questions(db: Session = Depends(get_db)) -> list[Question]:
    pending = (
        db.query(Question)
        .filter(Question.status == "pending")
        .order_by(Question.created_at.asc())
        .all()
    )

    deduped: list[Question] = []
    seen: set[str] = set()
    for question in pending:
        normalized = normalize_question_text(question.text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(question)

    return deduped


@app.post("/api/questions/{question_id}/answer")
def answer_question(
    question_id: int,
    body: AnswerQuestionRequest,
    db: Session = Depends(get_db),
) -> dict:
    question = db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    memory: Optional[MemoryEntry] = None
    if body.answer_memory_id is not None:
        memory = db.get(MemoryEntry, body.answer_memory_id)
        if not memory:
            raise HTTPException(status_code=404, detail="Answer memory not found")

    question.status = "answered"
    question.answer_memory_id = body.answer_memory_id
    if memory:
        memory.response_to_question_id = question.id
        memory.response_to_question_text = question.text
    db.commit()
    return {"status": "answered"}


@app.post("/api/questions/{question_id}/dismiss")
def dismiss_question(question_id: int, db: Session = Depends(get_db)) -> dict:
    question = db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    question.status = "dismissed"
    db.commit()
    return {"status": "dismissed"}


_ALLOWED_SETTING_KEYS = {"main_character_name"}


@app.get("/api/settings", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db)) -> SettingsResponse:
    rows = db.query(Setting).all()
    mapping = {row.key: row.value for row in rows}
    return SettingsResponse(main_character_name=mapping.get("main_character_name"))


@app.put("/api/settings/{key}")
def update_setting(
    key: str,
    body: UpdateSettingRequest,
    db: Session = Depends(get_db),
) -> dict:
    if key not in _ALLOWED_SETTING_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown setting key: {key}")
    setting = db.get(Setting, key)
    if setting:
        setting.value = body.value
        setting.updated_at = datetime.utcnow()
    else:
        db.add(Setting(key=key, value=body.value))
    db.commit()
    return {"key": key, "value": body.value}
