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
            SELECT ci.id, ci.user_id, ci.product_variant_id, ci.quantity,
                   pv.product_id, pv.sku, pv.price_override, pv.stock_quantity, pv.is_active,
                   p.name AS product_name, p.slug AS product_slug, p.base_price, p.discount_percent,
                   c.name AS color_name, c.hex AS color_hex,
                   s.name AS size_name,
                   vi.url AS image_url,
                   ci.created_at AS created_at,
                   ci.updated_at AS updated_at
            FROM cart_items AS ci
            JOIN product_variants AS pv ON pv.id = ci.product_variant_id
            JOIN products AS p ON p.id = pv.product_id
            LEFT JOIN colors AS c ON c.id = pv.color_id
            LEFT JOIN sizes AS s ON s.id = pv.size_id
            LEFT JOIN variant_images AS vi ON vi.id = (
                SELECT id FROM variant_images AS vi2
                WHERE vi2.product_id = p.id AND vi2.color_id = pv.color_id
                ORDER BY vi2.sort_order ASC
                LIMIT 1
            )
            WHERE ci.user_id = :uid
            ORDER BY ci.created_at ASC
        """),
        {"uid": user_id},
    ).mappings().all()

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

        cat_rows = db.execute(
            text("""
                SELECT c.name
                FROM product_categories AS pc
                JOIN categories AS c ON c.id = pc.category_id
                WHERE pc.product_id = :pid
                ORDER BY c.id
            """),
            {"pid": r["product_id"]},
        ).mappings().all()
        category_name = ", ".join(row["name"] for row in cat_rows) if cat_rows else ""

        cart_items.append({
            "id": r["id"],
            "user_id": r["user_id"],
            "product_variant_id": r["product_variant_id"],
            "quantity": r["quantity"],
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
            "stock_quantity": r["stock_quantity"],
            "is_active": bool(r["is_active"]),
            "category_name": category_name,
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        });

    return cart_items


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