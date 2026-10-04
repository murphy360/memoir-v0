import base64
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests
from fastapi import HTTPException

from app.services.memory_analysis import (
    MemoryMetadata,
    build_sort_date,
    normalize_string_list,
)

logger = logging.getLogger("memoir.api")


@dataclass
class ResearchSource:
    title: str
    url: str


@dataclass
class ResearchResult:
    summary: str
    queries: list[str] = field(default_factory=list)
    sources: list[ResearchSource] = field(default_factory=list)


@dataclass
class PhotoSummary:
    summary: str
    suggested_title: Optional[str] = None
    assessed_place: Optional[str] = None
    visual_evidence: Optional[str] = None
    contextual_narrative: Optional[str] = None
    discrepancy_flag: Optional[str] = None

    def excerpt_text(self, *, max_length: int = 1200) -> str:
        """Build a readable asset excerpt with optional discrepancy warning."""
        visual = (self.visual_evidence or "").strip()
        contextual = (self.contextual_narrative or "").strip()
        discrepancy = (self.discrepancy_flag or "").strip()
        fallback = (self.summary or "").strip()

        parts: list[str] = []
        if visual:
            parts.append(f"Visual evidence: {visual}")
        if contextual:
            parts.append(f"Contextual narrative: {contextual}")
        elif fallback:
            parts.append(fallback)
        if discrepancy:
            parts.append(f"Metadata discrepancy: {discrepancy}")

        text = "\n".join(parts).strip() or fallback
        return text[:max_length]


def _extract_metadata_field(
    metadata_hint: Optional[str], field_name: str
) -> Optional[str]:
    """Extract a semicolon-delimited metadata hint value like key=value."""
    hint = (metadata_hint or "").strip()
    if not hint:
        return None
    target_prefix = f"{field_name}="
    for chunk in hint.split(";"):
        piece = chunk.strip()
        if piece.startswith(target_prefix):
            value = piece[len(target_prefix) :].strip()
            return value or None
    return None


@dataclass
class DateSuggestion:
    estimated_date_text: str
    date_precision: str
    date_year: Optional[int]
    date_month: Optional[int]
    date_day: Optional[int]
    date_decade: Optional[int]
    reasoning: str


@dataclass
class EventEditSuggestion:
    title: Optional[str]
    event_date_text: Optional[str]
    description: Optional[str]
    reasoning: str


def suggest_date_from_research(
    research_summary: str,
    current_date_text: Optional[str],
    current_date_precision: Optional[str],
) -> Optional[DateSuggestion]:
    """Use Gemini function calling to extract date suggestion from research summary.

    Returns None if no meaningful improvement over the current date is found,
    or if the Gemini API key is unavailable.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return None

    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "You are analyzing research results for a personal memory and extracting date refinements. "
                            "Read the research summary and suggest an improved date if the evidence is clear. "
                            "If no meaningful improvement is possible, call suggest_date_refinement with no arguments (or empty args). "
                            "Current recorded date: {current_date_text or 'Unknown'}\n"
                            "Current precision: {current_date_precision or 'unknown'}\n\n"
                            f"Research summary:\n{research_summary}"
                        )
                    }
                ]
            }
        ],
        "tools": [
            {
                "functionDeclarations": [
                    {
                        "name": "suggest_date_refinement",
                        "description": "Suggest a refined date for a memory based on research findings. Leave all fields null if no refinement is warranted.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "estimated_date_text": {"type": "string"},
                                "date_precision": {
                                    "type": "string",
                                    "enum": [
                                        "exact",
                                        "approximate",
                                        "month",
                                        "year",
                                        "decade",
                                    ],
                                },
                                "date_year": {"type": "integer"},
                                "date_month": {"type": "integer"},
                                "date_day": {"type": "integer"},
                                "date_decade": {"type": "integer"},
                                "reasoning": {"type": "string"},
                            },
                            "required": [],
                        },
                    }
                ]
            }
        ],
        "toolConfig": {
            "functionCallingConfig": {
                "mode": "ANY",
                "allowedFunctionNames": ["suggest_date_refinement"],
            }
        },
    }

    try:
        response = requests.post(
            endpoint, params={"key": gemini_key}, json=payload, timeout=30
        )
        if not response.ok:
            logger.warning("Date suggestion request failed: %s", response.text[:200])
            return None
        data = response.json()
    except Exception as exc:
        logger.warning("Date suggestion exception: %s", exc)
        return None

    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    for part in parts:
        function_call = part.get("functionCall")
        if not function_call or function_call.get("name") != "suggest_date_refinement":
            continue

        args = function_call.get("args", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if not isinstance(args, dict):
            args = {}

        # If no estimated_date_text, no suggestion to make
        estimated_date_text = str(args.get("estimated_date_text") or "").strip()
        if not estimated_date_text:
            return None

        return DateSuggestion(
            estimated_date_text=estimated_date_text[:100],
            date_precision=str(args.get("date_precision") or "approximate"),
            date_year=_int_or_none(args.get("date_year")),
            date_month=_int_or_none(args.get("date_month")),
            date_day=_int_or_none(args.get("date_day")),
            date_decade=_int_or_none(args.get("date_decade")),
            reasoning=str(args.get("reasoning") or "")[:500],
        )

    return None


def _int_or_none(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def suggest_event_edit_from_context(
    analysis_text: str,
    current_title: str,
    current_event_date_text: Optional[str],
    current_description: Optional[str],
) -> Optional[EventEditSuggestion]:
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return None

    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "You are reviewing an event summary/research result and deciding whether to suggest edits to event metadata. "
                            "Only suggest changes if they are meaningfully better than current values and are grounded in the provided text. "
                            "If no meaningful edit is warranted, call suggest_event_edit with no args.\n\n"
                            f"Current title: {current_title}\n"
                            f"Current event_date_text: {current_event_date_text or 'Unknown'}\n"
                            f"Current description: {current_description or 'None'}\n\n"
                            f"Summary/Research text:\n{analysis_text[:12000]}"
                        )
                    }
                ]
            }
        ],
        "tools": [
            {
                "functionDeclarations": [
                    {
                        "name": "suggest_event_edit",
                        "description": "Suggest edits for event title/date/description if there is strong evidence. Use only fields that should change.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "event_date_text": {"type": "string"},
                                "description": {"type": "string"},
                                "reasoning": {"type": "string"},
                            },
                            "required": [],
                        },
                    }
                ]
            }
        ],
        "toolConfig": {
            "functionCallingConfig": {
                "mode": "ANY",
                "allowedFunctionNames": ["suggest_event_edit"],
            }
        },
    }

    try:
        response = requests.post(
            endpoint, params={"key": gemini_key}, json=payload, timeout=35
        )
        if not response.ok:
            logger.warning(
                "Event edit suggestion request failed: %s", response.text[:200]
            )
            return None
        data = response.json()
    except Exception as exc:
        logger.warning("Event edit suggestion exception: %s", exc)
        return None

    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    for part in parts:
        function_call = part.get("functionCall")
        if not function_call or function_call.get("name") != "suggest_event_edit":
            continue

        args = function_call.get("args", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if not isinstance(args, dict):
            args = {}

        suggested_title = str(args.get("title") or "").strip()
        suggested_date = str(args.get("event_date_text") or "").strip()
        suggested_description = str(args.get("description") or "").strip()
        reasoning = str(args.get("reasoning") or "").strip()

        changed_title = suggested_title and suggested_title != current_title
        changed_date = suggested_date and suggested_date != (
            current_event_date_text or ""
        )
        changed_description = suggested_description and suggested_description != (
            current_description or ""
        )
        if not (changed_title or changed_date or changed_description):
            return None

        return EventEditSuggestion(
            title=suggested_title[:180] if changed_title else None,
            event_date_text=suggested_date[:100] if changed_date else None,
            description=suggested_description[:1200] if changed_description else None,
            reasoning=(reasoning or "Suggested from summary/research evidence.")[:500],
        )

    return None


def generate_insightful_questions(
    transcript: str,
    event_description: str,
    metadata: "MemoryMetadata",
) -> list[str]:
    """Use Gemini to generate leading, insightful follow-up questions from a memory transcript.

    These questions are meant to carry the conversation forward — probing emotion,
    significance, relationships, and consequences rather than just filling gaps.
    Returns an empty list if Gemini is unavailable or the request fails.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return []

    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"

    context_parts: list[str] = []
    if metadata.recorder_name:
        context_parts.append(f"Narrator: {metadata.recorder_name}")
    if metadata.date_text and metadata.date_text != "unknown":
        context_parts.append(f"Date: {metadata.date_text}")
    if metadata.people:
        context_parts.append(f"People mentioned: {', '.join(metadata.people[:5])}")
    if metadata.locations:
        context_parts.append(f"Locations: {', '.join(metadata.locations[:3])}")
    context_block = "\n".join(context_parts)

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "You are helping someone build a personal memoir. They just shared a memory. "
                            "Your job is to ask 2-3 insightful, leading questions that will carry the conversation forward "
                            "and help them tell a richer story. "
                            "Good questions:\n"
                            "- Probe emotion, significance, or what changed as a result of this moment\n"
                            "- Ask about key people present and their roles\n"
                            "- Invite reflection on why this memory has stayed with them\n"
                            "- Connect to larger life themes (family, ambition, loss, joy, identity)\n"
                            "- Are specific to what was shared, NOT generic\n\n"
                            "Bad questions repeat facts already stated, ask for logistics, "
                            "or say things like 'what happened just before'.\n\n"
                            "Return exactly 2-3 questions, one per line, no numbering, no bullets, "
                            "each ending with a question mark.\n\n"
                            f"Memory transcript:\n{transcript[:1500]}\n\n"
                            f"Context:\n{context_block}"
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 400,
        },
    }

    try:
        response = requests.post(
            endpoint, params={"key": gemini_key}, json=payload, timeout=30
        )
        if not response.ok:
            logger.warning(
                "Insightful questions request failed: %s", response.text[:200]
            )
            return []
        data = response.json()
        candidate = data.get("candidates", [{}])[0]
        parts = candidate.get("content", {}).get("parts", [])
        text = "\n".join(
            part.get("text", "").strip() for part in parts if part.get("text")
        ).strip()
        if not text:
            return []
        questions = [
            q.strip() for q in text.split("\n") if q.strip() and q.strip().endswith("?")
        ]
        return questions[:3]
    except Exception as exc:
        logger.warning("generate_insightful_questions exception: %s", exc)
        return []


def generate_research_questions(
    research_summary: str,
    event_description: str,
    referenced_people: list[str],
) -> list[str]:
    """Generate 2-3 follow-up research questions based on findings.

    Uses Gemini to extract the most important unanswered questions or entities
    worth exploring further from the research summary.
    """
    logger.info(
        "GENERATE_RESEARCH_QUESTIONS called with event: %s, num_people: %d",
        event_description[:50],
        len(referenced_people),
    )
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        logger.warning("No GEMINI_API_KEY found")
        return []

    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "Based on this research summary, generate 2-3 specific follow-up questions "
                            "that would help deepen understanding of the memory. "
                            "Focus on:\n"
                            "- Key people or organizations mentioned that deserve deeper investigation\n"
                            "- Important events or situations referenced that warrant their own memory\n"
                            "- Gaps or contradictions that need clarification\n"
                            "- Related events that might connect to other memories\n\n"
                            "Each question should be concrete, answerable, and directly connected to something in the research.\n\n"
                            "IMPORTANT: Return exactly 2-3 complete questions, one per line, with NO numbering, bullets, or extra text. "
                            "Each line must be a complete question ending with a question mark.\n\n"
                            f"Original event: {event_description}\n"
                            f"Research findings:\n{research_summary}"
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 500,
        },
    }

    try:
        response = requests.post(
            endpoint, params={"key": gemini_key}, json=payload, timeout=30
        )
        if not response.ok:
            logger.warning("Research questions request failed: %s", response.text[:200])
            return []
        data = response.json()
        candidate = data.get("candidates", [{}])[0]
        parts = candidate.get("content", {}).get("parts", [])
        text = "\n".join(
            part.get("text", "").strip() for part in parts if part.get("text")
        ).strip()
        logger.info("Research questions raw response: %s", text[:300])
        if not text:
            logger.warning("Research questions returned empty text")
            return []
        # Split by newline, filter empty lines, and keep only lines ending with ?
        all_lines = [q.strip() for q in text.split("\n") if q.strip()]
        logger.info("All extracted lines: %s", all_lines)
        questions = [q for q in all_lines if q.endswith("?")]
        logger.info("Questions with question marks: %s", questions)
        return questions[:3]  # Return at most 3 questions
    except Exception as exc:
        logger.warning("Generate research questions exception: %s", exc)
        return []


def research_memory_details(
    transcript: str,
    event_description: str,
    estimated_date_text: Optional[str],
    referenced_locations: list[str],
    referenced_people: list[str],
    document_bytes: Optional[bytes] = None,
    document_mime_type: Optional[str] = None,
) -> ResearchResult:
    gemini_key = os.getenv("GEMINI_API_KEY")
    gemini_model = os.getenv("GEMINI_RESEARCH_MODEL") or os.getenv(
        "GEMINI_MODEL", "gemini-2.5-flash"
    )

    location_text = (
        ", ".join(referenced_locations) if referenced_locations else "Unknown"
    )
    people_text = ", ".join(referenced_people) if referenced_people else "Unknown"

    if gemini_key:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"

        parts = [
            {
                "text": (
                    "Research this personal memory by exploring the broader context and implications beyond what the document explicitly states.\n\n"
                    "Your goal is to help understand: What was the bigger picture? What were the consequences? What related things happened? "
                    "Think of this as investigative research that expands the story, not just confirms facts already in the document.\n\n"
                    "PRIORITY 1 - Explore broader context and implications:\n"
                    "- If a decision/order is documented, research: What were its likely effects? What was happening before/after? How did it matter?\n"
                    "- If a time/place is mentioned, research: What was the geopolitical/social/historical situation? What crises existed? What were people experiencing?\n"
                    "- Search for cause-and-effect: Why did this happen? What led to it? What consequences followed?\n\n"
                    "PRIORITY 2 - Ask exploratory leading questions:\n"
                    "- If a deployment is mentioned: What were conditions in that location? What challenges would personnel face? What was the strategic importance?\n"
                    "- If a transition/change occurred: What were the career implications? How would this have affected the person's trajectory? What opportunities or obstacles emerged?\n"
                    "- If a crisis context exists (pandemic, conflict, economic): How did that specific crisis manifest in the relevant domain? What were the ripple effects?\n\n"
                    "PRIORITY 3 - Expand with related research:\n"
                    "- Search for related policies, precedents, or similar situations: Were there other people/units experiencing the same thing? What was standard vs. unusual?\n"
                    "- Look for historical patterns: Has this type of situation happened before? What were the long-term outcomes in similar cases?\n\n"
                    "Structure your response with these sections:\n"
                    "- 'What this likely meant': Implications and consequences beyond the document's explicit content\n"
                    "- 'The bigger picture': Broader context that shaped this experience (political climate, operational situation, institutional changes, etc.)\n"
                    "- 'Related developments': Similar events, policies, or situations happening concurrently or as follow-ups\n"
                    "- 'Questions worth exploring': What aspects remain unclear or warrant further investigation?\n\n"
                    "Use search results to support exploratory answers, not just to corroborate what's already stated. "
                    "Flag areas where research reveals new dimensions or implications of the documented event.\n\n"
                    f"Event description: {event_description}\n"
                    f"Estimated date: {estimated_date_text or 'Unknown'}\n"
                    f"Referenced locations: {location_text}\n"
                    f"Referenced people: {people_text}\n"
                    f"Transcript:\n{transcript}"
                    + (
                        "\n\nThe original document is attached below."
                        if document_bytes
                        else ""
                    )
                )
            }
        ]

        if document_bytes and document_mime_type:
            encoded_doc = base64.b64encode(document_bytes).decode("utf-8")
            parts.append(
                {
                    "inline_data": {
                        "mime_type": document_mime_type,
                        "data": encoded_doc,
                    }
                }
            )

        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "tools": [{"googleSearch": {"searchTypes": {"webSearch": {}}}}],
            "generationConfig": {
                "temperature": 0.15,
                "maxOutputTokens": 3000,
                "responseMimeType": "text/plain",
            },
        }

        try:
            response = requests.post(
                endpoint, params={"key": gemini_key}, json=payload, timeout=90
            )
            if response.ok:
                data = response.json()
                candidate = data.get("candidates", [{}])[0]
                text_parts = candidate.get("content", {}).get("parts", [])
                text = "\n".join(
                    part.get("text", "").strip()
                    for part in text_parts
                    if part.get("text")
                ).strip()
                if text:
                    grounding = candidate.get("groundingMetadata", {})
                    queries = _extract_grounding_queries(grounding)
                    sources = _extract_grounding_sources(grounding)
                    return ResearchResult(
                        summary=text[:10000], queries=queries, sources=sources
                    )
            else:
                logger.warning(
                    "Gemini research request failed: %s", response.text[:300]
                )
        except Exception as exc:
            logger.warning("Gemini research request exception: %s", exc)

    return ResearchResult(
        summary="Research could not be completed at this time. Try running research again.",
        queries=[],
        sources=[],
    )


def summarize_event_details(
    event_title: str,
    event_date_text: Optional[str],
    memory_points: list[str],
    asset_points: list[str],
) -> str:
    gemini_key = os.getenv("GEMINI_API_KEY")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    clean_memory_points = [
        point.strip() for point in memory_points if point and point.strip()
    ]
    clean_asset_points = [
        point.strip() for point in asset_points if point and point.strip()
    ]

    if gemini_key:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"
        memory_block = (
            "\n".join(f"- {point}" for point in clean_memory_points[:20])
            or "- No memory narration provided"
        )
        asset_block = (
            "\n".join(f"- {point}" for point in clean_asset_points[:20])
            or "- No supporting assets linked"
        )

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "Write a concise event summary for a personal memoir timeline. "
                                "Keep it factual and readable in 2-4 short paragraphs, then end with 3-6 bullet highlights.\n\n"
                                f"Event title: {event_title}\n"
                                f"Event date text: {event_date_text or 'Unknown'}\n\n"
                                "Memory narration snippets:\n"
                                f"{memory_block}\n\n"
                                "Supporting assets and notes:\n"
                                f"{asset_block}"
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1500,
                "responseMimeType": "text/plain",
            },
        }

        try:
            response = requests.post(
                endpoint, params={"key": gemini_key}, json=payload, timeout=60
            )
            if response.ok:
                data = response.json()
                candidate = data.get("candidates", [{}])[0]
                parts = candidate.get("content", {}).get("parts", [])
                text = "\n".join(
                    part.get("text", "").strip() for part in parts if part.get("text")
                ).strip()
                if text:
                    return text[:8000]
            else:
                logger.warning(
                    "Gemini event summary request failed: %s", response.text[:300]
                )
        except Exception as exc:
            logger.warning("Gemini event summary request exception: %s", exc)

    if clean_memory_points:
        opening = clean_memory_points[0]
    else:
        opening = "No narrated memories are linked yet."
    lines = [
        f"{event_title} ({event_date_text or 'Unknown date'})",
        "",
        opening,
    ]
    if len(clean_memory_points) > 1:
        lines.append("")
        lines.append("Additional memory highlights:")
        lines.extend(f"- {point}" for point in clean_memory_points[1:6])
    if clean_asset_points:
        lines.append("")
        lines.append("Supporting assets:")
        lines.extend(f"- {point}" for point in clean_asset_points[:6])
    return "\n".join(lines)[:8000]


def _extract_grounding_queries(grounding: object) -> list[str]:
    if not isinstance(grounding, dict):
        return []
    queries = grounding.get("webSearchQueries")
    if not isinstance(queries, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for query in queries:
        if not isinstance(query, str):
            continue
        normalized = query.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result[:8]


def _extract_grounding_sources(grounding: object) -> list[ResearchSource]:
    if not isinstance(grounding, dict):
        return []
    chunks = grounding.get("groundingChunks")
    if not isinstance(chunks, list):
        return []

    sources: list[ResearchSource] = []
    seen: set[str] = set()
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        web = chunk.get("web")
        if not isinstance(web, dict):
            continue
        url = str(web.get("uri") or "").strip()
        title = str(web.get("title") or url).strip()
        if not url:
            continue
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        sources.append(ResearchSource(title=title[:200], url=url[:1000]))
    return sources[:8]


def transcribe_audio(filename: str, audio_bytes: bytes) -> str:
    allow_placeholder = (
        os.getenv("ALLOW_PLACEHOLDER_TRANSCRIPT", "false").lower() == "true"
    )
    gemini_key = os.getenv("GEMINI_API_KEY")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    failure_reasons: list[str] = []

    if gemini_key:
        mime_types = [
            "audio/webm",
            "audio/webm;codecs=opus",
            "audio/ogg",
            "audio/mpeg",
            "audio/wav",
            "audio/mp4",
        ]
        if filename.lower().endswith(".wav"):
            mime_types = ["audio/wav"]
        elif filename.lower().endswith(".mp3"):
            mime_types = ["audio/mpeg"]
        elif filename.lower().endswith(".m4a"):
            mime_types = ["audio/mp4"]

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"
        encoded_audio = base64.b64encode(audio_bytes).decode("utf-8")

        for mime_type in mime_types:
            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": "Transcribe this audio exactly. Return plain text only."
                            },
                            {
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": encoded_audio,
                                }
                            },
                        ]
                    }
                ]
            }

            try:
                response = requests.post(
                    endpoint, params={"key": gemini_key}, json=payload, timeout=45
                )
            except Exception as exc:
                failure_reasons.append(f"Gemini exception: {str(exc)}")
                logger.exception("Gemini transcription request failed")
                continue

            if not response.ok:
                failure_reasons.append(
                    f"Gemini ({mime_type}) HTTP {response.status_code}: {response.text[:180]}"
                )
                continue

            data = response.json()
            text_parts = (
                data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            )
            text = " ".join(part.get("text", "") for part in text_parts).strip()
            if text:
                return text
            failure_reasons.append(f"Gemini ({mime_type}) returned empty transcription")

    if allow_placeholder:
        return (
            "My name is Alex. I remember last summer when my family and I drove our red car "
            "to the coast near Brighton. It felt joyful, but I cannot remember exactly what happened first."
        )

    raise HTTPException(
        status_code=502,
        detail=(
            "Transcription failed. Configure GEMINI_API_KEY to enable speech-to-text "
            "or set ALLOW_PLACEHOLDER_TRANSCRIPT=true for demo mode. "
            f"Details: {' | '.join(failure_reasons)[:800]}"
        ),
    )


def extract_metadata_with_gemini_function_call(
    transcript: str,
) -> Optional[MemoryMetadata]:
    gemini_key = os.getenv("GEMINI_API_KEY")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    if not gemini_key:
        return None

    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "Extract structured metadata from this memoir transcript. "
                            "You must call set_memory_metadata exactly once. "
                            "Use best-effort date precision: day, month, year, decade, approximate, or unknown. "
                            "Transcript:\n"
                            f"{transcript}"
                        )
                    }
                ]
            }
        ],
        "tools": [
            {
                "functionDeclarations": [
                    {
                        "name": "set_memory_metadata",
                        "description": "Set recorder, date granularity, and referenced people/locations for one memory.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "date_text": {"type": "string"},
                                "date_precision": {
                                    "type": "string",
                                    "enum": [
                                        "day",
                                        "month",
                                        "year",
                                        "decade",
                                        "approximate",
                                        "unknown",
                                    ],
                                },
                                "date_year": {"type": "integer"},
                                "date_month": {"type": "integer"},
                                "date_day": {"type": "integer"},
                                "date_decade": {"type": "integer"},
                                "recorder_name": {"type": "string"},
                                "people": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "locations": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": [
                                "date_text",
                                "date_precision",
                                "people",
                                "locations",
                            ],
                        },
                    }
                ]
            }
        ],
        "toolConfig": {
            "functionCallingConfig": {
                "mode": "ANY",
                "allowedFunctionNames": ["set_memory_metadata"],
            }
        },
    }

    try:
        response = requests.post(
            endpoint, params={"key": gemini_key}, json=payload, timeout=30
        )
        if not response.ok:
            logger.warning("Gemini metadata extraction failed: %s", response.text[:300])
            return None
        data = response.json()
    except Exception as exc:
        logger.warning("Gemini metadata request exception: %s", exc)
        return None

    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    for part in parts:
        function_call = part.get("functionCall")
        if not function_call or function_call.get("name") != "set_memory_metadata":
            continue

        args = function_call.get("args", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if not isinstance(args, dict):
            args = {}

        date_precision = str(args.get("date_precision") or "unknown").strip().lower()
        if date_precision not in {
            "day",
            "month",
            "year",
            "decade",
            "approximate",
            "unknown",
        }:
            date_precision = "unknown"

        date_year = _safe_int(args.get("date_year"))
        date_month = _safe_int(args.get("date_month"))
        date_day = _safe_int(args.get("date_day"))
        date_decade = _safe_int(args.get("date_decade"))

        sort_date = build_sort_date(
            date_precision, date_year, date_month, date_day, date_decade
        )
        people = normalize_string_list(_safe_string_list(args.get("people")))
        locations = normalize_string_list(_safe_string_list(args.get("locations")))

        recorder_name = str(args.get("recorder_name") or "").strip() or None
        date_text = str(args.get("date_text") or "unknown").strip() or "unknown"

        return MemoryMetadata(
            date_text=date_text[:100],
            date_precision=date_precision,
            sort_date=sort_date,
            date_year=date_year,
            date_month=date_month,
            date_day=date_day,
            date_decade=date_decade,
            recorder_name=recorder_name,
            people=people,
            locations=locations,
        )

    return None


def _safe_int(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            result.append(item)
    return result


def extract_text_from_document(filename: str, file_bytes: bytes, mime_type: str) -> str:
    """Use Gemini to extract memory-relevant content from a document or image.

    Returns a plain-text transcript suitable for further metadata extraction.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        raise HTTPException(status_code=502, detail="GEMINI_API_KEY not configured")

    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"
    encoded_data = base64.b64encode(file_bytes).decode("utf-8")

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "IMPORTANT: Your response must be plain text only. "
                            "Do NOT use any markdown formatting. "
                            "Do NOT use asterisks (*), double asterisks (**), underscores, pound signs (#), or backticks. "
                            "Do NOT bold or italicize any text. "
                            "Use only regular letters, numbers, hyphens, colons, and periods.\n\n"
                            "Analyze this uploaded document and write a 2-3 sentence plain-text summary of the most important facts: "
                            "who is involved, what action or order is described, key dates, units, roles, and any modifications. "
                            "Do not use first-person language. Do not frame it as a story or memory. "
                            "Clean up awkward wording and OCR noise, but do not invent facts. "
                            "If a date or value appears truncated or unclear, give a best-effort version and note it as uncertain. "
                            "Preserve full unit names and identifiers exactly as written. "
                            "Write only the 2-3 sentence summary. Do not add headers, bullet points, or any other structure."
                        )
                    },
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": encoded_data,
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
        },
    }

    try:
        response = requests.post(
            endpoint, params={"key": gemini_key}, json=payload, timeout=60
        )
        if not response.ok:
            raise HTTPException(
                status_code=502,
                detail=f"Gemini document analysis failed: {response.text[:300]}",
            )
        data = response.json()
        text_parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "\n".join(
            part.get("text", "").strip() for part in text_parts if part.get("text")
        ).strip()
        if not text:
            raise HTTPException(
                status_code=502,
                detail="Gemini returned empty analysis for document",
            )
        return text
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Document analysis request failed for %s", filename)
        raise HTTPException(
            status_code=502,
            detail=f"Document analysis failed: {str(exc)}",
        )


def _parse_photo_research_notes(raw_text: str) -> dict[int, str]:
    """Parse PHOTO_INDEX blocks from pass-1 text research notes.

    Expected format repeats blocks like:
    PHOTO_INDEX=1
    RESEARCH_NOTES: ...
    """
    notes_by_index: dict[int, str] = {}
    if not raw_text:
        return notes_by_index

    pattern = re.compile(r"PHOTO_INDEX=(\d+)\s*(.*?)(?=PHOTO_INDEX=\d+|\Z)", re.DOTALL)
    for match in pattern.finditer(raw_text):
        try:
            index_value = int(match.group(1))
        except (TypeError, ValueError):
            continue
        note_text = match.group(2).strip()
        if note_text.upper().startswith("RESEARCH_NOTES:"):
            note_text = note_text.split(":", 1)[1].strip()
        if note_text:
            notes_by_index[index_value] = note_text[:1500]
    return notes_by_index


def extract_text_from_photo_batch(
    photo_payloads: list[tuple[str, bytes, str] | tuple[str, bytes, str, str | None]],
) -> dict[int, "PhotoSummary"]:
    """Use a two-pass Gemini flow to summarize a batch of uploaded photos.

    Pass 1 runs plain-text research with web search enabled.
    Pass 2 consumes those notes and returns strict JSON summaries.

    The return value is keyed by 1-based photo index from `photo_payloads`.
    Each value is a PhotoSummary with structured visual/contextual analysis,
    plus title/place fields. Returns {} if Gemini is unavailable or parsing fails.
    """
    if not photo_payloads:
        return {}

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return {}

    # Allow photo analysis to use stronger models than the global default.
    research_model = (
        os.getenv("GEMINI_PHOTO_RESEARCH_MODEL")
        or os.getenv("GEMINI_RESEARCH_MODEL")
        or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    )
    structured_model = (
        os.getenv("GEMINI_PHOTO_STRUCTURED_MODEL")
        or os.getenv("GEMINI_PHOTO_MODEL")
        or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    )
    research_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{research_model}:generateContent"
    structured_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{structured_model}:generateContent"
    logger.info(
        "photo analysis models selected: photo_research_model=%s photo_structured_model=%s",
        research_model,
        structured_model,
    )

    today_date = datetime.now().strftime("%B %d, %Y")

    photo_parts_by_index: dict[int, list[dict]] = {}
    reverse_geocode_by_index: dict[int, str] = {}

    for index, payload in enumerate(photo_payloads, start=1):
        filename, file_bytes, mime_type = payload[0], payload[1], payload[2]
        metadata_hint = payload[3] if len(payload) > 3 else None
        reverse_geocode_name = _extract_metadata_field(
            metadata_hint, "reverse_geocode_location_name"
        )
        if reverse_geocode_name:
            reverse_geocode_by_index[index] = reverse_geocode_name
        photo_parts: list[dict] = [
            {"text": f"PHOTO_INDEX={index}; filename={filename}"}
        ]
        captured_at_hint = _extract_metadata_field(metadata_hint, "captured_at")
        if captured_at_hint:
            photo_parts.append({"text": f"PHOTO_CAPTURED_AT={captured_at_hint}"})
        gps_hint = _extract_metadata_field(metadata_hint, "gps")
        if gps_hint:
            photo_parts.append({"text": f"PHOTO_COORDINATES={gps_hint}"})
        if metadata_hint:
            photo_parts.append({"text": f"PHOTO_METADATA={metadata_hint}"})
        place_guess = (
            reverse_geocode_name
            or _extract_metadata_field(metadata_hint, "exif_place_name")
            or "Unknown"
        )
        date_guess = captured_at_hint or "Unknown"
        people_guess = _extract_metadata_field(metadata_hint, "people") or "Unknown"
        event_title = _extract_metadata_field(metadata_hint, "event_title")
        event_date_text = _extract_metadata_field(metadata_hint, "event_date_text")
        event_description = _extract_metadata_field(metadata_hint, "event_description")
        linked_memory_excerpt = _extract_metadata_field(
            metadata_hint, "linked_memory_excerpt"
        )
        period_title = _extract_metadata_field(metadata_hint, "period_title")

        context_lines: list[str] = [
            f"CONTEXT_PLACE={place_guess}",
            f"CONTEXT_DATE={date_guess}",
            f"KNOWN_PEOPLE={people_guess}",
        ]
        if event_title:
            context_lines.append(f"LINKED_EVENT_TITLE={event_title}")
        if event_date_text:
            context_lines.append(f"LINKED_EVENT_DATE={event_date_text}")
        if event_description:
            context_lines.append(f"LINKED_EVENT_DESCRIPTION={event_description}")
        if period_title:
            context_lines.append(f"LINKED_PERIOD={period_title}")
        if linked_memory_excerpt:
            context_lines.append(f"LINKED_MEMORY={linked_memory_excerpt}")

        if (
            place_guess == "Unknown"
            and date_guess == "Unknown"
            and people_guess == "Unknown"
        ):
            context_lines.append(
                "ANALYSIS_MODE=No metadata available. Infer from visual evidence and research only."
            )
        elif event_title or linked_memory_excerpt:
            context_lines.append(
                "ANALYSIS_MODE=Use linked event/memory context as strong user-provided evidence unless visual evidence clearly conflicts."
            )
        else:
            context_lines.append(
                "ANALYSIS_MODE=Use available metadata as hints; validate against visual evidence."
            )

        photo_parts.append({"text": "\n".join(context_lines)})
        photo_parts.append(
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(file_bytes).decode("utf-8"),
                }
            }
        )
        photo_parts_by_index[index] = photo_parts

    research_notes_by_index: dict[int, str] = {}
    research_parts: list[dict] = [
        {
            "text": (
                "You are a forensic visual research analyst. For each photo, identify the most specific real-world details visible, "
                "then use web search to verify and enrich those findings.\n\n"
                "Prioritize high-value identifiers when present:\n"
                "- Naval/air/vehicle identifiers (hull numbers, tail numbers, registrations, unit marks)\n"
                "- Specific hardware/equipment models and likely purpose\n"
                "- Signs, plaques, logos, uniforms, insignia, and landmarks\n"
                "- Time/place context: what documented events, missions, games, performances, incidents, or operations were occurring there then\n\n"
                "When LINKED_EVENT or LINKED_MEMORY context is provided, treat it as strong user-provided context and use it to guide search terms.\n"
                "Do not return JSON.\n\n"
                "Return exactly this repeated block format:\n"
                "PHOTO_INDEX=<index>\n"
                "RESEARCH_NOTES: 5-12 sentences with concrete findings, grounded hypotheses, and what evidence supports each claim."
            )
        }
    ]
    for index in sorted(photo_parts_by_index):
        research_parts.extend(photo_parts_by_index[index])

    research_payload = {
        "contents": [{"parts": research_parts}],
        "tools": [{"googleSearch": {"searchTypes": {"webSearch": {}}}}],
        "generationConfig": {
            "temperature": 1.0,
            "maxOutputTokens": 3000,
            "responseMimeType": "text/plain",
        },
    }

    try:
        research_response = requests.post(
            research_endpoint,
            params={"key": gemini_key},
            json=research_payload,
            timeout=90,
        )
        if research_response.ok:
            research_data = research_response.json()
            research_text_parts = (
                research_data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [])
            )
            raw_research_text = "\n".join(
                part.get("text", "").strip()
                for part in research_text_parts
                if part.get("text")
            ).strip()
            if raw_research_text:
                research_notes_by_index = _parse_photo_research_notes(raw_research_text)
        else:
            logger.warning(
                "Gemini photo research pass failed: %s", research_response.text[:300]
            )
    except Exception as exc:
        logger.warning("Gemini photo research pass exception: %s", exc)

    parts: list[dict] = [
        {
            "text": (
                "You are a structured distiller for memoir photo analysis. Convert the image evidence and WEB_RESEARCH_NOTES into the required JSON schema. "
                f"Today's date for context is {today_date}. Use context fields (place/date/people/event/memory) as hints, and preserve concrete identifiers from research notes. "
                "Do not invent unsupported facts. If metadata and visual/research evidence conflict, explain that in discrepancy_flag.\n\n"
                "Return JSON fields for each photo:\n"
                "- suggested_title: 4-8 words, specific and descriptive, and include the most identifiable entity when known.\n"
                "- assessed_place: the most specific defensible place (prefer specific venue/base/pier/site over city-level labels when supported).\n"
                "- visual_evidence: 1-2 sentences of observable facts only.\n"
                "- contextual_narrative: 3-5 sentences integrating strongest IDs, likely scene purpose, and historical/social context relevant to the provided date/place.\n"
                "- discrepancy_flag: metadata conflicts or competing interpretations; empty string if none.\n\n"
                "Use the exact photo index provided before each image."
            )
        }
    ]
    for index in sorted(photo_parts_by_index):
        note = research_notes_by_index.get(index)
        for part in photo_parts_by_index[index]:
            if note and "inline_data" in part:
                parts.append({"text": f"WEB_RESEARCH_NOTES={note}"})
            parts.append(part)

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "index": {
                                    "type": "integer",
                                    "description": "1-based photo index matching the PHOTO_INDEX provided",
                                },
                                "summary": {
                                    "type": "string",
                                    "description": "Legacy fallback summary field; may be empty when contextual_narrative is provided",
                                },
                                "suggested_title": {
                                    "type": "string",
                                    "description": "Short descriptive title for this photo, 4-8 words, suitable as an asset label",
                                },
                                "assessed_place": {
                                    "type": "string",
                                    "description": "Most specific defensible named place, prioritizing PHOTO_COORDINATES when present; empty string only when no specific place can be inferred",
                                },
                                "visual_evidence": {
                                    "type": "string",
                                    "description": "One or two sentences of strictly observable visual facts, with specific object/equipment identification (not generic shape descriptors) and notable details like colors, text, insignia",
                                },
                                "contextual_narrative": {
                                    "type": "string",
                                    "description": "Three to five sentences synthesizing people, place, time, and operational context. For each significant object or activity, answer: what is it? why would it be present on this date at this location? What operation or situation does it suggest?",
                                },
                                "discrepancy_flag": {
                                    "type": "string",
                                    "description": "Metadata conflict note, or empty string when no conflict",
                                },
                            },
                            "required": [
                                "index",
                                "suggested_title",
                                "assessed_place",
                                "visual_evidence",
                                "contextual_narrative",
                                "discrepancy_flag",
                            ],
                        },
                    }
                },
                "required": ["items"],
            },
        },
    }

    try:
        response = requests.post(
            structured_endpoint, params={"key": gemini_key}, json=payload, timeout=90
        )
        if not response.ok:
            logger.warning(
                "Gemini photo batch extraction failed: %s", response.text[:300]
            )
            return {}
        data = response.json()
        text_parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        raw_text = "\n".join(
            part.get("text", "").strip() for part in text_parts if part.get("text")
        ).strip()
        if not raw_text:
            return {}

        parsed = json.loads(raw_text)
        items = parsed.get("items", []) if isinstance(parsed, dict) else []
        result: dict[int, PhotoSummary] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            index_value = item.get("index")
            if not isinstance(index_value, int):
                continue
            legacy_summary = str(item.get("summary") or "").strip()
            raw_visual_evidence = str(item.get("visual_evidence") or "").strip()
            raw_contextual_narrative = str(
                item.get("contextual_narrative") or ""
            ).strip()
            if not raw_contextual_narrative and legacy_summary:
                raw_contextual_narrative = legacy_summary
            if not raw_contextual_narrative and not raw_visual_evidence:
                continue
            raw_title = str(item.get("suggested_title") or "").strip()
            suggested_title: Optional[str] = raw_title[:180] if raw_title else None
            raw_assessed_place = str(item.get("assessed_place") or "").strip()
            assessed_place: Optional[str] = (
                raw_assessed_place[:200] if raw_assessed_place else None
            )
            raw_discrepancy_flag = str(item.get("discrepancy_flag") or "").strip()
            discrepancy_flag: Optional[str] = (
                raw_discrepancy_flag[:300] if raw_discrepancy_flag else None
            )
            reverse_geocode_name = reverse_geocode_by_index.get(index_value)
            # Avoid storing a duplicate city/state/country as "assessed place" when Gemini echoes reverse geocode output.
            if (
                assessed_place
                and reverse_geocode_name
                and assessed_place.casefold() == reverse_geocode_name.casefold()
            ):
                assessed_place = None
            result[index_value] = PhotoSummary(
                summary=raw_contextual_narrative[:1200],
                suggested_title=suggested_title,
                assessed_place=assessed_place,
                visual_evidence=raw_visual_evidence[:500] or None,
                contextual_narrative=raw_contextual_narrative[:1200] or None,
                discrepancy_flag=discrepancy_flag,
            )
        return result
    except Exception as exc:
        logger.warning("Gemini photo batch extraction exception: %s", exc)
        return {}


def generate_period_biography(
    period_title: str,
    year_range: str,
    event_titles: list[str],
    event_descriptions: list[str],
    event_date_texts: list[str],
    asset_count: int,
) -> Optional[str]:
    """Use Gemini to write a short biography-style narrative paragraph for a life period.

    Returns None if Gemini is unavailable or fails, so the caller can fall back
    to the template-based summary.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return None

    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"

    # Build a concise bullet list of events for the prompt, including dates when known
    event_lines = []
    for title, desc, date_text in zip(
        event_titles, event_descriptions, event_date_texts
    ):
        date_label = f" [{date_text}]" if date_text else ""
        if desc and desc.strip():
            event_lines.append(f"- {title}{date_label}: {desc.strip()[:300]}")
        else:
            event_lines.append(f"- {title}{date_label}")
    events_block = "\n".join(event_lines) if event_lines else "(no events recorded yet)"

    prompt = (
        "You are writing a biography-style narrative for a chapter in a personal memoir.\n\n"
        f"Chapter title: {period_title}\n"
        f"Time period: {year_range}\n"
        f"Number of supporting photos/documents: {asset_count}\n\n"
        "Key events in this chapter (listed in chronological order — dates in brackets where known):\n"
        f"{events_block}\n\n"
        "Write a rich, flowing narrative in the style of a warm personal biography. Rules:\n"
        "- Write in third person (use 'he', 'she', or 'they' — infer from context, default to 'they' if unclear)\n"
        "- Weave all the events into connected prose — do NOT list them as bullets\n"
        "- Preserve the chronological sequence of events exactly as listed above — do not reorder them\n"
        "- Use the actual names of places, schools, organisations, and people mentioned in the events\n"
        "- Write as many paragraphs as the material warrants — this may become a full memoir chapter\n"
        "- Always end on a complete sentence\n"
        "- Plain text only — no markdown, no asterisks, no bullet points, no headers"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7},
    }

    try:
        response = requests.post(
            endpoint, params={"key": gemini_key}, json=payload, timeout=30
        )
        if not response.ok:
            logger.warning("Period biography request failed: %s", response.text[:200])
            return None
        data = response.json()
        candidate = data.get("candidates", [{}])[0]
        finish_reason = candidate.get("finishReason", "UNKNOWN")
        if finish_reason not in ("STOP", "UNKNOWN"):
            logger.warning(
                "Period biography finish reason: %s — output may be truncated",
                finish_reason,
            )
        parts = candidate.get("content", {}).get("parts", [])
        text = "\n".join(
            p.get("text", "").strip() for p in parts if p.get("text")
        ).strip()
        if not text:
            return None
        # Strip any accidental markdown bold/italic
        text = text.replace("**", "").replace("*", "").replace("__", "")
        return text
    except Exception as exc:
        logger.warning("Period biography generation failed: %s", exc)
        return None
