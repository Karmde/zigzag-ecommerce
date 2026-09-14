from pydantic import BaseModel, Field
from typing import Optional, List
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
    coupon_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


# ==========================================================
# Cart Coupon
# ==========================================================

class ApplyCouponRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)


class ApplyCouponResponse(BaseModel):
    success: bool
    message: str
    applied_count: int
    eligible_item_ids: List[int] = Field(default_factory=list)
    ineligible_item_ids: List[int] = Field(default_factory=list)
    coupon: Optional[dict] = None


class RemoveCouponRequest(BaseModel):
    cart_item_ids: Optional[List[int]] = Field(default=None, description="Specific item IDs to remove coupon from. If omitted, removes from all.")


class RemoveCouponResponse(BaseModel):
    success: bool
    removed_count: int