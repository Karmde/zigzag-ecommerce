from pydantic import BaseModel, EmailStr, Field, field_validator


# ==========================================================
# Check Email
# ==========================================================

class CheckEmailRequest(BaseModel):
    email: EmailStr


class CheckEmailResponse(BaseModel):
    exists: bool


# ==========================================================
# Signup
# ==========================================================

class SignupRequest(BaseModel):
    firstname: str
    lastname: str
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=10)
    password: str = Field(..., min_length=8, max_length=72)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("Phone number must contain only digits.")
        return value


class SignupResponse(BaseModel):
    token: str


# ==========================================================
# Email Verification
# ==========================================================

class VerifyEmailRequest(BaseModel):
    token: str
    otp: str


class VerifyEmailResponse(BaseModel):
    success: bool
    message: str


class ResendOtpRequest(BaseModel):
    token: str


class PendingEmailResponse(BaseModel):
    email: str


# ==========================================================
# Login
# ==========================================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)


class UserOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: EmailStr
    role: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    access_token: str
    user: UserOut


# ==========================================================
# Refresh Token
# ==========================================================

class RefreshTokenResponse(BaseModel):
    success: bool
    message: str
    access_token: str
    user: UserOut


# ==========================================================
# Logout
# ==========================================================

class LogoutResponse(BaseModel):
    success: bool
    message: str


# ==========================================================
# Change Password
# ==========================================================

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=8, max_length=72)
    new_password: str = Field(..., min_length=8, max_length=72)


# ==========================================================
# Forgot Password
# ==========================================================

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    success: bool
    message: str
    token: str | None


class VerifyForgotPasswordRequest(BaseModel):
    token: str
    otp: str


class ResetPasswordRequest(BaseModel):
    token: str
    otp: str
    new_password: str = Field(..., min_length=8, max_length=72)


class ResendResetOtpRequest(BaseModel):
    token: str


class ResetAccountResponse(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str


class VerifyForgotPasswordResponse(BaseModel):
    success: bool
    message: str


class IsAdminResponse(BaseModel):
    is_admin: bool