from enum import Enum
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field


class AddressType(str, Enum):
    home = "home"
    work = "work"
    other = "other"


class AddAddressRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)

    phone_number: str = Field(pattern=r"^\d{10}$")
    alternate_phone: Optional[str] = Field(default=None, pattern=r"^\d{10}$")

    address: str = Field(min_length=5, max_length=255)
    landmark: Optional[str] = Field(default=None, max_length=255)

    city: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    country: str = "India"

    postal_code: str = Field(
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$"
    )

    address_type: AddressType

    delivery_instructions: Optional[str] = Field(
        default=None,
        max_length=255
    )

    is_default: bool = False


class AddAddressResponse(BaseModel):
    message: str
    address_id: int


class UpdateAddressRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)

    phone_number: str = Field(pattern=r"^\d{10}$")
    alternate_phone: Optional[str] = Field(default=None, pattern=r"^\d{10}$")

    address: str = Field(min_length=5, max_length=255)
    landmark: Optional[str] = Field(default=None, max_length=255)

    city: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    country: str = "India"

    postal_code: str = Field(
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$"
    )

    address_type: AddressType

    delivery_instructions: Optional[str] = Field(
        default=None,
        max_length=255
    )

    is_default: bool = False


class AddressItemResponse(BaseModel):
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

    address_type: AddressType

    delivery_instructions: Optional[str] = None

    is_default: bool
    updated_at: datetime