from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database.database import get_db
from dependencies.auth_dependency import get_current_user

from services import order_services
from schemas.order_schemas import (
    CancelOrderItemRequest,
    ReturnOrderItemRequest,
    OrderDetailResponse,
)

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("/mine")
def list_orders(
    limit: int = Query(3, ge=1, le=50),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
    search: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = order_services.get_user_orders_paginated(
        db=db,
        user_id=current_user["id"],
        limit=limit,
        offset=offset,
        status=status,
        search=search,
    )
    return result


@router.get("/{order_id}", response_model=OrderDetailResponse)
def get_order(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = order_services.get_order_details(db, order_id, current_user["id"])
        return data
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{order_id}/items/{item_id}/tracking")
def get_order_item_tracking(
    order_id: int,
    item_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = order_services.get_order_item_tracking(db, order_id, item_id, current_user["id"])
        return data
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{order_id}/items/{item_id}/cancel")
def cancel_order_item(
    order_id: int,
    item_id: int,
    payload: CancelOrderItemRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = order_services.cancel_order_item(
            db=db,
            order_id=order_id,
            order_item_id=item_id,
            user_id=current_user["id"],
            reason=payload.reason,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{order_id}/items/{item_id}/return")
def return_order_item(
    order_id: int,
    item_id: int,
    payload: ReturnOrderItemRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = order_services.return_order_item(
            db=db,
            order_id=order_id,
            order_item_id=item_id,
            user_id=current_user["id"],
            reason=payload.reason,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
