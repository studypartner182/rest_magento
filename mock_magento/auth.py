from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from jose import JWTError, ExpiredSignatureError, jwt
from passlib.context import CryptContext

from . import config

logger = logging.getLogger("mock_magento.auth")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Store the simulated admin user with a hashed password in memory.
ADMIN_USER = {
    "username": config.ADMIN_USERNAME,
    "role": config.ADMIN_ROLE,
    "hashed_password": pwd_context.hash(config.ADMIN_PASSWORD),
}


def authenticate_admin(username: str, password: str) -> bool:
    if username != ADMIN_USER["username"]:
        logger.warning("Authentication failed: unknown username '%s'", username)
        return False

    is_valid = pwd_context.verify(password, ADMIN_USER["hashed_password"])
    if not is_valid:
        logger.warning("Authentication failed: invalid password for '%s'", username)
    return is_valid


def create_token(*, subject: str, role: str, token_type: str, expires_delta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "token_type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
    except ExpiredSignatureError as exc:
        logger.warning("Token expired")
        raise exc
    except JWTError as exc:
        logger.warning("Token validation failed: %s", exc)
        raise exc
