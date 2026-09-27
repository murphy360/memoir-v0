from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import UploadFile


def _guess_extension(filename: str, content_type: Optional[str]) -> str:
    lower_name = filename.lower()
    if "." in lower_name:
        candidate = lower_name.rsplit(".", 1)[1]
        if candidate in {"pdf", "jpg", "jpeg", "png", "gif", "webp", "txt"}:
            return f".{candidate}"

    content_map = {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "text/plain": ".txt",
    }
    return content_map.get((content_type or "").lower(), ".bin")


def save_document_file(
    upload: UploadFile, file_bytes: bytes, storage_dir: Path
) -> tuple[str, Optional[str], int, str]:
    content_type = (upload.content_type or "").split(";")[0].strip().lower() or None
    extension = _guess_extension(upload.filename or "document", content_type)
    stored_name = (
        f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex}{extension}"
    )
    file_path = storage_dir / stored_name
    file_path.write_bytes(file_bytes)

    original_name = (upload.filename or "document").strip() or "document"
    return stored_name, content_type, len(file_bytes), original_name
