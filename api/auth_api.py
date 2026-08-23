from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    BackgroundTasks,
    Request,
    Response,
    Cookie,
)
from sqlalchemy import text
from sqlalchemy.orm import Session
from database.database import get_db
from services.auth_services import (
    check_email_exists,
    create_pending_signup,
    verify_otp_and_create_user,
    resend_otp,
    get_masked_pending_email,
    login_user,
    change_password,
    request_password_reset,
    get_reset_account_info,
    verify_reset_otp,
    complete_password_reset,
    resend_reset_otp,
)
from services.email_services import send_otp_email
from schemas.auth_schemas import (
    CheckEmailRequest,
    CheckEmailResponse,
    SignupRequest,
    SignupResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
    ResendOtpRequest,
    PendingEmailResponse,
    LoginRequest,
    LoginResponse,
    RefreshTokenResponse,
    LogoutResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    VerifyForgotPasswordRequest,
    ResetPasswordRequest,
    ResendResetOtpRequest,
    ResetAccountResponse,
    IsAdminResponse,
)
from services.token_services import (
    create_access_token,
    issue_refresh_token,
    rotate_refresh_token,
    revoke_refresh_token,
    revoke_all_user_tokens,
    get_user_id_from_refresh_token,
)
from dependencies.auth_dependency import get_current_user, get_current_admin

from core.config import (
    COOKIE_NAME,
    COOKIE_SECURE,
    REFRESH_TOKEN_EXPIRE_DAYS,
    COOKIE_HTTPONLY,
    COOKIE_SAMESITE,
    COOKIE_PATH
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/check-email", response_model=CheckEmailResponse)
def check_email(payload: CheckEmailRequest, db: Session = Depends(get_db)):
    exists = check_email_exists(db, payload.email)
    return CheckEmailResponse(exists=exists)


@router.post("/signup", response_model=SignupResponse)
def signup(payload: SignupRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if check_email_exists(db, payload.email):
        raise HTTPException(status_code=409, detail="Email already registered.")

    token, otp = create_pending_signup(db, payload)

    # Email sends after the response goes out — doesn't block the request
    background_tasks.add_task(send_otp_email, payload.email, otp, payload.firstname)

    return SignupResponse(token=token)


@router.post("/verify-email", response_model=VerifyEmailResponse)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    success, message = verify_otp_and_create_user(db, payload.token, payload.otp)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return VerifyEmailResponse(success=success, message=message)


@router.post("/resend-otp", response_model=VerifyEmailResponse)
def resend(payload: ResendOtpRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    success, message, email, otp = resend_otp(db, payload.token)
    if not success:
        raise HTTPException(status_code=400, detail=message)

    background_tasks.add_task(send_otp_email, email, otp)

    return VerifyEmailResponse(success=success, message=message)


@router.get("/pending-signup", response_model=PendingEmailResponse)
def get_pending_signup(token: str, db: Session = Depends(get_db)):
    masked = get_masked_pending_email(db, token)
    if not masked:
        raise HTTPException(status_code=404, detail="Invalid or expired verification link.")
    return PendingEmailResponse(email=masked)


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    success, message, status_code, user = login_user(
        db,
        payload.email,
        payload.password,
    )

    if not success:
        raise HTTPException(
            status_code=status_code,
            detail=message,
        )

    # Create short-lived JWT access token
    access_token = create_access_token(
        user["id"],
        user["role"],
    )

    # Create refresh token and store it in database
    refresh_token, _ = issue_refresh_token(
        db=db,
        user_id=user["id"],
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host,
    )

    # Send refresh token as HttpOnly cookie
    response.set_cookie(
        key=COOKIE_NAME,
        value=refresh_token,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )

    return LoginResponse(
        success=True,
        message=message,
        access_token=access_token,
        user=user,
    )

@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail="Session expired. Please log in again.",
        )

    success, message, new_refresh_token, user_id, role = rotate_refresh_token(
        db=db,
        raw_token=refresh_token,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host,
    )

    if not success:
        response.delete_cookie(
            key=COOKIE_NAME,
            path=COOKIE_PATH,
        )

        raise HTTPException(
            status_code=401,
            detail=message,
        )

    # Load the user so the client can render the logged-in navbar state
    # (login button -> profile) after a page reload / refresh.
    user_row = db.execute(
        text("""
            SELECT id, first_name, last_name, email, role
            FROM users
            WHERE id = :user_id AND is_deleted = 0
        """),
        {"user_id": user_id},
    ).mappings().first()

    if not user_row:
        response.delete_cookie(key=COOKIE_NAME, path=COOKIE_PATH)
        raise HTTPException(
            status_code=401,
            detail="User no longer exists.",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.execute(text("""
        UPDATE users
        SET last_login_at = :now
        WHERE id = :user_id
    """), {"now": now, "user_id": user_id})
    db.commit()

    user = {
        "id": user_row["id"],
        "first_name": user_row["first_name"],
        "last_name": user_row["last_name"],
        "email": user_row["email"],
        "role": user_row["role"],
    }

    access_token = create_access_token(
        user_id=user_id,
        role=role,
    )

    response.set_cookie(
        key=COOKIE_NAME,
        value=new_refresh_token,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )

    return RefreshTokenResponse(
        success=True,
        message="Access token refreshed successfully.",
        access_token=access_token,
        user=user,
    )

@router.get("/is-admin", response_model=IsAdminResponse)
def is_admin(current_user: dict = Depends(get_current_admin)):
    return IsAdminResponse(is_admin=True)

@router.post("/logout", response_model=LogoutResponse)
def logout(
    response: Response,
    current_user: dict = Depends(get_current_user),
    refresh_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_db),
):
    if refresh_token:
        revoke_refresh_token(db, refresh_token)

    response.delete_cookie(
        key=COOKIE_NAME,
        path=COOKIE_PATH,
    )

    return LogoutResponse(
        success=True,
        message="Logged out successfully.",
    )

@router.post("/change-password")
def change_password_api(
    payload: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    success, message = change_password(
        db=db,
        user_id=current_user["id"],
        current_password=payload.current_password,
        new_password=payload.new_password,
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail=message,
        )

    revoke_all_user_tokens(db, current_user["id"])

    return {
        "success": True,
        "message": message,
    }

@router.post("/forgot-password")
def forgot_password(
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    success, message, token, otp, firstname = request_password_reset(
        db,
        payload.email,
    )

    # Only email when a brand-new OTP was generated (otp is None when an
    # existing, still-valid request was reused — don't spam a second email).
    if success and otp:
        background_tasks.add_task(
            send_otp_email,
            payload.email,
            otp,
            firstname,
        )

    return {
        "success": success,
        "message": message,
        "token": token,
    }


@router.get("/reset-account", response_model=ResetAccountResponse)
def reset_account(token: str, db: Session = Depends(get_db)):
    info = get_reset_account_info(db, token)

    if not info:
        raise HTTPException(
            status_code=404,
            detail="Invalid or expired reset request.",
        )

    return info


@router.post("/verify-forgot-password")
def verify_forgot_password(
    payload: VerifyForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    success, message = verify_reset_otp(
        db=db,
        token=payload.token,
        otp=payload.otp,
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail=message,
        )

    return {
        "success": True,
        "message": message,
    }


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    success, message = complete_password_reset(
        db=db,
        token=payload.token,
        otp=payload.otp,
        new_password=payload.new_password,
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail=message,
        )

    return {
        "success": True,
        "message": message,
    }


@router.post("/resend-reset-otp")
def resend_reset(
    payload: ResendResetOtpRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    success, message, email, otp, firstname = resend_reset_otp(
        db,
        payload.token,
    )

    if success:
        background_tasks.add_task(
            send_otp_email,
            email,
            otp,
            firstname,
        )

    if not success:
        raise HTTPException(
            status_code=400,
            detail=message,
        )

    return {
        "success": True,
        "message": message,
    }