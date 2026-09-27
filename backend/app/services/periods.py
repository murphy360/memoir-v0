import re
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    Asset,
    EventAsset,
    LifeEpic,
    LifeEvent,
    LifePeriod,
    LifeThread,
    MemoryEntry,
)
from app.schemas import (
    AssetResponse,
    LifeEpicResponse,
    LifeEventResponse,
    LifePeriodAnalysisResponse,
    LifePeriodResponse,
    LifeThreadResponse,
    UpdateLifeEpicRequest,
    UpdateLifeEventRequest,
    UpdateLifePeriodRequest,
)
from app.services.date_normalization import (
    clean_date_text,
    parse_text_date_range,
    resolve_start_end_dates,
)
from app.services.gemini_client import generate_period_biography


def normalize_directory_name(value: Optional[str]) -> Optional[str]:
    candidate = (value or "").strip()
    if not candidate:
        return None
    if len(candidate) > 120:
        candidate = candidate[:120].rstrip()
    return candidate


def normalize_period_title(value: Optional[str]) -> Optional[str]:
    title = normalize_directory_name(value)
    if not title:
        return None
    if len(title) > 160:
        title = title[:160].rstrip()
    return title


def slugify_period_title(value: str) -> str:
    compact = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return compact[:180] or "period"


def unique_period_slug(
    db: Session, title: str, existing_id: Optional[int] = None
) -> str:
    base = slugify_period_title(title)
    candidate = base
    suffix = 2
    while True:
        match = db.query(LifePeriod).filter(LifePeriod.slug == candidate).first()
        if not match or (existing_id is not None and match.id == existing_id):
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


def unique_thread_slug(
    db: Session, title: str, existing_id: Optional[int] = None
) -> str:
    base = slugify_period_title(title)
    candidate = base
    suffix = 2
    while True:
        match = db.query(LifeThread).filter(LifeThread.slug == candidate).first()
        if not match or (existing_id is not None and match.id == existing_id):
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


def apply_period_updates(
    db: Session, period: LifePeriod, body: UpdateLifePeriodRequest
) -> None:
    """Apply mutable period fields, including normalized date sort bounds."""
    if body.title is not None:
        clean_title = normalize_period_title(body.title)
        if not clean_title:
            raise HTTPException(status_code=400, detail="Period title cannot be empty")
        period.title = clean_title
        period.slug = unique_period_slug(db, clean_title, existing_id=period.id)

    if body.start_date_text is not None:
        period.start_date_text = clean_date_text(body.start_date_text)

    if body.end_date_text is not None:
        period.end_date_text = clean_date_text(body.end_date_text)

    period.start_sort, period.end_sort = resolve_start_end_dates(
        period.start_date_text, period.end_date_text
    )


def apply_epic_updates(
    db: Session, epic: LifeEpic, body: UpdateLifeEpicRequest
) -> None:
    """Apply epic edits and keep epic/event period alignment intact."""
    previous_period_id = epic.period_id

    if body.title is not None:
        clean_title = normalize_directory_name(body.title)
        if not clean_title:
            raise HTTPException(status_code=400, detail="Epic title cannot be empty")
        epic.title = clean_title

    if "thread_id" in body.model_fields_set:
        if body.thread_id is not None and not db.get(LifeThread, body.thread_id):
            raise HTTPException(status_code=404, detail="Thread not found")
        epic.thread_id = body.thread_id

    if "period_id" in body.model_fields_set:
        if body.period_id is None:
            raise HTTPException(status_code=400, detail="Epic period cannot be cleared")
        target_period = db.get(LifePeriod, body.period_id)
        if not target_period:
            raise HTTPException(status_code=404, detail="Target period not found")
        epic.period_id = body.period_id
        db.query(LifeEvent).filter(LifeEvent.epic_id == epic.id).update(
            {"period_id": body.period_id}
        )

    if "description" in body.model_fields_set:
        epic.description = (body.description or "").strip()[:2000] or None

    if body.weight is not None:
        epic.weight = body.weight

    if "start_date_text" in body.model_fields_set:
        epic.start_date_text = clean_date_text(body.start_date_text)

    if "end_date_text" in body.model_fields_set:
        epic.end_date_text = clean_date_text(body.end_date_text)

    epic.start_sort, epic.end_sort = resolve_start_end_dates(
        epic.start_date_text, epic.end_date_text
    )

    if epic.period_id != previous_period_id:
        if previous_period_id is not None:
            refresh_period_summary(db, db.get(LifePeriod, previous_period_id))
        refresh_period_summary(db, db.get(LifePeriod, epic.period_id))


def apply_event_updates(
    db: Session, event: LifeEvent, body: UpdateLifeEventRequest
) -> None:
    """Apply event edits and enforce valid period/epic relationships for move operations."""
    previous_period_id = event.period_id

    if body.title is not None:
        clean_title = body.title.strip()
        if not clean_title:
            raise HTTPException(status_code=400, detail="Event title cannot be empty")
        event.title = clean_title

    if "description" in body.model_fields_set:
        event.description = (body.description or "").strip()[:1200] or None

    if "location" in body.model_fields_set:
        event.location = (body.location or "").strip()[:255] or None

    if "event_date_text" in body.model_fields_set:
        event.event_date_text = clean_date_text(body.event_date_text) or None
        parsed_start, parsed_end = parse_text_date_range(event.event_date_text)
        if parsed_start is not None and parsed_end is None:
            parsed_end = parsed_start
        event.event_date_sort = parsed_start
        event.event_end_date_sort = parsed_end

    next_period_id = event.period_id
    next_epic_id = event.epic_id

    if "period_id" in body.model_fields_set:
        next_period_id = body.period_id
    if "epic_id" in body.model_fields_set:
        next_epic_id = body.epic_id

    if next_epic_id is not None:
        resolved_epic = db.get(LifeEpic, next_epic_id)
        if not resolved_epic:
            raise HTTPException(status_code=404, detail="Epic not found")
        if next_period_id is not None and resolved_epic.period_id != next_period_id:
            raise HTTPException(
                status_code=400, detail="Epic does not belong to the provided period"
            )
        next_period_id = resolved_epic.period_id

    if next_period_id is not None and not db.get(LifePeriod, next_period_id):
        raise HTTPException(status_code=404, detail="Target period not found")
    if next_period_id is None:
        raise HTTPException(
            status_code=400, detail="Event requires period_id or epic_id"
        )

    event.period_id = next_period_id
    event.epic_id = next_epic_id

    if "thread_id" in body.model_fields_set:
        if body.thread_id is not None and not db.get(LifeThread, body.thread_id):
            raise HTTPException(status_code=404, detail="Thread not found")
        event.thread_id = body.thread_id

    if body.weight is not None:
        event.weight = body.weight

    if event.period_id != previous_period_id:
        refresh_period_summary(
            db,
            db.get(LifePeriod, previous_period_id)
            if previous_period_id is not None
            else None,
        )
        refresh_period_summary(
            db,
            db.get(LifePeriod, event.period_id)
            if event.period_id is not None
            else None,
        )


def period_asset_count_from_events(events: list[LifeEvent]) -> int:
    """Count unique assets linked through events in the period."""
    asset_ids: set[int] = set()
    for event in events:
        for link in event.linked_assets:
            if link.asset_id is not None:
                asset_ids.add(link.asset_id)
    return len(asset_ids)


def build_period_response(period: LifePeriod) -> LifePeriodResponse:
    event_count = len(period.events)
    epic_count = len(period.epics)
    asset_count = period_asset_count_from_events(period.events)
    return LifePeriodResponse(
        id=period.id,
        title=period.title,
        slug=period.slug,
        start_date_text=period.start_date_text,
        end_date_text=period.end_date_text,
        start_sort=period.start_sort,
        end_sort=period.end_sort,
        summary=period.summary,
        event_count=event_count,
        epic_count=epic_count,
        asset_count=asset_count,
        created_at=period.created_at,
        updated_at=period.updated_at,
    )


def build_thread_response(thread: LifeThread) -> LifeThreadResponse:
    return LifeThreadResponse(
        id=thread.id,
        title=thread.title,
        slug=thread.slug,
        summary=thread.summary,
        event_count=len(thread.events),
        epic_count=len(thread.epics),
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


def build_epic_response(epic: LifeEpic) -> LifeEpicResponse:
    return LifeEpicResponse(
        id=epic.id,
        period_id=epic.period_id,
        thread_id=epic.thread_id,
        title=epic.title,
        description=epic.description,
        weight=epic.weight,
        start_date_text=epic.start_date_text,
        end_date_text=epic.end_date_text,
        start_sort=epic.start_sort,
        end_sort=epic.end_sort,
        event_count=len(epic.events),
        created_at=epic.created_at,
        updated_at=epic.updated_at,
    )


def build_event_response(event: LifeEvent) -> LifeEventResponse:
    legacy_memory = event.legacy_memory
    linked_memory_ids: list[int] = []
    if event.legacy_memory_id is not None:
        linked_memory_ids.append(event.legacy_memory_id)
    for link in event.linked_assets:
        asset = link.asset
        if (
            asset
            and asset.legacy_memory_id is not None
            and asset.legacy_memory_id not in linked_memory_ids
        ):
            linked_memory_ids.append(asset.legacy_memory_id)

    return LifeEventResponse(
        id=event.id,
        period_id=event.period_id,
        epic_id=event.epic_id,
        thread_id=event.thread_id,
        title=event.title,
        description=event.description,
        weight=event.weight,
        summary=event.summary,
        research_summary=event.research_summary,
        research_queries=event.research_queries,
        research_sources=event.research_sources,
        research_suggested_edit=event.research_suggested_edit,
        event_date_text=event.event_date_text,
        event_date_sort=event.event_date_sort,
        event_end_date_sort=event.event_end_date_sort,
        date_precision=event.date_precision,
        date_year=event.date_year,
        date_month=event.date_month,
        date_day=event.date_day,
        date_decade=event.date_decade,
        location=event.location,
        legacy_memory_id=event.legacy_memory_id,
        linked_memory_ids=linked_memory_ids,
        legacy_audio_url=(legacy_memory.audio_url if legacy_memory else None),
        legacy_audio_size_bytes=(
            legacy_memory.audio_size_bytes if legacy_memory else None
        ),
        linked_asset_count=len(event.linked_assets),
        analysis_status=event.analysis_status,
        analysis_last_analyzed_at=event.analysis_last_analyzed_at,
        analysis_last_error=event.analysis_last_error,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def _extract_year_hint(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if not match:
        return None
    return int(match.group(1))


def _extract_year_hints(text: Optional[str]) -> list[int]:
    if not text:
        return []
    return [int(value) for value in re.findall(r"\b(19\d{2}|20\d{2})\b", text)]


def _period_bounds_in_years(period: LifePeriod) -> tuple[Optional[int], Optional[int]]:
    start_year = (
        period.start_sort.year
        if period.start_sort
        else _extract_year_hint(period.start_date_text)
    )
    end_year = (
        period.end_sort.year
        if period.end_sort
        else _extract_year_hint(period.end_date_text)
    )
    return start_year, end_year


def _event_year_bounds(events: list[LifeEvent]) -> tuple[Optional[int], Optional[int]]:
    years: list[int] = []
    for event in events:
        text_years = _extract_year_hints(event.event_date_text)
        if text_years:
            years.extend(text_years)

        if event.date_year:
            years.append(event.date_year)
            continue
        if event.date_decade:
            years.extend([event.date_decade, event.date_decade + 9])
            continue
        if event.event_date_sort:
            years.append(event.event_date_sort.year)
            continue

    if not years:
        return None, None
    return min(years), max(years)


def _recommended_period_dates_from_events(
    events: list[LifeEvent],
) -> tuple[Optional[str], Optional[str], Optional[date], Optional[date]]:
    min_year, max_year = _event_year_bounds(events)
    if min_year is None or max_year is None:
        return None, None, None, None

    recommended_start_text = str(min_year)
    recommended_end_text = str(max_year)
    recommended_start_sort = date(min_year, 1, 1)
    recommended_end_sort = date(max_year, 12, 31)
    return (
        recommended_start_text,
        recommended_end_text,
        recommended_start_sort,
        recommended_end_sort,
    )


def _is_generic_period_title(title: str) -> bool:
    normalized = (title or "").strip().lower()
    if not normalized:
        return True
    if normalized == "undated":
        return True
    if re.fullmatch(r"\d{4}", normalized):
        return True
    if re.fullmatch(r"\d{4}s", normalized):
        return True
    return False


_NARRATIVE_OPENERS = re.compile(
    r"^(i\s+)?(attended|went\s+to|started\s+(at|attending)?|enrolled\s+at|graduated\s+from|"
    r"transferred\s+to|moved\s+to|joined|was\s+(born|raised|stationed|deployed|assigned)\s+(in|at|to)?|"
    r"began\s+(working\s+at|at)?|took\s+a\s+job\s+at|worked\s+at|lived\s+(in|at)?|"
    r"returned\s+to|retired\s+from|left)\s+",
    re.IGNORECASE,
)
_TITLE_TAIL_STRIP = re.compile(r"\s+(in|at|to|from|for|and|the|a|an)$", re.IGNORECASE)


def _event_title_to_period_candidate(event_title: str, year_suffix: str) -> str | None:
    cleaned = _NARRATIVE_OPENERS.sub("", event_title.strip())
    cleaned = re.sub(
        r"\s+(from\s+\d{4}.*|in\s+(january|february|march|april|may|june|july|august|september|october|november|december|\d{4}).*|"
        r"during\s+\d{4}.*|until\s+\d{4}.*)$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    cleaned = _TITLE_TAIL_STRIP.sub("", cleaned).strip()
    if len(cleaned) < 4 or cleaned == event_title.strip():
        return None
    cleaned = cleaned[:80]
    return f"{cleaned} {year_suffix}".strip()


def _suggest_period_titles(
    period: LifePeriod, events: list[LifeEvent]
) -> tuple[list[str], str]:
    if not events:
        return (
            [],
            "No events in this period yet, so there is no evidence to suggest a better title.",
        )

    min_year, max_year = _event_year_bounds(events)
    if min_year is None or max_year is None:
        return [], "Event dates are too uncertain to suggest a stronger period title."

    if min_year == max_year:
        year_suffix = f"({min_year})"
        decade_label = f"the {(min_year // 10) * 10}s"
    else:
        year_suffix = f"({min_year}\u2013{max_year})"
        if (min_year // 10) == (max_year // 10):
            decade_label = f"the {(min_year // 10) * 10}s"
        else:
            decade_label = f"the {(min_year // 10) * 10}s\u2013{(max_year // 10) * 10}s"

    haystack = " ".join(
        f"{event.title or ''} {event.description or ''}".lower() for event in events
    )

    candidates: list[str] = []

    for event in events[:3]:
        raw = (event.title or "").strip()
        if not raw:
            continue
        derived = _event_title_to_period_candidate(raw, year_suffix)
        if derived:
            candidates.append(derived)

    institution_hits: list[str] = []
    for keyword, label in [
        ("cathedral prep", "Cathedral Prep"),
        ("bishop mccort", "Bishop McCort"),
        ("central catholic", "Central Catholic"),
        ("north catholic", "North Catholic"),
        ("duquesne", "Duquesne University"),
        ("university of pittsburgh", "University of Pittsburgh"),
        ("pitt", "University of Pittsburgh"),
        ("carnegie mellon", "Carnegie Mellon"),
        ("penn state", "Penn State"),
        ("temple university", "Temple University"),
        ("ohio state", "Ohio State"),
        ("community college", "Community College"),
        ("bahrain", "Bahrain"),
        ("norfolk", "Norfolk Naval Station"),
        ("fort bragg", "Fort Bragg"),
        ("fort campbell", "Fort Campbell"),
    ]:
        if keyword in haystack:
            institution_hits.append(f"{label} {year_suffix}")
    candidates.extend(institution_hits)

    if any(
        tok in haystack
        for tok in [
            "elementary",
            "grade school",
            "primary school",
            "first grade",
            "second grade",
            "third grade",
            "fourth grade",
            "fifth grade",
        ]
    ):
        candidates.append(f"Elementary School Years {year_suffix}")
    if any(
        tok in haystack
        for tok in [
            "middle school",
            "junior high",
            "sixth grade",
            "seventh grade",
            "eighth grade",
        ]
    ):
        candidates.append(f"Middle School Years {year_suffix}")
    if any(
        tok in haystack
        for tok in [
            "high school",
            "ninth grade",
            "tenth grade",
            "eleventh grade",
            "twelfth grade",
            "prep school",
            "senior year",
            "prom",
            "homecoming",
        ]
    ):
        candidates.append(f"High School Years {year_suffix}")
    if any(
        tok in haystack
        for tok in [
            "university",
            "college",
            "undergraduate",
            "campus",
            "fraternity",
            "sorority",
        ]
    ):
        candidates.append(f"College Years {year_suffix}")
    if any(
        tok in haystack
        for tok in [
            "graduate school",
            "master",
            "phd",
            "doctorate",
            "dissertation",
            "thesis",
        ]
    ):
        candidates.append(f"Graduate Studies {year_suffix}")
    if any(
        tok in haystack
        for tok in ["deployment", "deployed", "mobilized", "mobilization"]
    ):
        candidates.append(f"Overseas Deployment {year_suffix}")
    if any(
        tok in haystack
        for tok in [
            "navy",
            "army",
            "marine",
            "air force",
            "coast guard",
            "military",
            "enlisted",
        ]
    ):
        candidates.append(f"Military Service {year_suffix}")
    if any(
        tok in haystack for tok in ["married", "wedding", "engagement", "honeymoon"]
    ):
        candidates.append(f"Marriage and Early Family {year_suffix}")
    if any(
        tok in haystack for tok in ["daughter", "son", "newborn", "baby", "pregnancy"]
    ):
        candidates.append(f"Growing Our Family {year_suffix}")
    if any(
        tok in haystack for tok in ["scout", "troop", "eagle", "cub scout", "boy scout"]
    ):
        candidates.append(f"Scouting Years {year_suffix}")
    if any(
        tok in haystack
        for tok in [
            "job",
            "career",
            "hired",
            "promotion",
            "manager",
            "engineer",
            "developer",
        ]
    ):
        candidates.append(f"Career Years {year_suffix}")
    if any(
        tok in haystack for tok in ["childhood", "born", "growing up", "playground"]
    ):
        candidates.append(f"Early Childhood {year_suffix}")

    candidates.append(f"A Chapter from {decade_label}")

    current = period.title.strip()
    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        if candidate not in seen and candidate.lower() != current.lower():
            seen.add(candidate)
            unique.append(candidate)

    if not unique:
        return [], "The current title already reflects the events in this period."

    reasoning = (
        "The current title is generic. These candidates reflect the specific events and date range in this period."
        if _is_generic_period_title(period.title)
        else "These alternatives capture the themes and timeframe of events in this period."
    )
    return unique[:5], reasoning


def _generate_period_summary(
    period: LifePeriod, events: list[LifeEvent], asset_count: int
) -> tuple[str, str]:
    if not events:
        return (
            "Auto-generated biography: This chapter is waiting for its first memory. As new moments and supporting materials are added, this biography-style summary will grow into a fuller life story.",
            "Summary generated from period structure because there are no events yet.",
        )

    min_year, max_year = _event_year_bounds(events)
    if min_year is None or max_year is None:
        range_text = "those years"
    elif min_year == max_year:
        range_text = str(min_year)
    else:
        range_text = f"{min_year} to {max_year}"

    event_data = [
        (
            (event.title or "").strip(),
            (event.description or "").strip(),
            (event.event_date_text or "").strip(),
        )
        for event in events
        if (event.title or "").strip()
    ]
    event_titles = [t for t, d, dt in event_data]
    event_descriptions = [d for t, d, dt in event_data]
    event_date_texts = [dt for t, d, dt in event_data]

    ai_text = generate_period_biography(
        period_title=period.title,
        year_range=range_text,
        event_titles=event_titles,
        event_descriptions=event_descriptions,
        event_date_texts=event_date_texts,
        asset_count=asset_count,
    )
    if ai_text:
        return (
            f"Auto-generated biography: {ai_text}",
            "Summary written by AI from current events and linked assets.",
        )

    count = len(event_titles)
    if count == 0:
        event_line = "No events have been recorded for this period yet."
    elif count == 1:
        event_line = f"This chapter contains one recorded moment from {range_text}."
    else:
        event_line = (
            f"This chapter covers {count} recorded moments spanning {range_text}."
        )

    if asset_count == 0:
        asset_line = "No supporting photos or documents are linked yet."
    elif asset_count == 1:
        asset_line = "One supporting asset is linked to help tell the story."
    else:
        asset_line = (
            f"{asset_count} supporting assets are linked to help tell the story."
        )

    summary = f"Auto-generated biography: {event_line} {asset_line}"
    return summary[:1200], "Summary generated from current events and linked assets."


def _should_auto_update_period_summary(period: LifePeriod) -> bool:
    if not period.summary:
        return True
    return period.summary.startswith(
        "Auto-generated summary:"
    ) or period.summary.startswith("Auto-generated biography:")


def refresh_period_summary(
    db: Session, period: Optional[LifePeriod], force: bool = False
) -> Optional[str]:
    if not period:
        return None

    if not force and not _should_auto_update_period_summary(period):
        return period.summary

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
    summary_text, _ = _generate_period_summary(
        period, events, period_asset_count_from_events(events)
    )
    period.summary = summary_text
    return summary_text


def analyze_period(
    period: LifePeriod,
    events: list[LifeEvent],
    asset_count: int,
    *,
    pipeline_stats: Optional[dict] = None,
) -> LifePeriodAnalysisResponse:
    period_start_year, period_end_year = _period_bounds_in_years(period)
    event_min_year, event_max_year = _event_year_bounds(events)

    coverage_ok = True
    coverage_gaps: list[str] = []
    if event_min_year is not None and (
        period_start_year is None or period_start_year > event_min_year
    ):
        coverage_ok = False
        coverage_gaps.append(f"start should be {event_min_year}")
    if event_max_year is not None and (
        period_end_year is None or period_end_year < event_max_year
    ):
        coverage_ok = False
        coverage_gaps.append(f"end should be {event_max_year}")

    if coverage_ok:
        coverage_reasoning = "Current period dates cover the known event date range."
    elif coverage_gaps:
        coverage_reasoning = (
            "Period date coverage can improve: " + ", ".join(coverage_gaps) + "."
        )
    else:
        coverage_reasoning = "Event dates are too uncertain to assess period coverage."

    rec_start_text, rec_end_text, _, _ = _recommended_period_dates_from_events(events)
    recommended_titles, title_reasoning = _suggest_period_titles(period, events)
    generated_summary, summary_reasoning = _generate_period_summary(
        period, events, asset_count
    )

    return LifePeriodAnalysisResponse(
        period_id=period.id,
        event_count=len(events),
        asset_count=asset_count,
        coverage_ok=coverage_ok,
        coverage_reasoning=coverage_reasoning,
        current_title=period.title,
        recommended_titles=recommended_titles,
        title_reasoning=title_reasoning,
        current_start_date_text=period.start_date_text,
        current_end_date_text=period.end_date_text,
        recommended_start_date_text=rec_start_text,
        recommended_end_date_text=rec_end_text,
        generated_summary=generated_summary,
        summary_reasoning=summary_reasoning,
        queued_event_count=(pipeline_stats or {}).get("queued_event_count", 0),
        analyzed_event_count=(pipeline_stats or {}).get("analyzed_event_count", 0),
        skipped_event_count=(pipeline_stats or {}).get("skipped_event_count", 0),
        failed_event_count=(pipeline_stats or {}).get("failed_event_count", 0),
        photo_assets_analyzed=(pipeline_stats or {}).get("photo_assets_analyzed", 0),
        memories_researched=(pipeline_stats or {}).get("memories_researched", 0),
    )


def build_asset_response(asset: Asset) -> AssetResponse:
    return AssetResponse(
        id=asset.id,
        period_id=asset.period_id,
        kind=asset.kind,
        title=asset.title,
        gemini_suggested_title=asset.gemini_suggested_title,
        legacy_memory_id=asset.legacy_memory_id,
        original_filename=asset.original_filename,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        captured_at=asset.captured_at,
        captured_end_at=asset.captured_end_at,
        captured_at_text=asset.captured_at_text,
        gps_latitude=asset.gps_latitude,
        gps_longitude=asset.gps_longitude,
        exif_place_name=asset.exif_place_name,
        reverse_geocode_location_name=asset.reverse_geocode_location_name,
        analyzed_place_name=asset.analyzed_place_name,
        location_name=asset.location_name,
        camera_make=asset.camera_make,
        camera_model=asset.camera_model,
        lens_model=asset.lens_model,
        orientation=asset.orientation,
        image_width=asset.image_width,
        image_height=asset.image_height,
        playback_url=(
            asset.download_url
            if (asset.content_type or "").startswith("audio/")
            else None
        ),
        text_excerpt=asset.text_excerpt,
        notes=asset.notes,
        download_url=asset.download_url,
        linked_event_ids=[link.event_id for link in asset.event_links],
        created_at=asset.created_at,
    )


def ensure_event_asset_link(
    db: Session, event: LifeEvent, asset: Asset, relation_type: str = "evidence"
) -> None:
    exists = any(link.asset_id == asset.id for link in event.linked_assets)
    if not exists:
        db.add(
            EventAsset(
                event_id=event.id, asset_id=asset.id, relation_type=relation_type[:30]
            )
        )


def get_or_create_period_for_memory(db: Session, memory: MemoryEntry) -> LifePeriod:
    if memory.date_year:
        title = f"{memory.date_year}"
        slug = f"year-{memory.date_year}"
        start_sort = date(memory.date_year, 1, 1)
        end_sort = date(memory.date_year, 12, 31)
        start_text = str(memory.date_year)
        end_text = str(memory.date_year)
    elif memory.date_decade:
        decade_start = memory.date_decade
        decade_end = memory.date_decade + 9
        title = f"{decade_start}s"
        slug = f"decade-{decade_start}"
        start_sort = date(decade_start, 1, 1)
        end_sort = date(decade_end, 12, 31)
        start_text = str(decade_start)
        end_text = str(decade_end)
    elif memory.estimated_date_sort:
        inferred_year = memory.estimated_date_sort.year
        title = f"{inferred_year}"
        slug = f"year-{inferred_year}"
        start_sort = date(inferred_year, 1, 1)
        end_sort = date(inferred_year, 12, 31)
        start_text = str(inferred_year)
        end_text = str(inferred_year)
    else:
        title = "Undated"
        slug = "undated"
        start_sort = None
        end_sort = None
        start_text = "unknown"
        end_text = "unknown"

    period = db.query(LifePeriod).filter(LifePeriod.slug == slug).first()
    if period:
        return period

    period = LifePeriod(
        title=title,
        slug=unique_period_slug(db, slug),
        start_date_text=start_text,
        end_date_text=end_text,
        start_sort=start_sort,
        end_sort=end_sort,
        summary="Auto-created from existing memories.",
    )
    db.add(period)
    db.flush()
    return period
