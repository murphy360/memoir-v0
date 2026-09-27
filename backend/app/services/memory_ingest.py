import logging
from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException

from app.services.gemini_client import (
    extract_metadata_with_gemini_function_call,
    transcribe_audio,
)
from app.services.memory_analysis import (
    build_default_narration_title,
    MemoryMetadata,
    detect_emotional_tone,
    fallback_metadata_from_transcript,
    generate_follow_up_question,
)

logger = logging.getLogger("memoir.api")


def analyze_memory_audio(
    filename: str,
    audio_bytes: bytes,
    transcription_enabled: bool,
) -> tuple[str, str, Optional[date], str, str, str, MemoryMetadata]:
    if transcription_enabled:
        try:
            transcript = transcribe_audio(filename, audio_bytes)
            metadata = extract_metadata_with_gemini_function_call(transcript)
            if metadata is None:
                metadata = fallback_metadata_from_transcript(transcript)

            estimated_date_text = metadata.date_text
            estimated_date_sort = metadata.sort_date
            emotional_tone = detect_emotional_tone(transcript)
            event_description = build_default_narration_title(metadata.recorder_name)
            follow_up_question = generate_follow_up_question(
                transcript, event_description, metadata
            )
            return (
                transcript,
                event_description,
                estimated_date_sort,
                estimated_date_text,
                emotional_tone,
                follow_up_question,
                metadata,
            )
        except HTTPException as exc:
            logger.warning("Transcription failed for %s: %s", filename, exc.detail)
            return (
                "Transcription failed.",
                build_default_narration_title(None),
                None,
                "unknown",
                "unknown",
                "Transcription failed for this memory. You can still play the original audio.",
                MemoryMetadata(),
            )

    now = datetime.utcnow()
    return (
        "Transcription disabled.",
        build_default_narration_title(None),
        now.date(),
        "recorded now",
        "unknown",
        "Transcription is turned off while testing recording and playback.",
        MemoryMetadata(
            date_text="recorded now",
            date_precision="day",
            sort_date=now.date(),
            date_year=now.year,
            date_month=now.month,
            date_day=now.day,
        ),
    )
