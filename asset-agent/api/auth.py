import os
import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status


API_TOKEN_ENV = "ASSET_API_TOKEN"
MIN_API_TOKEN_LENGTH = 32


def get_configured_api_token() -> str:
    """Return the server-side API token or fail closed."""
    token = os.getenv(API_TOKEN_ENV)
    if token is None or not token:
        raise RuntimeError(
            f"{API_TOKEN_ENV} must be set before the Asset Management HQ API starts"
        )
    if token != token.strip():
        raise RuntimeError(f"{API_TOKEN_ENV} must not contain surrounding whitespace")
    if len(token) < MIN_API_TOKEN_LENGTH:
        raise RuntimeError(
            f"{API_TOKEN_ENV} must contain at least {MIN_API_TOKEN_LENGTH} characters"
        )
    return token


def require_api_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Require an RFC 6750-style Bearer token without leaking comparison details."""
    if authorization is None:
        _raise_unauthorized()

    scheme, separator, supplied_token = authorization.partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not supplied_token
        or " " in supplied_token
    ):
        _raise_unauthorized()

    configured_token = get_configured_api_token()
    if not secrets.compare_digest(supplied_token, configured_token):
        _raise_unauthorized()


def _raise_unauthorized() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
