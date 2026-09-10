from uuid import UUID
from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from model.look import Look
from model.category import Category
from schemas.look import LookCreate, LookUpdate
from service import seller_service


async def _commit_ou_400(db: AsyncSession) -> None:
    """Rede de segurança: o Pydantic (schemas/look.py) já espelha os CHECKs
    de nome/preço/estoque do banco, mas essa é a última linha de defesa
    contra qualquer constraint que o schema não cubra — sem isso, o commit
    falhando vira um 500 genérico em vez de um erro claro pro cliente."""
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não foi possível salvar o look — confira os dados enviados.",
        )


async def _get_look(db: AsyncSession, look_id: UUID) -> Look:
    result = await db.execute(select(Look).where(Look.id == look_id))
    look = result.scalar_one_or_none()
    if not look:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Look não encontrado"
        )
    return look


async def _validar_categoria(db: AsyncSession, category_id: UUID) -> None:
    cat = await db.execute(select(Category).where(Category.id == category_id))
    if not cat.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Categoria inexistente"
        )


async def _assert_visible(db: AsyncSession, look: Look, user_id: UUID | None) -> None:
    """Looks fora de `active` (draft/under_review/removed) só são visíveis para
    quem gerencia a loja dona do look. Sem isso, o feed filtra por status mas
    o acesso direto por ID (e o link de compartilhamento) expunha qualquer
    conteúdo em moderação para quem tivesse ou adivinhasse o UUID.
    """
    if look.status == "active":
        return
    if user_id is not None and await seller_service.can_manage_store(
        db, user_id, look.seller_id
    ):
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Look não encontrado")


async def get_look(db: AsyncSession, look_id: UUID, user_id: UUID | None = None) -> Look:
    look = await _get_look(db, look_id)
    await _assert_visible(db, look, user_id)
    return look


async def search_looks(
    db: AsyncSession,
    q: str | None,
    category_slug: str | None,
    limit: int,
    cursor: datetime | None,
    seller_id: UUID | None = None,
) -> dict:
    """Busca por texto em looks ativos — deliberadamente SEM a exclusão de
    "já visto" do feed: procurar precisa achar algo que a pessoa já swipou.
    `seller_id` reaproveita esta mesma função para `GET /sellers/{id}/looks`
    (o catálogo público de uma loja é só esta busca sem termo, filtrada por dona).
    """
    query = select(Look).where(Look.status == "active")

    if q:
        termo = f"%{q}%"
        query = query.where(
            Look.name.ilike(termo) | Look.description.ilike(termo)
        )
    if category_slug:
        query = query.join(Category, Look.category_id == Category.id).where(
            Category.slug == category_slug
        )
    if seller_id is not None:
        query = query.where(Look.seller_id == seller_id)
    if cursor is not None:
        query = query.where(Look.created_at < cursor)

    query = query.order_by(Look.created_at.desc()).limit(limit)

    result = await db.execute(query)
    looks = list(result.scalars().all())
    next_cursor = looks[-1].created_at.isoformat() if len(looks) == limit else None
    return {"items": looks, "next_cursor": next_cursor}


async def list_my_looks(
    db: AsyncSession, user_id: UUID, limit: int, cursor: datetime | None
) -> dict:
    """Todos os looks da loja logada, qualquer status — usado pela tela de
    gestão de catálogo/estoque. Diferente de `search_looks`, que só mostra
    `status == 'active'` (é a versão pública, via `GET /sellers/{id}/looks`).
    """
    seller = await seller_service.get_seller_by_owner(db, user_id)
    if not seller:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas vendedores têm catálogo próprio",
        )
    query = select(Look).where(Look.seller_id == seller.id)
    if cursor is not None:
        query = query.where(Look.created_at < cursor)
    query = query.order_by(Look.created_at.desc()).limit(limit)

    result = await db.execute(query)
    looks = list(result.scalars().all())
    next_cursor = looks[-1].created_at.isoformat() if len(looks) == limit else None
    return {"items": looks, "next_cursor": next_cursor}


async def create_look(db: AsyncSession, user_id: UUID, dados: LookCreate) -> Look:
    # Só quem tem loja publica looks; o look pertence à loja (seller_id).
    seller = await seller_service.get_seller_by_owner(db, user_id)
    if not seller:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas vendedores podem criar looks",
        )
    await _validar_categoria(db, dados.category_id)

    look = Look(seller_id=seller.id, **dados.model_dump())
    db.add(look)
    await _commit_ou_400(db)
    await db.refresh(look)
    return look


async def _get_manageable_look(db: AsyncSession, user_id: UUID, look_id: UUID) -> Look:
    look = await _get_look(db, look_id)
    if not await seller_service.can_manage_store(db, user_id, look.seller_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não gerencia a loja deste look",
        )
    return look


async def update_look(
    db: AsyncSession, user_id: UUID, look_id: UUID, dados: LookUpdate
) -> Look:
    look = await _get_manageable_look(db, user_id, look_id)

    payload = dados.model_dump(exclude_unset=True)
    if "category_id" in payload:
        await _validar_categoria(db, payload["category_id"])
    for campo, valor in payload.items():
        setattr(look, campo, valor)
    await _commit_ou_400(db)
    await db.refresh(look)
    return look


async def delete_look(db: AsyncSession, user_id: UUID, look_id: UUID) -> None:
    look = await _get_manageable_look(db, user_id, look_id)
    await db.delete(look)
    await db.commit()


async def get_share_payload(db: AsyncSession, look_id: UUID, user_id: UUID | None = None) -> dict:
    """Payload de compartilhamento externo (WhatsApp/Instagram)."""
    look = await _get_look(db, look_id)
    await _assert_visible(db, look, user_id)
    deep_link = f"lookly://looks/{look.id}"
    texto = "Olha esse look que achei no Lookly!"
    return {
        "look_id": str(look.id),
        "deep_link": deep_link,
        "whatsapp_url": f"https://wa.me/?text={texto} {deep_link}",
        "buy_link": look.buy_link,
    }
