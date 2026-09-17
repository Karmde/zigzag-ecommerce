from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.database import get_db
from dependencies.auth_dependency import get_current_admin, get_current_admin_from_cookie
from schemas.admin_schemas import UserSearchRequest, UserSearchResult, UserDetailResponse

router = APIRouter(prefix="", tags=["Admin"])


def _format_date(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y")
    return str(value)


def _format_datetime(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y, %I:%M %p")
    return str(value)


@router.get("/users/search", response_model=list[UserSearchResult])
def search_users(
    search: str = Query(..., min_length=1, description="Search by user ID or email"),
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    search = search.strip()
    if not search:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    user_id_filter = None
    email_filter = None

    if search.isdigit():
        user_id_filter = int(search)

    email_filter = f"%{search}%"

    query = text("""
        SELECT id, first_name, last_name, email, role, is_active, created_at
        FROM users
        WHERE is_deleted = 0
          AND (
              :user_id IS NOT NULL AND id = :user_id
              OR email LIKE :email
          )
        ORDER BY id DESC
        LIMIT 20
    """)

    rows = db.execute(query, {
        "user_id": user_id_filter,
        "email": email_filter,
    }).mappings().all()

    return [
        {
            "id": row["id"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "email": row["email"],
            "role": row["role"],
            "is_active": row["is_active"],
            "created_at": _format_date(row["created_at"]),
        }
        for row in rows
    ]


@router.get("/users/{user_id}", response_model=UserDetailResponse)
def get_user_details(
    user_id: int,
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user_row = db.execute(
        text("""
            SELECT id, first_name, last_name, email, phone_number, auth_provider,
                   role, is_active, email_verified, phone_verified,
                   created_at, last_login_at
            FROM users
            WHERE id = :user_id AND is_deleted = 0
        """),
        {"user_id": user_id},
    ).mappings().first()

    if not user_row:
        raise HTTPException(status_code=404, detail="User not found.")

    orders_count_row = db.execute(
        text("""
            SELECT COUNT(*) as total FROM orders WHERE user_id = :user_id
        """),
        {"user_id": user_id},
    ).mappings().first()

    total_spent_row = db.execute(
        text("""
            SELECT COALESCE(SUM(total_amount), 0) as total FROM orders WHERE user_id = :user_id
        """),
        {"user_id": user_id},
    ).mappings().first()

    wishlist_count_row = db.execute(
        text("""
            SELECT COUNT(*) as total FROM wishlist WHERE user_id = :user_id
        """),
        {"user_id": user_id},
    ).mappings().first()

    result = dict(user_row)
    result["orders_count"] = orders_count_row["total"] if orders_count_row else 0
    result["total_spent"] = float(total_spent_row["total"] or 0)
    result["wishlist_count"] = wishlist_count_row["total"] if wishlist_count_row else 0
    result["created_at"] = _format_datetime(result.get("created_at"))
    result["last_login_at"] = _format_datetime(result.get("last_login_at"))

    return result
