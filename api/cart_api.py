from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.database import get_db
from dependencies.auth_dependency import get_current_user
from schemas.cart_schemas import (
    AddToCartRequest,
    AddToCartResponse,
    CartItemResponse,
    UpdateCartQuantityRequest,
    ApplyCouponRequest,
    ApplyCouponResponse,
    RemoveCouponRequest,
    RemoveCouponResponse,
)
from services import cart_services, coupon_services

router = APIRouter(prefix="/cart", tags=["Cart"])


@router.post("", response_model=AddToCartResponse, status_code=201)
def add_to_cart(
    payload: AddToCartRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return cart_services.add_to_cart(db, current_user["id"], payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=list[CartItemResponse])
def get_cart(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return cart_services.get_cart(db, current_user["id"])


@router.post("/coupon/apply", response_model=ApplyCouponResponse)
def apply_coupon(
    payload: ApplyCouponRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user["id"]
    cart_items = cart_services.get_cart(db, user_id)
    if not cart_items:
        raise HTTPException(status_code=400, detail="Your cart is empty.")

    cart_total = sum((item.get("unit_price") or 0) * item["quantity"] for item in cart_items)
    verification = coupon_services.verify_coupon(
        db, payload.code, user_id, cart_total, cart_items=cart_items
    )

    if not verification["valid"]:
        raise HTTPException(status_code=400, detail=verification["message"])

    coupon = dict(verification["coupon"])
    coupon["discount_amount"] = verification["discount_amount"]
    eligible_item_ids = verification.get("eligible_item_ids") or []
    if not eligible_item_ids:
        raise HTTPException(
            status_code=400,
            detail="This coupon is not applicable to any products in your cart.",
        )

    applied = cart_services.apply_coupon(db, user_id, coupon["id"], eligible_item_ids)
    ineligible_item_ids = [item["id"] for item in cart_items if item["id"] not in eligible_item_ids]

    return ApplyCouponResponse(
        success=True,
        message=verification["message"],
        applied_count=applied["updated_count"],
        eligible_item_ids=eligible_item_ids,
        ineligible_item_ids=ineligible_item_ids,
        coupon=coupon,
    )


@router.post("/coupon/remove", response_model=RemoveCouponResponse)
def remove_coupon(
    payload: RemoveCouponRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    removed = cart_services.remove_coupon(
        db, current_user["id"], payload.cart_item_ids
    )
    return RemoveCouponResponse(
        success=True,
        removed_count=removed["removed_count"],
    )


@router.delete("/{cart_item_id}")
def remove_from_cart(
    cart_item_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    removed = cart_services.remove_from_cart(db, current_user["id"], cart_item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Cart item not found.")
    return {"success": True, "deleted": cart_item_id}


@router.patch("/{cart_item_id}")
def update_cart_item(
    cart_item_id: int,
    payload: UpdateCartQuantityRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        updated = cart_services.update_cart_item_quantity(
            db, current_user["id"], cart_item_id, payload.quantity
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not updated:
        raise HTTPException(status_code=404, detail="Cart item not found.")
    return {"success": True, "cart_item_id": cart_item_id, "quantity": payload.quantity}


@router.delete("/clear")
def clear_cart(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = cart_services.clear_cart(db, current_user["id"])
    return {"success": True, "removed_items": count}