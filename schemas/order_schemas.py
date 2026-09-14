from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class CancelOrderItemRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=255, description="Reason for cancellation")


class ReturnOrderItemRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=255, description="Reason for return")


class OrderItemResponse(BaseModel):
    id: int
    order_id: int
    product_id: int
    product_variant_id: int
    product_name: str
    product_image: Optional[str] = None
    sku: str
    color_name: Optional[str] = None
    size_name: Optional[str] = None
    unit_price: float
    quantity: int
    line_total: float
    status: str
    cancelled_quantity: int
    returned_quantity: int
    refund_amount: float
    refund_status: str
    cancel_reason: Optional[str] = None
    return_reason: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    returned_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class OrderDetailResponse(BaseModel):
    order: dict
    items: list[OrderItemResponse]
