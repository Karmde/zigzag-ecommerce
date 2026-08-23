from fastapi import APIRouter, Request
from core.templates import templates

router = APIRouter(prefix="/auth")

@router.get("/signup")
async def signup(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth/signup.html"
    )

@router.get("/verify-email")
async def verify_email(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth/verify-email.html"
    )

@router.get("/login")
async def login(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html"
    )

@router.get("/forgot-password")
async def forgot_password(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth/forgot_password.html"
    )
