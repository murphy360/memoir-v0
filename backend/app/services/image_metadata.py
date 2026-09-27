import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Optional

from PIL import ExifTags, Image

from app.services.geocoding import reverse_geocode


PHOTO_MAX_DIMENSION: int = int(os.environ.get("PHOTO_MAX_DIMENSION", "2048"))
PHOTO_JPEG_QUALITY: int = int(os.environ.get("PHOTO_JPEG_QUALITY", "85"))

EXIF_TAGS = ExifTags.TAGS
GPS_TAGS = ExifTags.GPSTAGS


@dataclass
class ImageMetadata:
    captured_at: Optional[datetime] = None
    captured_at_text: Optional[str] = None
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    exif_place_name: Optional[str] = None
    reverse_geocode_location_name: Optional[str] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    lens_model: Optional[str] = None
    orientation: Optional[int] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    exif_json: Optional[str] = None


def _to_float(value: Any) -> Optional[float]:
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            denominator = float(value.denominator)
            if denominator == 0:
                return None
            return float(value.numerator) / denominator
        if isinstance(value, tuple) and len(value) == 2:
            numerator = float(value[0])
            denominator = float(value[1])
            if denominator == 0:
                return None
            return numerator / denominator
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return None


def _dms_to_decimal(dms: Any, ref: Optional[str]) -> Optional[float]:
    if not isinstance(dms, (list, tuple)) or len(dms) != 3:
        return None

    degrees = _to_float(dms[0])
    minutes = _to_float(dms[1])
    seconds = _to_float(dms[2])
    if degrees is None or minutes is None or seconds is None:
        return None

    decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
    if (ref or "").upper() in {"S", "W"}:
        decimal *= -1.0
    return round(decimal, 7)


def _coerce_text(value: Any, max_len: int = 120) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_len:
        text = text[:max_len].rstrip()
    return text


def _parse_exif_datetime(
    raw: Optional[str], offset_raw: Optional[str]
) -> tuple[Optional[datetime], Optional[str]]:
    if not raw:
        return None, None

    cleaned = raw.strip().replace("\x00", "")
    if not cleaned:
        return None, None

    parsed: Optional[datetime] = None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(cleaned, fmt)
            break
        except ValueError:
            continue

    if not parsed:
        return None, cleaned

    offset_text = (offset_raw or "").strip()
    if offset_text:
        normalized_offset = offset_text.replace(" ", "")
        if len(normalized_offset) == 6 and normalized_offset[3] == ":":
            if normalized_offset[0] in {"+", "-"}:
                try:
                    parsed_with_tz = datetime.fromisoformat(
                        f"{parsed.isoformat()}{normalized_offset}"
                    )
                    utc_value = parsed_with_tz.astimezone(timezone.utc).replace(
                        tzinfo=None
                    )
                    return utc_value, parsed_with_tz.isoformat()
                except ValueError:
                    pass

    return parsed, cleaned


def _build_exif_dump(exif_data: dict[str, Any]) -> Optional[str]:
    if not exif_data:
        return None

    serializable: dict[str, Any] = {}
    for key, value in exif_data.items():
        try:
            json.dumps(value)
            serializable[key] = value
        except (TypeError, ValueError):
            serializable[key] = str(value)

    raw = json.dumps(serializable, ensure_ascii=True)
    return raw if raw else None


def compress_photo_for_storage(
    file_bytes: bytes,
    content_type: Optional[str],
    *,
    max_dimension: int = PHOTO_MAX_DIMENSION,
    jpeg_quality: int = PHOTO_JPEG_QUALITY,
) -> tuple[bytes, str]:
    """Resize and re-encode a photo if it exceeds max_dimension.

    Returns (compressed_bytes, new_content_type). If the image is already
    within the size limit and is a supported format, the original bytes and
    content_type are returned unchanged.
    """
    if not (content_type or "").lower().startswith("image/"):
        return file_bytes, content_type or "application/octet-stream"

    try:
        with Image.open(BytesIO(file_bytes)) as img:
            w, h = img.size
            needs_resize = max(w, h) > max_dimension
            is_jpeg = img.format == "JPEG"

            if not needs_resize and is_jpeg:
                # Already a JPEG within bounds — return as-is
                return file_bytes, "image/jpeg"

            if needs_resize:
                img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

            # Convert palette / RGBA modes that JPEG can't handle
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # Preserve EXIF bytes when available so downstream tools still see them
            exif_bytes = img.info.get("exif", b"")

            buf = BytesIO()
            save_kwargs: dict = {
                "format": "JPEG",
                "quality": jpeg_quality,
                "optimize": True,
            }
            if exif_bytes:
                save_kwargs["exif"] = exif_bytes
            img.save(buf, **save_kwargs)
            return buf.getvalue(), "image/jpeg"
    except Exception:
        # If anything goes wrong, fall back to the original bytes
        return file_bytes, content_type or "image/jpeg"


def extract_image_metadata(
    file_bytes: bytes, content_type: Optional[str], *, skip_geocoding: bool = False
) -> ImageMetadata:
    if not (content_type or "").lower().startswith("image/"):
        return ImageMetadata()

    metadata = ImageMetadata()

    try:
        with Image.open(BytesIO(file_bytes)) as image:
            metadata.image_width = image.width
            metadata.image_height = image.height

            exif_raw = image.getexif()
            if not exif_raw:
                return metadata

            exif: dict[str, Any] = {}
            for tag_id, value in exif_raw.items():
                name = EXIF_TAGS.get(tag_id, str(tag_id))
                exif[name] = value

            metadata.camera_make = _coerce_text(exif.get("Make"))
            metadata.camera_model = _coerce_text(exif.get("Model"))
            metadata.lens_model = _coerce_text(exif.get("LensModel"))

            orientation_value = exif.get("Orientation")
            if isinstance(orientation_value, int):
                metadata.orientation = orientation_value

            raw_capture = _coerce_text(
                exif.get("DateTimeOriginal"), max_len=64
            ) or _coerce_text(exif.get("DateTime"), max_len=64)
            raw_offset = _coerce_text(exif.get("OffsetTimeOriginal"), max_len=12)
            captured_at, captured_text = _parse_exif_datetime(raw_capture, raw_offset)
            metadata.captured_at = captured_at
            metadata.captured_at_text = captured_text

            GPS_IFD_TAG = 0x8825
            gps_ifd = exif_raw.get_ifd(GPS_IFD_TAG)
            if gps_ifd:
                gps: dict[str, Any] = {}
                for gps_tag_id, value in gps_ifd.items():
                    gps_name = GPS_TAGS.get(gps_tag_id, str(gps_tag_id))
                    gps[gps_name] = value

                metadata.gps_latitude = _dms_to_decimal(
                    gps.get("GPSLatitude"),
                    _coerce_text(gps.get("GPSLatitudeRef"), max_len=2),
                )
                metadata.gps_longitude = _dms_to_decimal(
                    gps.get("GPSLongitude"),
                    _coerce_text(gps.get("GPSLongitudeRef"), max_len=2),
                )
                metadata.exif_place_name = _coerce_text(
                    gps.get("GPSAreaInformation"), max_len=200
                )

                if (
                    metadata.gps_latitude is not None
                    and metadata.gps_longitude is not None
                    and not skip_geocoding
                ):
                    metadata.reverse_geocode_location_name = reverse_geocode(
                        metadata.gps_latitude, metadata.gps_longitude
                    )

                if gps:
                    exif["GPSInfo"] = {key: str(value) for key, value in gps.items()}

            metadata.exif_json = _build_exif_dump(exif)
    except Exception:
        return metadata

    return metadata


def apply_image_metadata_to_asset(asset: Any, metadata: ImageMetadata) -> None:
    asset.captured_at = metadata.captured_at
    asset.captured_end_at = metadata.captured_at
    asset.captured_at_text = metadata.captured_at_text
    asset.gps_latitude = metadata.gps_latitude
    asset.gps_longitude = metadata.gps_longitude
    asset.exif_place_name = metadata.exif_place_name
    asset.reverse_geocode_location_name = metadata.reverse_geocode_location_name
    asset.location_name = (
        metadata.reverse_geocode_location_name or metadata.exif_place_name
    )
    asset.camera_make = metadata.camera_make
    asset.camera_model = metadata.camera_model
    asset.lens_model = metadata.lens_model
    asset.orientation = metadata.orientation
    asset.image_width = metadata.image_width
    asset.image_height = metadata.image_height
    asset.exif_json = metadata.exif_json


def extract_and_apply_image_metadata(
    asset: Any,
    file_bytes: bytes,
    content_type: Optional[str],
    *,
    skip_geocoding: bool = False,
) -> None:
    metadata = extract_image_metadata(
        file_bytes, content_type, skip_geocoding=skip_geocoding
    )
    apply_image_metadata_to_asset(asset, metadata)
