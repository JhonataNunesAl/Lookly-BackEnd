import hashlib
from datetime import datetime, timezone
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
from model.seller import Seller, SellerPrivate, StoreMember
from schemas.seller import SellerCreate, SellerUpdate, DocumentInput, DocumentVerifyResponse
from core import crypto
from core.document_validation import normalizar_documento, validar_documento
from core.cnpj_lookup import lookup_cnpj, CNPJLookupError


async def search_sellers(
    db: AsyncSession, q: str | None, limit: int, cursor: datetime | None
) -> dict:
    """Busca pública por nome/descrição da loja — só lojas ativas."""
    query = select(Seller).where(Seller.status == "active")
    if q:
        termo = f"%{q}%"
        query = query.where(Seller.store_name.ilike(termo) | Seller.description.ilike(termo))
    if cursor is not None:
        query = query.where(Seller.created_at < cursor)
    query = query.order_by(Seller.created_at.desc()).limit(limit)

    result = await db.execute(query)
    sellers = list(result.scalars().all())
    next_cursor = sellers[-1].created_at.isoformat() if len(sellers) == limit else None
    return {"items": sellers, "next_cursor": next_cursor}


async def get_public_seller(db: AsyncSession, seller_id: UUID, user_id: UUID | None) -> Seller:
    """Storefront pública — mesma regra de visibilidade do look: ativa é
    pública, não-ativa só para quem gerencia a loja (ver look_service._assert_visible)."""
    result = await db.execute(select(Seller).where(Seller.id == seller_id))
    seller = result.scalar_one_or_none()
    if not seller:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loja não encontrada")
    if seller.status != "active":
        if user_id is None or not await can_manage_store(db, user_id, seller.id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loja não encontrada")
    return seller


async def get_seller_by_owner(db: AsyncSession, user_id: UUID) -> Seller | None:
    result = await db.execute(
        select(Seller).where(Seller.owner_profile_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_me(db: AsyncSession, user_id: UUID) -> Seller:
    seller = await get_seller_by_owner(db, user_id)
    if not seller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Você ainda não tem uma loja"
        )
    return seller


async def become_seller(db: AsyncSession, user_id: UUID, dados: SellerCreate) -> Seller:
    if await get_seller_by_owner(db, user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Você já tem uma loja"
        )
    seller = Seller(owner_profile_id=user_id, **dados.model_dump())
    db.add(seller)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="store_slug já está em uso",
        )
    await db.refresh(seller)
    return seller


async def update_me(db: AsyncSession, user_id: UUID, dados: SellerUpdate) -> Seller:
    seller = await get_me(db, user_id)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(seller, campo, valor)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="store_slug já está em uso",
        )
    await db.refresh(seller)
    return seller


async def can_manage_store(db: AsyncSession, user_id: UUID, seller_id: UUID) -> bool:
    """Réplica de can_manage_store() do banco: dono OU membro owner/manager.

    RLS aplica isso para acesso direto via PostgREST; aqui é a verificação
    equivalente no caminho do FastAPI.
    """
    owner = await db.execute(
        select(Seller.id).where(
            Seller.id == seller_id, Seller.owner_profile_id == user_id
        )
    )
    if owner.scalar_one_or_none():
        return True
    member = await db.execute(
        select(StoreMember.role).where(
            StoreMember.seller_id == seller_id,
            StoreMember.profile_id == user_id,
            StoreMember.role.in_(["owner", "manager"]),
        )
    )
    return member.scalar_one_or_none() is not None


async def verify_document(dados: DocumentInput) -> DocumentVerifyResponse:
    """Prévia (não grava nada): confere dígito verificador e, para CNPJ, a
    situação cadastral real na Receita (via BrasilAPI). CPF não tem registro
    público equivalente — fica só no dígito verificador.
    """
    digits = normalizar_documento(dados.document_number)
    if not validar_documento(digits, dados.document_type):
        return DocumentVerifyResponse(
            valid=False, message=f"{dados.document_type} inválido — confira os números."
        )

    if dados.document_type == "CPF":
        return DocumentVerifyResponse(valid=True, message="CPF com formato válido.")

    try:
        resultado = await lookup_cnpj(digits)
    except CNPJLookupError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível verificar o CNPJ agora. Tente de novo em instantes.",
        )

    if not resultado.exists:
        return DocumentVerifyResponse(valid=False, message="CNPJ não encontrado na Receita Federal.")

    return DocumentVerifyResponse(
        valid=True,
        active=resultado.active,
        legal_name=resultado.legal_name,
        message=(
            f"Encontramos: {resultado.legal_name} — situação "
            f"{'ATIVA' if resultado.active else 'NÃO ATIVA'}."
        ),
    )


async def set_document(
    db: AsyncSession, user_id: UUID, dados: DocumentInput
) -> None:
    """Valida, verifica (CNPJ) e cifra o documento fiscal antes de gravar em
    sellers_private. O cliente manda o número em claro sobre HTTPS — este
    endpoint já exige um JWT válido; cifrar/hashear é responsabilidade do
    servidor agora, não do app (ver core/crypto.py)."""
    seller = await get_me(db, user_id)

    digits = normalizar_documento(dados.document_number)
    if not validar_documento(digits, dados.document_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{dados.document_type} inválido — confira os números.",
        )

    verified_at = None
    if dados.document_type == "CNPJ":
        try:
            resultado = await lookup_cnpj(digits)
        except CNPJLookupError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Não foi possível verificar o CNPJ agora. Tente de novo em instantes.",
            )
        if not resultado.exists or not resultado.active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Esse CNPJ não foi encontrado como uma empresa ativa na Receita Federal.",
            )
        verified_at = datetime.now(timezone.utc)

    document_enc = crypto.encrypt(digits)
    document_hash = hashlib.sha256(digits.encode("utf-8")).hexdigest()

    result = await db.execute(
        select(SellerPrivate).where(SellerPrivate.seller_id == seller.id)
    )
    priv = result.scalar_one_or_none()
    if priv:
        priv.document_enc = document_enc
        priv.document_hash = document_hash
        priv.document_type = dados.document_type
        priv.verified_at = verified_at
    else:
        db.add(
            SellerPrivate(
                seller_id=seller.id,
                document_enc=document_enc,
                document_hash=document_hash,
                document_type=dados.document_type,
                verified_at=verified_at,
            )
        )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Documento já cadastrado por outra loja",
        )
