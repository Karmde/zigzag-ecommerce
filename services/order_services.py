from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.checkout_services import (
    _calculate_item_price,
    _validate_cart_item,
    _validate_coupon_for_item,
    _calculate_coupon_discount,
)
from services.cart_services import get_cart as _get_cart, clear_cart as _clear_cart
from services.coupon_services import (
    get_coupon_by_id,
    get_coupon_products,
    get_coupon_categories,
)
from services.address_services import get_address as _get_address


def place_order(db: Session, user_id: int, address_id: int, payment_method: str) -> dict:
    with db.begin():
        cart_items = _get_cart(db, user_id)
        if not cart_items:
            raise ValueError("Cart is empty")

        now = datetime.now()
        validated_items = []
        subtotal = 0.0
        total_discount = 0.0
        used_coupon_ids = set()

        variant_ids = [item["product_variant_id"] for item in cart_items]

        locked_variants = {}
        if variant_ids:
            rows = db.execute(
                text("""
                    SELECT pv.id, pv.product_id, pv.sku, pv.stock_quantity, pv.is_active, pv.price_override,
                           p.base_price, p.discount_percent, p.discount_start, p.discount_end,
                           p.status, p.is_sellable, p.name, pv.color_id, pv.size_id
                    FROM product_variants pv
                    JOIN products p ON p.id = pv.product_id
                    WHERE pv.id IN :ids
                    FOR UPDATE
                """),
                {"ids": tuple(variant_ids)},
            ).mappings().all()
            for r in rows:
                locked_variants[r["id"]] = dict(r)

        product_ids = list(set(r["product_id"] for r in locked_variants.values() if r.get("product_id")))
        category_map = {}
        if product_ids:
            cat_rows = db.execute(
                text("""
                    SELECT pc.product_id, c.id AS category_id, c.name
                    FROM product_categories AS pc
                    JOIN categories AS c ON c.id = pc.category_id
                    WHERE pc.product_id IN :ids
                """),
                {"ids": tuple(product_ids)},
            ).mappings().all()
            for r in cat_rows:
                if r["product_id"] not in category_map:
                    category_map[r["product_id"]] = {"names": [], "ids": []}
                if r["category_id"] not in category_map[r["product_id"]]["ids"]:
                    category_map[r["product_id"]]["names"].append(r["name"])
                    category_map[r["product_id"]]["ids"].append(r["category_id"])

        for item in cart_items:
            variant = locked_variants.get(item["product_variant_id"])
            if not variant:
                raise ValueError(f"Product variant not found for item in cart.")

            cart_item_validation = {
                "product_id": variant["product_id"],
                "is_active": bool(variant["is_active"]),
                "stock_quantity": variant["stock_quantity"],
                "quantity": item["quantity"],
                "product_name": variant["name"],
            }
            error = _validate_cart_item(cart_item_validation)
            if error:
                raise ValueError(error)

            if variant["status"] != "active":
                raise ValueError(f"Product '{variant['name']}' is not active.")
            if not variant["is_sellable"]:
                raise ValueError(f"Product '{variant['name']}' is not sellable.")
            if variant["stock_quantity"] < item["quantity"]:
                raise ValueError(
                    f"Only {variant['stock_quantity']} items left in stock for '{variant['name']}'."
                )

            unit_price = _calculate_item_price(
                base_price=float(variant.get("base_price") or 0),
                discount_percent=float(variant.get("discount_percent") or 0),
                price_override=float(variant["price_override"]) if variant.get("price_override") is not None else None,
                discount_start=variant.get("discount_start"),
                discount_end=variant.get("discount_end"),
            )

            line_total = round(unit_price * item["quantity"], 2)
            subtotal += line_total

            coupon = None
            coupon_id = item.get("coupon_id")
            applied_discount = 0.0
            final_unit_price = unit_price
            final_line_total = line_total

            if coupon_id:
                coupon_row = get_coupon_by_id(db, coupon_id)
                if coupon_row:
                    item_for_coupon = {
                        "product_id": variant["product_id"],
                        "category_ids": category_map.get(variant["product_id"], {}).get("ids", []),
                    }
                    validated_coupon, coupon_error = _validate_coupon_for_item(db, coupon_row, item_for_coupon, now)
                    if validated_coupon and not coupon_error:
                        coupon = validated_coupon
                        applied_discount = _calculate_coupon_discount(
                            coupon=coupon,
                            unit_price=unit_price,
                            quantity=item["quantity"],
                            maximum_discount=float(coupon["maximum_discount"]) if coupon.get("maximum_discount") is not None else None,
                        )
                        total_discount += applied_discount
                        used_coupon_ids.add(coupon["id"])

                        if applied_discount > 0 and item["quantity"] > 0:
                            discount_per_unit = applied_discount / item["quantity"]
                            final_unit_price = max(0.0, unit_price - discount_per_unit)
                            final_line_total = round(final_unit_price * item["quantity"], 2)

            validated_items.append({
                "cart_item": item,
                "variant": variant,
                "unit_price": unit_price,
                "line_total": line_total,
                "final_unit_price": final_unit_price,
                "final_line_total": final_line_total,
                "coupon": coupon,
                "applied_discount": applied_discount,
            })

        address = _get_address(user_id, address_id, db)
        if not address:
            raise ValueError("Selected address not found.")

        order_result = db.execute(
            text("""
                INSERT INTO orders (
                    user_id, address_id, subtotal, discount, shipping_charge, total_amount,
                    payment_method, payment_status, created_at, updated_at
                ) VALUES (
                    :user_id, :address_id, :subtotal, :discount, :shipping_charge, :total_amount,
                    :payment_method, :payment_status, :now, :now
                )
            """),
            {
                "user_id": user_id,
                "address_id": address_id,
                "subtotal": round(subtotal, 2),
                "discount": round(total_discount, 2),
                "shipping_charge": 0.00,
                "total_amount": round(subtotal - total_discount, 2),
                "payment_method": payment_method,
                "payment_status": "paid" if payment_method == "upi" else "pending",
                "now": now,
            },
        )
        order_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()

        for vi in validated_items:
            item = vi["cart_item"]
            variant = vi["variant"]
            color_name = None
            size_name = None
            product_image = None
            if variant.get("color_id"):
                color_row = db.execute(
                    text("SELECT name FROM colors WHERE id = :id"),
                    {"id": variant["color_id"]},
                ).mappings().first()
                if color_row:
                    color_name = color_row["name"]

                variant_image_row = db.execute(
                    text("""
                        SELECT url FROM variant_images
                        WHERE product_id = :product_id AND color_id = :color_id
                        ORDER BY sort_order ASC
                        LIMIT 1
                    """),
                    {"product_id": variant["product_id"], "color_id": variant["color_id"]},
                ).mappings().first()
                if variant_image_row:
                    product_image = variant_image_row["url"]

            if variant.get("size_id"):
                size_row = db.execute(
                    text("SELECT name FROM sizes WHERE id = :id"),
                    {"id": variant["size_id"]},
                ).mappings().first()
                if size_row:
                    size_name = size_row["name"]

            if not product_image:
                image_row = db.execute(
                    text("""
                        SELECT url FROM product_images
                        WHERE product_id = :product_id
                        ORDER BY is_primary DESC, sort_order ASC
                        LIMIT 1
                    """),
                    {"product_id": variant["product_id"]},
                ).mappings().first()
                if image_row:
                    product_image = image_row["url"]

            db.execute(
                text("""
                    INSERT INTO order_items (
                        order_id, product_id, product_variant_id, coupon_id, coupon_discount,
                        product_name, product_image, sku,
                        color_name, size_name, unit_price, quantity, line_total,
                        status, cancelled_quantity, returned_quantity, refund_amount, refund_status,
                        cancel_reason, return_reason, cancelled_at, returned_at
                    ) VALUES (
                        :order_id, :product_id, :product_variant_id, :coupon_id, :coupon_discount,
                        :product_name, :product_image, :sku,
                        :color_name, :size_name, :unit_price, :quantity, :line_total,
                        :status, :cancelled_quantity, :returned_quantity, :refund_amount, :refund_status,
                        :cancel_reason, :return_reason, :cancelled_at, :returned_at
                    )
                """),
                {
                    "order_id": order_id,
                    "product_id": variant["product_id"],
                    "product_variant_id": variant["id"],
                    "coupon_id": vi["coupon"]["id"] if vi.get("coupon") else None,
                    "coupon_discount": round(vi.get("applied_discount", 0.0), 2) if vi.get("coupon") else None,
                    "product_name": variant["name"],
                    "product_image": product_image,
                    "sku": variant["sku"],
                    "color_name": color_name,
                    "size_name": size_name,
                    "unit_price": vi["unit_price"],
                    "quantity": item["quantity"],
                    "line_total": vi["line_total"],
                    "status": "pending",
                    "cancelled_quantity": 0,
                    "returned_quantity": 0,
                    "refund_amount": 0.00,
                    "refund_status": "none",
                    "cancel_reason": None,
                    "return_reason": None,
                    "cancelled_at": None,
                    "returned_at": None,
                },
            )

        for vi in validated_items:
            variant = vi["variant"]
            db.execute(
                text("""
                    UPDATE product_variants
                    SET stock_quantity = stock_quantity - :qty
                    WHERE id = :id AND stock_quantity >= :qty
                """),
                {"qty": vi["cart_item"]["quantity"], "id": variant["id"]},
            )

        for coupon_id in used_coupon_ids:
            db.execute(
                text("""
                    INSERT INTO coupon_users (coupon_id, user_id, used_at) VALUES (:coupon_id, :user_id, :used_at)
                """),
                {"coupon_id": coupon_id, "user_id": user_id, "used_at": now},
            )
            db.execute(
                text("""
                    UPDATE coupons SET used_count = used_count + 1, updated_at = :updated_at WHERE id = :id
                """),
                {"updated_at": now, "id": coupon_id},
            )

        db.execute(
            text("""
                UPDATE addresses
                SET is_used_for_order = 1, updated_at = :now
                WHERE id = :id AND user_id = :user_id
            """),
            {"now": now, "id": address_id, "user_id": user_id},
        )

        _clear_cart(db, user_id)

    return {
        "order_id": order_id,
        "payment_status": "paid" if payment_method == "upi" else "pending",
    }


def cancel_order_item(db: Session, order_id: int, order_item_id: int, user_id: int, reason: str | None = None) -> dict:
    with db.begin():
        order = db.execute(
            text("SELECT id, user_id FROM orders WHERE id = :order_id AND user_id = :user_id"),
            {"order_id": order_id, "user_id": user_id},
        ).mappings().first()
        if not order:
            raise ValueError("Order not found.")

        item = db.execute(
            text("""
                SELECT oi.*, pv.stock_quantity, pv.product_id, pv.sku, p.name AS product_name,
                       p.base_price, p.discount_percent, p.discount_start, p.discount_end, pv.price_override
                FROM order_items oi
                JOIN product_variants pv ON pv.id = oi.product_variant_id
                JOIN products p ON p.id = pv.product_id
                WHERE oi.id = :item_id AND oi.order_id = :order_id
                FOR UPDATE
            """),
            {"item_id": order_item_id, "order_id": order_id},
        ).mappings().first()
        if not item:
            raise ValueError("Order item not found.")

        if item["status"] not in ("pending", "confirmed", "processing"):
            raise ValueError("This item cannot be cancelled.")

        remaining_qty = item["quantity"] - item["cancelled_quantity"] - item["returned_quantity"]
        if remaining_qty <= 0:
            raise ValueError("This item has already been fully cancelled or returned.")

        cancel_qty = remaining_qty
        unit_price = float(item.get("unit_price") or 0)
        coupon_discount = float(item.get("coupon_discount") or 0)
        if coupon_discount > 0 and item["quantity"] > 0:
            coupon_per_unit = coupon_discount / item["quantity"]
            refund_unit_price = max(0.0, unit_price - coupon_per_unit)
        else:
            refund_unit_price = unit_price
        refund_amount = round(refund_unit_price * cancel_qty, 2)

        db.execute(
            text("""
                UPDATE order_items
                SET status = 'cancelled',
                    cancelled_quantity = :cancelled_quantity,
                    cancel_reason = :cancel_reason,
                    cancelled_at = :cancelled_at,
                    refund_amount = refund_amount + :refund_amount,
                    refund_status = 'pending',
                    updated_at = :updated_at
                WHERE id = :item_id
            """),
            {
                "cancelled_quantity": item["cancelled_quantity"] + cancel_qty,
                "cancel_reason": reason,
                "cancelled_at": datetime.now(),
                "refund_amount": refund_amount,
                "updated_at": datetime.now(),
                "item_id": order_item_id,
            },
        )

        db.execute(
            text("""
                UPDATE product_variants
                SET stock_quantity = stock_quantity + :qty
                WHERE id = :id
            """),
            {"qty": cancel_qty, "id": item["product_variant_id"]},
        )

        db.execute(
            text("""
                UPDATE orders
                SET payment_status = 'partially_refunded', updated_at = :updated_at
                WHERE id = :order_id
            """),
            {"updated_at": datetime.now(), "order_id": order_id},
        )

    return {
        "order_item_id": order_item_id,
        "cancelled_quantity": cancel_qty,
        "refund_amount": refund_amount,
        "refund_status": "pending",
    }


def return_order_item(db: Session, order_id: int, order_item_id: int, user_id: int, reason: str | None = None) -> dict:
    with db.begin():
        order = db.execute(
            text("SELECT id, user_id FROM orders WHERE id = :order_id AND user_id = :user_id"),
            {"order_id": order_id, "user_id": user_id},
        ).mappings().first()
        if not order:
            raise ValueError("Order not found.")

        item = db.execute(
            text("""
                SELECT oi.*, pv.stock_quantity, pv.product_id, pv.sku, p.name AS product_name,
                       p.base_price, p.discount_percent, p.discount_start, p.discount_end, pv.price_override
                FROM order_items oi
                JOIN product_variants pv ON pv.id = oi.product_variant_id
                JOIN products p ON p.id = pv.product_id
                WHERE oi.id = :item_id AND oi.order_id = :order_id
                FOR UPDATE
            """),
            {"item_id": order_item_id, "order_id": order_id},
        ).mappings().first()
        if not item:
            raise ValueError("Order item not found.")

        if item["status"] != "delivered":
            raise ValueError("Only delivered items can be returned.")

        remaining_qty = item["quantity"] - item["cancelled_quantity"] - item["returned_quantity"]
        if remaining_qty <= 0:
            raise ValueError("This item has already been fully returned.")

        return_qty = remaining_qty
        unit_price = float(item.get("unit_price") or 0)
        coupon_discount = float(item.get("coupon_discount") or 0)
        if coupon_discount > 0 and item["quantity"] > 0:
            coupon_per_unit = coupon_discount / item["quantity"]
            refund_unit_price = max(0.0, unit_price - coupon_per_unit)
        else:
            refund_unit_price = unit_price
        refund_amount = round(refund_unit_price * return_qty, 2)
        new_status = "returned" if return_qty == remaining_qty else item["status"]

        db.execute(
            text("""
                UPDATE order_items
                SET status = :status,
                    returned_quantity = :returned_quantity,
                    return_reason = :return_reason,
                    returned_at = :returned_at,
                    refund_amount = refund_amount + :refund_amount,
                    refund_status = 'pending',
                    updated_at = :updated_at
                WHERE id = :item_id
            """),
            {
                "status": new_status,
                "returned_quantity": item["returned_quantity"] + return_qty,
                "return_reason": reason,
                "returned_at": datetime.now(),
                "refund_amount": refund_amount,
                "updated_at": datetime.now(),
                "item_id": order_item_id,
            },
        )

        db.execute(
            text("""
                UPDATE product_variants
                SET stock_quantity = stock_quantity + :qty
                WHERE id = :id
            """),
            {"qty": return_qty, "id": item["product_variant_id"]},
        )

        db.execute(
            text("""
                UPDATE orders
                SET payment_status = 'partially_refunded', updated_at = :updated_at
                WHERE id = :order_id
            """),
            {"updated_at": datetime.now(), "order_id": order_id},
        )

    return {
        "order_item_id": order_item_id,
        "returned_quantity": return_qty,
        "refund_amount": refund_amount,
        "refund_status": "pending",
    }


def get_order_details(db: Session, order_id: int, user_id: int) -> dict:
    order = db.execute(
        text("""
            SELECT o.*, a.full_name, a.phone_number, a.address, a.landmark, a.city, a.state, a.country, a.postal_code, a.address_type
            FROM orders o
            JOIN addresses a ON a.id = o.address_id
            WHERE o.id = :order_id AND o.user_id = :user_id
        """),
        {"order_id": order_id, "user_id": user_id},
    ).mappings().first()
    if not order:
        raise ValueError("Order not found.")

    items = db.execute(
        text("""
            SELECT oi.*, pv.sku, p.name AS product_name, pv.product_id
            FROM order_items oi
            JOIN product_variants pv ON pv.id = oi.product_variant_id
            JOIN products p ON p.id = pv.product_id
            WHERE oi.order_id = :order_id
        """),
        {"order_id": order_id},
    ).mappings().all()

    return {
        "order": dict(order),
        "items": [dict(item) for item in items],
    }


def get_user_orders_paginated(
    db: Session,
    user_id: int,
    limit: int = 3,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
) -> dict:
    base_where = "WHERE o.user_id = :user_id"
    params: dict = {"user_id": user_id}

    if status:
        base_where += """
            AND EXISTS (
                SELECT 1 FROM order_items oi
                WHERE oi.order_id = o.id AND oi.status = :status
            )
        """
        params["status"] = status

    if search:
        term = f"%{search.strip()}%"
        base_where += """
            AND (
                CAST(o.id AS CHAR) LIKE :search
                OR EXISTS (
                    SELECT 1 FROM order_items oi2
                    JOIN products p ON p.id = oi2.product_id
                    WHERE oi2.order_id = o.id
                      AND (p.name LIKE :search OR oi2.sku LIKE :search)
                )
            )
        """
        params["search"] = term

    count_row = db.execute(
        text(f"""
            SELECT COUNT(DISTINCT o.id) AS total
            FROM orders o
            {base_where}
        """),
        params,
    ).mappings().first()
    total_count = count_row["total"] if count_row else 0

    orders = db.execute(
        text(f"""
            SELECT o.id, o.user_id, o.address_id, o.subtotal, o.discount, o.shipping_charge,
                   o.total_amount, o.payment_method, o.payment_status, o.created_at, o.updated_at,
                   a.full_name, a.phone_number, a.address, a.landmark, a.city, a.state, a.country,
                   a.postal_code, a.address_type
            FROM orders o
            JOIN addresses a ON a.id = o.address_id
            {base_where}
            ORDER BY o.created_at DESC, o.id DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": limit, "offset": offset},
    ).mappings().all()

    if not orders:
        return {"orders": [], "has_more": False, "total": total_count}

    order_list = [dict(order) for order in orders]
    order_ids = [o["id"] for o in order_list]

    search_term = f"%{search.strip()}%" if search else None

    items = db.execute(
        text("""
            SELECT oi.*, pv.sku, p.name AS product_name, pv.product_id, pv.color_id,
                   c.name AS color_name, s.name AS size_name, pv.stock_quantity, pv.is_active
            FROM order_items oi
            JOIN product_variants pv ON pv.id = oi.product_variant_id
            JOIN products p ON p.id = pv.product_id
            LEFT JOIN colors c ON c.id = pv.color_id
            LEFT JOIN sizes s ON s.id = pv.size_id
            WHERE oi.order_id IN :ids
              AND (:status IS NULL OR oi.status = :status)
              AND (
                  :search IS NULL
                  OR :search_is_order_id = 1
                  OR p.name LIKE :search_term
                  OR oi.sku LIKE :search_term
              )
            ORDER BY oi.id ASC
        """),
        {
            "ids": tuple(order_ids),
            "status": status,
            "search": search,
            "search_term": search_term,
            "search_is_order_id": 1 if (search and search.strip().isdigit()) else 0,
        },
    ).mappings().all()

    product_ids = list({item["product_id"] for item in items if item.get("product_id")})
    category_map: dict[int, str] = {}
    if product_ids:
        cat_rows = db.execute(
            text("""
                SELECT pc.product_id, c.name
                FROM product_categories pc
                JOIN categories c ON c.id = pc.category_id
                WHERE pc.product_id IN :ids
                ORDER BY pc.product_id, pc.category_id
            """),
            {"ids": tuple(product_ids)},
        ).mappings().all()
        for r in cat_rows:
            if r["product_id"] not in category_map:
                category_map[r["product_id"]] = r["name"]

    image_map: dict[tuple[int, int | None], str | None] = {}
    product_image_map: dict[int, str | None] = {}
    if product_ids:
        variant_image_rows = db.execute(
            text("""
                SELECT product_id, color_id, url
                FROM variant_images
                WHERE product_id IN :ids
                ORDER BY sort_order ASC
            """),
            {"ids": tuple(product_ids)},
        ).mappings().all()
        for r in variant_image_rows:
            key = (r["product_id"], r.get("color_id"))
            if key not in image_map:
                image_map[key] = r["url"]

        product_image_rows = db.execute(
            text("""
                SELECT product_id, url
                FROM product_images
                WHERE product_id IN :ids AND is_primary = 1
                ORDER BY sort_order ASC
            """),
            {"ids": tuple(product_ids)},
        ).mappings().all()
        for r in product_image_rows:
            if r["product_id"] not in product_image_map:
                product_image_map[r["product_id"]] = r["url"]

    product_has_available_variants: dict[int, bool] = {}
    if product_ids:
        availability_rows = db.execute(
            text("""
                SELECT product_id, COUNT(*) AS available_count
                FROM product_variants
                WHERE product_id IN :ids
                  AND is_active = 1
                  AND stock_quantity > 0
                GROUP BY product_id
            """),
            {"ids": tuple(product_ids)},
        ).mappings().all()
        for r in availability_rows:
            product_has_available_variants[r["product_id"]] = r["available_count"] > 0

    items_by_order: dict[int, list[dict]] = {}
    for item in items:
        oid = item["order_id"]
        items_by_order.setdefault(oid, []).append(dict(item))

    result = []
    for order in order_list:
        oid = order["id"]
        order_items = items_by_order.get(oid, [])
        if not order_items:
            continue
        enriched_items = []
        for item in order_items:
            product_image = None
            if item.get("product_id"):
                key = (item["product_id"], item.get("color_id"))
                product_image = image_map.get(key)
                if not product_image:
                    product_image = product_image_map.get(item["product_id"])

            enriched_items.append({
                "id": item["id"],
                "order_id": item["order_id"],
                "product_id": item.get("product_id"),
                "product_variant_id": item["product_variant_id"],
                "product_name": item.get("product_name", ""),
                "product_image": product_image,
                "sku": item.get("sku", ""),
                "color_id": item.get("color_id"),
                "size_id": item.get("size_id"),
                "color_name": item.get("color_name"),
                "size_name": item.get("size_name"),
                "unit_price": float(item.get("unit_price") or 0),
                "quantity": item.get("quantity", 0),
                "line_total": float(item.get("line_total") or 0),
                "status": item.get("status", "pending"),
                "category_name": category_map.get(item.get("product_id"), ""),
                "stock_quantity": item.get("stock_quantity", 0),
                "is_active": item.get("is_active", False),
                "has_available_variants": product_has_available_variants.get(item.get("product_id"), False),
                "cancelled_quantity": item.get("cancelled_quantity", 0),
                "returned_quantity": item.get("returned_quantity", 0),
                "cancel_reason": item.get("cancel_reason"),
                "return_reason": item.get("return_reason"),
                "cancelled_at": item.get("cancelled_at"),
                "returned_at": item.get("returned_at"),
                "refund_amount": float(item.get("refund_amount") or 0),
                "refund_status": item.get("refund_status", "none"),
                "coupon_id": item.get("coupon_id"),
                "coupon_discount": float(item.get("coupon_discount") or 0),
            })

        result.append({
            "id": order["id"],
            "user_id": order["user_id"],
            "address_id": order["address_id"],
            "subtotal": float(order.get("subtotal") or 0),
            "discount": float(order.get("discount") or 0),
            "shipping_charge": float(order.get("shipping_charge") or 0),
            "total_amount": float(order.get("total_amount") or 0),
            "payment_method": order.get("payment_method", ""),
            "payment_status": order.get("payment_status", ""),
            "created_at": order.get("created_at"),
            "updated_at": order.get("updated_at"),
            "full_name": order.get("full_name", ""),
            "phone_number": order.get("phone_number", ""),
            "address": order.get("address", ""),
            "landmark": order.get("landmark"),
            "city": order.get("city", ""),
            "state": order.get("state", ""),
            "country": order.get("country", ""),
            "postal_code": order.get("postal_code", ""),
            "address_type": order.get("address_type", "home"),
            "items": enriched_items,
        })

    has_more = len(result) == limit

    return {
        "orders": result,
        "has_more": has_more,
        "total": total_count,
    }


def get_user_orders(db: Session, user_id: int) -> list[dict]:
    orders = db.execute(
        text("""
            SELECT o.id, o.user_id, o.address_id, o.subtotal, o.discount, o.shipping_charge,
                   o.total_amount, o.payment_method, o.payment_status, o.created_at, o.updated_at,
                   a.full_name, a.phone_number, a.address, a.landmark, a.city, a.state, a.country,
                   a.postal_code, a.address_type
            FROM orders o
            JOIN addresses a ON a.id = o.address_id
            WHERE o.user_id = :user_id
            ORDER BY o.created_at DESC, o.id DESC
        """),
        {"user_id": user_id},
    ).mappings().all()

    if not orders:
        return []

    order_list = [dict(order) for order in orders]
    order_ids = [o["id"] for o in order_list]

    items = db.execute(
        text("""
            SELECT oi.*, pv.sku, p.name AS product_name, pv.product_id, pv.color_id,
                   c.name AS color_name, s.name AS size_name, pv.stock_quantity, pv.is_active
            FROM order_items oi
            JOIN product_variants pv ON pv.id = oi.product_variant_id
            JOIN products p ON p.id = pv.product_id
            LEFT JOIN colors c ON c.id = pv.color_id
            LEFT JOIN sizes s ON s.id = pv.size_id
            WHERE oi.order_id IN :ids
            ORDER BY oi.id ASC
        """),
        {"ids": tuple(order_ids)},
    ).mappings().all()

    product_ids = list({item["product_id"] for item in items if item.get("product_id")})
    category_map: dict[int, str] = {}
    if product_ids:
        cat_rows = db.execute(
            text("""
                SELECT pc.product_id, c.name
                FROM product_categories pc
                JOIN categories c ON c.id = pc.category_id
                WHERE pc.product_id IN :ids
                ORDER BY pc.product_id, pc.category_id
            """),
            {"ids": tuple(product_ids)},
        ).mappings().all()
        for r in cat_rows:
            if r["product_id"] not in category_map:
                category_map[r["product_id"]] = r["name"]

    image_map: dict[tuple[int, int | None], str | None] = {}
    variant_image_rows = db.execute(
        text("""
            SELECT product_id, color_id, url
            FROM variant_images
            WHERE product_id IN :ids
            ORDER BY sort_order ASC
        """),
        {"ids": tuple(product_ids)},
    ).mappings().all()
    for r in variant_image_rows:
        key = (r["product_id"], r.get("color_id"))
        if key not in image_map:
            image_map[key] = r["url"]

    product_image_rows = db.execute(
        text("""
            SELECT product_id, url
            FROM product_images
            WHERE product_id IN :ids AND is_primary = 1
            ORDER BY sort_order ASC
        """),
        {"ids": tuple(product_ids)},
    ).mappings().all()
    primary_image_map: dict[int, str | None] = {}
    for r in product_image_rows:
        if r["product_id"] not in primary_image_map:
            primary_image_map[r["product_id"]] = r["url"]

    product_has_available_variants: dict[int, bool] = {}
    if product_ids:
        availability_rows = db.execute(
            text("""
                SELECT product_id, COUNT(*) AS available_count
                FROM product_variants
                WHERE product_id IN :ids
                  AND is_active = 1
                  AND stock_quantity > 0
                GROUP BY product_id
            """),
            {"ids": tuple(product_ids)},
        ).mappings().all()
        for r in availability_rows:
            product_has_available_variants[r["product_id"]] = r["available_count"] > 0

    items_by_order: dict[int, list[dict]] = {}
    for item in items:
        oid = item["order_id"]
        items_by_order.setdefault(oid, []).append(dict(item))

    result = []
    for order in order_list:
        oid = order["id"]
        order_items = items_by_order.get(oid, [])
        enriched_items = []
        for item in order_items:
            product_image = None
            if item.get("product_id"):
                key = (item["product_id"], item.get("color_id"))
                product_image = image_map.get(key)
                if not product_image:
                    product_image = primary_image_map.get(item["product_id"])

            enriched_items.append({
                "id": item["id"],
                "order_id": item["order_id"],
                "product_id": item.get("product_id"),
                "product_variant_id": item["product_variant_id"],
                "product_name": item.get("product_name", ""),
                "product_image": product_image,
                "sku": item.get("sku", ""),
                "color_id": item.get("color_id"),
                "size_id": item.get("size_id"),
                "color_name": item.get("color_name"),
                "size_name": item.get("size_name"),
                "unit_price": float(item.get("unit_price") or 0),
                "quantity": item.get("quantity", 0),
                "line_total": float(item.get("line_total") or 0),
                "status": item.get("status", "pending"),
                "category_name": category_map.get(item.get("product_id"), ""),
                "stock_quantity": item.get("stock_quantity", 0),
                "is_active": item.get("is_active", False),
                "has_available_variants": product_has_available_variants.get(item.get("product_id"), False),
                "cancelled_quantity": item.get("cancelled_quantity", 0),
                "returned_quantity": item.get("returned_quantity", 0),
                "cancel_reason": item.get("cancel_reason"),
                "return_reason": item.get("return_reason"),
                "cancelled_at": item.get("cancelled_at"),
                "returned_at": item.get("returned_at"),
                "refund_amount": float(item.get("refund_amount") or 0),
                "refund_status": item.get("refund_status", "none"),
                "coupon_id": item.get("coupon_id"),
                "coupon_discount": float(item.get("coupon_discount") or 0),
            })

        result.append({
            "id": order["id"],
            "user_id": order["user_id"],
            "address_id": order["address_id"],
            "subtotal": float(order.get("subtotal") or 0),
            "discount": float(order.get("discount") or 0),
            "shipping_charge": float(order.get("shipping_charge") or 0),
            "total_amount": float(order.get("total_amount") or 0),
            "payment_method": order.get("payment_method", ""),
            "payment_status": order.get("payment_status", ""),
            "created_at": order.get("created_at"),
            "updated_at": order.get("updated_at"),
            "full_name": order.get("full_name", ""),
            "phone_number": order.get("phone_number", ""),
            "address": order.get("address", ""),
            "landmark": order.get("landmark"),
            "city": order.get("city", ""),
            "state": order.get("state", ""),
            "country": order.get("country", ""),
            "postal_code": order.get("postal_code", ""),
            "address_type": order.get("address_type", "home"),
            "items": enriched_items,
        })

    return result


def get_order_item_tracking(db: Session, order_id: int, order_item_id: int, user_id: int) -> dict:
    order = db.execute(
        text("""
            SELECT o.id, o.user_id, o.subtotal, o.discount, o.total_amount,
                   o.payment_method, o.payment_status, o.created_at, o.updated_at,
                   a.full_name, a.phone_number, a.address, a.landmark, a.city, a.state, a.country,
                   a.postal_code, a.address_type
            FROM orders o
            JOIN addresses a ON a.id = o.address_id
            WHERE o.id = :order_id AND o.user_id = :user_id
        """),
        {"order_id": order_id, "user_id": user_id},
    ).mappings().first()
    if not order:
        raise ValueError("Order not found.")

    item = db.execute(
        text("""
            SELECT oi.*, pv.sku, p.name AS product_name, pv.product_id
            FROM order_items oi
            JOIN product_variants pv ON pv.id = oi.product_variant_id
            JOIN products p ON p.id = pv.product_id
            WHERE oi.id = :item_id AND oi.order_id = :order_id
        """),
        {"item_id": order_item_id, "order_id": order_id},
    ).mappings().first()
    if not item:
        raise ValueError("Order item not found.")

    status = item.get("status", "pending")

    if status in ("cancelled", "returned"):
        return {
            "order": dict(order),
            "item": dict(item),
            "show_timeline": False,
            "timeline": [],
        }

    all_statuses = [
        ("pending", "Order Placed", "Your order has been successfully placed."),
        ("confirmed", "Order Confirmed", "Your order has been confirmed."),
        ("processing", "Processing", "Your order is being prepared for shipment."),
        ("shipped", "Shipped", "Your order has been shipped."),
        ("delivered", "Delivered", "Your order has been delivered."),
    ]

    current_index = -1
    for idx, (s, _, _) in enumerate(all_statuses):
        if s == status:
            current_index = idx
            break

    timeline = []
    for idx, (s, title, description) in enumerate(all_statuses):
        is_current = idx == current_index and status != "delivered"
        is_completed = idx <= current_index or status == "delivered"
        timeline.append({
            "status": s,
            "title": title,
            "description": description,
            "time": item.get("updated_at") if idx <= current_index else None,
            "completed": is_completed,
            "current": is_current,
        })

    return {
        "order": dict(order),
        "item": dict(item),
        "show_timeline": True,
        "timeline": timeline,
    }
