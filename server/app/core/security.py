import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from jwt import InvalidTokenError

JWT_ISSUER = "beyond-the-unknown"


def hash_wechat_openid(openid: str, pepper: str) -> str:
    if not openid or len(pepper) < 32:
        raise ValueError("OpenID and a 32-character HMAC secret are required")
    return hmac.new(pepper.encode(), openid.encode(), hashlib.sha256).hexdigest()


def create_access_token(player_id: UUID, secret: str, expires_in_seconds: int) -> str:
    if len(secret) < 32:
        raise ValueError("JWT secret must contain at least 32 characters")
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(player_id), "iss": JWT_ISSUER, "iat": now,
         "exp": now + timedelta(seconds=expires_in_seconds)},
        secret,
        algorithm="HS256",
    )


def decode_access_token(token: str, secret: str) -> UUID:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"], issuer=JWT_ISSUER)
        return UUID(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError, TypeError) as exc:
        raise ValueError("Invalid or expired access token") from exc
