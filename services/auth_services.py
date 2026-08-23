import re
import secrets
import bcrypt
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.token_services import revoke_all_user_tokens

OTP_VALIDITY_MINUTES = 15
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 60


def _hash(value: str) -> str:
    return bcrypt.hashpw(value.encode(), bcrypt.gensalt()).decode()


def _verify_hash(value: str, hashed: str) -> bool:
    return bcrypt.checkpw(value.encode(), hashed.encode())


def _generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def check_email_exists(db: Session, email: str) -> bool:
    query = text("""
        SELECT EXISTS(
            SELECT 1 FROM users WHERE email = :email
        ) AS email_exists
    """)
    result = db.execute(query, {"email": email}).scalar()
    return bool(result)


def create_pending_signup(db: Session, data) -> tuple[str, str]:
    """
    Creates (or replaces) a pending signup row.
    Returns (token, otp) — token goes in the URL, otp goes in the email.
    Note: this function only touches the DB. Sending the OTP email is the
    caller's (API layer's) responsibility, via BackgroundTasks.
    """

    delete_query = text("DELETE FROM pending_signups WHERE email = :email")
    db.execute(delete_query, {"email": data.email})

    token = secrets.token_urlsafe(32)
    otp = _generate_otp()
    otp_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=OTP_VALIDITY_MINUTES)

    insert_query = text("""
        INSERT INTO pending_signups
            (token, firstname, lastname, email, phone, password_hash, otp_hash, otp_expires_at)
        VALUES
            (:token, :firstname, :lastname, :email, :phone, :password_hash, :otp_hash, :otp_expires_at)
    """)
    db.execute(insert_query, {
        "token": token,
        "firstname": data.firstname,
        "lastname": data.lastname,
        "email": data.email,
        "phone": data.phone,
        "password_hash": _hash(data.password),
        "otp_hash": _hash(otp),
        "otp_expires_at": otp_expires_at,
    })
    db.commit()

    return token, otp


def verify_otp_and_create_user(db: Session, token: str, otp: str) -> tuple[bool, str]:
    select_query = text("""
        SELECT firstname, lastname, email, phone, password_hash, otp_hash, otp_expires_at
        FROM pending_signups
        WHERE token = :token
    """)
    row = db.execute(select_query, {"token": token}).mappings().first()

    if not row:
        return False, "Invalid or expired verification link."

    if datetime.now(timezone.utc).replace(tzinfo=None) > row["otp_expires_at"]:
        db.execute(text("DELETE FROM pending_signups WHERE token = :token"), {"token": token})
        db.commit()
        return False, "This code has expired. Please sign up again."

    if not _verify_hash(otp, row["otp_hash"]):
        return False, "Incorrect code. Please try again."

    insert_user_query = text("""
        INSERT INTO users (
            first_name, last_name, email, phone_number, password_hash,
            auth_provider, role, email_verified, phone_verified,
            is_active, is_deleted, failed_login_attempts
        )
        VALUES (
            :first_name, :last_name, :email, :phone_number, :password_hash,
            'local', 'customer', 1, 0,
            1, 0, 0
        )
    """)
    db.execute(insert_user_query, {
        "first_name": row["firstname"],
        "last_name": row["lastname"],
        "email": row["email"],
        "phone_number": row["phone"],
        "password_hash": row["password_hash"],
    })

    db.execute(text("DELETE FROM pending_signups WHERE token = :token"), {"token": token})
    db.commit()

    return True, "Email verified successfully. You can now log in."


def resend_otp(db: Session, token: str) -> tuple[bool, str, str | None, str | None]:
    """
    Generates a new OTP for an existing pending signup.
    Returns (success, message, email, otp) — email/otp are None on failure,
    and are handed back to the caller so the API layer can send the email
    via BackgroundTasks (this function only touches the DB).
    """
    select_query = text("SELECT email FROM pending_signups WHERE token = :token")
    row = db.execute(select_query, {"token": token}).mappings().first()

    if not row:
        return False, "Invalid or expired verification link.", None, None

    otp = _generate_otp()
    otp_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=OTP_VALIDITY_MINUTES)

    update_query = text("""
        UPDATE pending_signups
        SET otp_hash = :otp_hash, otp_expires_at = :otp_expires_at
        WHERE token = :token
    """)
    db.execute(update_query, {
        "otp_hash": _hash(otp),
        "otp_expires_at": otp_expires_at,
        "token": token,
    })
    db.commit()

    return True, "A new code has been sent to your email.", row["email"], otp


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        masked_local = local[0] + "*" * (len(local) - 1) if local else "*"
    else:
        masked_local = local[:2] + "*" * (len(local) - 2)
    return f"{masked_local}@{domain}"


def _mask_phone(phone: str | None) -> str:
    if not phone:
        return "**********"

    digits = re.sub(r"\D", "", phone)

    if len(digits) <= 4:
        return "*" * len(digits)

    return "*" * (len(digits) - 4) + digits[-4:]


def get_masked_pending_email(db: Session, token: str) -> str | None:
    query = text("SELECT email FROM pending_signups WHERE token = :token")
    row = db.execute(query, {"token": token}).mappings().first()
    return _mask_email(row["email"]) if row else None


def login_user(db: Session, email: str, password: str) -> tuple[bool, str, int, dict | None]:
    """
    Validates login credentials with rate limiting.
    Returns (success, message, http_status_code, user_dict_or_None).
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    select_query = text("""
        SELECT id, first_name, last_name, email, password_hash, role,
               email_verified, is_active, is_deleted,
               failed_login_attempts, locked_until
        FROM users
        WHERE email = :email
    """)
    row = db.execute(select_query, {"email": email}).mappings().first()

    if not row or row["is_deleted"]:
        return False, "No account found with this email.", 404, None

    if not row["is_active"]:
        return False, "This account has been deactivated. Please contact support.", 403, None

    failed_attempts = row["failed_login_attempts"]
    locked_until = row["locked_until"]

    # If a previous lockout has already expired, clear it before evaluating this attempt
    if locked_until and locked_until <= now:
        db.execute(text("""
            UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE id = :id
        """), {"id": row["id"]})
        db.commit()
        failed_attempts = 0
        locked_until = None

    # Still within an active lockout window — block before even checking the password
    if locked_until and locked_until > now:
        minutes_left = max(1, int((locked_until - now).total_seconds() // 60))
        return False, f"Too many failed attempts. Try again in {minutes_left} minute(s).", 423, None

    if not row["password_hash"]:
        return False, "This account uses Google Sign-In. Please continue with Google.", 400, None

    if not _verify_hash(password, row["password_hash"]):
        new_count = failed_attempts + 1

        if new_count >= MAX_FAILED_LOGIN_ATTEMPTS:
            new_locked_until = now + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
            db.execute(text("""
                UPDATE users
                SET failed_login_attempts = :count, locked_until = :locked_until
                WHERE id = :id
            """), {"count": new_count, "locked_until": new_locked_until, "id": row["id"]})
            db.commit()
            return False, f"Too many failed attempts. Your account is locked for {LOGIN_LOCKOUT_MINUTES} minutes.", 423, None

        db.execute(text("""
            UPDATE users SET failed_login_attempts = :count WHERE id = :id
        """), {"count": new_count, "id": row["id"]})
        db.commit()

        remaining = MAX_FAILED_LOGIN_ATTEMPTS - new_count
        return False, f"Incorrect password. {remaining} attempt(s) remaining.", 401, None

    if not row["email_verified"]:
        return False, "Please verify your email before logging in.", 403, None

    # Success — reset counters and record the login
    db.execute(text("""
        UPDATE users
        SET failed_login_attempts = 0, locked_until = NULL, last_login_at = :now
        WHERE id = :id
    """), {"now": now, "id": row["id"]})
    db.commit()

    user = {
        "id": row["id"],
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "email": row["email"],
        "role": row["role"],
    }
    return True, "Login successful.", 200, user

def change_password(
    db: Session,
    user_id: int,
    current_password: str,
    new_password: str,
) -> tuple[bool, str]:

    row = db.execute(text("""
        SELECT password_hash
        FROM users
        WHERE id = :id
    """), {"id": user_id}).mappings().first()

    if not row:
        return False, "User not found."

    if not row["password_hash"]:
        return False, "Google accounts cannot change password here."

    if not _verify_hash(current_password, row["password_hash"]):
        return False, "Current password is incorrect."

    if current_password == new_password:
        return False, "New password must be different."

    db.execute(text("""
        UPDATE users
        SET password_hash = :password_hash
        WHERE id = :id
    """), {
        "password_hash": _hash(new_password),
        "id": user_id,
    })

    db.commit()

    revoke_all_user_tokens(db, user_id)

    return True, "Password changed successfully."

def request_password_reset(
    db: Session,
    email: str,
) -> tuple[bool, str, str | None, str | None, str | None]:
    """
    Creates (or replaces) a password reset request for the given email.
    Returns (success, message, token, otp, firstname). The caller (API layer)
    is responsible for emailing the OTP via BackgroundTasks — this function
    only touches the DB.
    """

    row = db.execute(text("""
        SELECT email
        FROM users
        WHERE email = :email
          AND is_deleted = 0
    """), {
        "email": email,
    }).mappings().first()

    if not row:
        return False, "No account found with this email.", None, None, None

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    db.execute(text("""
        DELETE FROM password_reset_requests
        WHERE email = :email
    """), {
        "email": email,
    })

    token = secrets.token_urlsafe(32)
    otp = _generate_otp()

    expires = now + timedelta(minutes=OTP_VALIDITY_MINUTES)

    db.execute(text("""
        INSERT INTO password_reset_requests
            (token, email, otp_hash, otp_expires_at)
        VALUES
            (:token, :email, :otp_hash, :expires)
    """), {
        "token": token,
        "email": email,
        "otp_hash": _hash(otp),
        "expires": expires,
    })

    db.commit()

    user = db.execute(text("""
        SELECT first_name
        FROM users
        WHERE email = :email
    """), {
        "email": email,
    }).mappings().first()

    firstname = user["first_name"] if user else ""

    return True, "If this account exists, a reset code has been sent.", token, otp, firstname


def get_reset_account_info(
    db: Session,
    token: str,
) -> dict | None:
    """
    Returns masked account details (first_name, last_name, email, phone) for the
    reset request tied to `token`. Used by the "Confirm your account" step.
    Returns None when the token is missing or expired.
    """

    row = db.execute(text("""
        SELECT u.first_name, u.last_name, u.email, u.phone_number
        FROM password_reset_requests r
        JOIN users u ON u.email = r.email
        WHERE r.token = :token
    """), {
        "token": token,
    }).mappings().first()

    if not row:
        return None

    return {
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "email": _mask_email(row["email"]),
        "phone": _mask_phone(row["phone_number"]),
    }


def verify_reset_otp(
    db: Session,
    token: str,
    otp: str,
) -> tuple[bool, str]:
    """
    Validates the reset OTP only (step 3 of the forgot-password flow).
    Does NOT change the password — that happens in complete_password_reset.
    """

    row = db.execute(text("""
        SELECT otp_hash,
               otp_expires_at
        FROM password_reset_requests
        WHERE token = :token
    """), {
        "token": token,
    }).mappings().first()

    if not row:
        return False, "Invalid or expired reset request."

    if datetime.now(timezone.utc).replace(tzinfo=None) > row["otp_expires_at"]:
        db.execute(text("""
            DELETE FROM password_reset_requests
            WHERE token = :token
        """), {
            "token": token,
        })

        db.commit()

        return False, "This code has expired. Please request a new one."

    if not _verify_hash(otp, row["otp_hash"]):
        return False, "Incorrect code. Please try again."

    return True, "Code verified successfully."


def complete_password_reset(
    db: Session,
    token: str,
    otp: str,
    new_password: str,
) -> tuple[bool, str]:
    """
    Re-verifies the OTP and updates the user's password (step 4).
    Re-checks the OTP here so the request can only be completed with the
    code that was emailed — calling this endpoint directly without the OTP
    fails. Also revokes every refresh token (logs the user out everywhere).
    """

    row = db.execute(text("""
        SELECT email,
               otp_hash,
               otp_expires_at
        FROM password_reset_requests
        WHERE token = :token
    """), {
        "token": token,
    }).mappings().first()

    if not row:
        return False, "Invalid or expired reset request."

    if datetime.now(timezone.utc).replace(tzinfo=None) > row["otp_expires_at"]:
        db.execute(text("""
            DELETE FROM password_reset_requests
            WHERE token = :token
        """), {
            "token": token,
        })

        db.commit()

        return False, "This code has expired. Please request a new one."

    if not _verify_hash(otp, row["otp_hash"]):
        return False, "Incorrect code. Please try again."

    user = db.execute(text("""
        SELECT id, password_hash
        FROM users
        WHERE email = :email
          AND is_deleted = 0
    """), {
        "email": row["email"],
    }).mappings().first()

    if not user:
        return False, "User not found."

    if user["password_hash"] and _verify_hash(new_password, user["password_hash"]):
        return False, "New password must be different from your current password."

    db.execute(text("""
        UPDATE users
        SET password_hash = :password_hash
        WHERE email = :email
    """), {
        "password_hash": _hash(new_password),
        "email": row["email"],
    })

    db.execute(text("""
        DELETE FROM password_reset_requests
        WHERE token = :token
    """), {
        "token": token,
    })

    db.commit()

    # Revoke all refresh tokens (logout from every device)
    revoke_all_user_tokens(db, user["id"])

    return True, "Password reset successfully."


def resend_reset_otp(
    db: Session,
    token: str,
) -> tuple[bool, str, str | None, str | None, str | None]:
    """
    Generates a fresh OTP for an existing reset request.
    Returns (success, message, email, otp, firstname) — email/otp are None on
    failure, handed back so the API layer can email the OTP via BackgroundTasks.
    """

    row = db.execute(text("""
        SELECT email
        FROM password_reset_requests
        WHERE token = :token
    """), {
        "token": token,
    }).mappings().first()

    if not row:
        return False, "Invalid or expired reset request.", None, None, None

    otp = _generate_otp()
    otp_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=OTP_VALIDITY_MINUTES)

    db.execute(text("""
        UPDATE password_reset_requests
        SET otp_hash = :otp_hash, otp_expires_at = :otp_expires_at
        WHERE token = :token
    """), {
        "otp_hash": _hash(otp),
        "otp_expires_at": otp_expires_at,
        "token": token,
    })

    db.commit()

    user = db.execute(text("""
        SELECT first_name
        FROM users
        WHERE email = :email
    """), {
        "email": row["email"],
    }).mappings().first()

    firstname = user["first_name"] if user else ""

    return True, "A new code has been sent to your email.", row["email"], otp, firstname