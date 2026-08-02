from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    price: Decimal | None
    photos: list[str]


class CartItemsAdd(BaseModel):
    cart_id: UUID
    look_id: UUID
    quantity: int


class CartItemsDelete(BaseModel):
    cart_id: UUID
    look_id: UUID
    quantity: int


class CartItemsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cart_id: UUID
    look_id: UUID
    quantity: int
    created_at: datetime



class CartItemLookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    quantity: int
    created_at: datetime
    look: LookResponse


class ListCartItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    looks: list[CartItemLookResponse]
    price_total: Decimal


class DeleteLookCartItemUser(BaseModel):
    user_id: UUID
    look_id: UUID