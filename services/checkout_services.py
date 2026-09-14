from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.cart_services import get_cart as _get_cart
from services.coupon_services import (
    get_coupon_by_id,
    get_coupon_products,
    get_coupon_categories,
)
from services.address_services import get_addresses as _get_addresses


def _calculate_item_price(base_price: float, discount_percent: float, price_override: float | None, discount_start: datetime | None = None, discount_end: datetime | None = None) -> float:
    if price_override is not None:
        base = price_override
    else:
        base = base_price
    now = datetime.now()
    effective_discount = discount_percent
    if discount_start and discount_end:
        if discount_start > now or discount_end < now:
            effective_discount = 0.0
    sale_price = round(base - (base * effective_discount / 100), 2)
    return sale_price


def _validate_cart_item(item: dict) -> str | None:
    if not item.get("product_id"):
        return "Product not found."
    if not item.get("is_active"):
        return f"Product '{item.get('product_name', '')}' is not available."
    stock = item.get("stock_quantity", 0)
    qty = item.get("quantity", 0)
    if stock < qty:
        return f"Only {stock} items left in stock for '{item.get('product_name', '')}'."
    return None


def _validate_coupon_for_item(db: Session, coupon: dict, item: dict, now: datetime) -> tuple[dict | None, str | None]:
    if not coupon:
        return None, None

    if not coupon.get("is_active"):
        return None, "Coupon is no longer active."

    start_date = coupon.get("start_date")
    end_date = coupon.get("end_date")
    if start_date and start_date > now:
        return None, "Coupon is not yet valid."
    if end_date and end_date < now:
        return None, "Coupon has expired."

    if coupon.get("usage_limit") is not None and (coupon.get("used_count") or 0) >= coupon["usage_limit"]:
        return None, "Coupon usage limit exceeded."

    minimum_cart_amount = float(coupon.get("minimum_cart_amount") or 0)

    coupon_product_ids = get_coupon_products(db, coupon["id"])
    coupon_category_ids = get_coupon_categories(db, coupon["id"])

    is_eligible = False
    if not coupon_product_ids and not coupon_category_ids:
        is_eligible = True
    else:
        item_product_id = item.get("product_id")
        item_category_ids = item.get("category_ids") or []
        if coupon_product_ids and item_product_id in coupon_product_ids:
            is_eligible = True
        if coupon_category_ids and set(item_category_ids).intersection(coupon_category_ids):
            is_eligible = True

    if not is_eligible:
        return None, None

    return coupon, None


def _calculate_coupon_discount(coupon: dict, unit_price: float, quantity: int, maximum_discount: float | None) -> float:
    line_total = unit_price * quantity
    discount_type = coupon.get("discount_type")
    discount_value = float(coupon.get("discount_value") or 0)

    if discount_type == "percentage":
        discount = line_total * (discount_value / 100)
        if maximum_discount is not None and discount > maximum_discount:
            discount = maximum_discount
    elif discount_type == "fixed":
        discount = min(line_total, discount_value)
    else:
        discount = 0.0

    return round(discount, 2)


def prepare_checkout(db: Session, user_id: int) -> dict:
    cart_items = _get_cart(db, user_id)
    if not cart_items:
        raise ValueError("Cart is empty")

    now = datetime.now()
    validated_items = []
    subtotal = 0.0
    original_total = 0.0
    total_product_discount = 0.0
    total_coupon_discount = 0.0
    has_validation_error = False
    validation_errors = []

    for item in cart_items:
        error = _validate_cart_item(item)
        if error:
            has_validation_error = True
            validation_errors.append(error)
            continue

        base_price = float(item.get("base_price") or 0)
        discount_percent = float(item.get("discount_percent") or 0)
        price_override = float(item["price_override"]) if item.get("price_override") is not None else None

        unit_price = _calculate_item_price(
            base_price=base_price,
            discount_percent=discount_percent,
            price_override=price_override,
            discount_start=item.get("discount_start"),
            discount_end=item.get("discount_end"),
        )

        quantity = item["quantity"]
        line_total = round(unit_price * quantity, 2)

        effective_base = price_override if price_override is not None else base_price
        original_line_total = round(effective_base * quantity, 2)
        product_discount = round(original_line_total - line_total, 2)

        subtotal += line_total
        original_total += original_line_total
        total_product_discount += product_discount

        coupon = None
        coupon_id = item.get("coupon_id")
        applied_coupon_discount = 0.0
        coupon_error = None

        if coupon_id:
            coupon_row = get_coupon_by_id(db, coupon_id)
            if coupon_row:
                validated_coupon, coupon_error = _validate_coupon_for_item(db, coupon_row, item, now)
                if validated_coupon and not coupon_error:
                    coupon = validated_coupon
                    applied_coupon_discount = _calculate_coupon_discount(
                        coupon=coupon,
                        unit_price=unit_price,
                        quantity=quantity,
                        maximum_discount=float(coupon["maximum_discount"]) if coupon.get("maximum_discount") is not None else None,
                    )
                    total_coupon_discount += applied_coupon_discount

        validated_items.append({
            "cart_item_id": item["id"],
            "product_id": item["product_id"],
            "product_variant_id": item["product_variant_id"],
            "product_name": item["product_name"],
            "sku": item["sku"],
            "color_name": item.get("color_name"),
            "size_name": item.get("size_name"),
            "image_url": item.get("image_url"),
            "quantity": quantity,
            "unit_price": unit_price,
            "line_total": line_total,
            "stock_quantity": item.get("stock_quantity", 0),
            "coupon_id": coupon_id if coupon else None,
            "coupon_code": coupon.get("code") if coupon else None,
            "coupon_discount_type": coupon.get("discount_type") if coupon else None,
            "coupon_discount_value": float(coupon["discount_value"]) if coupon else None,
            "coupon_applied_discount": applied_coupon_discount if applied_coupon_discount > 0 else None,
            "product_discount": product_discount if product_discount > 0 else None,
            "original_line_total": original_line_total,
        })

    if has_validation_error and not validated_items:
        raise ValueError("; ".join(validation_errors))

    addresses = _get_addresses(user_id, db)

    return {
        "items": validated_items,
        "subtotal": round(original_total, 2),
        "product_discount": round(total_product_discount, 2),
        "coupon_discount": round(total_coupon_discount, 2),
        "grand_total": round(original_total - total_product_discount - total_coupon_discount, 2),
        "addresses": addresses,
    }
