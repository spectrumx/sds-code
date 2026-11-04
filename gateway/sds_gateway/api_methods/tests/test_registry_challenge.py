from sds_gateway.api_methods.federation.registry_challenge import (
    generate_registry_challenge_token,
)
from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)


def test_hash_is_deterministic() -> None:
    raw = generate_registry_challenge_token()
    assert hash_registry_challenge_token(raw) == hash_registry_challenge_token(raw)


def test_hash_differs_for_different_tokens() -> None:
    a = generate_registry_challenge_token()
    b = generate_registry_challenge_token()
    assert hash_registry_challenge_token(a) != hash_registry_challenge_token(b)
