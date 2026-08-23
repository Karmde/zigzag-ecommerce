from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.database import get_db
from schemas.coupon_schemas import (
    CouponCreateRequest,
    CouponUpdateRequest,
    CouponResponse,
    CouponVerifyRequest,
    CouponVerifyResponse,
)
from services import coupon_services
from dependencies.auth_dependency import get_current_user, get_current_admin

router = APIRouter(prefix="/coupons", tags=["Coupons"])


@router.post("", response_model=CouponResponse, status_code=201)
def create_coupon(
    payload: CouponCreateRequest,
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    existing = coupon_services.get_coupon_by_code(db, payload.code)
    if existing:
        raise HTTPException(status_code=409, detail="A coupon with this code already exists.")
    coupon = coupon_services.create_coupon(db, payload.model_dump())
    coupon_services.set_coupon_products(db, coupon["id"], payload.product_ids or [])
    coupon_services.set_coupon_categories(db, coupon["id"], payload.category_ids or [])
    return coupon


@router.get("", response_model=list[CouponResponse])
def list_coupons(
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return coupon_services.list_coupons(db)


@router.get("/active", response_model=list[CouponResponse])
def list_active_coupons(
    db: Session = Depends(get_db),
):
    return coupon_services.list_coupons(db, active_only=True)


@router.get("/{coupon_id}", response_model=CouponResponse)
def get_coupon(
    coupon_id: int,
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    coupon = coupon_services.get_coupon_by_id(db, coupon_id)
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found.")
    return coupon


@router.put("/{coupon_id}", response_model=CouponResponse)
def update_coupon(
    coupon_id: int,
    payload: CouponUpdateRequest,
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    data = payload.model_dump(exclude_none=True)
    if "product_ids" in data:
        product_ids = data.pop("product_ids") or []
        coupon = coupon_services.get_coupon_by_id(db, coupon_id)
        if not coupon:
            raise HTTPException(status_code=404, detail="Coupon not found.")
        coupon_services.set_coupon_products(db, coupon_id, product_ids)
    if "category_ids" in data:
        category_ids = data.pop("category_ids") or []
        coupon = coupon_services.get_coupon_by_id(db, coupon_id)
        if not coupon:
            raise HTTPException(status_code=404, detail="Coupon not found.")
        coupon_services.set_coupon_categories(db, coupon_id, category_ids)
    coupon = coupon_services.update_coupon(db, coupon_id, data)
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found.")
    return coupon


@router.delete("/{coupon_id}")
def delete_coupon(
    coupon_id: int,
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    success = coupon_services.soft_delete_coupon(db, coupon_id)
    if not success:
        raise HTTPException(status_code=404, detail="Coupon not found.")
    return {"success": True, "deleted": coupon_id}


@router.post("/verify", response_model=CouponVerifyResponse)
def verify_coupon(
    payload: CouponVerifyRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = coupon_services.verify_coupon(db, payload.code, current_user["id"], payload.cart_total)
    return CouponVerifyResponse(**result)
