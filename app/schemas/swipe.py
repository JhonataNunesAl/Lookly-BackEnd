from enum import Enum
from uuid import UUID
from pydantic import BaseModel


class SwipeDirection(str, Enum):
    RIGHT = "RIGHT"  # curtir (NÃO salva no armário — save é gesto separado)
    LEFT = "LEFT"  # descartar


class SwipeCreate(BaseModel):
    look_id: UUID
    direction: SwipeDirection


class SwipeResponse(BaseModel):
    look_id: UUID
    direction: SwipeDirection
    liked: bool = False  # True quando o RIGHT registrou uma curtida
