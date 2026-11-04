"""Registry domain-verification challenge hash compare (no token generation here)."""

from __future__ import annotations

import hashlib
import hmac


CHALLENGE_MISMATCH_MESSAGE = (
    "registry_challenge is missing or does not match your verification token."
)


def hash_registry_challenge_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def challenge_matches(well_known: dict, stored_hash: str) -> bool:
    raw = well_known.get("registry_challenge")
    if not isinstance(raw, str) or not raw.strip() or not stored_hash:
        return False
    candidate = hash_registry_challenge_token(raw.strip())
    return hmac.compare_digest(candidate, stored_hash.strip())
