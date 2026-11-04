from sds_federation.services.registry_challenge import challenge_matches
from sds_federation.services.registry_challenge import hash_registry_challenge_token


def test_registry_challenge_hash_roundtrip() -> None:
    raw = "challenge-token-value"
    stored = hash_registry_challenge_token(raw)
    assert challenge_matches({"registry_challenge": raw}, stored)
    assert not challenge_matches({"registry_challenge": "wrong"}, stored)


def test_registry_challenge_missing_field() -> None:
    assert not challenge_matches({}, hash_registry_challenge_token("x"))
