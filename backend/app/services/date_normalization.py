import re
from calendar import monthrange
from datetime import date, datetime
from typing import Optional


_SEASON_MONTH_RANGES: dict[str, tuple[int, int]] = {
    "spring": (3, 5),
    "summer": (6, 8),
    "fall": (9, 11),
    "autumn": (9, 11),
    "winter": (12, 2),
}


def clean_date_text(value: Optional[str], *, max_len: int = 100) -> Optional[str]:
    text = (value or "").strip()
    if not text:
        return None
    return text[:max_len].rstrip()


def _last_day(year: int, month: int) -> int:
    return monthrange(year, month)[1]


def _parse_with_formats(text: str) -> tuple[Optional[date], Optional[date]]:
    # Explicit date formats map to the same start and end day.
    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
        "%d %B %Y",
    ):
        try:
            parsed = datetime.strptime(text, fmt).date()
            return parsed, parsed
        except ValueError:
            continue

    # Month-year text maps to the full month range.
    for fmt in ("%b %Y", "%B %Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            start = date(parsed.year, parsed.month, 1)
            end = date(parsed.year, parsed.month, _last_day(parsed.year, parsed.month))
            return start, end
        except ValueError:
            continue

    return None, None


def _strip_ordinal_suffixes(text: str) -> str:
    return re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE)


def _month_name_to_number(month_name: str) -> Optional[int]:
    normalized = month_name.strip().lower()[:3]
    table = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    return table.get(normalized)


def _parse_month_day_range(text: str) -> tuple[Optional[date], Optional[date]]:
    cleaned = _strip_ordinal_suffixes(text)

    full_range_match = re.search(
        (
            r"\b([A-Za-z]+)\s+(\d{1,2})\s*(?:-|to|through|until|\u2013|\u2014)\s*"
            r"([A-Za-z]+)\s+(\d{1,2}),?\s*(19\d{2}|20\d{2})\b"
        ),
        cleaned,
        flags=re.IGNORECASE,
    )
    if full_range_match:
        start_month = _month_name_to_number(full_range_match.group(1))
        start_day = int(full_range_match.group(2))
        end_month = _month_name_to_number(full_range_match.group(3))
        end_day = int(full_range_match.group(4))
        year = int(full_range_match.group(5))
        if start_month and end_month:
            try:
                start = date(year, start_month, start_day)
                end = date(year, end_month, end_day)
                return (start, end) if start <= end else (end, start)
            except ValueError:
                return None, None

    same_month_range_match = re.search(
        (
            r"\b([A-Za-z]+)\s+(\d{1,2})\s*(?:-|to|through|until|\u2013|\u2014)\s*"
            r"(\d{1,2}),?\s*(19\d{2}|20\d{2})\b"
        ),
        cleaned,
        flags=re.IGNORECASE,
    )
    if same_month_range_match:
        month = _month_name_to_number(same_month_range_match.group(1))
        first_day = int(same_month_range_match.group(2))
        second_day = int(same_month_range_match.group(3))
        year = int(same_month_range_match.group(4))
        if month:
            start_day = min(first_day, second_day)
            end_day = max(first_day, second_day)
            try:
                return date(year, month, start_day), date(year, month, end_day)
            except ValueError:
                return None, None

    month_day_match = re.search(
        r"\b([A-Za-z]+)\s+(\d{1,2}),?\s*(19\d{2}|20\d{2})\b",
        cleaned,
        flags=re.IGNORECASE,
    )
    if month_day_match:
        month = _month_name_to_number(month_day_match.group(1))
        day = int(month_day_match.group(2))
        year = int(month_day_match.group(3))
        if month:
            try:
                parsed = date(year, month, day)
                return parsed, parsed
            except ValueError:
                return None, None

    return None, None


def parse_text_date_range(text: Optional[str]) -> tuple[Optional[date], Optional[date]]:
    cleaned = (text or "").strip()
    if not cleaned:
        return None, None

    iso_candidate = cleaned.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_candidate).date()
        return parsed, parsed
    except ValueError:
        pass

    by_format_start, by_format_end = _parse_with_formats(cleaned)
    if by_format_start or by_format_end:
        return by_format_start, by_format_end

    # Retry format parsing after stripping ordinal suffixes (e.g. "16th July 2007" -> "16 July 2007").
    stripped = _strip_ordinal_suffixes(cleaned)
    if stripped != cleaned:
        by_format_start, by_format_end = _parse_with_formats(stripped)
        if by_format_start or by_format_end:
            return by_format_start, by_format_end

    month_day_start, month_day_end = _parse_month_day_range(cleaned)
    if month_day_start or month_day_end:
        return month_day_start, month_day_end

    year_range_match = re.search(
        r"\b(19\d{2}|20\d{2})\s*(?:-|to|through|until|\u2013|\u2014)\s*(19\d{2}|20\d{2})\b",
        cleaned,
        flags=re.IGNORECASE,
    )
    if year_range_match:
        first = int(year_range_match.group(1))
        second = int(year_range_match.group(2))
        start_year = min(first, second)
        end_year = max(first, second)
        return date(start_year, 1, 1), date(end_year, 12, 31)

    season_match = re.search(
        r"\b(spring|summer|fall|autumn|winter)\s+(19\d{2}|20\d{2})\b",
        cleaned,
        flags=re.IGNORECASE,
    )
    if season_match:
        season = season_match.group(1).lower()
        year = int(season_match.group(2))
        start_month, end_month = _SEASON_MONTH_RANGES[season]
        if season == "winter":
            start = date(year, 12, 1)
            end = date(year + 1, 2, _last_day(year + 1, 2))
            return start, end
        start = date(year, start_month, 1)
        end = date(year, end_month, _last_day(year, end_month))
        return start, end

    decade_match = re.search(r"\b(19\d0|20\d0)s\b", cleaned, flags=re.IGNORECASE)
    if decade_match:
        decade = int(decade_match.group(1))
        return date(decade, 1, 1), date(decade + 9, 12, 31)

    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", cleaned)
    if year_match:
        year = int(year_match.group(1))
        return date(year, 1, 1), date(year, 12, 31)

    return None, None


def resolve_start_end_dates(
    start_text: Optional[str],
    end_text: Optional[str],
) -> tuple[Optional[date], Optional[date]]:
    parsed_start, parsed_end_from_start = parse_text_date_range(start_text)
    parsed_start_from_end, parsed_end = parse_text_date_range(end_text)

    start_sort = parsed_start or parsed_start_from_end
    end_sort = parsed_end or parsed_end_from_start

    has_explicit_end = bool((end_text or "").strip())

    if not has_explicit_end and start_sort is not None:
        end_sort = start_sort

    if start_sort and end_sort and start_sort > end_sort:
        start_sort, end_sort = end_sort, start_sort

    return start_sort, end_sort
