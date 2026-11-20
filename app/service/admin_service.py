"""Painel de administração: ver, editar e apagar usuários, lojas, peças,
categorias e denúncias; ver pedidos.

Regras que protegem a produção (há pagamentos reais):

- **Pedido é intocável.** Nada aqui altera pedido/pagamento — isso é do webhook
  do Mercado Pago. E nada que um pedido cite pode ser APAGADO: `order_items.look_id`
  é `ON DELETE CASCADE`, então apagar uma peça vendida apagaria a linha do pedido
  pago. Para peça/loja/conta com pedido, o caminho é suspender/remover (status),
  que tira do ar e mantém o registro.
- **Apagar pede confirmação** (`confirm=APAGAR`), conferida no servidor.
- **O admin não se bloqueia nem se apaga** pelo painel.
- Cada ação fica no log com o id do admin.
"""
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dependencies.admin import emails_admin
from model.category import Category
from model.look import Look
from model.orders import Order, PaymentStatus
from model.orders_items import OrderItems
from model.profile import Profile
from model.report import Report
from model.seller import Seller
from schemas.admin import (
    CONFIRMACAO_EXCLUSAO,
    CategoriaCreate,
    CategoriaUpdate,
    DenunciaUpdate,
    LojaUpdate,
    PecaUpdate,
    UsuarioUpdate,
)
from service import account_service, auth_admin_service

logger = logging.getLogger(__name__)


def _404(o_que: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{o_que} não encontrad{'a' if o_que.endswith('a') else 'o'}.")


def exigir_confirmacao(confirm: str | None) -> None:
    if (confirm or "").strip().upper() != CONFIRMACAO_EXCLUSAO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Para apagar, confirme digitando "{CONFIRMACAO_EXCLUSAO}".',
        )


def _termo(q: str | None) -> str | None:
    q = (q or "").strip()
    return f"%{q}%" if q else None


async def _emails(db: AsyncSession, ids: list[UUID]) -> dict[UUID, str]:
    """E-mails de login (auth.users). Melhor esforço: sem leitura do schema auth,
    o painel mostra tudo menos o e-mail."""
    if not ids:
        return {}
    try:
        async with db.begin_nested():
            linhas = (
                await db.execute(
                    text("SELECT id, email FROM auth.users WHERE id = ANY(:ids)"),
                    {"ids": list(ids)},
                )
            ).all()
    except DBAPIError as e:
        logger.warning("Admin: e-mails indisponíveis (%s)", type(e).__name__)
        return {}
    return {UUID(str(i)): (e or "") for i, e in linhas}


async def _ids_por_email(db: AsyncSession, termo: str) -> list[UUID]:
    try:
        async with db.begin_nested():
            linhas = (
                await db.execute(text("SELECT id FROM auth.users WHERE email ILIKE :t LIMIT 200"), {"t": termo})
            ).all()
    except DBAPIError:
        return []
    return [UUID(str(r[0])) for r in linhas]


def _pago():
    return Order.payment_status == PaymentStatus.APPROVED


# ── resumo ────────────────────────────────────────────────────────────────────

async def resumo(db: AsyncSession) -> dict:
    async def contar(stmt) -> int:
        return int((await db.execute(stmt)).scalar() or 0)

    semana = datetime.now(timezone.utc) - timedelta(days=7)
    receita = (await db.execute(select(func.coalesce(func.sum(Order.total_amount), 0)).where(_pago()))).scalar()
    return {
        "users": await contar(select(func.count()).select_from(Profile)),
        "users_blocked": await contar(select(func.count()).select_from(Profile).where(Profile.status.in_(["suspended", "banned"]))),
        "stores": await contar(select(func.count()).select_from(Seller)),
        "stores_inactive": await contar(select(func.count()).select_from(Seller).where(Seller.status != "active")),
        "looks_active": await contar(select(func.count()).select_from(Look).where(Look.status == "active")),
        "looks_total": await contar(select(func.count()).select_from(Look)),
        "orders_paid": await contar(select(func.count()).select_from(Order).where(_pago())),
        "orders_pending": await contar(select(func.count()).select_from(Order).where(Order.payment_status == PaymentStatus.PENDING)),
        "revenue_paid": Decimal(receita or 0),
        "reports_open": await contar(select(func.count()).select_from(Report).where(Report.status.in_(["open", "reviewing"]))),
        "new_users_7d": await contar(select(func.count()).select_from(Profile).where(Profile.created_at >= semana)),
    }


# ── usuários ──────────────────────────────────────────────────────────────────

async def listar_usuarios(db: AsyncSession, q: str | None, status_: str | None, limit: int, offset: int) -> dict:
    filtro = select(Profile.id)
    termo = _termo(q)
    if termo:
        por_email = await _ids_por_email(db, termo)
        filtro = filtro.where(
            or_(Profile.username.ilike(termo), Profile.full_name.ilike(termo), Profile.id.in_(por_email))
        )
    if status_:
        filtro = filtro.where(Profile.status == status_)

    total = int((await db.execute(select(func.count()).select_from(filtro.subquery()))).scalar() or 0)
    pedidos = (
        select(Order.user_id, func.count().label("n")).group_by(Order.user_id).subquery()
    )
    linhas = (
        await db.execute(
            select(Profile, Seller, func.coalesce(pedidos.c.n, 0))
            .outerjoin(Seller, Seller.owner_profile_id == Profile.id)
            .outerjoin(pedidos, pedidos.c.user_id == Profile.id)
            .where(Profile.id.in_(filtro))
            .order_by(Profile.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    emails = await _emails(db, [p.id for p, _, _ in linhas])
    admins = emails_admin()
    itens = []
    for p, s, n in linhas:
        email = emails.get(UUID(str(p.id)))
        itens.append({
            "id": p.id,
            "username": p.username,
            "full_name": p.full_name,
            "email": email,
            "status": p.status,
            "created_at": p.created_at,
            "store": {"id": s.id, "store_name": s.store_name, "status": s.status} if s else None,
            "orders_count": int(n or 0),
            "is_admin": bool(email and email.lower() in admins),
        })
    return {"items": itens, "total": total}


async def _usuario(db: AsyncSession, user_id: UUID) -> Profile:
    p = (await db.execute(select(Profile).where(Profile.id == user_id))).scalar_one_or_none()
    if not p:
        raise _404("Usuário")
    return p


async def atualizar_usuario(db: AsyncSession, admin_id: UUID, user_id: UUID, dados: UsuarioUpdate) -> dict:
    p = await _usuario(db, user_id)
    mudancas = dados.model_dump(exclude_unset=True)
    if "status" in mudancas and mudancas["status"] is not None:
        if user_id == admin_id and mudancas["status"] != "active":
            raise HTTPException(status_code=400, detail="Você não pode bloquear a sua própria conta.")
        if mudancas["status"] != p.status:
            # Primeiro o login (pode falhar na rede); só então o banco.
            await auth_admin_service.bloquear_login(user_id, mudancas["status"] != "active")
        p.status = mudancas["status"]
    if mudancas.get("full_name") is not None:
        p.full_name = mudancas["full_name"].strip() or None
    if mudancas.get("username") is not None:
        p.username = mudancas["username"]
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Esse nome de usuário já está em uso.")
    logger.info("ADMIN %s atualizou usuário %s: %s", admin_id, user_id, sorted(mudancas))
    return (await listar_usuario_unico(db, user_id))


async def listar_usuario_unico(db: AsyncSession, user_id: UUID) -> dict:
    p = await _usuario(db, user_id)
    s = (await db.execute(select(Seller).where(Seller.owner_profile_id == user_id))).scalar_one_or_none()
    n = int((await db.execute(select(func.count()).select_from(Order).where(Order.user_id == user_id))).scalar() or 0)
    email = (await _emails(db, [user_id])).get(user_id)
    return {
        "id": p.id, "username": p.username, "full_name": p.full_name, "email": email,
        "status": p.status, "created_at": p.created_at,
        "store": {"id": s.id, "store_name": s.store_name, "status": s.status} if s else None,
        "orders_count": n, "is_admin": bool(email and email.lower() in emails_admin()),
    }


async def apagar_usuario(db: AsyncSession, admin_id: UUID, user_id: UUID, confirm: str | None) -> None:
    exigir_confirmacao(confirm)
    if user_id == admin_id:
        raise HTTPException(status_code=400, detail="Você não pode apagar a sua própria conta pelo painel.")
    await _usuario(db, user_id)
    # Mesma rotina da exclusão pelo próprio usuário: trava se houver pedido
    # (como comprador ou como loja), apaga dados, arquivos e o login.
    try:
        await account_service.excluir_conta(db, user_id)
    except HTTPException as e:
        if e.status_code == 409:
            raise HTTPException(
                status_code=409,
                detail="Esta conta tem pedidos registrados e não pode ser apagada. Bloqueie a conta em vez disso.",
            )
        raise
    logger.info("ADMIN %s apagou a conta %s", admin_id, user_id)


# ── lojas ─────────────────────────────────────────────────────────────────────

def _vendas_por_loja():
    return (
        select(
            Look.seller_id.label("seller_id"),
            func.coalesce(func.sum(OrderItems.quantity), 0).label("qtd"),
            func.coalesce(func.sum(OrderItems.subtotal), 0).label("valor"),
        )
        .join(OrderItems, OrderItems.look_id == Look.id)
        .join(Order, Order.id == OrderItems.order_id)
        .where(_pago())
        .group_by(Look.seller_id)
        .subquery()
    )


async def listar_lojas(db: AsyncSession, q: str | None, status_: str | None, limit: int, offset: int, seller_id: UUID | None = None) -> dict:
    filtro = select(Seller.id)
    termo = _termo(q)
    if termo:
        filtro = filtro.where(or_(Seller.store_name.ilike(termo), Seller.store_slug.ilike(termo)))
    if status_:
        filtro = filtro.where(Seller.status == status_)
    if seller_id:
        filtro = filtro.where(Seller.id == seller_id)
    total = int((await db.execute(select(func.count()).select_from(filtro.subquery()))).scalar() or 0)

    pecas = select(Look.seller_id, func.count().label("n")).group_by(Look.seller_id).subquery()
    vendas = _vendas_por_loja()
    linhas = (
        await db.execute(
            select(Seller, Profile.username, func.coalesce(pecas.c.n, 0), vendas.c.qtd, vendas.c.valor)
            .join(Profile, Profile.id == Seller.owner_profile_id)
            .outerjoin(pecas, pecas.c.seller_id == Seller.id)
            .outerjoin(vendas, vendas.c.seller_id == Seller.id)
            .where(Seller.id.in_(filtro))
            .order_by(Seller.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    emails = await _emails(db, [s.owner_profile_id for s, *_ in linhas])
    itens = [
        {
            "id": s.id, "store_name": s.store_name, "store_slug": s.store_slug,
            "store_logo_url": s.store_logo_url, "description": s.description,
            "status": s.status, "created_at": s.created_at,
            "owner_id": s.owner_profile_id, "owner_username": username,
            "owner_email": emails.get(UUID(str(s.owner_profile_id))),
            "looks_count": int(n or 0), "items_sold": int(qtd or 0), "revenue": Decimal(valor or 0),
        }
        for s, username, n, qtd, valor in linhas
    ]
    return {"items": itens, "total": total}


async def _loja(db: AsyncSession, seller_id: UUID) -> Seller:
    s = (await db.execute(select(Seller).where(Seller.id == seller_id))).scalar_one_or_none()
    if not s:
        raise _404("Loja")
    return s


async def atualizar_loja(db: AsyncSession, admin_id: UUID, seller_id: UUID, dados: LojaUpdate) -> dict:
    s = await _loja(db, seller_id)
    mudancas = dados.model_dump(exclude_unset=True)
    for campo in ("store_name", "description", "status"):
        if mudancas.get(campo) is not None:
            setattr(s, campo, mudancas[campo].strip() if campo != "status" else mudancas[campo])
    s.updated_at = func.now()
    await db.commit()
    logger.info("ADMIN %s atualizou loja %s: %s", admin_id, seller_id, sorted(mudancas))
    return (await listar_lojas(db, None, None, 1, 0, seller_id=seller_id))["items"][0]


async def _citada_em_pedido(db: AsyncSession, cond) -> bool:
    achou = await db.execute(select(OrderItems.id).join(Look, Look.id == OrderItems.look_id).where(cond).limit(1))
    return achou.first() is not None


async def apagar_loja(db: AsyncSession, admin_id: UUID, seller_id: UUID, confirm: str | None) -> None:
    exigir_confirmacao(confirm)
    await _loja(db, seller_id)
    if await _citada_em_pedido(db, Look.seller_id == seller_id):
        raise HTTPException(
            status_code=409,
            detail="Esta loja tem peças em pedidos e não pode ser apagada (o histórico de vendas precisa ficar). Remova a loja do ar em vez disso.",
        )
    try:
        # look_views é particionada e sem FK: não sai em cascata.
        await db.execute(
            text("DELETE FROM public.look_views WHERE look_id IN (SELECT id FROM public.looks WHERE seller_id = :s)"),
            {"s": seller_id},
        )
        await db.execute(delete(Seller).where(Seller.id == seller_id))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.exception("Admin: exclusão da loja %s barrada por integridade", seller_id)
        raise HTTPException(status_code=409, detail="Não foi possível apagar a loja. Remova-a do ar em vez disso.")
    logger.info("ADMIN %s apagou a loja %s", admin_id, seller_id)


# ── peças ─────────────────────────────────────────────────────────────────────

async def listar_pecas(
    db: AsyncSession, q: str | None, status_: str | None, seller_id: UUID | None, limit: int, offset: int,
    look_id: UUID | None = None,
) -> dict:
    filtro = select(Look.id)
    termo = _termo(q)
    if termo:
        filtro = filtro.where(or_(Look.name.ilike(termo), Look.sku.ilike(termo), Look.brand.ilike(termo)))
    if status_:
        filtro = filtro.where(Look.status == status_)
    if seller_id:
        filtro = filtro.where(Look.seller_id == seller_id)
    if look_id:
        filtro = filtro.where(Look.id == look_id)
    total = int((await db.execute(select(func.count()).select_from(filtro.subquery()))).scalar() or 0)

    vendidas = (
        select(OrderItems.look_id, func.sum(OrderItems.quantity).label("n"))
        .join(Order, Order.id == OrderItems.order_id)
        .where(_pago())
        .group_by(OrderItems.look_id)
        .subquery()
    )
    linhas = (
        await db.execute(
            select(Look, Seller.store_name, Category.name, func.coalesce(vendidas.c.n, 0))
            .join(Seller, Seller.id == Look.seller_id)
            .outerjoin(Category, Category.id == Look.category_id)
            .outerjoin(vendidas, vendidas.c.look_id == Look.id)
            .where(Look.id.in_(filtro))
            .order_by(Look.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    itens = [
        {
            "id": l.id, "name": l.name, "photo": (l.photos or [None])[0], "price": l.price,
            "stock_quantity": l.stock_quantity or 0, "status": l.status, "created_at": l.created_at,
            "seller_id": l.seller_id, "store_name": loja, "category_name": cat, "times_sold": int(n or 0),
        }
        for l, loja, cat, n in linhas
    ]
    return {"items": itens, "total": total}


async def _peca(db: AsyncSession, look_id: UUID) -> Look:
    l = (await db.execute(select(Look).where(Look.id == look_id))).scalar_one_or_none()
    if not l:
        raise _404("Peça")
    return l


async def atualizar_peca(db: AsyncSession, admin_id: UUID, look_id: UUID, dados: PecaUpdate) -> dict:
    l = await _peca(db, look_id)
    mudancas = dados.model_dump(exclude_unset=True)
    if mudancas.get("name") is not None:
        l.name = mudancas["name"].strip()
    if "price" in mudancas and mudancas["price"] is not None:
        l.price = mudancas["price"]
    if mudancas.get("status") is not None:
        l.status = mudancas["status"]
    l.updated_at = func.now()
    await db.commit()
    logger.info("ADMIN %s atualizou peça %s: %s", admin_id, look_id, sorted(mudancas))
    return (await listar_pecas(db, None, None, None, 1, 0, look_id=look_id))["items"][0]


async def apagar_peca(db: AsyncSession, admin_id: UUID, look_id: UUID, confirm: str | None) -> None:
    exigir_confirmacao(confirm)
    await _peca(db, look_id)
    if await _citada_em_pedido(db, Look.id == look_id):
        raise HTTPException(
            status_code=409,
            detail="Esta peça está em pedidos e não pode ser apagada (apagaria a linha do pedido). Remova-a do ar em vez disso.",
        )
    await db.execute(text("DELETE FROM public.look_views WHERE look_id = :l"), {"l": look_id})
    await db.execute(delete(Look).where(Look.id == look_id))
    await db.commit()
    logger.info("ADMIN %s apagou a peça %s", admin_id, look_id)


# ── pedidos (só leitura) ──────────────────────────────────────────────────────

async def listar_pedidos(db: AsyncSession, pagamento: str | None, q: str | None, limit: int, offset: int) -> dict:
    filtro = select(Order.id)
    if pagamento:
        try:
            filtro = filtro.where(Order.payment_status == PaymentStatus(pagamento))
        except ValueError:
            raise HTTPException(status_code=400, detail="Situação de pagamento inválida.")
    termo = _termo(q)
    if termo:
        filtro = filtro.join(Profile, Profile.id == Order.user_id).where(Profile.username.ilike(termo))
    total = int((await db.execute(select(func.count()).select_from(filtro.subquery()))).scalar() or 0)

    pedidos = (
        await db.execute(
            select(Order, Profile.username)
            .outerjoin(Profile, Profile.id == Order.user_id)
            .options(selectinload(Order.items).selectinload(OrderItems.look))
            .where(Order.id.in_(filtro))
            .order_by(Order.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    seller_ids = {i.look.seller_id for o, _ in pedidos for i in o.items if i.look}
    lojas = {}
    if seller_ids:
        lojas = dict((await db.execute(select(Seller.id, Seller.store_name).where(Seller.id.in_(seller_ids)))).all())
    emails = await _emails(db, [o.user_id for o, _ in pedidos if o.user_id])
    itens = []
    for o, username in pedidos:
        itens.append({
            "id": o.id, "created_at": o.created_at,
            "status": o.status.value if hasattr(o.status, "value") else str(o.status),
            "payment_status": o.payment_status.value if hasattr(o.payment_status, "value") else str(o.payment_status),
            "total": o.total_amount or Decimal("0"),
            "buyer_id": o.user_id, "buyer_username": username,
            "buyer_email": emails.get(UUID(str(o.user_id))) if o.user_id else None,
            "items": [
                {
                    "look_id": i.look_id,
                    "name": i.look.name if i.look else "Peça",
                    "store_name": lojas.get(i.look.seller_id) if i.look else None,
                    "quantity": i.quantity, "unit_price": i.unit_price, "subtotal": i.subtotal,
                    "fulfillment_status": i.fulfillment_status,
                }
                for i in o.items
            ],
        })
    return {"items": itens, "total": total}


# ── categorias ────────────────────────────────────────────────────────────────

def slugify(nome: str) -> str:
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base[:50] or "categoria"


async def listar_categorias(db: AsyncSession) -> list[dict]:
    n = select(Look.category_id, func.count().label("n")).group_by(Look.category_id).subquery()
    linhas = (
        await db.execute(
            select(Category, func.coalesce(n.c.n, 0))
            .outerjoin(n, n.c.category_id == Category.id)
            .order_by(Category.sort_order, Category.name)
        )
    ).all()
    return [
        {"id": c.id, "name": c.name, "slug": c.slug, "image_url": c.image_url,
         "is_active": c.is_active, "sort_order": c.sort_order, "looks_count": int(k or 0)}
        for c, k in linhas
    ]


async def _categoria_saida(db: AsyncSession, cat_id: UUID) -> dict:
    return next(c for c in await listar_categorias(db) if c["id"] == cat_id)


async def criar_categoria(db: AsyncSession, admin_id: UUID, dados: CategoriaCreate) -> dict:
    slug = slugify(dados.name)
    if (await db.execute(select(Category.id).where(Category.slug == slug))).first():
        raise HTTPException(status_code=409, detail="Já existe uma categoria com esse nome.")
    c = Category(name=dados.name.strip(), slug=slug, image_url=dados.image_url, sort_order=dados.sort_order)
    db.add(c)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Já existe uma categoria com esse nome.")
    logger.info("ADMIN %s criou categoria %s", admin_id, slug)
    return await _categoria_saida(db, c.id)


async def atualizar_categoria(db: AsyncSession, admin_id: UUID, cat_id: UUID, dados: CategoriaUpdate) -> dict:
    c = (await db.execute(select(Category).where(Category.id == cat_id))).scalar_one_or_none()
    if not c:
        raise _404("Categoria")
    mudancas = dados.model_dump(exclude_unset=True)
    if mudancas.get("name") is not None:
        c.name = mudancas["name"].strip()  # o slug fica: links e filtros já usam ele
    if "image_url" in mudancas:
        c.image_url = mudancas["image_url"] or None
    if mudancas.get("is_active") is not None:
        c.is_active = mudancas["is_active"]
    if mudancas.get("sort_order") is not None:
        c.sort_order = mudancas["sort_order"]
    await db.commit()
    logger.info("ADMIN %s atualizou categoria %s: %s", admin_id, cat_id, sorted(mudancas))
    return await _categoria_saida(db, cat_id)


async def apagar_categoria(db: AsyncSession, admin_id: UUID, cat_id: UUID, confirm: str | None) -> None:
    exigir_confirmacao(confirm)
    c = (await db.execute(select(Category).where(Category.id == cat_id))).scalar_one_or_none()
    if not c:
        raise _404("Categoria")
    if (await db.execute(select(Look.id).where(Look.category_id == cat_id).limit(1))).first():
        raise HTTPException(status_code=409, detail="Há peças nesta categoria. Desative a categoria em vez de apagar.")
    await db.execute(delete(Category).where(Category.id == cat_id))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Categoria em uso. Desative-a em vez de apagar.")
    logger.info("ADMIN %s apagou categoria %s", admin_id, cat_id)


# ── denúncias ─────────────────────────────────────────────────────────────────

async def listar_denuncias(db: AsyncSession, status_: str | None, limit: int, offset: int) -> dict:
    filtro = select(Report.id)
    if status_:
        filtro = filtro.where(Report.status == status_)
    total = int((await db.execute(select(func.count()).select_from(filtro.subquery()))).scalar() or 0)
    linhas = (
        await db.execute(
            select(Report, Profile.username)
            .outerjoin(Profile, Profile.id == Report.reporter_id)
            .where(Report.id.in_(filtro))
            .order_by(Report.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    # Nome legível do alvo (perfil, loja ou peça).
    alvos: dict[str, set] = {"profile": set(), "seller": set(), "look": set()}
    for r, _ in linhas:
        alvos.setdefault(r.target_type, set()).add(r.target_id)
    nomes: dict = {}
    if alvos["profile"]:
        nomes.update(dict((await db.execute(select(Profile.id, Profile.username).where(Profile.id.in_(alvos["profile"])))).all()))
    if alvos["seller"]:
        nomes.update(dict((await db.execute(select(Seller.id, Seller.store_name).where(Seller.id.in_(alvos["seller"])))).all()))
    if alvos["look"]:
        nomes.update(dict((await db.execute(select(Look.id, Look.name).where(Look.id.in_(alvos["look"])))).all()))
    itens = [
        {
            "id": r.id, "target_type": r.target_type, "target_id": r.target_id,
            "target_label": nomes.get(r.target_id), "reason": r.reason, "description": r.description,
            "contact_email": r.contact_email, "status": r.status, "created_at": r.created_at,
            "reporter_username": username,
        }
        for r, username in linhas
    ]
    return {"items": itens, "total": total}


async def atualizar_denuncia(db: AsyncSession, admin_id: UUID, report_id: UUID, dados: DenunciaUpdate) -> dict:
    r = (await db.execute(select(Report).where(Report.id == report_id))).scalar_one_or_none()
    if not r:
        raise _404("Denúncia")
    r.status = dados.status
    r.resolved_at = func.now() if dados.status in ("resolved", "rejected") else None
    await db.commit()
    logger.info("ADMIN %s marcou denúncia %s como %s", admin_id, report_id, dados.status)
    await db.refresh(r)
    return {
        "id": r.id, "target_type": r.target_type, "target_id": r.target_id, "target_label": None,
        "reason": r.reason, "description": r.description, "contact_email": r.contact_email,
        "status": r.status, "created_at": r.created_at, "reporter_username": None,
    }
