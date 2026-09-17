from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_round_trip():
    hashed = hash_password("strong-password")
    assert hashed != "strong-password"
    assert verify_password("strong-password", hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_contains_tenant_and_role():
    token = create_access_token(42, "school_admin", 7)
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "school_admin"
    assert payload["school_id"] == 7
