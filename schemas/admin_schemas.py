from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class UserSearchRequest(BaseModel):
    search: str = Field(..., min_length=1, max_length=255, description="Search by user ID or email")


class UserSearchResult(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    role: str
    is_active: bool
    created_at: Optional[str] = None


class UserDetailResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    phone_number: Optional[str] = None
    auth_provider: str
    role: str
    is_active: bool
    email_verified: bool
    phone_verified: bool
    created_at: Optional[str] = None
    last_login_at: Optional[str] = None
    orders_count: int = 0
    total_spent: float = 0.0
    wishlist_count: int = 0
