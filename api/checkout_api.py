from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.database import get_db
from dependencies.auth_dependency import get_current_user

from services import checkout_services, order_services
from services.token_services import create_order_confirmation_token
from schemas.checkout_schemas import (
    CheckoutResponse,
    PlaceOrderRequest,
    PlaceOrderResponse,
)

router = APIRouter(prefix="/checkout", tags=["Checkout"])


@router.get("", response_model=CheckoutResponse)
def get_checkout(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = checkout_services.prepare_checkout(db, current_user["id"])
        return data
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders", response_model=PlaceOrderResponse, status_code=201)
def place_order(
    payload: PlaceOrderRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = order_services.place_order(
            db=db,
            user_id=current_user["id"],
            address_id=payload.address_id,
            payment_method=payload.payment_method,
        )
        confirmation_token = create_order_confirmation_token(
            result["order_id"], current_user["id"]
        )
        return PlaceOrderResponse(
            order_id=result["order_id"],
            payment_status=result["payment_status"],
            confirmation_token=confirmation_token,
            redirect_url=None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
