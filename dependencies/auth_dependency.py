from fastapi import Header, Depends, HTTPException, status, Cookie
from sqlalchemy.orm import Session

from database.database import get_db
from services.token_services import decode_access_token, get_user_from_refresh_token

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials

    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token.",
        )

    if "sub" not in payload or "role" not in payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid access token.",
        )

    return {
        "id": int(payload["sub"]),
        "role": payload["role"],
    }


def get_current_user_from_cookie(
    refresh_token: str | None = Cookie(default=None, alias="refresh_token"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Authenticates via the httpOnly refresh token cookie.
    Used for page routes where the browser does not send an Authorization header.
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )

    user = get_user_from_refresh_token(db, refresh_token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again.",
        )

    return user


def get_current_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Allows access only to admin users.
    """
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )

    return current_user


def get_current_admin_from_cookie(
    current_user: dict = Depends(get_current_user_from_cookie),
) -> dict:
    """
    Allows access only to admin users, authenticated via cookie.
    """
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )

    return current_user


def get_optional_current_user(
    authorization: str | None = Header(default=None),
) -> dict | None:
    """
    Optionally validates the JWT access token.
    Returns the user dict if a valid token is provided, otherwise None.
    Does not raise an error when no token is present.
    """
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None

    payload = decode_access_token(token)
    if payload is None:
        return None

    if "sub" not in payload or "role" not in payload:
        return None

    return {
        "id": int(payload["sub"]),
        "role": payload["role"],
    }