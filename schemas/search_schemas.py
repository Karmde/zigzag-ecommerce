from pydantic import BaseModel, Field
from typing import Optional, List


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class SearchResult(BaseModel):
    product_id: int
    name: str
    slug: str
    brand_name: Optional[str] = None
    base_price: float
    discount_percent: float
    main_image: Optional[str] = None
    score: float


class SearchResponse(BaseModel):
    query: str
    total: int
    results: List[SearchResult]
