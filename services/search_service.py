import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.database import get_db

logger = logging.getLogger(__name__)


class SearchService:
    def ensure_index(self) -> None:
        # No external search index is used; search runs directly against SQL.
        return

    def index_product(self, document: dict) -> None:
        # No external search index is used; nothing to index.
        return

    def delete_product(self, product_id: int) -> None:
        # No external search index is used; nothing to delete.
        return

    def search(self, query: str, limit: int = 20, offset: int = 0) -> dict:
        return self._sql_search(query, limit, offset)

    def _sql_search(self, query: str, limit: int = 20, offset: int = 0) -> dict:
        db: Session = next(get_db())
        try:
            like = f"%{query.lower()}%"
            rows = db.execute(text("""
                WITH matched AS (
                    SELECT
                        p.id AS product_id,
                        p.name,
                        p.slug,
                        b.name AS brand_name,
                        p.base_price,
                        p.discount_percent,
                        pi.url AS main_image,
                        COUNT(*) OVER() AS total
                    FROM products p
                    LEFT JOIN brands b ON b.id = p.brand_id
                    LEFT JOIN (
                        SELECT
                            product_id,
                            url,
                            ROW_NUMBER() OVER (
                                PARTITION BY product_id
                                ORDER BY is_primary DESC, id ASC
                            ) AS rn
                        FROM product_images
                    ) pi ON pi.product_id = p.id AND pi.rn = 1
                    WHERE
                        p.status = 'active'
                        AND (
                            LOWER(p.name) LIKE :like
                            OR LOWER(b.name) LIKE :like
                            OR EXISTS (
                                SELECT 1
                                FROM product_tags pt
                                JOIN tags t ON t.id = pt.tag_id
                                WHERE pt.product_id = p.id AND LOWER(t.name) LIKE :like
                            )
                            OR EXISTS (
                                SELECT 1
                                FROM product_categories pc
                                JOIN categories c ON c.id = pc.category_id
                                WHERE pc.product_id = p.id AND LOWER(c.name) LIKE :like
                            )
                        )
                    ORDER BY p.id DESC
                    LIMIT :limit OFFSET :offset
                )
                SELECT * FROM matched
            """), {"like": like, "limit": limit, "offset": offset}).mappings().all()

            total = rows[0]["total"] if rows else 0

            results = []
            for r in rows:
                results.append({
                    "product_id": r["product_id"],
                    "name": r["name"],
                    "slug": r["slug"],
                    "brand_name": r["brand_name"],
                    "base_price": float(r["base_price"] or 0),
                    "discount_percent": float(r["discount_percent"] or 0),
                    "main_image": r["main_image"],
                    "score": 0.0,
                })

            return {
                "total": total,
                "results": results,
            }
        finally:
            db.close()


search_service = SearchService()
