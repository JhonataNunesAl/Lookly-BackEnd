"""Coleções da loja: conjuntos de peças com nome livre ("Roupas sessão de
carnaval"), só para o lojista se organizar. Cada consulta filtra pela loja do
usuário (ver inventory_service.minha_loja)."""
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from model.look import Look
from model.store_collection import StoreCollection, StoreCollectionItem
from schemas.inventory import ColecaoCreate, ColecaoUpdate
from service.inventory_service import minha_loja, _peca_da_loja

MAX_COLECOES = 100


def _nome(n: str) -> str:
    n = " ".join(n.split())
    if not n:
        raise HTTPException(status_code=422, detail="Dê um nome para a coleção.")
    return n


async def _colecao(db: AsyncSession, seller_id: UUID, collection_id: UUID) -> StoreCollection:
    c = (
        await db.execute(
            select(StoreCollection).where(StoreCollection.id == collection_id, StoreCollection.seller_id == seller_id)
        )
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coleção não encontrada")
    return c


async def _commit_nome(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já existe uma coleção com esse nome.")


async def listar(db: AsyncSession, user_id: UUID) -> list[dict]:
    seller = await minha_loja(db, user_id)
    contagem = (
        select(StoreCollectionItem.collection_id, func.count().label("n"))
        .group_by(StoreCollectionItem.collection_id)
        .subquery()
    )
    linhas = (
        await db.execute(
            select(StoreCollection, func.coalesce(contagem.c.n, 0))
            .outerjoin(contagem, contagem.c.collection_id == StoreCollection.id)
            .where(StoreCollection.seller_id == seller.id)
            .order_by(StoreCollection.sort_order, func.lower(StoreCollection.name))
        )
    ).all()
    ids = [c.id for c, _ in linhas]
    capas: dict = {}
    if ids:
        # Capa das 3 peças adicionadas por último em cada coleção.
        ordem = func.row_number().over(
            partition_by=StoreCollectionItem.collection_id, order_by=StoreCollectionItem.added_at.desc()
        ).label("r")
        sub = (
            select(StoreCollectionItem.collection_id, Look.photos, ordem)
            .join(Look, Look.id == StoreCollectionItem.look_id)
            .where(StoreCollectionItem.collection_id.in_(ids))
            .subquery()
        )
        for cid, fotos, _ in (await db.execute(select(sub).where(sub.c.r <= 3))).all():
            if fotos:
                capas.setdefault(cid, []).append(fotos[0])
    return [
        {
            "id": c.id, "name": c.name, "description": c.description, "sort_order": c.sort_order,
            "item_count": int(n), "covers": capas.get(c.id, []), "created_at": c.created_at,
        }
        for c, n in linhas
    ]


async def criar(db: AsyncSession, user_id: UUID, dados: ColecaoCreate) -> dict:
    seller = await minha_loja(db, user_id)
    total = (
        await db.execute(select(func.count()).where(StoreCollection.seller_id == seller.id))
    ).scalar() or 0
    if total >= MAX_COLECOES:
        raise HTTPException(status_code=400, detail=f"No máximo {MAX_COLECOES} coleções por loja.")
    c = StoreCollection(seller_id=seller.id, name=_nome(dados.name), description=dados.description, sort_order=total)
    db.add(c)
    await _commit_nome(db)
    await db.refresh(c)
    return {"id": c.id, "name": c.name, "description": c.description, "sort_order": c.sort_order,
            "item_count": 0, "covers": [], "created_at": c.created_at}


async def atualizar(db: AsyncSession, user_id: UUID, collection_id: UUID, dados: ColecaoUpdate) -> dict:
    seller = await minha_loja(db, user_id)
    c = await _colecao(db, seller.id, collection_id)
    payload = dados.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"] is not None:
        c.name = _nome(payload["name"])
    if "description" in payload:
        c.description = payload["description"]
    if payload.get("sort_order") is not None:
        c.sort_order = payload["sort_order"]
    c.updated_at = func.now()
    await _commit_nome(db)
    return next(x for x in await listar(db, user_id) if x["id"] == c.id)


async def apagar(db: AsyncSession, user_id: UUID, collection_id: UUID) -> None:
    """Apaga só a coleção; as peças continuam no estoque."""
    seller = await minha_loja(db, user_id)
    c = await _colecao(db, seller.id, collection_id)
    await db.delete(c)
    await db.commit()


async def adicionar_pecas(db: AsyncSession, user_id: UUID, collection_id: UUID, look_ids: list[UUID]) -> int:
    seller = await minha_loja(db, user_id)
    await _colecao(db, seller.id, collection_id)
    # Só peças da própria loja entram (ids de outra loja são ignorados).
    validas = list(
        (await db.execute(select(Look.id).where(Look.id.in_(look_ids), Look.seller_id == seller.id))).scalars()
    )
    if not validas:
        raise HTTPException(status_code=404, detail="Nenhuma dessas peças é da sua loja.")
    await db.execute(
        insert(StoreCollectionItem)
        .values([{"collection_id": collection_id, "look_id": i} for i in validas])
        .on_conflict_do_nothing()
    )
    await db.commit()
    return len(validas)


async def remover_peca(db: AsyncSession, user_id: UUID, collection_id: UUID, look_id: UUID) -> None:
    seller = await minha_loja(db, user_id)
    await _colecao(db, seller.id, collection_id)
    await db.execute(
        delete(StoreCollectionItem).where(
            StoreCollectionItem.collection_id == collection_id, StoreCollectionItem.look_id == look_id
        )
    )
    await db.commit()


async def definir_colecoes_da_peca(db: AsyncSession, user_id: UUID, look_id: UUID, collection_ids: list[UUID]) -> list[UUID]:
    """Marca em quais coleções a peça está (a lista substitui a anterior)."""
    seller = await minha_loja(db, user_id)
    await _peca_da_loja(db, seller.id, look_id)
    desejadas = set(collection_ids)
    if desejadas:
        validas = set(
            (
                await db.execute(
                    select(StoreCollection.id).where(
                        StoreCollection.id.in_(desejadas), StoreCollection.seller_id == seller.id
                    )
                )
            ).scalars()
        )
        if validas != desejadas:
            raise HTTPException(status_code=404, detail="Coleção não encontrada")
    minhas = select(StoreCollection.id).where(StoreCollection.seller_id == seller.id)
    await db.execute(
        delete(StoreCollectionItem).where(
            StoreCollectionItem.look_id == look_id,
            StoreCollectionItem.collection_id.in_(minhas),
            StoreCollectionItem.collection_id.not_in(desejadas) if desejadas else True,
        )
    )
    if desejadas:
        await db.execute(
            insert(StoreCollectionItem)
            .values([{"collection_id": c, "look_id": look_id} for c in desejadas])
            .on_conflict_do_nothing()
        )
    await db.commit()
    return sorted(desejadas, key=str)


async def colecoes_por_peca(db: AsyncSession, look_ids: list[UUID]) -> dict:
    if not look_ids:
        return {}
    saida: dict = {}
    for look_id, cid in (
        await db.execute(
            select(StoreCollectionItem.look_id, StoreCollectionItem.collection_id).where(
                StoreCollectionItem.look_id.in_(look_ids)
            )
        )
    ).all():
        saida.setdefault(look_id, []).append(cid)
    return saida
