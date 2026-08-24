from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import datetime


def _now() -> datetime:
    return datetime.now()


def _row_to_coupon(row: dict) -> dict:
    return {
        "id": row["id"],
        "code": row["code"],
        "description": row["description"],
        "discount_type": row["discount_type"],
        "discount_value": float(row["discount_value"]),
        "minimum_cart_amount": float(row["minimum_cart_amount"]),
        "maximum_discount": float(row["maximum_discount"]) if row["maximum_discount"] is not None else None,
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "usage_limit": row["usage_limit"],
        "usage_per_user": row["usage_per_user"],
        "used_count": row["used_count"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "product_ids": [],
        "category_ids": [],
    }


def get_coupon_by_code(db: Session, code: str) -> dict | None:
    row = db.execute(text("""
        SELECT * FROM coupons
        WHERE UPPER(code) = :code AND deleted_at IS NULL
        LIMIT 1
    """), {"code": code.upper()}).mappings().first()
    return _row_to_coupon(row) if row else None


def get_coupon_by_id(db: Session, coupon_id: int) -> dict | None:
    row = db.execute(text("""
        SELECT * FROM coupons
        WHERE id = :id AND deleted_at IS NULL
        LIMIT 1
    """), {"id": coupon_id}).mappings().first()
    return _row_to_coupon(row) if row else None


def list_coupons(db: Session, active_only: bool = False) -> list[dict]:
    query = "SELECT * FROM coupons WHERE deleted_at IS NULL"
    params = {}
    if active_only:
        query += " AND is_active = 1 AND start_date <= :now AND end_date >= :now"
        params["now"] = _now()
    query += " ORDER BY created_at DESC"
    rows = db.execute(text(query), params).mappings().all()
    coupons = [_row_to_coupon(r) for r in rows]
    if not coupons:
        return coupons
    coupon_ids = [c["id"] for c in coupons]
    product_rows = db.execute(text("""
        SELECT coupon_id, product_id FROM coupon_products WHERE coupon_id IN :ids
    """), {"ids": coupon_ids}).mappings().all()
    category_rows = db.execute(text("""
        SELECT coupon_id, category_id FROM coupon_categories WHERE coupon_id IN :ids
    """), {"ids": coupon_ids}).mappings().all()
    product_map = {}
    for row in product_rows:
        product_map.setdefault(row["coupon_id"], []).append(row["product_id"])
    category_map = {}
    for row in category_rows:
        category_map.setdefault(row["coupon_id"], []).append(row["category_id"])
    for coupon in coupons:
        coupon["product_ids"] = product_map.get(coupon["id"], [])
        coupon["category_ids"] = category_map.get(coupon["id"], [])
    return coupons


def create_coupon(db: Session, data: dict) -> dict:
    data["code"] = data["code"].strip().upper()
    if not data.get("end_date"):
        data["end_date"] = datetime(9999, 12, 31, 23, 59, 59)
    row = db.execute(text("""
        INSERT INTO coupons (
            code, description, discount_type, discount_value,
            minimum_cart_amount, maximum_discount, start_date, end_date,
            usage_limit, usage_per_user, is_active, created_at, updated_at
        ) VALUES (
            :code, :description, :discount_type, :discount_value,
            :minimum_cart_amount, :maximum_discount, :start_date, :end_date,
            :usage_limit, :usage_per_user, :is_active, :created_at, :updated_at
        )
    """), {
        "code": data["code"],
        "description": data.get("description"),
        "discount_type": data["discount_type"],
        "discount_value": data["discount_value"],
        "minimum_cart_amount": data["minimum_cart_amount"],
        "maximum_discount": data.get("maximum_discount"),
        "start_date": data.get("start_date") or _now(),
        "end_date": data.get("end_date"),
        "usage_limit": data.get("usage_limit"),
        "usage_per_user": data.get("usage_per_user", 1),
        "is_active": 1 if data.get("is_active", True) else 0,
        "created_at": _now(),
        "updated_at": _now(),
    })
    db.commit()
    coupon_id = row.lastrowid
    return get_coupon_by_id(db, coupon_id)


def update_coupon(db: Session, coupon_id: int, data: dict) -> dict | None:
    coupon = get_coupon_by_id(db, coupon_id)
    if not coupon:
        return None
    fields = []
    params = {"id": coupon_id}
    for key in [
        "description", "discount_type", "discount_value",
        "minimum_cart_amount", "maximum_discount", "start_date", "end_date",
        "usage_limit", "usage_per_user", "is_active"
    ]:
        if key in data and data[key] is not None:
            fields.append(f"{key} = :{key}")
            params[key] = data[key]
    if not fields:
        return coupon
    fields.append("updated_at = :updated_at")
    params["updated_at"] = _now()
    db.execute(text(f"UPDATE coupons SET {', '.join(fields)} WHERE id = :id"), params)
    db.commit()
    return get_coupon_by_id(db, coupon_id)


def soft_delete_coupon(db: Session, coupon_id: int) -> bool:
    row = db.execute(text("""
        UPDATE coupons SET deleted_at = :now, is_active = 0, updated_at = :now
        WHERE id = :id AND deleted_at IS NULL
    """), {"now": _now(), "id": coupon_id})
    db.commit()
    return row.rowcount > 0


def get_coupon_products(db: Session, coupon_id: int) -> list[int]:
    rows = db.execute(text("""
        SELECT product_id FROM coupon_products WHERE coupon_id = :coupon_id
    """), {"coupon_id": coupon_id}).mappings().all()
    return [r["product_id"] for r in rows]


def get_coupon_categories(db: Session, coupon_id: int) -> list[int]:
    rows = db.execute(text("""
        SELECT category_id FROM coupon_categories WHERE coupon_id = :coupon_id
    """), {"coupon_id": coupon_id}).mappings().all()
    return [r["category_id"] for r in rows]


def set_coupon_products(db: Session, coupon_id: int, product_ids: list[int]) -> None:
    db.execute(text("DELETE FROM coupon_products WHERE coupon_id = :coupon_id"), {"coupon_id": coupon_id})
    if product_ids:
        values = [{"coupon_id": coupon_id, "product_id": pid} for pid in product_ids]
        db.execute(
            text("INSERT INTO coupon_products (coupon_id, product_id) VALUES (:coupon_id, :product_id)"),
            values,
        )
    db.commit()


def set_coupon_categories(db: Session, coupon_id: int, category_ids: list[int]) -> None:
    db.execute(text("DELETE FROM coupon_categories WHERE coupon_id = :coupon_id"), {"coupon_id": coupon_id})
    if category_ids:
        values = [{"coupon_id": coupon_id, "category_id": cid} for cid in category_ids]
        db.execute(
            text("INSERT INTO coupon_categories (coupon_id, category_id) VALUES (:coupon_id, :category_id)"),
            values,
        )
    db.commit()


def verify_coupon(db: Session, code: str, user_id: int, cart_total: float) -> dict:
    coupon = get_coupon_by_code(db, code)
    if not coupon:
        return {"valid": False, "message": "Invalid coupon code."}

    if not coupon["is_active"]:
        return {"valid": False, "message": "This coupon is no longer active."}

    now = _now()
    if coupon["start_date"] and coupon["start_date"] > now:
        return {"valid": False, "message": "This coupon is not yet valid."}

    if coupon["end_date"] and coupon["end_date"] < now:
        return {"valid": False, "message": "This coupon has expired."}

    if coupon["usage_limit"] is not None and coupon["used_count"] >= coupon["usage_limit"]:
        return {"valid": False, "message": "This coupon has reached its usage limit."}

    user_usage = db.execute(text("""
        SELECT COUNT(*) AS cnt FROM coupon_users
        WHERE coupon_id = :coupon_id AND user_id = :user_id
    """), {"coupon_id": coupon["id"], "user_id": user_id}).scalar()
    if user_usage >= coupon["usage_per_user"]:
        return {"valid": False, "message": "You have already used this coupon the maximum number of times."}

    if cart_total < coupon["minimum_cart_amount"]:
        return {
            "valid": False,
            "message": f"Minimum cart amount is ₹{coupon['minimum_cart_amount']:.2f} to apply this coupon.",
        }

    discount_amount = 0.0
    if coupon["discount_type"] == "percentage":
        discount_amount = cart_total * (coupon["discount_value"] / 100)
        if coupon["maximum_discount"] is not None and discount_amount > coupon["maximum_discount"]:
            discount_amount = float(coupon["maximum_discount"])
    elif coupon["discount_type"] == "fixed":
        discount_amount = min(cart_total, float(coupon["discount_value"]))
    elif coupon["discount_type"] == "free_shipping":
        discount_amount = 0.0

    final_amount = max(0.0, cart_total - discount_amount)

    return {
        "valid": True,
        "message": "Coupon applied successfully!",
        "coupon": coupon,
        "discount_amount": round(discount_amount, 2),
        "final_amount": round(final_amount, 2),
    }


def record_coupon_usage(db: Session, coupon_id: int, user_id: int) -> None:
    db.execute(text("""
        INSERT INTO coupon_users (coupon_id, user_id, used_at) VALUES (:coupon_id, :user_id, :used_at)
    """), {"coupon_id": coupon_id, "user_id": user_id, "used_at": _now()})
    db.execute(text("""
        UPDATE coupons SET used_count = used_count + 1, updated_at = :updated_at WHERE id = :id
    """), {"updated_at": _now(), "id": coupon_id})
    db.commit()
