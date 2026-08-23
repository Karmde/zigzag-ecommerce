import os
from datetime import timedelta


def _require(name: str) -> str:
    value = os.environ.get(name)

    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Set it in your .env file before starting the application."
        )

    return value


# ============================================================
# JWT Secrets
# ============================================================

JWT_ACCESS_SECRET = _require("JWT_ACCESS_SECRET")

# Used to hash (pepper) refresh tokens before storing them
JWT_REFRESH_PEPPER = _require("JWT_REFRESH_PEPPER")

JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")


# ============================================================
# Token Lifetimes
# ============================================================

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "10")
)

REFRESH_TOKEN_EXPIRE_DAYS = int(
    os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "18")
)

ACCESS_TOKEN_EXPIRE_DELTA = timedelta(
    minutes=ACCESS_TOKEN_EXPIRE_MINUTES
)

REFRESH_TOKEN_EXPIRE_DELTA = timedelta(
    days=REFRESH_TOKEN_EXPIRE_DAYS
)


# ============================================================
# Refresh token device binding
# ============================================================

# When enabled, rotate_refresh_token verifies that the IP address
# and User-Agent of the refresh request match the values stored
# when the token was issued.  A mismatch revokes the entire
# token family and forces re-authentication.

REFRESH_TOKEN_CHECK_IP = os.environ.get("REFRESH_TOKEN_CHECK_IP", "true").lower() == "true"
REFRESH_TOKEN_CHECK_USER_AGENT = os.environ.get("REFRESH_TOKEN_CHECK_USER_AGENT", "true").lower() == "true"


# ============================================================
# Refresh Cookie Settings
# ============================================================

COOKIE_NAME = "refresh_token"

# False only while developing on localhost over HTTP.
# Automatically becomes True in production.
COOKIE_SECURE = (
    os.environ.get("APP_ENV", "production").lower() != "development"
)

# Prevent JavaScript from reading the refresh token.
COOKIE_HTTPONLY = True

# Helps protect against CSRF while still allowing normal navigation.
COOKIE_SAMESITE = "lax"

# Cookie path (available to the whole website)
COOKIE_PATH = "/"