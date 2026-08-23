from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class CouponCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    discount_type: str = Field(..., pattern="^(percentage|fixed|free_shipping)$")
    discount_value: float = Field(..., ge=0)
    minimum_cart_amount: float = Field(0.0, ge=0)
    maximum_discount: Optional[float] = Field(None, ge=0)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    usage_limit: Optional[int] = Field(None, ge=1)
    usage_per_user: int = Field(1, ge=1)
    is_active: bool = True
    product_ids: Optional[List[int]] = Field(default_factory=list)
    category_ids: Optional[List[int]] = Field(default_factory=list)


class CouponUpdateRequest(BaseModel):
    description: Optional[str] = Field(None, max_length=255)
    discount_type: Optional[str] = Field(None, pattern="^(percentage|fixed|free_shipping)$")
    discount_value: Optional[float] = Field(None, ge=0)
    minimum_cart_amount: Optional[float] = Field(None, ge=0)
    maximum_discount: Optional[float] = Field(None, ge=0)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    usage_limit: Optional[int] = Field(None, ge=1)
    usage_per_user: int = Field(1, ge=1)
    is_active: Optional[bool] = None
    product_ids: Optional[List[int]] = None
    category_ids: Optional[List[int]] = None


class CouponResponse(BaseModel):
    id: int
    code: str
    description: Optional[str]
    discount_type: str
    discount_value: float
    minimum_cart_amount: float
    maximum_discount: Optional[float]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    usage_limit: Optional[int]
    usage_per_user: int
    used_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    product_ids: List[int] = Field(default_factory=list)
    category_ids: List[int] = Field(default_factory=list)


class CouponVerifyRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    cart_total: float = Field(..., ge=0)


class CouponVerifyResponse(BaseModel):
    valid: bool
    message: str
    coupon: Optional[CouponResponse] = None
    discount_amount: Optional[float] = None
    final_amount: Optional[float] = None
