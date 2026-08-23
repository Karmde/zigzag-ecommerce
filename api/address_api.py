from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.database import get_db
from dependencies.auth_dependency import get_current_user

from services import address_services
from schemas.address_schemas import AddAddressRequest, AddAddressResponse, AddressItemResponse, UpdateAddressRequest

router = APIRouter(prefix="/address", tags=["Address"])

@router.post("", response_model=AddAddressResponse, status_code=201)
def add_to_address(payload: AddAddressRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return address_services.create_address(payload, current_user["id"], db)


@router.get("", response_model=list[AddressItemResponse])
def get_addresses(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return address_services.get_addresses(current_user["id"], db)


@router.get("/{address_id}", response_model=AddressItemResponse)
def get_address(address_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    address = address_services.get_address(current_user["id"], address_id, db)

    if not address:
        raise HTTPException(
            status_code=404,
            detail="Address not found"
        )

    return address

@router.put("/{address_id}", status_code=204)
def update_address(
    address_id: int,
    payload: UpdateAddressRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    status, message = address_services.update_address(
        payload,
        current_user["id"],
        address_id,
        db,
    )

    if status != 204:
        raise HTTPException(
            status_code=status,
            detail=message,
        )

    return None

@router.delete("/{address_id}", status_code=204)
def delete_address(address_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    status, message = address_services.delete_address(address_id, current_user["id"], db)

    if status != 204:
        raise HTTPException(
            status_code=status,
            detail=message
        )

    return None


@router.patch("/{address_id}/default")
def mark_as_default(address_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    status, message = address_services.mark_to_default(
        current_user["id"],
        address_id,
        db
    )

    if status != 200:
        raise HTTPException(
            status_code=status,
            detail=message
        )

    return {"message": message}