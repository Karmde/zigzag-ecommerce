from fastapi import APIRouter, Request
from core.templates import templates
from database.database import get_db
from services import product_services

router = APIRouter()

@router.get("/catalog")
async def catalog(
    request: Request,
    q: str = None,
    category: str = None,
    brand: str = None,
    gender: str = None,
    color: str = None,
    size: str = None,
    min_price: float = None,
    max_price: float = None,
    sort: str = "newest",
    category_name: str = None,
    brand_name: str = None,
    sales: bool = False,
):
    category_ids = [int(x) for x in category.split(",") if x] if category else None
    brand_ids = [int(x) for x in brand.split(",") if x] if brand else None
    gender_ids = [int(x) for x in gender.split(",") if x] if gender else None
    color_ids = [int(x) for x in color.split(",") if x] if color else None
    size_ids = [int(x) for x in size.split(",") if x] if size else None

    db = next(get_db())
    try:
        result = product_services.get_catalog_products_filtered(
            db,
            limit=15,
            offset=0,
            query=q,
            category_ids=category_ids,
            brand_ids=brand_ids,
            gender_ids=gender_ids,
            color_ids=color_ids,
            size_ids=size_ids,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort,
            category_name=category_name,
            brand_name=brand_name,
            sales=sales,
        )
    finally:
        db.close()

    products = result["products"]
    for p in products:
        p["sale_price"] = round(p["sale_price"], 2)
        p["original_price"] = round(p["original_price"], 2)

    return templates.TemplateResponse(
        request=request,
        name="product/catalog.html",
        context={
            "products": products,
            "search_query": q,
            "total_products": result["total"],
        },
    )

@router.get("/product")
async def product(request: Request, id: int = None, color_id: int = None):
    product_detail = None
    if id is not None:
        db = next(get_db())
        try:
            product_detail = product_services.get_product_detail(db, id, color_id=color_id)
        finally:
            db.close()

    product_json = product_detail.model_dump(mode="json") if product_detail else {}
    base = float(product_json.get("base_price") or 0)
    disc = float(product_json.get("discount_percent") or 0)
    product_json["sale_price"] = round(base - (base * disc / 100), 2)
    product_json["original_price"] = round(base, 2)
    product_json["discount_percent_value"] = round(disc, 2)

    return templates.TemplateResponse(
        request=request,
        name="product/product.html",
        context={"product": product_json},
    )