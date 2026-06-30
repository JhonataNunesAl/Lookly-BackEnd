from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.look import LookCreate, LookUpdate, LookResponse
from service import look_service

router = APIRouter(prefix="/looks", tags=["Looks"])


@router.post("", response_model=LookResponse, status_code=status.HTTP_201_CREATED)
async def criar_look(
    dados: LookCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await look_service.create_look(db, user_id, dados)


@router.get("/{look_id}", response_model=LookResponse)
async def get_look(look_id: UUID, db: AsyncSession = Depends(get_db)):
    return await look_service.get_look(db, look_id)


@router.put("/{look_id}", response_model=LookResponse)
async def atualizar_look(
    look_id: UUID,
    dados: LookUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await look_service.update_look(db, user_id, look_id, dados)


@router.delete("/{look_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deletar_look(
    look_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await look_service.delete_look(db, user_id, look_id)


@router.get("/{look_id}/share")
async def compartilhar_look(look_id: UUID, db: AsyncSession = Depends(get_db)):
    return await look_service.get_share_payload(db, look_id)
