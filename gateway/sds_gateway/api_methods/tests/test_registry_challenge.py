from sds_gateway.api_methods.federation.registry_challenge import (
    generate_registry_challenge_token,
)
from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.federation.registry_challenge import (
    verify_registry_challenge_token,
)


def test_registry_challenge_hash_roundtrip() -> None:
    raw = generate_registry_challenge_token()
    stored = hash_registry_challenge_token(raw)
    assert verify_registry_challenge_token(raw, stored)
    assert not verify_registry_challenge_token("wrong", stored)
