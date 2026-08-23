from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class AddToWishlistRequest(BaseModel):
    product_variant_id: int = Field(..., gt=0, description="ID of the selected product variant")


class AddToWishlistResponse(BaseModel):
    id: int
    user_id: int
    product_variant_id: int
    created_at: datetime


class WishlistItemResponse(BaseModel):
    id: int
    user_id: int
    product_variant_id: int
    sku: str
    product_name: str
    product_slug: str
    color_name: Optional[str]
    color_hex: Optional[str]
    size_name: Optional[str]
    image_url: Optional[str]
    unit_price: float
    stock_quantity: int
    is_active: bool
    category_name: str
    created_at: datetime