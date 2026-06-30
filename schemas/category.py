from uuid import UUID
from pydantic import BaseModel


class CategoryCreate(BaseModel):
    name: str
    slug: str
    image_url: str | None = None


class CategoryResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    image_url: str | None = None

    class Config:
        from_attributes = True
