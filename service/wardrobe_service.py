from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
from model.saved_look import SavedLook
from model.look import Look
from model.collection import Collection, CollectionItem
from schemas.collection import CollectionCreate


# ---- Armário (looks salvos) ----

async def list_saved_looks(db: AsyncSession, user_id: UUID) -> list[Look]:
    query = (
        select(Look)
        .join(SavedLook, SavedLook.look_id == Look.id)
        .where(SavedLook.user_id == user_id)
        .order_by(SavedLook.created_at.desc())
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def remove_saved_look(db: AsyncSession, user_id: UUID, look_id: UUID) -> None:
    result = await db.execute(
        select(SavedLook).where(
            SavedLook.user_id == user_id, SavedLook.look_id == look_id
        )
    )
    saved = result.scalar_one_or_none()
    if not saved:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Look não está no armário"
        )
    await db.delete(saved)
    await db.commit()


# ---- Coleções (pastas) ----

async def _get_owned_collection(
    db: AsyncSession, user_id: UUID, collection_id: UUID
) -> Collection:
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id)
    )
    collection = result.scalar_one_or_none()
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coleção não encontrada"
        )
    if collection.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Esta coleção não é sua"
        )
    return collection


async def list_collections(db: AsyncSession, user_id: UUID) -> list[Collection]:
    result = await db.execute(
        select(Collection)
        .where(Collection.user_id == user_id)
        .order_by(Collection.created_at.desc())
    )
    return list(result.scalars().all())


async def create_collection(
    db: AsyncSession, user_id: UUID, dados: CollectionCreate
) -> Collection:
    collection = Collection(user_id=user_id, name=dados.name)
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return collection


async def list_collection_looks(
    db: AsyncSession, user_id: UUID, collection_id: UUID
) -> list[Look]:
    await _get_owned_collection(db, user_id, collection_id)
    query = (
        select(Look)
        .join(CollectionItem, CollectionItem.look_id == Look.id)
        .where(CollectionItem.collection_id == collection_id)
        .order_by(CollectionItem.created_at.desc())
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def add_look_to_collection(
    db: AsyncSession, user_id: UUID, collection_id: UUID, look_id: UUID
) -> None:
    await _get_owned_collection(db, user_id, collection_id)

    look = await db.execute(select(Look).where(Look.id == look_id))
    if not look.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Look não encontrado"
        )

    db.add(CollectionItem(collection_id=collection_id, look_id=look_id))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Look já está nesta coleção",
        )


async def remove_look_from_collection(
    db: AsyncSession, user_id: UUID, collection_id: UUID, look_id: UUID
) -> None:
    await _get_owned_collection(db, user_id, collection_id)
    result = await db.execute(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection_id,
            CollectionItem.look_id == look_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Look não está na coleção"
        )
    await db.delete(item)
    await db.commit()
