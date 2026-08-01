from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class CartUserResponse(BaseModel):
    id: UUID
    user_id: UUID
    created_at: datetime
    update_at: datetime