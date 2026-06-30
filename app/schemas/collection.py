from uuid import UUID
from pydantic import BaseModel
from schemas.look import LookResponse


class CollectionCreate(BaseModel):
    name: str


class CollectionItemAdd(BaseModel):
    look_id: UUID


class CollectionResponse(BaseModel):
    id: UUID
    name: str

    class Config:
        from_attributes = True


class CollectionWithLooks(CollectionResponse):
    looks: list[LookResponse] = []
