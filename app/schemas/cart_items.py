from pydantic import BaseModel
from uuid import UUID
from typing import List
from datetime import datetime


class CartItemsAdd(BaseModel):
    cart_id: UUID
    look_id: UUID
    quantity: int


class CartItemsResponse(BaseModel):
    id: UUID
    cart_id: UUID
    look_id: UUID
    quantity: int
    created_at: datetime


class ListCartItemResponse(BaseModel):
    looks: List[CartItemsResponse]


class DeleteLookCartItemUser(BaseModel):
    user_id: UUID
    look_id: UUID    
