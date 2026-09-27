"""Reverse geocoding via OpenStreetMap Nominatim (free, no API key required).

Results are cached in-process by rounded coordinates (~100 m grid) to avoid
redundant network calls during batch photo imports.
"""

import logging
from typing import Optional, TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
_USER_AGENT = "Memoir/1.0 (personal memoir app)"
_CACHE: dict[tuple[float, float], Optional[str]] = {}
_CACHE_PRECISION = 3  # decimal places → ~111 m resolution


def _cache_key(lat: float, lon: float) -> tuple[float, float]:
    return (round(lat, _CACHE_PRECISION), round(lon, _CACHE_PRECISION))


def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """Return a human-readable place name (e.g. 'Tulsa, Oklahoma, US') or None."""
    key = _cache_key(lat, lon)
    if key in _CACHE:
        return _CACHE[key]

    name: Optional[str] = None
    try:
        response = requests.get(
            _NOMINATIM_URL,
            params={"lat": lat, "lon": lon, "format": "json"},
            headers={"User-Agent": _USER_AGENT},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        address = data.get("address", {})

        city = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("hamlet")
            or address.get("county")
        )
        state = address.get("state")
        country_code = (address.get("country_code") or "").upper()

        parts = [p for p in [city, state, country_code] if p]
        name = ", ".join(parts) if parts else None
    except Exception:
        logger.debug("Reverse geocode failed for (%s, %s)", lat, lon, exc_info=True)

    # Cache only successful lookups so transient API/network failures can retry later.
    if name:
        _CACHE[key] = name
    return name


def backfill_asset_location_names(db: "Session") -> None:
    """One-time backfill: geocode assets that have GPS coords but no reverse-geocoded locality."""
    from sqlalchemy import text

    rows = db.execute(
        text(
            "SELECT id, gps_latitude, gps_longitude FROM assets "
            "WHERE gps_latitude IS NOT NULL AND gps_longitude IS NOT NULL "
            "AND (reverse_geocode_location_name IS NULL OR reverse_geocode_location_name = '')"
        )
    ).fetchall()

    if not rows:
        return

    logger.info(
        "Backfilling reverse_geocode_location_name for %d asset(s)...", len(rows)
    )
    updated = 0
    for row in rows:
        asset_id, lat, lon = row[0], row[1], row[2]
        name = reverse_geocode(lat, lon)
        if name:
            db.execute(
                text(
                    "UPDATE assets "
                    "SET reverse_geocode_location_name = :name, "
                    "location_name = COALESCE(location_name, :name) "
                    "WHERE id = :id"
                ),
                {"name": name, "id": asset_id},
            )
            updated += 1

    if updated:
        db.commit()
    logger.info("Backfilled reverse_geocode_location_name for %d asset(s).", updated)
