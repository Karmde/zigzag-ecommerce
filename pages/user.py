from fastapi import APIRouter, Request, Depends
from core.templates import templates
from database.database import get_db
from services import cart_services, wishlist_services
from dependencies.auth_dependency import get_current_user_from_cookie


router = APIRouter()


@router.get("/cart")
async def cart(request: Request, current_user: dict = Depends(get_current_user_from_cookie)):
    db = next(get_db())
    try:
        user_id = current_user["id"]
        cart_items = []
        cart_total = 0.0
        original_total = 0.0
        total_savings = 0.0
        wishlist_variant_ids = []
        wishlist_map = {}

        cart_items = cart_services.get_cart(db, user_id)
        for item in cart_items:
            qty = item["quantity"]
            base = item.get("base_price") or 0
            unit = item.get("unit_price") or 0
            original_total += base * qty
            cart_total += unit * qty
            total_savings += (base - unit) * qty
        wishlist_items = wishlist_services.get_wishlist(db, user_id)
        wishlist_variant_ids = [item["product_variant_id"] for item in wishlist_items]
        wishlist_map = {str(item["product_variant_id"]): item["id"] for item in wishlist_items}
    finally:
        db.close()

    has_discount = any((item.get("discount_percent") or 0) > 0 for item in cart_items)

    return templates.TemplateResponse(
        request=request,
        name="user/cart.html",
        context={
            "cart_items": cart_items,
            "cart_total": round(cart_total, 2),
            "original_total": round(original_total, 2),
            "total_savings": int(total_savings),
            "has_discount": has_discount,
            "wishlist_variant_ids": wishlist_variant_ids,
            "wishlist_map": wishlist_map,
        },
    )

@router.get("/wishlist")
async def wishlist(request: Request, current_user: dict = Depends(get_current_user_from_cookie)):
    db = next(get_db())
    try:
        user_id = current_user["id"]
        wishlist_items = []
        wishlist_variant_ids = []

        wishlist_items = wishlist_services.get_wishlist(db, user_id)
        wishlist_variant_ids = [item["product_variant_id"] for item in wishlist_items]
    finally:
        db.close()

    return templates.TemplateResponse(
        request=request,
        name="user/wishlist.html",
        context={"wishlist_items": wishlist_items, "wishlist_variant_ids": wishlist_variant_ids},
    )

@router.get("/coupon")
async def coupon(request: Request):
    return templates.TemplateResponse(
            request=request,
            name="user/coupon.html"
        )

@router.get("/addresses")
async def coupon(request: Request):
    return templates.TemplateResponse(
            request=request,
            name="user/addresses.html"
        )