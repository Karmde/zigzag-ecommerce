from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.database import get_db
from dependencies.auth_dependency import get_current_user
from schemas.wishlist_schemas import AddToWishlistRequest, AddToWishlistResponse, WishlistItemResponse
from services import wishlist_services

router = APIRouter(prefix="/wishlist", tags=["Wishlist"])


@router.post("", response_model=AddToWishlistResponse, status_code=201)
def add_to_wishlist(
    payload: AddToWishlistRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return wishlist_services.add_to_wishlist(db, current_user["id"], payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=list[WishlistItemResponse])
def get_wishlist(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return wishlist_services.get_wishlist(db, current_user["id"])


@router.delete("/{wishlist_item_id}")
def remove_from_wishlist(
    wishlist_item_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    removed = wishlist_services.remove_from_wishlist(db, current_user["id"], wishlist_item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Wishlist item not found.")
    return {"success": True, "deleted": wishlist_item_id}


@router.get("/check")
def check_wishlist(
    product_variant_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    in_wishlist = wishlist_services.is_in_wishlist(db, current_user["id"], product_variant_id)
    return {"product_variant_id": product_variant_id, "in_wishlist": in_wishlist}