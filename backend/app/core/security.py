import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


def create_oauth_state(secret: str) -> str:
    nonce = secrets.token_urlsafe(32)
    return URLSafeTimedSerializer(secret, salt="yahoo-oauth-state").dumps({"nonce": nonce})


def validate_oauth_state(
    state: str,
    expected_state: str | None,
    secret: str,
    max_age_seconds: int = 600,
) -> bool:
    if not expected_state or not hmac.compare_digest(state, expected_state):
        return False
    try:
        payload = URLSafeTimedSerializer(secret, salt="yahoo-oauth-state").loads(
            state,
            max_age=max_age_seconds,
        )
    except (BadSignature, SignatureExpired):
        return False
    return isinstance(payload, dict) and isinstance(payload.get("nonce"), str)


def encrypt_token(token: str, key: str) -> str:
    return Fernet(key.encode("ascii")).encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_token(encrypted_token: str, key: str) -> str:
    try:
        return Fernet(key.encode("ascii")).decrypt(encrypted_token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as error:
        raise ValueError("Stored Yahoo token cannot be decrypted with the configured key") from error