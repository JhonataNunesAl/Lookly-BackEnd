from uuid import UUID
from pydantic import BaseModel


class CategoryResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    image_url: str | None = None
    is_active: bool
    sort_order: int

    class Config:
        from_attributes = True
