import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from jwt import InvalidTokenError
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import (
    JWT_ACCESS_SECRET,
    JWT_REFRESH_PEPPER,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_DELTA,
    REFRESH_TOKEN_EXPIRE_DELTA,
    REFRESH_TOKEN_CHECK_IP,
    REFRESH_TOKEN_CHECK_USER_AGENT
)


# ============================================================
# Access tokens — short-lived, stateless JWTs (10 min)
# ============================================================

def create_access_token(user_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + ACCESS_TOKEN_EXPIRE_DELTA,
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, JWT_ACCESS_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(
            token,
            JWT_ACCESS_SECRET,
            algorithms=[JWT_ALGORITHM],
        )

        if payload.get("type") != "access":
            return None

        return payload

    except InvalidTokenError:
        return None


# ============================================================
# Refresh tokens — opaque random strings (18 days), stored
# server-side by hash only, rotated on every use.
# ============================================================
#
# Why opaque instead of another JWT? A refresh token must be revocable
# (logout, theft, password change) and a stateless JWT can't be revoked
# without maintaining a blocklist anyway — so we just store it directly
# and get revocation, rotation and reuse-detection for free.

def _hash_token(raw_token: str) -> str:
    # The raw token already has 512 bits of entropy from secrets.token_urlsafe,
    # so a fast keyed hash (HMAC-SHA256, peppered with a server-side secret)
    # is appropriate here — unlike a password, it doesn't need bcrypt's
    # deliberate slowness, and we need a direct lookup by hash on every call.
    return hmac.new(JWT_REFRESH_PEPPER.encode(), raw_token.encode(), hashlib.sha256).hexdigest()


def issue_refresh_token(
    db: Session,
    user_id: int,
    family_id: str | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, str]:
    """
    Creates and stores a new refresh token. Returns (raw_token, family_id).
    raw_token is what gets sent to the client (as an httpOnly cookie) —
    only its hash is ever persisted in the database.

    family_id groups every token descended from one login together, so
    that if a stolen/already-rotated token is ever reused, the whole
    chain can be revoked at once (see rotate_refresh_token).
    """
    raw_token = secrets.token_urlsafe(64)
    token_hash = _hash_token(raw_token)
    family_id = family_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = now + REFRESH_TOKEN_EXPIRE_DELTA

    db.execute(text("""
        INSERT INTO refresh_tokens
            (user_id, token_hash, family_id, created_at, expires_at,
             revoked_at, replaced_by_hash, user_agent, ip_address)
        VALUES
            (:user_id, :token_hash, :family_id, :created_at, :expires_at,
             NULL, NULL, :user_agent, :ip_address)
    """), {
        "user_id": user_id,
        "token_hash": token_hash,
        "family_id": family_id,
        "created_at": now,
        "expires_at": expires_at,
        "user_agent": user_agent,
        "ip_address": ip_address,
    })
    db.commit()

    return raw_token, family_id


def _revoke_family(db: Session, family_id: str) -> None:
    db.execute(text("""
        UPDATE refresh_tokens SET revoked_at = :now
        WHERE family_id = :family_id AND revoked_at IS NULL
    """), {"now": datetime.now(timezone.utc).replace(tzinfo=None), "family_id": family_id})
    db.commit()


def rotate_refresh_token(
    db: Session,
    raw_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[bool, str, str | None, int | None, str | None]:

    token_hash = _hash_token(raw_token)

    row = db.execute(text("""
        SELECT
            rt.id,
            rt.user_id,
            rt.family_id,
            rt.expires_at,
            rt.revoked_at,
            rt.ip_address,
            rt.user_agent,
            u.role,
            u.is_active,
            u.is_deleted
        FROM refresh_tokens rt
        JOIN users u
            ON u.id = rt.user_id
        WHERE rt.token_hash = :token_hash
    """), {
        "token_hash": token_hash,
    }).mappings().first()

    if not row:
        return False, "Invalid session. Please log in again.", None, None, None

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Token already used/revoked -> possible theft
    if row["revoked_at"] is not None:
        _revoke_family(db, row["family_id"])
        return False, "Session invalidated for security reasons. Please log in again.", None, None, None

    # Expired
    if row["expires_at"] <= now:

        db.execute(text("""
            UPDATE refresh_tokens
            SET revoked_at = :now
            WHERE id = :id
            AND revoked_at IS NULL
        """), {
            "now": now,
            "id": row["id"],
        })

        db.commit()

        return (
            False,
            "Session expired. Please log in again.",
            None,
            None,
            None,
        )

    # Account disabled/deleted
    if row["is_deleted"] or not row["is_active"]:
        _revoke_family(db, row["family_id"])
        return False, "This account is no longer active.", None, None, None

    # Device binding — verify IP and User-Agent match the original token
    if REFRESH_TOKEN_CHECK_IP:
        stored_ip = row.get("ip_address")
        if stored_ip is not None and stored_ip != ip_address:
            _revoke_family(db, row["family_id"])
            return False, "Session invalidated for security reasons. Please log in again.", None, None, None

    if REFRESH_TOKEN_CHECK_USER_AGENT:
        stored_ua = row.get("user_agent")
        if stored_ua is not None and stored_ua != user_agent:
            _revoke_family(db, row["family_id"])
            return False, "Session invalidated for security reasons. Please log in again.", None, None, None

    # -------------------------------
    # Create new refresh token
    # -------------------------------
    new_raw_token = secrets.token_urlsafe(64)
    new_hash = _hash_token(new_raw_token)
    expires_at = now + REFRESH_TOKEN_EXPIRE_DELTA

    db.execute(text("""
        INSERT INTO refresh_tokens
        (
            user_id,
            token_hash,
            family_id,
            created_at,
            expires_at,
            revoked_at,
            replaced_by_hash,
            user_agent,
            ip_address
        )
        VALUES
        (
            :user_id,
            :token_hash,
            :family_id,
            :created_at,
            :expires_at,
            NULL,
            NULL,
            :user_agent,
            :ip_address
        )
    """), {
        "user_id": row["user_id"],
        "token_hash": new_hash,
        "family_id": row["family_id"],
        "created_at": now,
        "expires_at": expires_at,
        "user_agent": user_agent,
        "ip_address": ip_address,
    })

    # Revoke old refresh token
    db.execute(text("""
        UPDATE refresh_tokens
        SET
            revoked_at = :now,
            replaced_by_hash = :new_hash
        WHERE id = :id
    """), {
        "now": now,
        "new_hash": new_hash,
        "id": row["id"],
    })

    # Single commit
    db.commit()

    return (
        True,
        "Rotated.",
        new_raw_token,
        row["user_id"],
        row["role"],
    )

def get_user_id_from_refresh_token(
    db: Session,
    raw_token: str,
) -> int | None:
    """
    Returns the user ID associated with a refresh token.
    Returns None if the token does not exist.
    """

    token_hash = _hash_token(raw_token)

    row = db.execute(text("""
        SELECT user_id
        FROM refresh_tokens
        WHERE token_hash = :token_hash
    """), {
        "token_hash": token_hash,
    }).mappings().first()

    if not row:
        return None

    return row["user_id"]

def get_user_from_refresh_token(db: Session, raw_token: str) -> dict | None:
    """
    Validates a refresh token and returns the associated user.
    Returns None if the token is invalid or expired.
    """
    token_hash = _hash_token(raw_token)

    row = db.execute(text("""
        SELECT rt.user_id, rt.revoked_at, rt.expires_at, u.role, u.is_active, u.is_deleted
        FROM refresh_tokens rt
        JOIN users u ON u.id = rt.user_id
        WHERE rt.token_hash = :token_hash
    """), {"token_hash": token_hash}).mappings().first()

    if not row:
        return None

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if row["revoked_at"] is not None:
        return None

    if row["expires_at"] <= now:
        return None

    if row["is_deleted"] or not row["is_active"]:
        return None

    return {
        "id": row["user_id"],
        "role": row["role"],
    }

def revoke_refresh_token(db: Session, raw_token: str) -> None:
    """Used for logout — revokes just the one presented token."""
    token_hash = _hash_token(raw_token)
    db.execute(text("""
        UPDATE refresh_tokens SET revoked_at = :now
        WHERE token_hash = :token_hash AND revoked_at IS NULL
    """), {"now": datetime.now(timezone.utc).replace(tzinfo=None), "token_hash": token_hash})
    db.commit()


def revoke_all_user_tokens(db: Session, user_id: int) -> None:
    """Revoke every active refresh token for a user — e.g. on password
    change, on 'log out everywhere', or when account is deactivated."""
    db.execute(text("""
        UPDATE refresh_tokens SET revoked_at = :now
        WHERE user_id = :user_id AND revoked_at IS NULL
    """), {"now": datetime.now(timezone.utc).replace(tzinfo=None), "user_id": user_id})
    db.commit()


# ============================================================
# Order confirmation tokens — short-lived signed JWTs
# ============================================================

CONFIRMATION_TOKEN_EXPIRE_MINUTES = int(
    os.environ.get("CONFIRMATION_TOKEN_EXPIRE_MINUTES", "60")
)

CONFIRMATION_TOKEN_EXPIRE_DELTA = timedelta(
    minutes=CONFIRMATION_TOKEN_EXPIRE_MINUTES
)


def create_order_confirmation_token(order_id: int, user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "type": "order_confirmation",
        "order_id": order_id,
        "user_id": user_id,
        "iat": now,
        "exp": now + CONFIRMATION_TOKEN_EXPIRE_DELTA,
    }
    return jwt.encode(payload, JWT_ACCESS_SECRET, algorithm=JWT_ALGORITHM)


def decode_order_confirmation_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(
            token,
            JWT_ACCESS_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
    except InvalidTokenError:
        return None

    if payload.get("type") != "order_confirmation":
        return None

    try:
        return {
            "order_id": int(payload["order_id"]),
            "user_id": int(payload["user_id"]),
        }
    except (KeyError, TypeError, ValueError):
        return None