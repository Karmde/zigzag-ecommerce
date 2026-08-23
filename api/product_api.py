from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List

from database.database import get_db
from schemas.product_schemas import (
    ProductPayload,
    ProductPayloadResponse,
    ProductResponse,
    ProductDetailResponse,
)
from services import product_services
from dependencies.auth_dependency import get_current_user, get_current_admin

router = APIRouter(prefix="/products", tags=["Products"])


@router.post("", response_model=ProductPayloadResponse, status_code=201)
def create_product(
    payload: ProductPayload,
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        return product_services.save_product(db, payload)
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=_friendly_integrity_error(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _friendly_integrity_error(e: IntegrityError) -> str:
    msg = str(e)
    if "products.slug" in msg:
        return "A product with this slug already exists. Change the product name or slug and try again."
    if "product_variants.sku" in msg:
        return "One of the variant SKUs is already in use. Use a unique SKU for every variant."
    if "Duplicate entry" in msg:
        import re
        m = re.search(r"Duplicate entry '(.+?)' for key '(.+?)'", msg)
        if m:
            value, key = m.group(1), m.group(2)
            return f"Duplicate value '{value}' for '{key}'. A record with this value already exists — use a unique value."
        return "A value conflicts with an existing record. Please check the name, slug and SKUs."
    return "Could not save the product due to a database conflict. Please try again."


@router.get("", response_model=list[ProductResponse])
def list_products(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str = Query(None),
    brand_id: int = Query(None),
    gender_id: int = Query(None),
):
    is_admin = False
    return product_services.get_products(
        db,
        limit=limit,
        offset=offset,
        status=status,
        brand_id=brand_id,
        gender_id=gender_id,
        is_admin=is_admin,
    )


@router.post("/{product_id}/viewed")
def view_product(
    product_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.execute(text("SELECT id FROM products WHERE id = :id"), {"id": product_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Product not found.")
    product_services.add_recently_viewed(db, current_user["id"], product_id)
    db.commit()
    return {"success": True}


@router.get("/recently-viewed")
def get_recently_viewed(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    results = product_services.get_recently_viewed(db, current_user["id"])
    return results


@router.get("/related")
def get_related_products(
    product_id: int,
    limit: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db),
):
    row = db.execute(text("SELECT id FROM products WHERE id = :id"), {"id": product_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Product not found.")
    results = product_services.get_related_products(db, product_id, limit)
    return results


@router.get("/{product_id}", response_model=ProductPayloadResponse)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    product = product_services.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    if product.status != "active":
        raise HTTPException(status_code=404, detail="Product not found.")
    return product


@router.get("/{product_id}/detail", response_model=ProductDetailResponse)
def get_product_detail(
    product_id: int,
    color_id: int = None,
    db: Session = Depends(get_db),
):
    detail = product_services.get_product_detail(db, product_id, color_id=color_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Product not found.")
    if detail.status != "active":
        raise HTTPException(status_code=404, detail="Product not found.")
    return detail


@router.delete("/{product_id}")
def delete_product(
    product_id: int,
    current_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    deleted = product_services.delete_product(db, product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Product not found.")
    return {"success": True, "deleted": product_id}
