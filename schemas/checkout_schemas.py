from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class CheckoutItemResponse(BaseModel):
    cart_item_id: int
    product_id: int
    product_variant_id: int
    product_name: str
    sku: str
    color_name: Optional[str] = None
    size_name: Optional[str] = None
    image_url: Optional[str] = None
    quantity: int
    unit_price: float
    line_total: float
    stock_quantity: int
    coupon_id: Optional[int] = None
    coupon_code: Optional[str] = None
    coupon_discount_type: Optional[str] = None
    coupon_discount_value: Optional[float] = None
    coupon_applied_discount: Optional[float] = None


class CheckoutAddressResponse(BaseModel):
    id: int
    full_name: str
    phone_number: str
    alternate_phone: Optional[str] = None
    address: str
    landmark: Optional[str] = None
    city: str
    state: str
    country: str
    postal_code: str
    address_type: str
    delivery_instructions: Optional[str] = None
    is_default: bool
    updated_at: Optional[datetime] = None


class CheckoutResponse(BaseModel):
    items: List[CheckoutItemResponse]
    subtotal: float
    discount: float
    grand_total: float
    addresses: List[CheckoutAddressResponse]


class PlaceOrderRequest(BaseModel):
    address_id: int = Field(..., gt=0, description="ID of the selected address")
    payment_method: str = Field(..., pattern="^(cod|upi)$", description="Payment method")


class PlaceOrderResponse(BaseModel):
    order_id: int
    payment_status: str
    confirmation_token: str
    redirect_url: Optional[str] = None
