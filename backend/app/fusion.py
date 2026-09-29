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


def is_uncertain_review_candidate(
    *,
    existing_canonical_name: str,
    incoming_canonical_name: str,
    existing_identifiers: list[dict[str, str]] | None = None,
    incoming_identifiers: list[dict[str, str]] | None = None,
) -> tuple[bool, str, float]:
    """Detect if two entities have similar or identical names but lack shared publisher keys.
    Returns (is_candidate, match_reason, confidence).
    """
    existing_ids = existing_identifiers or []
    incoming_ids = incoming_identifiers or []
    for e_id in existing_ids:
        for i_id in incoming_ids:
            if e_id.get("scheme") == i_id.get("scheme") and e_id.get("value") == i_id.get("value"):
                return False, "shared_publisher_identifier", 1.0

    norm_existing = normalized_name(existing_canonical_name)
    norm_incoming = normalized_name(incoming_canonical_name)

    if norm_existing and norm_incoming and norm_existing == norm_incoming:
        return True, "normalized_name_exact_match_unconfirmed", 0.70

    return False, "no_match", 0.0


