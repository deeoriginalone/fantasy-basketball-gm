from cryptography.fernet import Fernet

from app.core.security import create_oauth_state, decrypt_token, encrypt_token, validate_oauth_state


def test_oauth_state_is_signed_and_rejects_tampering() -> None:
    state = create_oauth_state("test-secret")
    second_state = create_oauth_state("test-secret")

    assert validate_oauth_state(state, state, "test-secret")
    assert state != second_state
    assert not validate_oauth_state(f"{state}tampered", state, "test-secret")
    assert not validate_oauth_state(state, second_state, "test-secret")
    assert not validate_oauth_state(state, state, "different-secret")


def test_token_round_trip_uses_fernet_encryption() -> None:
    key = Fernet.generate_key().decode("ascii")

    encrypted = encrypt_token("oauth-access-token", key)

    assert encrypted != "oauth-access-token"
    assert decrypt_token(encrypted, key) == "oauth-access-token"