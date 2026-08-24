import re
from datetime import datetime
from typing import Optional, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from schemas.product_schemas import (
    ProductPayload,
    ProductPayloadResponse,
    ProductResponse,
    ProductCategoryResponse,
    ProductTagResponse,
    ProductImageResponse,
    ProductVariantResponse,
    VariantImageResponse,
    ProductColorResponse,
    ProductSizeResponse,
    ProductDetailResponse,
    ProductDetailColor,
    ProductDetailCategory,
    ProductAvailableColor,
    ProductDetailSize,
    ProductDetailVariant,
    ProductDetailImage,
)
from services.search_service import search_service


def _slugify(value: str) -> str:
    slug = value.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "untitled"


def _get_or_create_brand(db: Session, name: str) -> Optional[int]:
    if not name:
        return None
    name = name.strip()
    row = db.execute(text("SELECT id, name FROM brands WHERE name = :name"), {"name": name}).mappings().first()
    if row:
        if row["name"] != name:
            db.execute(text("UPDATE brands SET name = :name WHERE id = :id"), {"name": name, "id": row["id"]})
        return row["id"]
    db.execute(text("INSERT INTO brands (name) VALUES (:name)"), {"name": name})
    return db.execute(text("SELECT LAST_INSERT_ID()")).scalar()


def _get_gender_id(db: Session, name: str) -> Optional[int]:
    if not name:
        return None
    name = name.strip()
    row = db.execute(text("SELECT id FROM genders WHERE name = :name"), {"name": name}).mappings().first()
    if row:
        return row["id"]
    db.execute(text("INSERT INTO genders (name) VALUES (:name)"), {"name": name})
    return db.execute(text("SELECT LAST_INSERT_ID()")).scalar()


def _resolve_category(db: Session, path: str) -> int:
    parts = [p.strip() for p in path.split(">") if p.strip()]
    parent_id = None
    category_id = None

    for part in parts:
        slug = _slugify(part)
        row = db.execute(
            text("SELECT id, name FROM categories WHERE slug = :slug"),
            {"slug": slug},
        ).mappings().first()

        if row:
            category_id = row["id"]
            if row["name"] != part:
                db.execute(
                    text("UPDATE categories SET name = :name WHERE id = :id"),
                    {"name": part, "id": category_id},
                )
        else:
            db.execute(
                text("INSERT INTO categories (parent_id, name, slug) VALUES (:parent_id, :name, :slug)"),
                {"parent_id": parent_id, "name": part, "slug": slug},
            )
            category_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()

        parent_id = category_id

    return category_id


def _get_or_create_tag(db: Session, name: str) -> int:
    row = db.execute(
        text("SELECT id FROM tags WHERE name = :name COLLATE utf8mb4_bin"),
        {"name": name}
    ).mappings().first()
    if row:
        return row["id"]
    row = db.execute(
        text("SELECT id FROM tags WHERE LOWER(name) = LOWER(:name)"),
        {"name": name}
    ).mappings().first()
    if row:
        db.execute(text("UPDATE tags SET name = :name WHERE id = :id"), {"name": name, "id": row["id"]})
        return row["id"]
    db.execute(text("INSERT INTO tags (name) VALUES (:name)"), {"name": name})
    return db.execute(text("SELECT LAST_INSERT_ID()")).scalar()


def _get_or_create_color(db: Session, name: str, hex_value: Optional[str]) -> int:
    name = name.strip()
    hex_value = hex_value.strip() if hex_value else None
    row = db.execute(text("SELECT id, hex FROM colors WHERE name = :name"), {"name": name}).mappings().first()
    if row:
        if hex_value and row["hex"] != hex_value:
            db.execute(text("UPDATE colors SET hex = :hex WHERE id = :id"), {"hex": hex_value, "id": row["id"]})
        return row["id"]
    db.execute(text("INSERT INTO colors (name, hex) VALUES (:name, :hex)"), {"name": name, "hex": hex_value})
    return db.execute(text("SELECT LAST_INSERT_ID()")).scalar()


def _get_or_create_size(db: Session, name: str) -> int:
    name = name.strip()
    row = db.execute(text("SELECT id FROM sizes WHERE name = :name"), {"name": name}).mappings().first()
    if row:
        return row["id"]
    db.execute(text("INSERT INTO sizes (name) VALUES (:name)"), {"name": name})
    return db.execute(text("SELECT LAST_INSERT_ID()")).scalar()


def save_product(db: Session, payload: ProductPayload) -> ProductPayloadResponse:
    p = payload.product
    
    brand_id = _get_or_create_brand(db, p.brand) if p.brand else None
    gender_id = _get_gender_id(db, p.gender) if p.gender else None
    slug = p.slug or _slugify(p.name)
    
    now = datetime.now()
    
    db.execute(text("""
        INSERT INTO products 
            (name, slug, description, specification, brand_id, gender_id, 
             base_price, discount_percent, discount_start, discount_end, 
             is_sellable, status, created_at, updated_at)
        VALUES
            (:name, :slug, :description, :specification, :brand_id, :gender_id,
             :base_price, :discount_percent, :discount_start, :discount_end,
             :is_sellable, :status, :now, :now)
    """), {
        "name": p.name,
        "slug": slug,
        "description": p.description,
        "specification": p.specification,
        "brand_id": brand_id,
        "gender_id": gender_id,
        "base_price": p.base_price,
        "discount_percent": p.discount_percent,
        "discount_start": p.discount_start,
        "discount_end": p.discount_end,
        "is_sellable": 1 if p.is_sellable else 0,
        "status": p.status.value,
        "now": now,
    })
    product_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
    
    product_categories = []
    category_ids = []
    for cat_req in payload.product_categories:
        category_id = _resolve_category(db, cat_req.category_path)
        category_ids.append(category_id)
        product_categories.append(ProductCategoryResponse(product_id=product_id, category_id=category_id))

    if category_ids:
        db.execute(
            text("INSERT INTO product_categories (product_id, category_id) VALUES (:product_id, :category_id)"),
            [{"product_id": product_id, "category_id": cid} for cid in category_ids],
        )

    product_tags = []
    tag_ids = []
    for tag_req in payload.product_tags:
        tag_id = _get_or_create_tag(db, tag_req.tag)
        tag_ids.append(tag_id)
        product_tags.append(ProductTagResponse(product_id=product_id, tag_id=tag_id))

    if tag_ids:
        db.execute(
            text("INSERT INTO product_tags (product_id, tag_id) VALUES (:product_id, :tag_id)"),
            [{"product_id": product_id, "tag_id": tid} for tid in tag_ids],
        )
    
    product_images = []
    for idx, img_req in enumerate(payload.product_images):
        db.execute(text("""
            INSERT INTO product_images (product_id, url, alt_text, is_primary, sort_order)
            VALUES (:product_id, :url, :alt_text, :is_primary, :sort_order)
        """), {
            "product_id": product_id,
            "url": img_req.url,
            "alt_text": img_req.alt_text,
            "is_primary": 1 if img_req.is_primary else 0,
            "sort_order": idx,
        })
        img_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
        product_images.append(ProductImageResponse(
            id=img_id,
            product_id=product_id,
            url=img_req.url,
            alt_text=img_req.alt_text,
            is_primary=img_req.is_primary,
            sort_order=idx,
        ))
    
    product_colors = []
    color_temp_to_real = {}
    for c_req in payload.product_colors:
        real_color_id = _get_or_create_color(db, c_req.name, c_req.hex)
        color_temp_to_real[c_req.id] = real_color_id
        product_colors.append(ProductColorResponse(id=real_color_id, name=c_req.name, hex=c_req.hex))

    product_sizes = []
    size_temp_to_real = {}
    for s_req in payload.product_sizes:
        real_size_id = _get_or_create_size(db, s_req.name)
        size_temp_to_real[s_req.id] = real_size_id
        product_sizes.append(ProductSizeResponse(id=real_size_id, name=s_req.name))

    temp_to_real_variant_id = {}
    product_variants = []
    for var_req in payload.product_variants:
        color_id = color_temp_to_real.get(var_req.color_id) if var_req.color_id else None
        size_id = size_temp_to_real.get(var_req.size_id) if var_req.size_id else None
        db.execute(text("""
            INSERT INTO product_variants 
                (product_id, color_id, size_id, sku, price_override, stock_quantity, is_active, created_at)
            VALUES
                (:product_id, :color_id, :size_id, :sku, :price_override, :stock_quantity, :is_active, :created_at)
        """), {
            "product_id": product_id,
            "color_id": color_id,
            "size_id": size_id,
            "sku": var_req.sku,
            "price_override": var_req.price_override,
            "stock_quantity": var_req.stock_quantity,
            "is_active": 1 if var_req.is_active else 0,
            "created_at": now,
        })
        real_variant_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
        temp_to_real_variant_id[var_req.id] = real_variant_id

        product_variants.append(ProductVariantResponse(
            id=real_variant_id,
            product_id=product_id,
            color_id=color_id,
            size_id=size_id,
            sku=var_req.sku,
            price_override=var_req.price_override,
            stock_quantity=var_req.stock_quantity,
            is_active=var_req.is_active,
            created_at=now,
        ))
    
    variant_images = []
    for vi_req in payload.variant_images:
        real_color_id = color_temp_to_real.get(vi_req.color_id) if vi_req.color_id else None
        if real_color_id is None:
            continue
        db.execute(text("""
            INSERT INTO variant_images (product_id, color_id, url, sort_order)
            VALUES (:product_id, :color_id, :url, :sort_order)
        """), {
            "product_id": product_id,
            "color_id": real_color_id,
            "url": vi_req.url,
            "sort_order": vi_req.sort_order,
        })
        vi_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
        variant_images.append(VariantImageResponse(
            id=vi_id,
            product_id=product_id,
            color_id=real_color_id,
            url=vi_req.url,
            sort_order=vi_req.sort_order,
        ))
    
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    
    brand_name = p.brand
    gender_name = p.gender
    category_paths = [c.category_path for c in payload.product_categories]
    tag_names = [t.tag for t in payload.product_tags]
    
    primary_image = None
    for img_req in payload.product_images:
        if img_req.is_primary:
            primary_image = img_req.url
            break
    if primary_image is None and payload.product_images:
        primary_image = payload.product_images[0].url
    
    doc = {
        "product_id": product_id,
        "name": p.name,
        "slug": slug,
        "description": p.description,
        "specification": p.specification,
        "brand_name": brand_name,
        "category_paths": category_paths,
        "tag_names": tag_names,
        "gender_name": gender_name,
        "base_price": float(p.base_price),
        "discount_percent": float(p.discount_percent),
        "status": p.status.value if hasattr(p.status, "value") else str(p.status),
        "is_sellable": 1 if p.is_sellable else 0,
        "main_image": primary_image,
    }
    search_service.index_product(doc)
    
    product_response = ProductResponse(
        id=product_id,
        name=p.name,
        slug=slug,
        description=p.description,
        specification=p.specification,
        brand_id=brand_id,
        gender_id=gender_id,
        base_price=p.base_price,
        discount_percent=p.discount_percent,
        discount_start=p.discount_start,
        discount_end=p.discount_end,
        is_sellable=p.is_sellable,
        status=p.status,
        created_at=now,
        updated_at=now,
    )
    
    return ProductPayloadResponse(
        product=product_response,
        product_categories=product_categories,
        product_tags=product_tags,
        product_images=product_images,
        product_colors=product_colors,
        product_sizes=product_sizes,
        product_variants=product_variants,
        variant_images=variant_images,
    )


def get_product(db: Session, product_id: int) -> Optional[ProductPayloadResponse]:
    row = db.execute(text("SELECT * FROM products WHERE id = :id"), {"id": product_id}).mappings().first()
    if not row:
        return None

    product = ProductResponse(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        description=row["description"],
        specification=row["specification"],
        brand_id=row["brand_id"],
        gender_id=row["gender_id"],
        base_price=row["base_price"],
        discount_percent=row["discount_percent"],
        discount_start=row["discount_start"],
        discount_end=row["discount_end"],
        is_sellable=bool(row["is_sellable"]),
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

    pc_rows = db.execute(
        text("SELECT product_id, category_id FROM product_categories WHERE product_id = :id"),
        {"id": product_id},
    ).mappings().all()
    product_categories = [ProductCategoryResponse(**r) for r in pc_rows]

    pt_rows = db.execute(
        text("SELECT product_id, tag_id FROM product_tags WHERE product_id = :id"),
        {"id": product_id},
    ).mappings().all()
    product_tags = [ProductTagResponse(**r) for r in pt_rows]

    pi_rows = db.execute(
        text("""
            SELECT id, product_id, url, alt_text, is_primary, sort_order
            FROM product_images WHERE product_id = :id ORDER BY sort_order
        """),
        {"id": product_id},
    ).mappings().all()
    product_images = [
        ProductImageResponse(
            id=r["id"],
            product_id=r["product_id"],
            url=r["url"],
            alt_text=r["alt_text"],
            is_primary=bool(r["is_primary"]),
            sort_order=r["sort_order"],
        )
        for r in pi_rows
    ]

    pv_rows = db.execute(
        text("""
            SELECT id, product_id, color_id, size_id, sku, price_override, stock_quantity, is_active, created_at
            FROM product_variants WHERE product_id = :id ORDER BY id
        """),
        {"id": product_id},
    ).mappings().all()
    product_variants = [
        ProductVariantResponse(
            id=r["id"],
            product_id=r["product_id"],
            color_id=r["color_id"],
            size_id=r["size_id"],
            sku=r["sku"],
            price_override=r["price_override"],
            stock_quantity=r["stock_quantity"],
            is_active=bool(r["is_active"]),
            created_at=r["created_at"],
        )
        for r in pv_rows
    ]

    color_ids = [v.color_id for v in product_variants if v.color_id]
    size_ids = [v.size_id for v in product_variants if v.size_id]

    product_colors = []
    if color_ids:
        c_rows = db.execute(
            text("SELECT id, name, hex FROM colors WHERE id IN :ids"),
            {"ids": tuple(color_ids)},
        ).mappings().all()
        product_colors = [ProductColorResponse(id=r["id"], name=r["name"], hex=r["hex"]) for r in c_rows]

    product_sizes = []
    if size_ids:
        s_rows = db.execute(
            text("SELECT id, name FROM sizes WHERE id IN :ids"),
            {"ids": tuple(size_ids)},
        ).mappings().all()
        product_sizes = [ProductSizeResponse(id=r["id"], name=r["name"]) for r in s_rows]

    variant_images: List[VariantImageResponse] = []
    if color_ids:
        vi_rows = db.execute(
            text("""
                SELECT id, color_id, url, sort_order
                FROM variant_images WHERE color_id IN :ids ORDER BY sort_order
            """),
            {"ids": tuple(color_ids)},
        ).mappings().all()
        variant_images = [VariantImageResponse(**r) for r in vi_rows]

    return ProductPayloadResponse(
        product=product,
        product_categories=product_categories,
        product_tags=product_tags,
        product_images=product_images,
        product_colors=product_colors,
        product_sizes=product_sizes,
        product_variants=product_variants,
        variant_images=variant_images,
    )


def get_products(
    db: Session,
    limit: int = 90,
    offset: int = 0,
    status: Optional[str] = None,
    brand_id: Optional[int] = None,
    gender_id: Optional[int] = None,
    is_admin: bool = False,
) -> List[ProductResponse]:
    clauses = []
    params: dict = {"limit": limit, "offset": offset}
    if status:
        if not is_admin and status in ("draft", "archived"):
            status = "active"
        clauses.append("status = :status")
        params["status"] = status
    elif not is_admin:
        clauses.append("status = 'active'")
    if not is_admin:
        clauses.append("is_sellable = 1")
    if brand_id is not None:
        clauses.append("brand_id = :brand_id")
        params["brand_id"] = brand_id
    if gender_id is not None:
        clauses.append("gender_id = :gender_id")
        params["gender_id"] = gender_id

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.execute(
        text(f"SELECT * FROM products {where} ORDER BY id DESC LIMIT :limit OFFSET :offset"),
        params,
    ).mappings().all()

    return [
        ProductResponse(
            id=r["id"],
            name=r["name"],
            slug=r["slug"],
            description=r["description"],
            specification=r["specification"],
            brand_id=r["brand_id"],
            gender_id=r["gender_id"],
            base_price=r["base_price"],
            discount_percent=r["discount_percent"],
            discount_start=r["discount_start"],
            discount_end=r["discount_end"],
            is_sellable=bool(r["is_sellable"]),
            status=r["status"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


def get_catalog_products(db: Session, limit: int = 50, offset: int = 0, query: str = None) -> List[dict]:
    base_where = "WHERE status = 'active' AND is_sellable = 1"
    params: dict = {"limit": limit, "offset": offset}

    if query:
        base_where += """ AND (
            LOWER(name) LIKE :like
            OR EXISTS (
                SELECT 1 FROM product_categories pc
                JOIN categories c ON c.id = pc.category_id
                WHERE pc.product_id = products.id AND LOWER(c.name) LIKE :like
            )
            OR EXISTS (
                SELECT 1 FROM product_tags pt
                JOIN tags t ON t.id = pt.tag_id
                WHERE pt.product_id = products.id AND LOWER(t.name) LIKE :like
            )
            OR EXISTS (
                SELECT 1 FROM brands b
                WHERE b.id = products.brand_id AND LOWER(b.name) LIKE :like
            )
        )"""
        params["like"] = f"%{query.lower()}%"

    products = db.execute(text(f"""
        SELECT id, name, slug, base_price, discount_percent, status, is_sellable
        FROM products
        {base_where}
        ORDER BY id DESC
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()

    product_ids = [p["id"] for p in products]

    images = {}
    if product_ids:
        img_rows = db.execute(
            text("""
                SELECT product_id, url FROM product_images
                WHERE product_id IN :ids AND is_primary = 1
            """),
            {"ids": tuple(product_ids)},
        ).mappings().all()
        images = {r["product_id"]: r["url"] for r in img_rows}

    categories = {}
    if product_ids:
        cat_rows = db.execute(
            text("""
                SELECT pc.product_id, c.name
                FROM product_categories pc
                INNER JOIN categories c ON c.id = pc.category_id
                WHERE pc.product_id IN :ids
                ORDER BY pc.product_id, pc.category_id
            """),
            {"ids": tuple(product_ids)},
        ).mappings().all()
        for r in cat_rows:
            if r["product_id"] not in categories:
                categories[r["product_id"]] = r["name"]

    results = []
    for p in products:
        pid = p["id"]
        results.append(
            {
                "id": pid,
                "name": p["name"],
                "slug": p["slug"],
                "base_price": float(p["base_price"]),
                "discount_percent": float(p["discount_percent"]),
                "image_url": images.get(pid),
                "category_name": categories.get(pid),
            }
        )

    return results


def delete_product(db: Session, product_id: int) -> bool:
    result = db.execute(text("DELETE FROM products WHERE id = :id"), {"id": product_id})
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    deleted = result.rowcount > 0
    if deleted:
        search_service.delete_product(product_id)
    return deleted


def add_recently_viewed(db: Session, user_id: int, product_id: int) -> None:
    db.execute(text("""
        INSERT INTO recently_viewed_products (user_id, product_id, viewed_at)
        VALUES (:user_id, :product_id, NOW())
        ON DUPLICATE KEY UPDATE viewed_at = NOW()
    """), {"user_id": user_id, "product_id": product_id})

    db.execute(text("""
        DELETE FROM recently_viewed_products
        WHERE user_id = :user_id
          AND product_id NOT IN (
              SELECT product_id FROM (
                  SELECT product_id FROM recently_viewed_products
                  WHERE user_id = :user_id
                  ORDER BY viewed_at DESC
                  LIMIT 12
              ) AS keep_rows
          )
    """), {"user_id": user_id})


def get_recently_viewed(db: Session, user_id: int):
    rows = db.execute(text("""
        SELECT p.id, p.name, p.slug, p.base_price, p.discount_percent, p.status, p.is_sellable,
               p.created_at, p.updated_at
        FROM recently_viewed_products rvp
        JOIN products p ON p.id = rvp.product_id
        WHERE rvp.user_id = :user_id
        ORDER BY rvp.viewed_at DESC
        LIMIT 20
    """), {"user_id": user_id}).mappings().all()

    product_ids = [r["id"] for r in rows]

    images = {}
    if product_ids:
        img_rows = db.execute(
            text("""
                SELECT product_id, url FROM product_images
                WHERE product_id IN :ids AND is_primary = 1
            """),
            {"ids": tuple(product_ids)},
        ).mappings().all()
        images = {r["product_id"]: r["url"] for r in img_rows}

    categories = {}
    if product_ids:
        cat_rows = db.execute(
            text("""
                SELECT pc.product_id, c.name
                FROM product_categories pc
                INNER JOIN categories c ON c.id = pc.category_id
                WHERE pc.product_id IN :ids
                ORDER BY pc.product_id, pc.category_id
            """),
            {"ids": tuple(product_ids)},
        ).mappings().all()
        for r in cat_rows:
            if r["product_id"] not in categories:
                categories[r["product_id"]] = r["name"]

    results = []
    for r in rows:
        pid = r["id"]
        results.append(
            {
                "id": pid,
                "name": r["name"],
                "slug": r["slug"],
                "base_price": float(r["base_price"]),
                "discount_percent": float(r["discount_percent"]),
                "is_sellable": bool(r["is_sellable"]),
                "status": r["status"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
                "image_url": images.get(pid),
                "category_name": categories.get(pid),
                "description": None,
                "specification": None,
                "brand_id": None,
                "gender_id": None,
                "discount_start": None,
                "discount_end": None,
            }
        )

    return results


def get_related_products(db: Session, product_id: int, limit: int = 12):
    row = db.execute(text("""
        SELECT brand_id FROM products WHERE id = :id
    """), {"id": product_id}).mappings().first()

    if not row:
        return []

    brand_id = row["brand_id"]

    category_rows = db.execute(text("""
        SELECT category_id FROM product_categories WHERE product_id = :product_id
    """), {"product_id": product_id}).mappings().all()

    category_ids = [r["category_id"] for r in category_rows]

    if category_ids:
        rows = db.execute(text("""
            SELECT p.id, p.name, p.slug, p.base_price, p.discount_percent, p.status, p.is_sellable,
                   p.created_at, p.updated_at,
                   CASE
                       WHEN p.brand_id = :brand_id THEN 1
                       ELSE 2
                   END AS sort_rank
            FROM products p
            WHERE p.id <> :product_id
              AND p.status = 'active'
              AND p.is_sellable = 1
              AND EXISTS (
                  SELECT 1 FROM product_categories pc3
                  WHERE pc3.product_id = p.id
                    AND pc3.category_id IN :category_ids
              )
            ORDER BY sort_rank ASC, p.id DESC
            LIMIT :limit
        """), {
            "product_id": product_id,
            "brand_id": brand_id,
            "category_ids": tuple(category_ids),
            "limit": limit,
        }).mappings().all()

        if rows:
            product_ids = [r["id"] for r in rows]

            images = {}
            if product_ids:
                img_rows = db.execute(
                    text("""
                        SELECT product_id, url FROM product_images
                        WHERE product_id IN :ids AND is_primary = 1
                    """),
                    {"ids": tuple(product_ids)},
                ).mappings().all()
                images = {r["product_id"]: r["url"] for r in img_rows}

            categories = {}
            if product_ids:
                cat_rows = db.execute(
                    text("""
                        SELECT pc.product_id, c.name
                        FROM product_categories pc
                        INNER JOIN categories c ON c.id = pc.category_id
                        WHERE pc.product_id IN :ids
                        ORDER BY pc.product_id, pc.category_id
                    """),
                    {"ids": tuple(product_ids)},
                ).mappings().all()
                for r in cat_rows:
                    if r["product_id"] not in categories:
                        categories[r["product_id"]] = r["name"]

            results = []
            for r in rows:
                pid = r["id"]
                results.append(
                    {
                        "id": pid,
                        "name": r["name"],
                        "slug": r["slug"],
                        "base_price": float(r["base_price"]),
                        "discount_percent": float(r["discount_percent"]),
                        "is_sellable": bool(r["is_sellable"]),
                        "status": r["status"],
                        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
                        "image_url": images.get(pid),
                        "category_name": categories.get(pid),
                        "description": None,
                        "specification": None,
                        "brand_id": None,
                        "gender_id": None,
                        "discount_start": None,
                        "discount_end": None,
                    }
                )
            return results

    return []


def get_product_detail(
    db: Session, product_id: int, color_id: Optional[int] = None
) -> Optional[ProductDetailResponse]:
    row = db.execute(text("SELECT * FROM products WHERE id = :id"), {"id": product_id}).mappings().first()
    if not row:
        return None

    brand_name = None
    if row["brand_id"]:
        b = db.execute(text("SELECT name FROM brands WHERE id = :id"), {"id": row["brand_id"]}).mappings().first()
        brand_name = b["name"] if b else None

    gender_name = None
    if row["gender_id"]:
        g = db.execute(text("SELECT name FROM genders WHERE id = :id"), {"id": row["gender_id"]}).mappings().first()
        gender_name = g["name"] if g else None

    # Colors available for this product (catalog option), ordered by first appearance.
    color_ids_rows = db.execute(
        text("""
            SELECT DISTINCT color_id FROM product_variants
            WHERE product_id = :id AND color_id IS NOT NULL
        """),
        {"id": product_id},
    ).mappings().all()
    color_ids = [r["color_id"] for r in color_ids_rows]

    # Resolve the requested color, defaulting to the first available color.
    target_color_id = color_id if color_id in color_ids else (color_ids[0] if color_ids else None)

    # Only fetch variant_images for the current (target) color, scoped to this product.
    vi_rows = []
    if target_color_id is not None:
        vi_rows = db.execute(
            text("""
                SELECT id, color_id, url, sort_order, NULL AS alt_text
                FROM variant_images
                WHERE product_id = :pid AND color_id = :cid
                ORDER BY sort_order ASC
            """),
            {"pid": product_id, "cid": target_color_id},
        ).mappings().all()

    main_image = vi_rows[0]["url"] if vi_rows else None

    gallery_images = [
        ProductDetailImage(
            url=r["url"],
            alt_text=r["alt_text"],
            is_primary=(r["sort_order"] == 0),
            sort_order=r["sort_order"],
        )
        for r in vi_rows
    ]

    # Category names linked to this product (plain join, no parent/child path).
    pc_rows = db.execute(
        text("""
            SELECT c.id, c.name
            FROM product_categories AS pc
            INNER JOIN categories AS c ON c.id = pc.category_id
            WHERE pc.product_id = :id
        """),
        {"id": product_id},
    ).mappings().all()

    categories: List[ProductDetailCategory] = [
        ProductDetailCategory(id=r["id"], name=r["name"]) for r in pc_rows
    ]

    pt_rows = db.execute(
        text("SELECT product_id, tag_id FROM product_tags WHERE product_id = :id"),
        {"id": product_id},
    ).mappings().all()
    tags = [ProductTagResponse(**r) for r in pt_rows]

    # Colors (catalog option) limited to the current (target) color only.
    color_set = [target_color_id] if target_color_id is not None else []
    colors: List[ProductDetailColor] = []
    for color_id in color_set:
        c = db.execute(text("SELECT id, name, hex FROM colors WHERE id = :id"), {"id": color_id}).mappings().first()
        if not c:
            continue
        color_images = [
            ProductDetailImage(
                url=r["url"],
                alt_text=r["alt_text"],
                is_primary=(r["sort_order"] == 0),
                sort_order=r["sort_order"],
            )
            for r in vi_rows
            if r["color_id"] == color_id
        ]
        colors.append(ProductDetailColor(
            id=c["id"],
            name=c["name"],
            hex=c["hex"],
            images=color_images,
        ))

    # All colors available for this product (for the swatch bar),
    # regardless of which color is currently selected.
    available_colors: List[ProductAvailableColor] = []
    if color_ids:
        ac_rows = db.execute(
            text("SELECT id, name, hex FROM colors WHERE id IN :ids"),
            {"ids": tuple(color_ids)},
        ).mappings().all()
        # First variant_image per color, for the swatch thumbnail.
        avi_rows = db.execute(
            text("""
                SELECT color_id, url FROM variant_images
                WHERE product_id = :pid AND color_id IN :ids
                ORDER BY sort_order ASC
            """),
            {"pid": product_id, "ids": tuple(color_ids)},
        ).mappings().all()
        first_image_by_color = {}
        for r in avi_rows:
            first_image_by_color.setdefault(r["color_id"], r["url"])
        available_colors = [
            ProductAvailableColor(
                id=r["id"],
                name=r["name"],
                hex=r["hex"],
                image=first_image_by_color.get(r["id"]),
            )
            for r in ac_rows
        ]

    size_ids = [
        v["size_id"]
        for v in db.execute(
            text("SELECT DISTINCT size_id FROM product_variants WHERE product_id = :id AND size_id IS NOT NULL"),
            {"id": product_id},
        ).mappings().all()
    ]
    sizes: List[ProductDetailSize] = []
    if size_ids:
        s_rows = db.execute(text("SELECT id, name FROM sizes WHERE id IN :ids"), {"ids": tuple(size_ids)}).mappings().all()
        sizes = [ProductDetailSize(id=r["id"], name=r["name"]) for r in s_rows]

    pv_rows = db.execute(
        text("""
            SELECT id, color_id, size_id, sku, price_override, stock_quantity, is_active
            FROM product_variants WHERE product_id = :id ORDER BY id
        """),
        {"id": product_id},
    ).mappings().all()
    variants = [
        ProductDetailVariant(
            id=r["id"],
            color_id=r["color_id"],
            size_id=r["size_id"],
            sku=r["sku"],
            price_override=r["price_override"],
            stock_quantity=r["stock_quantity"],
            is_active=bool(r["is_active"]),
        )
        for r in pv_rows
    ]

    return ProductDetailResponse(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        description=row["description"],
        specification=row["specification"],
        base_price=row["base_price"],
        discount_percent=row["discount_percent"],
        is_sellable=bool(row["is_sellable"]),
        status=row["status"],
        brand_name=brand_name,
        gender_name=gender_name,
        main_image=main_image,
        gallery_images=gallery_images,
        categories=categories,
        tags=tags,
        colors=colors,
        available_colors=available_colors,
        sizes=sizes,
        variants=variants,
    )

def _get_descendant_category_ids(db, category_id):
    """Get all descendant category IDs for a given category (including itself)."""
    # Use recursive CTE or iterative approach
    ids = [category_id]
    changed = True
    while changed:
        changed = False
        rows = db.execute(text("""
            SELECT id FROM categories WHERE parent_id IN :ids
        """), {"ids": tuple(ids)}).mappings().all()
        for r in rows:
            if r["id"] not in ids:
                ids.append(r["id"])
                changed = True
    return ids

def get_filter_options(db):
    """Get all available filter options from the database."""
    # Categories (hierarchical)
    cat_rows = db.execute(text("""
        SELECT id, name, parent_id FROM categories ORDER BY parent_id, name
    """)).mappings().all()
    
    # Build tree
    cats_by_id = {r["id"]: {**r, "children": []} for r in cat_rows}
    root_cats = []
    for c in cats_by_id.values():
        if c["parent_id"] is None or c["parent_id"] not in cats_by_id:
            root_cats.append(c)
        else:
            cats_by_id[c["parent_id"]]["children"].append(c)
    
    # Brands
    brand_rows = db.execute(text("""
        SELECT id, name FROM brands ORDER BY name
    """)).mappings().all()
    
    # Genders
    gender_rows = db.execute(text("""
        SELECT id, name FROM genders ORDER BY name
    """)).mappings().all()
    
    # Colors
    color_rows = db.execute(text("""
        SELECT id, name, hex FROM colors ORDER BY name
    """)).mappings().all()
    
    # Sizes
    size_rows = db.execute(text("""
        SELECT id, name FROM sizes ORDER BY name
    """)).mappings().all()
    
    # Price range
    price_row = db.execute(text("""
        SELECT MIN(base_price) as min_price, MAX(base_price) as max_price
        FROM products
        WHERE status = 'active' AND is_sellable = 1
    """)).mappings().first()
    
    return {
        "categories": root_cats,
        "brands": [{"id": r["id"], "name": r["name"]} for r in brand_rows],
        "genders": [{"id": r["id"], "name": r["name"]} for r in gender_rows],
        "colors": [{"id": r["id"], "name": r["name"], "hex": r["hex"]} for r in color_rows],
        "sizes": [{"id": r["id"], "name": r["name"]} for r in size_rows],
        "price_range": {
            "min": float(price_row["min_price"]) if price_row["min_price"] else 0,
            "max": float(price_row["max_price"]) if price_row["max_price"] else 100000,
        }
    }

def _build_product_where_clause(params, include_category_filter=True, category_ids_override=None):
    clauses = ["status = 'active'", "is_sellable = 1"]
    
    if params.get("query"):
        clauses.append("""AND (LOWER(name) LIKE :like)""")
        params["like"] = f"%{params['query'].lower()}%"
    
    if params.get("brand_ids"):
        clauses.append("brand_id IN :brand_ids")
        params["brand_ids"] = tuple(params["brand_ids"])
    
    # ... etc
    
    return "WHERE " + " AND ".join(clauses)

def _get_category_and_descendant_ids(db, category_ids):
    if not category_ids:
        return []
    result = set(category_ids)
    rows = db.execute(text("""
        SELECT id, parent_id FROM categories WHERE id IN :ids
    """), {"ids": tuple(category_ids)}).mappings().all()
    parent_ids = [r["id"] for r in rows]
    while parent_ids:
        children = db.execute(text("""
            SELECT id FROM categories WHERE parent_id IN :parent_ids
        """), {"parent_ids": tuple(parent_ids)}).mappings().all()
        child_ids = [r["id"] for r in children]
        new_ids = [cid for cid in child_ids if cid not in result]
        if not new_ids:
            break
        result.update(new_ids)
        parent_ids = new_ids
    return list(result)

def _build_catalog_where(query, category_ids, brand_ids, gender_ids, color_ids, size_ids, min_price, max_price, is_admin=False):
    clauses = []
    if not is_admin:
        clauses.extend(["status = 'active'", "is_sellable = 1"])
    params = {}
    
    if query:
        like = f"%{query.lower()}%"
        clauses.append("""(
            LOWER(name) LIKE :like
            OR EXISTS (SELECT 1 FROM product_categories pc JOIN categories c ON c.id = pc.category_id WHERE pc.product_id = products.id AND LOWER(c.name) LIKE :like)
            OR EXISTS (SELECT 1 FROM product_tags pt JOIN tags t ON t.id = pt.tag_id WHERE pt.product_id = products.id AND LOWER(t.name) LIKE :like)
            OR EXISTS (SELECT 1 FROM brands b WHERE b.id = products.brand_id AND LOWER(b.name) LIKE :like)
        )""")
        params["like"] = like
    
    if category_ids:
        clauses.append("EXISTS (SELECT 1 FROM product_categories pc WHERE pc.product_id = products.id AND pc.category_id IN :category_ids)")
        params["category_ids"] = tuple(category_ids)
    
    if brand_ids:
        clauses.append("brand_id IN :brand_ids")
        params["brand_ids"] = tuple(brand_ids)
    
    if gender_ids:
        clauses.append("gender_id IN :gender_ids")
        params["gender_ids"] = tuple(gender_ids)
    
    if color_ids:
        clauses.append("EXISTS (SELECT 1 FROM product_variants pv WHERE pv.product_id = products.id AND pv.color_id IN :color_ids AND pv.is_active = 1)")
        params["color_ids"] = tuple(color_ids)
    
    if size_ids:
        clauses.append("EXISTS (SELECT 1 FROM product_variants pv WHERE pv.product_id = products.id AND pv.size_id IN :size_ids AND pv.is_active = 1)")
        params["size_ids"] = tuple(size_ids)
    
    if min_price is not None:
        clauses.append("(base_price * (100 - discount_percent) / 100) >= :min_price")
        params["min_price"] = min_price
    
    if max_price is not None:
        clauses.append("(base_price * (100 - discount_percent) / 100) <= :max_price")
        params["max_price"] = max_price

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params

def get_catalog_filters(db, query=None, category_ids=None, brand_ids=None, gender_ids=None, color_ids=None, size_ids=None, min_price=None, max_price=None, category_name=None, brand_name=None, is_admin=False):
    # Resolve category_name ONLY if no category IDs were supplied.
    if category_name and not category_ids:
        names = [n.strip().lower() for n in category_name.split(",") if n.strip()]

        rows = db.execute(
            text("SELECT id FROM categories WHERE LOWER(name) IN :names"),
            {"names": tuple(names)}
        ).mappings().all()

        category_ids = [r["id"] for r in rows]

    if category_ids:
        category_ids = _get_category_and_descendant_ids(db, category_ids)

    if brand_name:
        names = [n.strip().lower() for n in brand_name.split(",") if n.strip()]
        rows = db.execute(text("SELECT id FROM brands WHERE LOWER(name) IN :names"), {"names": tuple(names)}).mappings().all()
        resolved = [r["id"] for r in rows]
        brand_ids = (brand_ids or []) + resolved

    base_where, params = _build_catalog_where(query, category_ids, brand_ids, gender_ids, color_ids, size_ids, min_price, max_price, is_admin=is_admin)
    
    # Get product IDs for counting
    rows = db.execute(text(f"SELECT id FROM products {base_where}"), params).mappings().all()
    product_ids = [r["id"] for r in rows]
    
    result = {
        "categories": [],
        "brands": [],
        "genders": [],
        "colors": [],
        "sizes": [],
        "price_range": {"min": 0, "max": 0},
    }
    
    if not product_ids:
        return result
    
    ids_tuple = tuple(product_ids)
    
    # Categories
    cat_rows = db.execute(text("""
        SELECT
            c.id,
            c.name,
            COUNT(DISTINCT CONCAT(pv.product_id, '-', pv.color_id)) AS count
        FROM product_categories pc
        JOIN categories c
            ON c.id = pc.category_id
        JOIN product_variants pv
            ON pv.product_id = pc.product_id
        WHERE pc.product_id IN :ids
        GROUP BY c.id, c.name
        ORDER BY c.name
    """), {"ids": ids_tuple}).mappings().all()

    result["categories"] = [
        {
            "id": r["id"],
            "name": r["name"],
            "count": r["count"]
        }
        for r in cat_rows
    ]
    
    # Brands
    brand_rows = db.execute(text("""
        SELECT
            b.id,
            b.name,
            COUNT(DISTINCT CONCAT(pv.product_id, '-', pv.color_id)) AS count
        FROM products p
        JOIN brands b
            ON b.id = p.brand_id
        JOIN product_variants pv
            ON pv.product_id = p.id
        WHERE
            p.id IN :ids
            AND p.brand_id IS NOT NULL
            AND pv.is_active = 1
        GROUP BY b.id, b.name
        ORDER BY b.name
    """), {"ids": ids_tuple}).mappings().all()
    result["brands"] = [{"id": r["id"], "name": r["name"], "count": r["count"]} for r in brand_rows]
    
    # Genders
    gender_rows = db.execute(text("""
        SELECT
            g.id,
            g.name,
            COUNT(DISTINCT CONCAT(pv.product_id, '-', pv.color_id)) AS count
        FROM products p
        JOIN genders g
            ON g.id = p.gender_id
        JOIN product_variants pv
            ON pv.product_id = p.id
        WHERE
            p.id IN :ids
            AND p.gender_id IS NOT NULL
            AND pv.is_active = 1
        GROUP BY g.id, g.name
        ORDER BY g.name
    """), {"ids": ids_tuple}).mappings().all()
    result["genders"] = [{"id": r["id"], "name": r["name"], "count": r["count"]} for r in gender_rows]
    
    # Colors
    color_rows = db.execute(text("""
        SELECT c.id, c.name, c.hex, COUNT(DISTINCT CONCAT(pv.product_id, '-', pv.color_id)) AS count
        FROM product_variants pv
        JOIN colors c ON c.id = pv.color_id
        WHERE pv.product_id IN :ids AND pv.color_id IS NOT NULL AND pv.is_active = 1
        GROUP BY c.id, c.name, c.hex
        ORDER BY c.name
    """), {"ids": ids_tuple}).mappings().all()
    result["colors"] = [{"id": r["id"], "name": r["name"], "hex": r["hex"], "count": r["count"]} for r in color_rows]

    # Sizes
    size_rows = db.execute(text("""
        SELECT s.id, s.name, COUNT(DISTINCT CONCAT(pv.product_id, '-', pv.color_id)) AS count
        FROM product_variants pv
        JOIN sizes s ON s.id = pv.size_id
        WHERE pv.product_id IN :ids AND pv.size_id IS NOT NULL AND pv.is_active = 1
        GROUP BY s.id, s.name
        ORDER BY s.name
    """), {"ids": ids_tuple}).mappings().all()
    result["sizes"] = [{"id": r["id"], "name": r["name"], "count": r["count"]} for r in size_rows]
    
    # Price range (global across all active products)
    price_row = db.execute(text("""
        SELECT 
            MIN(base_price * (100 - discount_percent) / 100) as min_price,
            MAX(base_price * (100 - discount_percent) / 100) as max_price
        FROM products
        WHERE status = 'active' AND is_sellable = 1
    """)).mappings().first()
    
    if price_row:
        result["price_range"] = {
            "min": float(price_row["min_price"] or 0),
            "max": float(price_row["max_price"] or 0),
        }
    
    return result


def get_catalog_products_filtered(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    query: str = None,
    category_ids: List[int] = None,
    brand_ids: List[int] = None,
    gender_ids: List[int] = None,
    color_ids: List[int] = None,
    size_ids: List[int] = None,
    min_price: float = None,
    max_price: float = None,
    sort_by: str = "featured",
    category_name: str = None,
    brand_name: str = None,
    is_admin: bool = False,
) -> dict:
    if category_name and not category_ids:
        names = [n.strip().lower() for n in category_name.split(",") if n.strip()]

        rows = db.execute(
            text("SELECT id FROM categories WHERE LOWER(name) IN :names"),
            {"names": tuple(names)}
        ).mappings().all()

        category_ids = [r["id"] for r in rows]

    if category_ids:
        category_ids = _get_category_and_descendant_ids(db, category_ids)

    if brand_name:
        names = [n.strip().lower() for n in brand_name.split(",") if n.strip()]
        rows = db.execute(text("SELECT id FROM brands WHERE LOWER(name) IN :names"), {"names": tuple(names)}).mappings().all()
        resolved = [r["id"] for r in rows]
        brand_ids = (brand_ids or []) + resolved

    where, params = _build_catalog_where(query, category_ids, brand_ids, gender_ids, color_ids, size_ids, min_price, max_price, is_admin=is_admin)

    order_by = "id DESC"
    if sort_by == "newest":
        order_by = "created_at DESC, id DESC"
    elif sort_by == "price_low_high":
        order_by = "(base_price * (100 - discount_percent) / 100) ASC, id DESC"
    elif sort_by == "price_high_low":
        order_by = "(base_price * (100 - discount_percent) / 100) DESC, id DESC"

    params["limit"] = limit
    params["offset"] = offset

    count_row = db.execute(
        text(f"SELECT COUNT(*) as total FROM products {where}"),
        params,
    ).mappings().first()
    total = count_row["total"] if count_row else 0

    products = db.execute(text(f"""
        SELECT id, name, slug, base_price, discount_percent, status, is_sellable
        FROM products
        {where}
        ORDER BY {order_by}
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()

    product_ids = [p["id"] for p in products]

    images = {}
    if product_ids:
        img_rows = db.execute(
            text("""
                SELECT product_id, url FROM product_images
                WHERE product_id IN :ids AND is_primary = 1
            """),
            {"ids": tuple(product_ids)},
        ).mappings().all()
        images = {r["product_id"]: r["url"] for r in img_rows}

    categories = {}
    if product_ids:
        cat_rows = db.execute(
            text("""
                SELECT pc.product_id, c.name
                FROM product_categories pc
                INNER JOIN categories c ON c.id = pc.category_id
                WHERE pc.product_id IN :ids
                ORDER BY pc.product_id, pc.category_id
            """),
            {"ids": tuple(product_ids)},
        ).mappings().all()
        for r in cat_rows:
            if r["product_id"] not in categories:
                categories[r["product_id"]] = r["name"]

    brands = {}
    if product_ids:
        brand_rows = db.execute(
            text("""
                SELECT p.id, b.name
                FROM products p
                JOIN brands b ON b.id = p.brand_id
                WHERE p.id IN :ids AND p.brand_id IS NOT NULL
            """),
            {"ids": tuple(product_ids)},
        ).mappings().all()
        brands = {r["id"]: r["name"] for r in brand_rows}

    genders = {}
    if product_ids:
        gender_rows = db.execute(
            text("""
                SELECT p.id, g.name
                FROM products p
                JOIN genders g ON g.id = p.gender_id
                WHERE p.id IN :ids AND p.gender_id IS NOT NULL
            """),
            {"ids": tuple(product_ids)},
        ).mappings().all()
        genders = {r["id"]: r["name"] for r in gender_rows}

    product_colors = {}
    color_variant_images = {}
    if product_ids:
        color_rows = db.execute(
            text("""
                SELECT pv.product_id, c.id, c.name, c.hex
                FROM product_variants pv
                JOIN colors c ON c.id = pv.color_id
                WHERE pv.product_id IN :ids AND pv.color_id IS NOT NULL
                GROUP BY pv.product_id, c.id, c.name, c.hex
            """),
            {"ids": tuple(product_ids)},
        ).mappings().all()
        for r in color_rows:
            pid = r["product_id"]
            if pid not in product_colors:
                product_colors[pid] = []
            product_colors[pid].append(
                {"id": r["id"], "name": r["name"], "hex": r["hex"]}
            )

    variant_images_by_color = {}
    if product_ids:
        vi_rows = db.execute(
            text("""
                SELECT product_id, color_id, url
                FROM variant_images
                WHERE product_id IN :ids
                ORDER BY sort_order ASC
            """),
            {"ids": tuple(product_ids)},
        ).mappings().all()
        for r in vi_rows:
            key = (r["product_id"], r["color_id"])
            if key not in variant_images_by_color:
                variant_images_by_color[key] = r["url"]

    results = []
    for p in products:
        pid = p["id"]
        base = float(p["base_price"])
        disc = float(p["discount_percent"])
        sale_price = round(base - (base * disc / 100), 2)
        primary_image = images.get(pid)
        colors = product_colors.get(pid, [])

        if not colors:
            results.append(
                {
                    "id": pid,
                    "name": p["name"],
                    "slug": p["slug"],
                    "base_price": base,
                    "discount_percent": disc,
                    "sale_price": sale_price,
                    "original_price": base,
                    "image_url": primary_image,
                    "category_name": categories.get(pid),
                    "brand_name": brands.get(pid),
                    "gender_name": genders.get(pid),
                    "color_name": None,
                    "color_hex": None,
                    "color_id": None,
                    "colors": [],
                }
            )
        else:
            for color in colors:
                if color_ids and color["id"] not in color_ids:
                    continue
                variant_image = variant_images_by_color.get((pid, color["id"]), primary_image)
                results.append(
                    {
                        "id": pid,
                        "name": p["name"],
                        "slug": p["slug"],
                        "base_price": base,
                        "discount_percent": disc,
                        "sale_price": sale_price,
                        "original_price": base,
                        "image_url": variant_image,
                        "category_name": categories.get(pid),
                        "brand_name": brands.get(pid),
                        "gender_name": genders.get(pid),
                        "color_name": color["name"],
                        "color_hex": color["hex"],
                        "color_id": color["id"],
                        "colors": colors,
                    }
                )

    return {"total": total, "products": results}