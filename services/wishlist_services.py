from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session

from schemas.wishlist_schemas import AddToWishlistRequest, AddToWishlistResponse


def _get_variant(db: Session, variant_id: int):
    row = db.execute(
        text("SELECT id, product_id, stock_quantity, is_active FROM product_variants WHERE id = :id"),
        {"id": variant_id},
    ).mappings().first()
    return row


def _wishlist_item_exists(db: Session, user_id: int, variant_id: int):
    row = db.execute(
        text("SELECT id FROM wishlist WHERE user_id = :uid AND product_variant_id = :vid"),
        {"uid": user_id, "vid": variant_id},
    ).mappings().first()
    return row


def add_to_wishlist(db: Session, user_id: int, payload: AddToWishlistRequest) -> AddToWishlistResponse:
    variant = _get_variant(db, payload.product_variant_id)
    if not variant:
        raise ValueError("Product variant not found.")

    existing = _wishlist_item_exists(db, user_id, payload.product_variant_id)
    if existing:
        raise ValueError("Item is already in your wishlist.")

    db.execute(
        text("""
            INSERT INTO wishlist (user_id, product_variant_id)
            VALUES (:uid, :vid)
        """),
        {"uid": user_id, "vid": payload.product_variant_id},
    )
    wishlist_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
    db.commit()

    row = db.execute(
        text("SELECT id, user_id, product_variant_id, created_at FROM wishlist WHERE id = :wid"),
        {"wid": wishlist_id},
    ).mappings().first()

    return AddToWishlistResponse(
        id=row["id"],
        user_id=row["user_id"],
        product_variant_id=row["product_variant_id"],
        created_at=row["created_at"],
    )


def get_wishlist(db: Session, user_id: int) -> list[dict]:
    rows = db.execute(
        text("""
            SELECT w.id, w.user_id, w.product_variant_id,
                   w.created_at AS created_at,
                   pv.product_id, pv.sku, pv.price_override, pv.stock_quantity, pv.is_active,
                   p.name AS product_name, p.slug AS product_slug, p.base_price, p.discount_percent,
                   c.name AS color_name, c.hex AS color_hex,
                   s.name AS size_name,
                   vi.url AS image_url
            FROM wishlist AS w
            JOIN product_variants AS pv ON pv.id = w.product_variant_id
            JOIN products AS p ON p.id = pv.product_id
            LEFT JOIN colors AS c ON c.id = pv.color_id
            LEFT JOIN sizes AS s ON s.id = pv.size_id
            LEFT JOIN (
                SELECT
                    product_id,
                    color_id,
                    url,
                    ROW_NUMBER() OVER (
                        PARTITION BY product_id, color_id
                        ORDER BY sort_order ASC
                    ) AS rn
                FROM variant_images
            ) vi
            ON vi.product_id = p.id
            AND vi.color_id = pv.color_id
            AND vi.rn = 1
            WHERE w.user_id = :uid
            ORDER BY w.created_at DESC
        """),
        {"uid": user_id},
    ).mappings().all()

    if not rows:
        return []

    product_ids = [r["product_id"] for r in rows]

    cat_rows = db.execute(
        text("""
            SELECT pc.product_id, c.name
            FROM product_categories AS pc
            JOIN categories AS c ON c.id = pc.category_id
            WHERE pc.product_id IN :ids
            ORDER BY pc.product_id, c.id
        """),
        {"ids": tuple(product_ids)},
    ).mappings().all()

    categories = {}
    for r in cat_rows:
        if r["product_id"] not in categories:
            categories[r["product_id"]] = r["name"]

    items = []
    for r in rows:
        base = float(r["base_price"]) if r["base_price"] else 0
        disc = float(r["discount_percent"]) if r["discount_percent"] else 0
        price_override = float(r["price_override"]) if r["price_override"] is not None else None
        if price_override is not None:
            base = price_override
            sale_price = round(base - (base * disc / 100), 2)
            unit_price = sale_price
        else:
            sale_price = round(base - (base * disc / 100), 2)
            unit_price = sale_price

        items.append({
            "id": r["id"],
            "user_id": r["user_id"],
            "product_variant_id": r["product_variant_id"],
            "sku": r["sku"],
            "product_name": r["product_name"],
            "product_slug": r["product_slug"],
            "color_name": r["color_name"],
            "color_hex": r["color_hex"],
            "size_name": r["size_name"],
            "image_url": r["image_url"],
            "unit_price": unit_price,
            "stock_quantity": r["stock_quantity"],
            "is_active": bool(r["is_active"]),
            "category_name": categories.get(r["product_id"], ""),
            "created_at": r["created_at"],
        })

    return items


def remove_from_wishlist(db: Session, user_id: int, wishlist_item_id: int) -> bool:
    result = db.execute(
        text("DELETE FROM wishlist WHERE id = :wid AND user_id = :uid"),
        {"wid": wishlist_item_id, "uid": user_id},
    )
    db.commit()
    return result.rowcount > 0


def is_in_wishlist(db: Session, user_id: int, variant_id: int) -> bool:
    row = db.execute(
        text("SELECT id FROM wishlist WHERE user_id = :uid AND product_variant_id = :vid"),
        {"uid": user_id, "vid": variant_id},
    ).mappings().first()
    return row is not None