"""Registry domain-verification challenge tokens (generate, hash, verify)."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_registry_challenge_token() -> str:
    """Return a one-time secret shown to the applicant (not stored in the DB)."""
    return secrets.token_urlsafe(32)


def hash_registry_challenge_token(raw_token: str) -> str:
    """Persisted form of the challenge token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def verify_registry_challenge_token(raw_token: str, stored_hash: str) -> bool:
    """Constant-time compare of a candidate token to the stored hash."""
    if not raw_token or not stored_hash:
        return False
    candidate = hash_registry_challenge_token(raw_token)
    return hmac.compare_digest(candidate, stored_hash)
