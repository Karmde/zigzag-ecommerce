from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ==========================================================
# Add to Cart
# ==========================================================

class AddToCartRequest(BaseModel):
    product_variant_id: int = Field(..., gt=0, description="ID of the selected product variant")
    quantity: int = Field(1, ge=1, le=99, description="Quantity to add")


class UpdateCartQuantityRequest(BaseModel):
    quantity: int = Field(..., ge=1, le=99, description="New quantity")


class AddToCartResponse(BaseModel):
    id: int
    user_id: int
    product_variant_id: int
    quantity: int
    created_at: datetime
    updated_at: datetime


# ==========================================================
# Cart Item
# ==========================================================

class CartItemResponse(BaseModel):
    id: int
    user_id: int
    product_variant_id: int
    quantity: int
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
    updated_at: datetime