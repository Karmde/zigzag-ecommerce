from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from core.templates import templates
from database.database import get_db
from services import cart_services, wishlist_services, coupon_services, checkout_services, order_services
from services.token_services import decode_order_confirmation_token
from dependencies.auth_dependency import get_current_user_from_cookie


router = APIRouter()


@router.get("/cart")
async def cart(request: Request, current_user: dict = Depends(get_current_user_from_cookie), db: Session = Depends(get_db)):
    user_id = current_user["id"]
    cart_items = []
    cart_total = 0.0
    original_total = 0.0
    total_savings = 0.0
    wishlist_variant_ids = []
    wishlist_map = {}
    applied_coupon = None

    cart_items = cart_services.get_cart(db, user_id)
    for item in cart_items:
        qty = item["quantity"]
        base = item.get("base_price") or 0
        unit = item.get("unit_price") or 0
        original_total += base * qty
        cart_total += unit * qty
        total_savings += (base - unit) * qty

    applied_coupon_ids = [item["coupon_id"] for item in cart_items if item.get("coupon_id")]
    if applied_coupon_ids:
        coupon_id = applied_coupon_ids[0]
        coupon = coupon_services.get_coupon_by_id(db, coupon_id)
        if coupon:
            verification = coupon_services.verify_coupon(
                db, coupon["code"], user_id, cart_total, cart_items=cart_items
            )
            if verification["valid"]:
                applied_coupon = {
                    "code": coupon["code"],
                    "discount_amount": verification["discount_amount"],
                    "message": verification["message"],
                }

    wishlist_items = wishlist_services.get_wishlist(db, user_id)
    wishlist_variant_ids = [item["product_variant_id"] for item in wishlist_items]
    wishlist_map = {str(item["product_variant_id"]): item["id"] for item in wishlist_items}

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
            "applied_coupon": applied_coupon,
        },
    )


@router.get("/wishlist")
async def wishlist(request: Request, current_user: dict = Depends(get_current_user_from_cookie), db: Session = Depends(get_db)):
    user_id = current_user["id"]
    wishlist_items = []
    wishlist_variant_ids = []

    wishlist_items = wishlist_services.get_wishlist(db, user_id)
    wishlist_variant_ids = [item["product_variant_id"] for item in wishlist_items]

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


@router.get("/checkout")
async def checkout(request: Request, current_user: dict = Depends(get_current_user_from_cookie), db: Session = Depends(get_db)):
    user_id = current_user["id"]
    checkout_data = checkout_services.prepare_checkout(db, user_id)
    return templates.TemplateResponse(
        request=request,
        name="user/checkout.html",
        context={
            "checkout_items": checkout_data.get("items", []),
            "checkout_subtotal": checkout_data.get("subtotal", 0),
            "checkout_product_discount": checkout_data.get("product_discount", 0),
            "checkout_coupon_discount": checkout_data.get("coupon_discount", 0),
            "checkout_grand_total": checkout_data.get("grand_total", 0),
            "checkout_addresses": checkout_data.get("addresses", []),
        },
    )

@router.get("/order-confirmation", response_class=HTMLResponse)
async def order_confirmation(
    request: Request,
    token: str,
    current_user: dict = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db),
):
    decoded = decode_order_confirmation_token(token)
    if not decoded:
        raise HTTPException(status_code=404, detail="Invalid or expired confirmation link.")

    order_id = decoded["order_id"]
    token_user_id = decoded["user_id"]

    if token_user_id != current_user["id"]:
        raise HTTPException(status_code=404, detail="Order not found.")

    try:
        data = order_services.get_order_details(db, order_id, current_user["id"])
    except ValueError:
        raise HTTPException(status_code=404, detail="Order not found.")

    order = data["order"]
    items = data["items"]

    address_type = order.get("address_type") or "home"
    order_date = order.get("created_at")
    if order_date:
        formatted_date = order_date.strftime("%d %b %Y, %I:%M %p")
    else:
        formatted_date = ""

    return templates.TemplateResponse(
        request=request,
        name="user/order_confirmation.html",
        context={
            "order_id": order_id,
            "order_date": formatted_date,
            "payment_method": order.get("payment_method", ""),
            "payment_status": order.get("payment_status", ""),
            "total_amount": order.get("total_amount", 0),
            "address": {
                "full_name": order.get("full_name", ""),
                "phone_number": order.get("phone_number", ""),
                "address": order.get("address", ""),
                "landmark": order.get("landmark"),
                "city": order.get("city", ""),
                "state": order.get("state", ""),
                "country": order.get("country", ""),
                "postal_code": order.get("postal_code", ""),
                "address_type": address_type,
            },
            "items": items,
            "items_count": len(items),
        },
    )

@router.get("/orders")
async def orders(request: Request, current_user: dict = Depends(get_current_user_from_cookie)):
    return templates.TemplateResponse(
        request=request,
        name="user/orders.html",
        context={},
    )


@router.get("/view-details")
async def view_details(
    request: Request,
    order_id: int = Query(...),
    item_id: int = Query(...),
    current_user: dict = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db),
):
    try:
        data = order_services.get_order_item_tracking(db, order_id, item_id, current_user["id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    order = data["order"]
    item = data["item"]

    if data["show_timeline"]:
        timeline = data["timeline"]
    else:
        timeline = []

    address_type = order.get("address_type") or "home"
    order_date = order.get("created_at")
    if order_date:
        formatted_date = order_date.strftime("%d %b %Y, %I:%M %p")
    else:
        formatted_date = ""

    return templates.TemplateResponse(
        request=request,
        name="user/view_details.html",
        context={
            "order_id": order.get("id"),
            "item_id": item.get("id"),
            "order_date": formatted_date,
            "payment_method": order.get("payment_method", ""),
            "payment_status": order.get("payment_status", ""),
            "total_amount": order.get("total_amount", 0),
            "address": {
                "full_name": order.get("full_name", ""),
                "phone_number": order.get("phone_number", ""),
                "address": order.get("address", ""),
                "landmark": order.get("landmark"),
                "city": order.get("city", ""),
                "state": order.get("state", ""),
                "country": order.get("country", ""),
                "postal_code": order.get("postal_code", ""),
                "address_type": address_type,
            },
            "item": item,
            "show_timeline": data["show_timeline"],
            "timeline": timeline,
            "item_status": item.get("status", "pending"),
        },
    )