import hashlib
import secrets


def generate_registry_challenge_token() -> str:
    """Return a URL-safe random token for one-time display to the applicant."""
    return secrets.token_urlsafe(32)


def hash_registry_challenge_token(raw_token: str) -> str:
    """SHA-256 hex digest stored on RegistryApplication (never store raw token)."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
