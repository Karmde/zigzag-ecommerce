from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Optional, List

from database.database import get_db
from schemas.product_schemas import CatalogFiltersResponse, CatalogProductsResponse
from services import product_services
from dependencies.auth_dependency import get_optional_current_user

router = APIRouter(prefix="/catalog", tags=["Catalog"])

@router.get("/categories")
def get_categories(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT id, name, parent_id FROM categories ORDER BY name")).mappings().all()
    return [{"id": r["id"], "name": r["name"], "parent_id": r["parent_id"]} for r in rows]

@router.get("/filters", response_model=CatalogFiltersResponse)
def get_filters(
    current_user: dict | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
    q: Optional[str] = None,
    category: Optional[List[int]] = Query(None),
    brand: Optional[List[int]] = Query(None),
    gender: Optional[List[int]] = Query(None),
    color: Optional[List[int]] = Query(None),
    size: Optional[List[int]] = Query(None),
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    category_name: Optional[str] = None,
    brand_name: Optional[str] = None,
):
    return product_services.get_catalog_filters(
        db, query=q, category_ids=category, brand_ids=brand, gender_ids=gender,
        color_ids=color, size_ids=size, min_price=min_price, max_price=max_price,
        category_name=category_name, brand_name=brand_name,
        is_admin=(current_user["role"] == "admin" if current_user else False),
    )

@router.get("/products", response_model=CatalogProductsResponse)
def get_products(
    current_user: dict | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: Optional[str] = None,
    category: Optional[List[int]] = Query(None),
    brand: Optional[List[int]] = Query(None),
    gender: Optional[List[int]] = Query(None),
    color: Optional[List[int]] = Query(None),
    size: Optional[List[int]] = Query(None),
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort: str = Query("featured"),
    category_name: Optional[str] = None,
    brand_name: Optional[str] = None,
):
    result = product_services.get_catalog_products_filtered(
        db, limit=limit, offset=offset, query=q,
        category_ids=category, brand_ids=brand, gender_ids=gender,
        color_ids=color, size_ids=size, min_price=min_price, max_price=max_price,
        sort_by=sort, category_name=category_name, brand_name=brand_name,
        is_admin=(current_user["role"] == "admin" if current_user else False),
    )
    return CatalogProductsResponse(total=result["total"], products=result["products"])