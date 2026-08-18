from uuid import UUID
from pydantic import BaseModel, Field
from schemas.look import LookResponse


class CollectionCreate(BaseModel):
    # Espelha o CHECK de public.collections.name em nem_schema.sql — sem
    # isso, um nome vazio ou muito longo só falhava no commit e virava a
    # mensagem errada ("você já tem uma coleção com esse nome", ver
    # wardrobe_service.create_collection) em vez de um erro de formato.
    name: str = Field(min_length=1, max_length=60)
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
