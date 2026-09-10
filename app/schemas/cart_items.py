from datetime import datetime
from decimal import Decimal
from uuid import UUID
from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class LookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    price: Decimal | None
    photos: list[str]


class CartItemsAdd(BaseModel):
    look_id: UUID
    quantity: int = 1


class CartItemsAddQuantity(BaseModel):
    quantity: int = 1


class CartItemsDelete(BaseModel):
    quantity: int = 1


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
    price_quantity_total: Decimal
    look: LookResponse
    created_at: datetime


class ListCartItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    looks: list[CartItemLookResponse]
    price_total: Decimal



class DeleteLookCartItemUser(BaseModel):
    look_id: UUID