from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.look import LookResponse
from schemas.collection import (
    CollectionCreate,
    CollectionItemAdd,
    CollectionResponse,
)
from service import wardrobe_service

router = APIRouter(tags=["Armário"])


# ---- Looks salvos ----

@router.get("/saved-looks", response_model=list[LookResponse])
async def listar_armario(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await wardrobe_service.list_saved_looks(db, user_id)


@router.delete("/saved-looks/{look_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_do_armario(
    look_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await wardrobe_service.remove_saved_look(db, user_id, look_id)


# ---- Coleções ----

@router.get("/collections", response_model=list[CollectionResponse])
async def listar_colecoes(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await wardrobe_service.list_collections(db, user_id)


@router.post(
    "/collections", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED
)
async def criar_colecao(
    dados: CollectionCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await wardrobe_service.create_collection(db, user_id, dados)


@router.get("/collections/{collection_id}/looks", response_model=list[LookResponse])
async def listar_looks_da_colecao(
    collection_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await wardrobe_service.list_collection_looks(db, user_id, collection_id)


@router.post("/collections/{collection_id}/looks", status_code=status.HTTP_201_CREATED)
async def adicionar_look_na_colecao(
    collection_id: UUID,
    dados: CollectionItemAdd,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await wardrobe_service.add_look_to_collection(
        db, user_id, collection_id, dados.look_id
    )
    return {"status": "adicionado"}


@router.delete(
    "/collections/{collection_id}/looks/{look_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remover_look_da_colecao(
    collection_id: UUID,
    look_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await wardrobe_service.remove_look_from_collection(
        db, user_id, collection_id, look_id
    )
