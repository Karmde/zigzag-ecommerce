from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.database import get_db
from dependencies.auth_dependency import get_current_user
from schemas.cart_schemas import AddToCartRequest, AddToCartResponse, CartItemResponse, UpdateCartQuantityRequest
from services import cart_services

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