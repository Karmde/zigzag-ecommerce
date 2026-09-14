from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session

from schemas.cart_schemas import AddToCartRequest, AddToCartResponse


def _get_variant(db: Session, variant_id: int):
    row = db.execute(
        text("SELECT id, product_id, stock_quantity, is_active FROM product_variants WHERE id = :id"),
        {"id": variant_id},
    ).mappings().first()
    return row


def _cart_item_exists(db: Session, user_id: int, variant_id: int):
    row = db.execute(
        text("SELECT id, quantity FROM cart_items WHERE user_id = :uid AND product_variant_id = :vid"),
        {"uid": user_id, "vid": variant_id},
    ).mappings().first()
    return row


def add_to_cart(db: Session, user_id: int, payload: AddToCartRequest) -> AddToCartResponse:
    variant = _get_variant(db, payload.product_variant_id)
    if not variant:
        raise ValueError("Product variant not found.")
    if not variant["is_active"]:
        raise ValueError("Product variant is not active.")
    if payload.quantity > variant["stock_quantity"]:
        raise ValueError(
            f"Requested quantity ({payload.quantity}) exceeds available stock ({variant['stock_quantity']})."
        )

    existing = _cart_item_exists(db, user_id, payload.product_variant_id)
    if existing:
        new_quantity = existing["quantity"] + payload.quantity
        if new_quantity > variant["stock_quantity"]:
            raise ValueError(
                f"Requested quantity ({new_quantity}) exceeds available stock ({variant['stock_quantity']})."
            )
        db.execute(
            text("UPDATE cart_items SET quantity = :qty WHERE id = :cid"),
            {"qty": new_quantity, "cid": existing["id"]},
        )
        cart_item_id = existing["id"]
    else:
        db.execute(
            text("""
                INSERT INTO cart_items (user_id, product_variant_id, quantity)
                VALUES (:uid, :vid, :qty)
            """),
            {"uid": user_id, "vid": payload.product_variant_id, "qty": payload.quantity},
        )
        cart_item_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()

    db.commit()

    row = db.execute(
        text("SELECT id, user_id, product_variant_id, quantity, created_at, updated_at FROM cart_items WHERE id = :cid"),
        {"cid": cart_item_id},
    ).mappings().first()

    return AddToCartResponse(
        id=row["id"],
        user_id=row["user_id"],
        product_variant_id=row["product_variant_id"],
        quantity=row["quantity"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_cart(db: Session, user_id: int) -> list[dict]:
    rows = db.execute(
        text("""
            SELECT ci.id, ci.user_id, ci.product_variant_id, ci.quantity, ci.coupon_id,
                pv.product_id, pv.sku, pv.price_override, pv.stock_quantity, pv.is_active,
                p.name AS product_name, p.slug AS product_slug,
                p.base_price, p.discount_percent, p.discount_start, p.discount_end,
                c.name AS color_name, c.hex AS color_hex,
                s.name AS size_name,
                vi.url AS image_url,
                ci.created_at,
                ci.updated_at
            FROM cart_items ci
            JOIN product_variants pv
                ON pv.id = ci.product_variant_id
            JOIN products p
                ON p.id = pv.product_id
            LEFT JOIN colors c
                ON c.id = pv.color_id
            LEFT JOIN sizes s
                ON s.id = pv.size_id

            LEFT JOIN (
                SELECT
                    id,
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

            WHERE ci.user_id = :uid
            ORDER BY ci.created_at ASC;
        """),
        {"uid": user_id},
    ).mappings().all()

    if not rows:
        return []

    product_ids = [r["product_id"] for r in rows]

    cat_rows = db.execute(
        text("""
            SELECT pc.product_id, c.id AS category_id, c.name
            FROM product_categories AS pc
            JOIN categories AS c ON c.id = pc.category_id
            WHERE pc.product_id IN :ids
            ORDER BY pc.product_id, c.id
        """),
        {"ids": tuple(product_ids)},
    ).mappings().all()

    categories = {}
    category_ids_map = {}
    for r in cat_rows:
        if r["product_id"] not in categories:
            categories[r["product_id"]] = r["name"]
        if r["product_id"] not in category_ids_map:
            category_ids_map[r["product_id"]] = []
        category_ids_map[r["product_id"]].append(r["category_id"])

    cart_items = []
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

        cart_items.append({
            "id": r["id"],
            "user_id": r["user_id"],
            "product_variant_id": r["product_variant_id"],
            "quantity": r["quantity"],
            "coupon_id": r["coupon_id"],
            "sku": r["sku"],
            "product_name": r["product_name"],
            "product_slug": r["product_slug"],
            "color_name": r["color_name"],
            "color_hex": r["color_hex"],
            "size_name": r["size_name"],
            "image_url": r["image_url"],
            "unit_price": unit_price,
            "base_price": base,
            "discount_percent": disc,
            "price_override": price_override,
            "discount_start": r["discount_start"],
            "discount_end": r["discount_end"],
            "stock_quantity": r["stock_quantity"],
            "is_active": bool(r["is_active"]),
            "product_id": r["product_id"],
            "category_ids": category_ids_map.get(r["product_id"], []),
            "category_name": categories.get(r["product_id"], ""),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        });

    return cart_items


def apply_coupon(
    db: Session,
    user_id: int,
    coupon_id: int,
    cart_item_ids: list[int] | None = None,
) -> dict:
    if cart_item_ids:
        result = db.execute(
            text("""
                UPDATE cart_items
                SET coupon_id = :coupon_id, updated_at = :updated_at
                WHERE user_id = :uid
                  AND id IN :item_ids
            """),
            {
                "coupon_id": coupon_id,
                "uid": user_id,
                "item_ids": tuple(cart_item_ids),
                "updated_at": datetime.now(),
            },
        )
    else:
        result = db.execute(
            text("""
                UPDATE cart_items
                SET coupon_id = :coupon_id, updated_at = :updated_at
                WHERE user_id = :uid
            """),
            {
                "coupon_id": coupon_id,
                "uid": user_id,
                "updated_at": datetime.now(),
            },
        )
    db.commit()
    return {
        "updated_count": result.rowcount,
        "coupon_id": coupon_id,
    }


def remove_coupon(
    db: Session,
    user_id: int,
    cart_item_ids: list[int] | None = None,
) -> dict:
    if cart_item_ids:
        result = db.execute(
            text("""
                UPDATE cart_items
                SET coupon_id = NULL, updated_at = :updated_at
                WHERE user_id = :uid
                  AND coupon_id IS NOT NULL
                  AND id IN :item_ids
            """),
            {
                "uid": user_id,
                "item_ids": tuple(cart_item_ids),
                "updated_at": datetime.now(),
            },
        )
    else:
        result = db.execute(
            text("""
                UPDATE cart_items
                SET coupon_id = NULL, updated_at = :updated_at
                WHERE user_id = :uid
                  AND coupon_id IS NOT NULL
            """),
            {
                "uid": user_id,
                "updated_at": datetime.now(),
            },
        )
    db.commit()
    return {
        "removed_count": result.rowcount,
    }


def remove_from_cart(db: Session, user_id: int, cart_item_id: int) -> bool:
    result = db.execute(
        text("DELETE FROM cart_items WHERE id = :cid AND user_id = :uid"),
        {"cid": cart_item_id, "uid": user_id},
    )
    db.commit()
    return result.rowcount > 0


def update_cart_item_quantity(db: Session, user_id: int, cart_item_id: int, quantity: int) -> bool:
    row = db.execute(
        text("SELECT product_variant_id FROM cart_items WHERE id = :cid AND user_id = :uid"),
        {"cid": cart_item_id, "uid": user_id},
    ).mappings().first()
    if not row:
        return False

    variant = _get_variant(db, row["product_variant_id"])
    if not variant or not variant["is_active"]:
        raise ValueError("Product variant is not available.")
    if quantity > variant["stock_quantity"]:
        raise ValueError(
            f"Requested quantity ({quantity}) exceeds available stock ({variant['stock_quantity']})."
        )

    db.execute(
        text("UPDATE cart_items SET quantity = :qty WHERE id = :cid AND user_id = :uid"),
        {"qty": quantity, "cid": cart_item_id, "uid": user_id},
    )
    db.commit()
    return True


def clear_cart(db: Session, user_id: int) -> int:
    result = db.execute(
        text("DELETE FROM cart_items WHERE user_id = :uid"),
        {"uid": user_id},
    )
    db.commit()
    return result.rowcount