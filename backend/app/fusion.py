"""Conservative entity resolution. A false merge is worse than a duplicate."""
from __future__ import annotations

import re
import unicodedata


def normalized_name(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", folded.lower()).strip()


def resolution_key(source_slug: str, source_key: str | None, canonical_name: str) -> tuple[str, str]:
    """Prefer a publisher identifier; only use a name as an explicit review key."""
    return (source_slug, source_key or f"name:{normalized_name(canonical_name)}")


def can_auto_merge(
    *, existing_source_key: str | None, incoming_source_key: str | None, existing_name: str, incoming_name: str
) -> bool:
    return bool(existing_source_key and incoming_source_key and existing_source_key == incoming_source_key)

