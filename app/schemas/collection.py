from uuid import UUID
from pydantic import BaseModel
from schemas.look import LookResponse


class CollectionCreate(BaseModel):
    name: str
    cover_url: str | None = None
    is_public: bool = False


class CollectionItemAdd(BaseModel):
    look_id: UUID


class CollectionResponse(BaseModel):
    id: UUID
    name: str
    cover_url: str | None = None
    is_public: bool = False

    class Config:
        from_attributes = True


class CollectionWithLooks(CollectionResponse):
    looks: list[LookResponse] = []
