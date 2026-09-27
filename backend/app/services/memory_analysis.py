import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class MemoryMetadata:
    date_text: str = "unknown"
    date_precision: str = "unknown"
    sort_date: Optional[date] = None
    date_year: Optional[int] = None
    date_month: Optional[int] = None
    date_day: Optional[int] = None
    date_decade: Optional[int] = None
    recorder_name: Optional[str] = None
    people: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)


def normalize_string_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        candidate = (item or "").strip()
        if not candidate:
            continue
        if len(candidate) > 80:
            candidate = candidate[:80].rstrip()
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(candidate)
    return cleaned


def build_sort_date(
    date_precision: str,
    date_year: Optional[int],
    date_month: Optional[int],
    date_day: Optional[int],
    date_decade: Optional[int],
) -> Optional[date]:
    try:
        if date_precision == "day" and date_year and date_month and date_day:
            return date(date_year, date_month, date_day)
        if date_precision == "month" and date_year and date_month:
            return date(date_year, date_month, 1)
        if date_precision in {"year", "approximate"} and date_year:
            return date(date_year, 1, 1)
        if date_precision == "decade" and date_decade:
            return date(date_decade, 1, 1)
    except ValueError:
        return None
    return None


def fallback_metadata_from_transcript(transcript: str) -> MemoryMetadata:
    lowered = transcript.lower()
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", transcript)
    if year_match:
        year = int(year_match.group(1))
        return MemoryMetadata(
            date_text=f"{year}",
            date_precision="year",
            sort_date=date(year, 1, 1),
            date_year=year,
            recorder_name=extract_recorder_name(transcript),
            people=extract_people(transcript),
            locations=extract_locations(transcript),
        )

    decade_match = re.search(r"\b(19\d0|20\d0)s\b", lowered)
    if decade_match:
        decade = int(decade_match.group(1))
        return MemoryMetadata(
            date_text=f"{decade}s",
            date_precision="decade",
            sort_date=date(decade, 1, 1),
            date_decade=decade,
            recorder_name=extract_recorder_name(transcript),
            people=extract_people(transcript),
            locations=extract_locations(transcript),
        )

    if "last summer" in lowered:
        year = datetime.utcnow().year - 1
        return MemoryMetadata(
            date_text="last summer",
            date_precision="approximate",
            sort_date=date(year, 6, 1),
            date_year=year,
            recorder_name=extract_recorder_name(transcript),
            people=extract_people(transcript),
            locations=extract_locations(transcript),
        )

    return MemoryMetadata(
        date_text="unknown",
        date_precision="unknown",
        recorder_name=extract_recorder_name(transcript),
        people=extract_people(transcript),
        locations=extract_locations(transcript),
    )


def detect_emotional_tone(transcript: str) -> str:
    lowered = transcript.lower()
    if any(
        word in lowered for word in ["happy", "joy", "joyful", "excited", "grateful"]
    ):
        return "positive"
    if any(word in lowered for word in ["sad", "angry", "upset", "scared", "afraid"]):
        return "negative"
    if any(word in lowered for word in ["nostalgic", "remember", "miss"]):
        return "reflective"
    return "neutral"


def summarize_event(transcript: str) -> str:
    sentence = transcript.strip().split(".")[0].strip()
    if not sentence:
        return "Unspecified memory"
    return sentence[:180]


def build_default_narration_title(recorder_name: Optional[str]) -> str:
    name = (recorder_name or "").strip()
    if not name:
        return "Narration of this memory"
    if name.endswith(("s", "S")):
        return f"{name}' Narration of this memory"
    return f"{name}'s Narration of this memory"


def generate_follow_up_question(
    transcript: str, event_description: str, metadata: MemoryMetadata
) -> str:
    if not metadata.recorder_name:
        return "What name would you like attached to this memory card as the recorder?"
    if not metadata.locations:
        return "Where did this memory happen, or what place is most connected to it?"
    if metadata.date_precision == "unknown":
        return (
            "When was this memory from as best you can remember: exact date, month, year, "
            "or even just the decade?"
        )

    lowered = transcript.lower()
    if "car" in lowered:
        return "You mentioned that car memory. What detail from the trip still feels vivid today?"
    return f"You shared: '{event_description}'. Who else was there, and how did they shape this memory?"


RELATIONSHIP_PATTERNS: list[tuple[str, str]] = [
    (r"\bson\b", "You mentioned your son. What is his name, and when was he born?"),
    (
        r"\bdaughter\b",
        "You mentioned your daughter. What is her name, and when was she born?",
    ),
    (
        r"\bwife\b",
        "You mentioned your wife. How did you two meet, and when did you get married?",
    ),
    (
        r"\bhusband\b",
        "You mentioned your husband. How did you two meet, and when did you get married?",
    ),
    (
        r"\bmother\b|\bmom\b|\bmum\b",
        "You mentioned your mother. Where was she from and what was she like?",
    ),
    (
        r"\bfather\b|\bdad\b",
        "You mentioned your father. What do you remember most about him?",
    ),
]


def generate_questions_from_memory(
    transcript: str, event_description: str, metadata: MemoryMetadata
) -> list[str]:
    questions: list[str] = []
    lowered = transcript.lower()

    if not metadata.recorder_name:
        questions.append(
            "Before we continue, what should we call you on your memory cards?"
        )

    if not metadata.locations:
        questions.append(
            "Where did this memory happen, or which place does it belong to?"
        )

    if metadata.date_precision == "unknown":
        questions.append(
            "When was this memory from as best you can remember: day, month, year, or decade?"
        )

    for pattern, question in RELATIONSHIP_PATTERNS:
        if len(questions) >= 3:
            break
        if re.search(pattern, lowered):
            questions.append(question)

    if not questions:
        short_desc = event_description[:120].rstrip()
        questions.append(
            f"You shared: '{short_desc}'. What happened just before this moment that helps place it in your life?"
        )

    return questions[:3]


def extract_recorder_name(transcript: str) -> Optional[str]:
    patterns = [
        r"\bmy name is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"\bi am\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"\bi'm\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, transcript)
        if match:
            return match.group(1).strip()
    return None


def extract_people(transcript: str) -> list[str]:
    common = {
        "I",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
        "The",
        "A",
        "An",
        "We",
        "He",
        "She",
        "They",
        "It",
        "But",
        "And",
        "Or",
        "So",
        "Yet",
        "For",
        "Nor",
    }
    names: list[str] = []
    for word in transcript.split():
        clean = re.sub(r"[^a-zA-Z'-]", "", word)
        if clean and clean[0].isupper() and clean not in common and len(clean) > 2:
            names.append(clean)
    return normalize_string_list(names)


def extract_locations(transcript: str) -> list[str]:
    locations: list[str] = []
    for match in re.finditer(
        r"\b(?:in|at|to|from|near)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", transcript
    ):
        locations.append(match.group(1))
    return normalize_string_list(locations)
