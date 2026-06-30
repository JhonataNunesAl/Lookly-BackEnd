from enum import Enum
from uuid import UUID
from pydantic import BaseModel


class SwipeDirection(str, Enum):
    RIGHT = "RIGHT"  # curtir/salvar
    LEFT = "LEFT"  # descartar


class SwipeCreate(BaseModel):
    look_id: UUID
    direction: SwipeDirection


class SwipeResponse(BaseModel):
    id: UUID
    look_id: UUID
    direction: SwipeDirection
    saved: bool = False  # True quando o swipe RIGHT também salvou no armário

    class Config:
        from_attributes = True
