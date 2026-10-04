"""Event and memory analysis helpers used by API routes and period pipelines."""

import dataclasses
import json
import re
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models import LifeEvent, MemoryEntry
from app.services.gemini_client import (
    research_memory_details,
    suggest_date_from_research,
    suggest_event_edit_from_context,
    summarize_event_details,
)
from app.services.memory_analysis import summarize_event as summarize_memory_transcript


def extract_questions_from_research(summary: str) -> list[str]:
    """Extract bullet-point questions from the 'Questions worth exploring' section."""
    lines = summary.splitlines()
    in_section = False
    questions: list[str] = []
    section_headers = re.compile(r"^#{1,3}\s*questions worth exploring", re.IGNORECASE)
    next_section = re.compile(r"^#{1,3}\s+\w", re.IGNORECASE)
    bullet = re.compile(r"^[\*\-]\s+(.+)")

    for line in lines:
        stripped = line.strip()
        if section_headers.match(stripped):
            in_section = True
            continue
        if in_section:
            if next_section.match(stripped) and not section_headers.match(stripped):
                break
            match = bullet.match(stripped)
            if match:
                text = match.group(1).strip()
                if text.endswith("?"):
                    questions.append(text)
    return questions[:5]


def _possessive_name(name: str) -> str:
    clean = (name or "").strip()
    if not clean:
        return ""
    if clean.endswith(("s", "S")):
        return f"{clean}'"
    return f"{clean}'s"


def derive_quick_event_title(memory: MemoryEntry) -> str:
    """Build a quick fallback title from memory transcript and relationship clues."""
    transcript = (memory.transcript or "").strip()
    if not transcript:
        return "Unspecified memory"

    lowered = transcript.lower()
    if "play" in lowered:
        relationship_label: Optional[str] = None
        if "daughter" in lowered:
            relationship_label = "Daughter's Play"
        elif "son" in lowered:
            relationship_label = "Son's Play"
        elif "granddaughter" in lowered:
            relationship_label = "Granddaughter's Play"
        elif "grandson" in lowered:
            relationship_label = "Grandson's Play"

        play_title_match = re.search(r"['\"]([^'\"]{2,80})['\"]", transcript)
        if play_title_match:
            play_title = play_title_match.group(1).strip()
            if relationship_label:
                return f"{play_title} ({relationship_label})"
            return play_title

        people = memory.referenced_people
        if people:
            first_person = people[0].strip()
            if first_person:
                return f"{_possessive_name(first_person)} Play"

        if relationship_label:
            return relationship_label

    return summarize_memory_transcript(transcript).strip() or "Unspecified memory"


def collect_event_memories(event: LifeEvent, db: Session) -> list[MemoryEntry]:
    """Return unique memories linked to an event either directly or through assets."""
    memory_ids: list[int] = []
    if event.legacy_memory_id is not None:
        memory_ids.append(event.legacy_memory_id)

    for link in event.linked_assets:
        asset = link.asset
        if asset and asset.legacy_memory_id is not None:
            memory_ids.append(asset.legacy_memory_id)

    seen: set[int] = set()
    memories: list[MemoryEntry] = []
    for memory_id in memory_ids:
        if memory_id in seen:
            continue
        seen.add(memory_id)
        memory = db.get(MemoryEntry, memory_id)
        if memory:
            memories.append(memory)
    return memories


def event_research_source_memory_id(
    event: LifeEvent, memories: list[MemoryEntry]
) -> Optional[int]:
    """Pick a source memory id for derived follow-up questions from event research."""
    if event.legacy_memory_id is not None:
        return event.legacy_memory_id
    if memories:
        return memories[0].id
    return None


def refresh_event_summary_and_suggestion(
    db: Session,
    event: LifeEvent,
    *,
    auto_apply_title: bool = False,
) -> None:
    """Regenerate event summary and edit suggestion from current linked context."""
    memories = collect_event_memories(event, db)
    assets = [link.asset for link in event.linked_assets if link.asset]

    memory_points: list[str] = []
    for memory in memories:
        heading = (memory.event_description or "").strip() or f"Memory {memory.id}"
        transcript = " ".join((memory.transcript or "").split())
        if transcript:
            memory_points.append(f"{heading}: {transcript[:280]}")
        else:
            memory_points.append(heading)

    asset_points: list[str] = []
    for asset in assets:
        title = (asset.title or asset.original_filename or f"Asset {asset.id}").strip()
        details = []
        if asset.notes:
            details.append(" ".join(asset.notes.split())[:180])
        if asset.text_excerpt:
            details.append(" ".join(asset.text_excerpt.split())[:180])
        if asset.captured_at_text:
            details.append(asset.captured_at_text)
        place = (
            asset.analyzed_place_name or asset.reverse_geocode_location_name or ""
        ).strip()
        if place:
            details.append(f"Place: {place}")
        if details:
            asset_points.append(f"{title}: {' | '.join(details)}")
        else:
            asset_points.append(title)

    summary = summarize_event_details(
        event_title=event.title,
        event_date_text=event.event_date_text,
        memory_points=memory_points,
        asset_points=asset_points,
    )
    event.summary = summary

    suggestion = suggest_event_edit_from_context(
        analysis_text=summary,
        current_title=event.title,
        current_event_date_text=event.event_date_text,
        current_description=event.description,
    )

    if auto_apply_title:
        suggested_title = (suggestion.title or "").strip() if suggestion else ""
        if suggested_title:
            event.title = suggested_title[:180]
        elif memories:
            fallback_title = derive_quick_event_title(memories[0])
            if fallback_title and fallback_title.lower() != "unspecified memory":
                event.title = fallback_title[:180]

    event.research_suggested_edit_json = (
        json.dumps(dataclasses.asdict(suggestion)) if suggestion else None
    )


def research_memory_entry(memory: MemoryEntry, document_storage_dir: Path) -> None:
    """Run deep-memory research and store summary, sources, queries, and date suggestion."""
    document_bytes = None
    document_mime_type = None
    if memory.document_filename:
        doc_path = document_storage_dir / memory.document_filename
        if doc_path.exists():
            document_bytes = doc_path.read_bytes()
            document_mime_type = (
                memory.document_content_type or "application/octet-stream"
            )

    research = research_memory_details(
        transcript=memory.transcript,
        event_description=memory.event_description,
        estimated_date_text=memory.estimated_date_text,
        referenced_locations=memory.referenced_locations,
        referenced_people=memory.referenced_people,
        document_bytes=document_bytes,
        document_mime_type=document_mime_type,
    )
    memory.research_summary = research.summary
    memory.research_queries_json = json.dumps(research.queries)
    memory.research_sources_json = json.dumps(
        [{"title": source.title, "url": source.url} for source in research.sources]
    )

    suggestion = suggest_date_from_research(
        research_summary=research.summary,
        current_date_text=memory.estimated_date_text,
        current_date_precision=memory.date_precision,
    )
    if suggestion:
        memory.research_suggested_metadata_json = json.dumps(
            dataclasses.asdict(suggestion)
        )
    else:
        memory.research_suggested_metadata_json = None
