"""Gestão de estoque da loja: itens, movimentações, vendas a enviar e métricas.

Pensado para o brechó pequeno que vende no app E fora dele (Instagram, WhatsApp,
loja física): toda mudança de estoque vira uma linha em `stock_movements`, e as
vendas externas registradas aqui entram no faturamento junto com as do app.

Fontes de verdade:
  * vendas no app  -> `orders`/`order_items` com pagamento aprovado (o dinheiro);
  * vendas externas -> `stock_movements` com kind = 'venda_externa';
  * estoque         -> `looks.stock_quantity` / `looks.reserved_quantity`.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import and_, cast, func, literal, or_, select, union_all
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.ext.asyncio import AsyncSession

from model.look import Look
from model.orders import Order, OrderStatus, PaymentStatus
from model.orders_items import OrderItems
from model.profile import Profile
from model.seller import Seller, StoreMember
from model.signal import LookView
from model.stock_movement import StockMovement
from schemas.inventory import EnvioUpdate, MovimentoCreate, OrdemItens, Situacao
from service import platform_fee_service as taxa_svc

logger = logging.getLogger(__name__)

ESTOQUE_BAIXO = 3  # igual a ESTOQUE_BAIXO do front (src/utils/loja.ts)
DIAS_PARADO = 30
FUSO = ZoneInfo("America/Sao_Paulo")


# ── loja do usuário ───────────────────────────────────────────────────────────

async def minha_loja(db: AsyncSession, user_id: UUID) -> Seller:
    """Loja que o usuário gerencia: a dele (dono) ou uma em que é owner/manager."""
    seller = (
        await db.execute(select(Seller).where(Seller.owner_profile_id == user_id))
    ).scalar_one_or_none()
    if seller:
        return seller
    seller = (
        await db.execute(
            select(Seller)
            .join(StoreMember, StoreMember.seller_id == Seller.id)
            .where(StoreMember.profile_id == user_id, StoreMember.role.in_(["owner", "manager"]))
            .limit(1)
        )
    ).scalar_one_or_none()
    if not seller:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas lojas têm gestão de estoque")
    return seller


async def _peca_da_loja(db: AsyncSession, seller_id: UUID, look_id: UUID, travar: bool = False) -> Look:
    q = select(Look).where(Look.id == look_id, Look.seller_id == seller_id)
    if travar:
        q = q.with_for_update()
    look = (await db.execute(q)).scalar_one_or_none()
    if not look:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Peça não encontrada na sua loja")
    return look


# ── regra das movimentações (pura, sem banco) ─────────────────────────────────

@dataclass(frozen=True)
class Efeito:
    novo_estoque: int
    nova_reserva: int
    quantidade: int  # o que vai para stock_movements.quantity (com sinal)


def aplicar_movimento(estoque: int, reservado: int, tipo: str, qtd: int) -> Efeito:
    """Calcula o novo estoque/reserva de uma movimentação ou levanta 400.

    Reserva nunca passa do estoque: quando o estoque cai (venda, perda, ajuste),
    a reserva é cortada junto. Vender uma peça reservada é o caso comum
    (separou no Instagram, a cliente pagou), por isso a venda externa pode
    consumir unidades reservadas.
    """
    estoque, reservado = max(estoque or 0, 0), max(reservado or 0, 0)
    disponivel = max(estoque - reservado, 0)

    def _erro(msg: str) -> HTTPException:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    if tipo in ("entrada", "devolucao"):
        novo = estoque + qtd
        return Efeito(novo, reservado, qtd)
    if tipo in ("venda_externa", "perda"):
        if qtd > estoque:
            raise _erro(f"Só há {estoque} em estoque.")
        novo = estoque - qtd
        return Efeito(novo, min(reservado, novo), -qtd)
    if tipo == "ajuste":
        if qtd == estoque:
            raise _erro(f"O estoque já é {estoque}.")
        return Efeito(qtd, min(reservado, qtd), qtd - estoque)
    if tipo == "reserva":
        if qtd > disponivel:
            raise _erro(f"Só há {disponivel} disponível para reservar.")
        return Efeito(estoque, reservado + qtd, qtd)
    if tipo == "liberacao":
        if qtd > reservado:
            raise _erro(f"Só há {reservado} reservado.")
        return Efeito(estoque, reservado - qtd, -qtd)
    raise _erro("Tipo de movimentação inválido.")


def novo_movimento(
    look: Look,
    kind: str,
    quantidade: int,
    *,
    user_id: UUID | None = None,
    unit_price: Decimal | None = None,
    channel: str | None = None,
    note: str | None = None,
    order_id: UUID | None = None,
) -> StockMovement:
    """Linha do histórico com a foto do estado DEPOIS da mudança (o chamador já
    alterou o `look`). Não grava: o chamador faz `db.add` + commit junto com a
    mudança no estoque, na mesma transação."""
    return StockMovement(
        seller_id=look.seller_id,
        look_id=look.id,
        look_name=look.name,
        kind=kind,
        quantity=quantidade,
        stock_after=look.stock_quantity or 0,
        reserved_after=look.reserved_quantity or 0,
        unit_price=unit_price,
        unit_cost=look.cost_price,
        channel=channel,
        note=note,
        order_id=order_id,
        created_by=user_id,
    )


async def registrar_movimento(
    db: AsyncSession, user_id: UUID, look_id: UUID, dados: MovimentoCreate
) -> tuple[StockMovement, Look]:
    seller = await minha_loja(db, user_id)
    look = await _peca_da_loja(db, seller.id, look_id, travar=True)
    ef = aplicar_movimento(look.stock_quantity, look.reserved_quantity, dados.kind, dados.quantity)
    look.stock_quantity = ef.novo_estoque
    look.reserved_quantity = ef.nova_reserva

    preco = dados.unit_price
    if dados.kind == "venda_externa" and preco is None:
        preco = look.price  # vendeu pelo preço da etiqueta
    mov = novo_movimento(
        look, dados.kind, ef.quantidade, user_id=user_id,
        unit_price=preco if dados.kind == "venda_externa" else None,
        channel=dados.channel if dados.kind == "venda_externa" else None,
        note=dados.note,
    )
    db.add(mov)
    await db.commit()
    await db.refresh(look)
    await db.refresh(mov)
    return mov, look


async def alterar_status(db: AsyncSession, user_id: UUID, look_id: UUID, novo: str) -> Look:
    """Pausar (draft: sai do feed e do checkout) ou reativar. Peça em revisão ou
    removida pela moderação não muda por aqui."""
    seller = await minha_loja(db, user_id)
    look = await _peca_da_loja(db, seller.id, look_id, travar=True)
    if look.status not in ("active", "draft"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Essa peça está em revisão ou foi removida pela moderação.",
        )
    look.status = novo
    await db.commit()
    await db.refresh(look)
    return look


async def listar_movimentos(
    db: AsyncSession,
    user_id: UUID,
    look_id: UUID | None,
    kind: str | None,
    limit: int,
    cursor: datetime | None,
) -> dict:
    seller = await minha_loja(db, user_id)
    q = select(StockMovement).where(StockMovement.seller_id == seller.id)
    if look_id is not None:
        q = q.where(StockMovement.look_id == look_id)
    if kind:
        q = q.where(StockMovement.kind == kind)
    if cursor is not None:
        q = q.where(StockMovement.created_at < cursor)
    q = q.order_by(StockMovement.created_at.desc()).limit(limit)
    itens = list((await db.execute(q)).scalars().all())
    prox = itens[-1].created_at.isoformat() if len(itens) == limit else None
    return {"items": itens, "next_cursor": prox}


# ── vendas (app + externas) ───────────────────────────────────────────────────

def _quando_pedido():
    # orders.created_at é `timestamp` sem fuso (gravado em UTC pelo now() do
    # Supabase); vira timestamptz para casar com stock_movements no UNION.
    return cast(Order.created_at, TIMESTAMP(timezone=True))


def _vendas(seller_id: UUID):
    """Todas as vendas da loja, uma linha por peça vendida: (look_id, units,
    valor, quando, canal, custo_unit)."""
    app = (
        select(
            OrderItems.look_id.label("look_id"),
            OrderItems.quantity.label("units"),
            OrderItems.subtotal.label("valor"),
            _quando_pedido().label("quando"),
            literal("app").label("canal"),
            Look.cost_price.label("custo_unit"),
        )
        .join(Order, Order.id == OrderItems.order_id)
        .join(Look, Look.id == OrderItems.look_id)
        .where(Look.seller_id == seller_id, Order.payment_status == PaymentStatus.APPROVED)
    )
    externa = select(
        StockMovement.look_id.label("look_id"),
        (-StockMovement.quantity).label("units"),
        (func.coalesce(StockMovement.unit_price, 0) * -StockMovement.quantity).label("valor"),
        StockMovement.created_at.label("quando"),
        func.coalesce(StockMovement.channel, "outro").label("canal"),
        StockMovement.unit_cost.label("custo_unit"),
    ).where(StockMovement.seller_id == seller_id, StockMovement.kind == "venda_externa")
    return union_all(app, externa).subquery("vendas")


def _agregado_por_peca(vendas):
    return (
        select(
            vendas.c.look_id,
            func.sum(vendas.c.units).label("units"),
            func.sum(vendas.c.valor).label("valor"),
            func.max(vendas.c.quando).label("ultima"),
            func.min(vendas.c.quando).label("primeira"),
        )
        .where(vendas.c.look_id.is_not(None))
        .group_by(vendas.c.look_id)
        .subquery("agg")
    )


# ── itens ─────────────────────────────────────────────────────────────────────

def _condicoes_situacao(agg, agora: datetime):
    disponivel = Look.stock_quantity - Look.reserved_quantity
    ref = func.coalesce(agg.c.ultima, Look.created_at)
    return {
        "todos": None,
        "disponivel": disponivel > 0,
        "acabando": and_(disponivel > 0, disponivel <= ESTOQUE_BAIXO),
        "esgotado": Look.stock_quantity <= 0,
        "reservado": Look.reserved_quantity > 0,
        "pausado": Look.status == "draft",
        "parado": and_(
            Look.status == "active",
            Look.stock_quantity > 0,
            ref < agora - timedelta(days=DIAS_PARADO),
        ),
    }


async def _contagens(db, seller_id, agg, conds, q, category_id) -> dict[str, int]:
    colunas = [
        (func.count().filter(cond) if cond is not None else func.count()).label(nome)
        for nome, cond in conds.items()
    ]
    consulta = select(*colunas).select_from(Look).outerjoin(agg, agg.c.look_id == Look.id).where(
        Look.seller_id == seller_id
    )
    if q:
        termo = f"%{q.strip()}%"
        consulta = consulta.where(or_(Look.name.ilike(termo), Look.description.ilike(termo), Look.brand.ilike(termo)))
    if category_id is not None:
        consulta = consulta.where(Look.category_id == category_id)
    linha = (await db.execute(consulta)).one()
    return {nome: int(linha._mapping[nome] or 0) for nome in conds}


def _ordem_itens(sort: str, agg):
    ref = func.coalesce(agg.c.ultima, Look.created_at)
    return {
        "recentes": [Look.created_at.desc(), Look.id],
        "antigos": [Look.created_at.asc(), Look.id],
        "nome": [func.lower(Look.name).asc(), Look.id],
        "preco_asc": [Look.price.asc().nulls_last(), Look.id],
        "preco_desc": [Look.price.desc().nulls_last(), Look.id],
        "estoque_asc": [(Look.stock_quantity - Look.reserved_quantity).asc(), Look.id],
        "estoque_desc": [(Look.stock_quantity - Look.reserved_quantity).desc(), Look.id],
        "mais_vendidos": [func.coalesce(agg.c.units, 0).desc(), Look.created_at.desc(), Look.id],
        "parados": [ref.asc(), Look.id],
    }[sort]


async def listar_itens(
    db: AsyncSession,
    user_id: UUID,
    *,
    q: str | None = None,
    situacao: Situacao = "todos",
    category_id: UUID | None = None,
    sort: OrdemItens = "recentes",
    limit: int = 30,
    offset: int = 0,
) -> dict:
    seller = await minha_loja(db, user_id)
    agora = datetime.now(timezone.utc)
    agg = _agregado_por_peca(_vendas(seller.id))
    conds = _condicoes_situacao(agg, agora)

    base = select(Look, agg.c.units, agg.c.valor, agg.c.ultima).outerjoin(agg, agg.c.look_id == Look.id).where(
        Look.seller_id == seller.id
    )
    if q:
        termo = f"%{q.strip()}%"
        base = base.where(or_(Look.name.ilike(termo), Look.description.ilike(termo), Look.brand.ilike(termo)))
    if category_id is not None:
        base = base.where(Look.category_id == category_id)

    # Contagem por situação sobre o mesmo recorte (busca/categoria), para os chips.
    counts = await _contagens(db, seller.id, agg, conds, q, category_id)

    filtrada = base
    if conds.get(situacao) is not None:
        filtrada = filtrada.where(conds[situacao])
    total = counts.get(situacao, 0)

    linhas = (
        await db.execute(filtrada.order_by(*_ordem_itens(sort, agg)).limit(limit).offset(offset))
    ).all()
    itens = []
    for look, units, valor, ultima in linhas:
        ref = ultima or look.created_at
        itens.append(
            {
                **{c.name: getattr(look, c.key) for c in Look.__table__.columns},
                "available_quantity": max((look.stock_quantity or 0) - (look.reserved_quantity or 0), 0),
                "units_sold": int(units or 0),
                "revenue": valor or Decimal("0"),
                "last_sale_at": ultima,
                "days_without_sale": (agora - ref).days if ref else None,
            }
        )
    proximo = offset + limit if offset + limit < total else None
    return {"items": itens, "total": total, "next_offset": proximo, "counts": counts}


# ── vendas do app: o que enviar ───────────────────────────────────────────────

_ORDEM_ENVIO = {"pending": 0, "shipped": 1, "delivered": 2}


def _envio_do_conjunto(estados: list[str]) -> str:
    """Situação de um grupo de itens = a do item mais atrasado."""
    if not estados:
        return "pending"
    return min(estados, key=lambda e: _ORDEM_ENVIO.get(e, 0))


async def listar_vendas_app(db: AsyncSession, user_id: UUID, situacao: str, limit: int = 100) -> dict:
    """Pedidos PAGOS que têm peças desta loja — só as peças dela, com o endereço
    de entrega. Pedido pendente de pagamento não aparece (não há o que enviar)."""
    seller = await minha_loja(db, user_id)
    linhas = (
        await db.execute(
            select(OrderItems, Order, Look, Profile.full_name)
            .join(Order, Order.id == OrderItems.order_id)
            .join(Look, Look.id == OrderItems.look_id)
            .outerjoin(Profile, Profile.id == Order.user_id)
            .where(Look.seller_id == seller.id, Order.payment_status == PaymentStatus.APPROVED)
            .order_by(Order.created_at.desc())
            .limit(1000)
        )
    ).all()

    regra = await taxa_svc.regra_atual(db)
    pedidos: dict[UUID, dict] = {}
    for item, pedido, look, nome in linhas:
        t = taxa_svc.taxa_do_item(item, regra, seller.created_at, pedido.created_at)
        p = pedidos.setdefault(
            pedido.id,
            {
                "order_id": pedido.id,
                "created_at": pedido.created_at,
                "buyer_name": nome,
                "shipping_address": pedido.shipping_address or {},
                "payment_status": pedido.payment_status.value,
                "order_status": pedido.status.value,
                "items": [],
                "total": Decimal("0"),
                "fee_total": Decimal("0"),
                "mp_fee_total": Decimal("0"),
                "net_total": Decimal("0"),
            },
        )
        p["items"].append(
            {
                "order_item_id": item.id,
                "look_id": item.look_id,
                "name": look.name,
                "photo": (look.photos or [""])[0],
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "subtotal": item.subtotal,
                "fulfillment_status": item.fulfillment_status or "pending",
                "tracking_code": item.tracking_code,
                "shipped_at": item.shipped_at,
                "platform_fee_percent": t.percent,
                "platform_fee_amount": t.taxa,
                "mp_fee_amount": t.tarifa_mp,
                "seller_net_amount": t.liquido,
                "fee_rule": t.fase,
                "payout_status": item.payout_status or "pending",
            }
        )
        p["total"] += item.subtotal or Decimal("0")
        p["fee_total"] += t.taxa
        p["mp_fee_total"] += t.tarifa_mp or Decimal("0")
        p["net_total"] += t.liquido

    todos = list(pedidos.values())
    for p in todos:
        p["fulfillment_status"] = _envio_do_conjunto([i["fulfillment_status"] for i in p["items"]])
    counts = {e: sum(1 for p in todos if p["fulfillment_status"] == e) for e in _ORDEM_ENVIO}
    counts["todos"] = len(todos)
    if situacao != "todos":
        todos = [p for p in todos if p["fulfillment_status"] == situacao]
    return {"items": todos[:limit], "counts": counts}


async def atualizar_envio(db: AsyncSession, user_id: UUID, order_id: UUID, dados: EnvioUpdate) -> dict:
    """Marca as peças DESTA loja no pedido como enviadas/entregues. Quando todas
    as peças do pedido (de todas as lojas) chegam lá, o pedido acompanha — é o
    que a pessoa que comprou vê em "Meus pedidos"."""
    seller = await minha_loja(db, user_id)
    pedido = (
        await db.execute(select(Order).where(Order.id == order_id).with_for_update())
    ).scalar_one_or_none()
    if not pedido:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado")
    if pedido.payment_status != PaymentStatus.APPROVED or pedido.status == OrderStatus.CANCELED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esse pedido não está pago.")

    itens = (
        await db.execute(
            select(OrderItems, Look.seller_id)
            .join(Look, Look.id == OrderItems.look_id)
            .where(OrderItems.order_id == order_id)
            .with_for_update(of=OrderItems)
        )
    ).all()
    meus = [i for i, dono in itens if dono == seller.id]
    if not meus:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado")

    agora = datetime.now(timezone.utc)
    for item in meus:
        item.fulfillment_status = dados.fulfillment_status
        if item.shipped_at is None:
            item.shipped_at = agora
        if dados.tracking_code is not None:
            item.tracking_code = dados.tracking_code.strip() or None

    geral = _envio_do_conjunto([i.fulfillment_status or "pending" for i, _ in itens])
    if geral == "delivered":
        pedido.status = OrderStatus.DELIVERED
    elif geral == "shipped":
        pedido.status = OrderStatus.SHIPPED
    await db.commit()
    return {"order_id": order_id, "fulfillment_status": dados.fulfillment_status, "order_status": pedido.status.value}


# ── métricas ──────────────────────────────────────────────────────────────────

def inicio_do_periodo(dias: int, agora: datetime | None = None) -> datetime:
    """Meia-noite (horário de Brasília) de `dias - 1` dias atrás: "últimos 7 dias"
    inclui hoje inteiro e os 6 dias anteriores."""
    agora = (agora or datetime.now(timezone.utc)).astimezone(FUSO)
    dia = agora.date() - timedelta(days=dias - 1)
    return datetime.combine(dia, time.min, tzinfo=FUSO).astimezone(timezone.utc)


def serie_diaria(pontos: dict, inicio: datetime, dias: int) -> list[dict]:
    """Completa com zero os dias sem venda (o gráfico precisa de todos)."""
    primeiro = inicio.astimezone(FUSO).date()
    saida = []
    for i in range(dias):
        d = primeiro + timedelta(days=i)
        valor, units = pontos.get(d, (Decimal("0"), 0))
        saida.append({"day": d, "revenue": valor, "units": int(units)})
    return saida


async def metricas(db: AsyncSession, user_id: UUID, dias: int) -> dict:
    seller = await minha_loja(db, user_id)
    agora = datetime.now(timezone.utc)
    inicio = inicio_do_periodo(dias, agora)
    inicio_ant = inicio - timedelta(days=dias)
    vendas = _vendas(seller.id)

    # 1. Vendas no período e no período anterior (para comparar)
    def _soma(desde, ate):
        return select(
            func.coalesce(func.sum(vendas.c.valor), 0),
            func.coalesce(func.sum(vendas.c.units), 0),
        ).where(vendas.c.quando >= desde, vendas.c.quando < ate)

    receita, unidades = (await db.execute(_soma(inicio, agora + timedelta(minutes=1)))).one()
    receita_ant, unidades_ant = (await db.execute(_soma(inicio_ant, inicio))).one()

    # Nº de vendas: pedidos distintos do app + cada venda externa registrada.
    n_app = (
        await db.execute(
            select(func.count(func.distinct(Order.id)))
            .select_from(OrderItems)
            .join(Order, Order.id == OrderItems.order_id)
            .join(Look, Look.id == OrderItems.look_id)
            .where(
                Look.seller_id == seller.id,
                Order.payment_status == PaymentStatus.APPROVED,
                _quando_pedido() >= inicio,
            )
        )
    ).scalar() or 0
    n_ext = (
        await db.execute(
            select(func.count()).where(
                StockMovement.seller_id == seller.id,
                StockMovement.kind == "venda_externa",
                StockMovement.created_at >= inicio,
            )
        )
    ).scalar() or 0
    n_vendas = int(n_app) + int(n_ext)

    # 2. Por canal e lucro bruto (só onde há custo)
    por_canal = {
        canal: valor or Decimal("0")
        for canal, valor in (
            await db.execute(
                select(vendas.c.canal, func.sum(vendas.c.valor)).where(vendas.c.quando >= inicio).group_by(vendas.c.canal)
            )
        ).all()
    }
    receita_com_custo, custo_total = (
        await db.execute(
            select(
                func.coalesce(func.sum(vendas.c.valor), 0),
                func.coalesce(func.sum(vendas.c.custo_unit * vendas.c.units), 0),
            ).where(vendas.c.quando >= inicio, vendas.c.custo_unit.is_not(None))
        )
    ).one()

    # 2b. Taxa da plataforma sobre as vendas do app no período (congelada em
    # cada peça; peça sem taxa gravada conta como 0%, que é o caso da demo).
    taxas_app, tarifas_mp = (
        await db.execute(
            select(
                func.coalesce(func.sum(OrderItems.platform_fee_amount), 0),
                func.coalesce(func.sum(OrderItems.mp_fee_amount), 0),
            )
            .join(Order, Order.id == OrderItems.order_id)
            .join(Look, Look.id == OrderItems.look_id)
            .where(
                Look.seller_id == seller.id,
                Order.payment_status == PaymentStatus.APPROVED,
                _quando_pedido() >= inicio,
            )
        )
    ).one()
    taxa_atual = taxa_svc.taxa_da_loja(await taxa_svc.regra_atual(db), seller.created_at, agora)

    # 3. Série diária (dia no horário de Brasília)
    dia_local = func.date(func.timezone("America/Sao_Paulo", vendas.c.quando))
    pontos = {
        d: (v or Decimal("0"), u or 0)
        for d, v, u in (
            await db.execute(
                select(dia_local, func.sum(vendas.c.valor), func.sum(vendas.c.units))
                .where(vendas.c.quando >= inicio)
                .group_by(dia_local)
            )
        ).all()
    }

    # 4. Estoque agora
    disponivel = Look.stock_quantity - Look.reserved_quantity
    est = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(Look.status == "active"),
                func.count().filter(Look.status == "draft"),
                func.coalesce(func.sum(Look.stock_quantity), 0),
                func.coalesce(func.sum(Look.reserved_quantity), 0),
                func.count().filter(Look.stock_quantity <= 0),
                func.count().filter(and_(disponivel > 0, disponivel <= ESTOQUE_BAIXO)),
                func.coalesce(func.sum(Look.price * Look.stock_quantity), 0),
                func.coalesce(func.sum(Look.cost_price * Look.stock_quantity), 0),
                func.count().filter(and_(Look.cost_price.is_(None), Look.stock_quantity > 0)),
                func.coalesce(func.sum(Look.likes_count), 0),
                func.coalesce(func.sum(Look.saves_count), 0),
            ).where(Look.seller_id == seller.id, Look.status.in_(["active", "draft", "under_review"]))
        )
    ).one()
    (pecas, ativas, pausadas, unid_estoque, unid_reserv, esgotadas, acabando,
     valor_venda, valor_custo, sem_custo, curtidas, salvos) = est

    # 5. Giro: mais vendidas, tempo até vender, paradas
    agg = _agregado_por_peca(vendas)
    vendidas_periodo = (
        select(vendas.c.look_id, func.sum(vendas.c.units).label("u"), func.sum(vendas.c.valor).label("v"))
        .where(vendas.c.quando >= inicio, vendas.c.look_id.is_not(None))
        .group_by(vendas.c.look_id)
        .subquery("vp")
    )
    top = (
        await db.execute(
            select(Look.id, Look.name, Look.photos, vendidas_periodo.c.u, vendidas_periodo.c.v)
            .join(vendidas_periodo, vendidas_periodo.c.look_id == Look.id)
            .order_by(vendidas_periodo.c.u.desc(), vendidas_periodo.c.v.desc())
            .limit(5)
        )
    ).all()
    dias_ate_vender = (
        await db.execute(
            select(func.avg(func.extract("epoch", agg.c.primeira - Look.created_at) / 86400.0))
            .join(agg, agg.c.look_id == Look.id)
            .where(Look.seller_id == seller.id, agg.c.primeira >= inicio)
        )
    ).scalar()

    ref = func.coalesce(agg.c.ultima, Look.created_at)
    cond_parado = and_(
        Look.seller_id == seller.id,
        Look.status == "active",
        Look.stock_quantity > 0,
        ref < agora - timedelta(days=DIAS_PARADO),
    )
    n_parados = (
        await db.execute(select(func.count()).select_from(Look).outerjoin(agg, agg.c.look_id == Look.id).where(cond_parado))
    ).scalar() or 0
    parados = (
        await db.execute(
            select(Look.id, Look.name, Look.photos, ref.label("ref"))
            .outerjoin(agg, agg.c.look_id == Look.id)
            .where(cond_parado)
            .order_by(ref.asc())
            .limit(5)
        )
    ).all()

    a_enviar = (
        await db.execute(
            select(func.count(func.distinct(Order.id)))
            .select_from(OrderItems)
            .join(Order, Order.id == OrderItems.order_id)
            .join(Look, Look.id == OrderItems.look_id)
            .where(
                Look.seller_id == seller.id,
                Order.payment_status == PaymentStatus.APPROVED,
                Order.status != OrderStatus.CANCELED,
                OrderItems.fulfillment_status == "pending",
            )
        )
    ).scalar() or 0

    # 6. Visualizações (swipes) — por último e protegido: look_views é a maior
    # tabela do banco; se demorar ou falhar, as métricas saem sem ela.
    views, mais_vistas = None, []
    try:
        async with db.begin_nested():
            await db.execute(select(func.set_config("statement_timeout", "4000", True)))
            vistas = (
                select(LookView.look_id, func.count().label("n"))
                .join(Look, Look.id == LookView.look_id)
                .where(Look.seller_id == seller.id, LookView.created_at >= inicio)
                .group_by(LookView.look_id)
                .subquery("vistas")
            )
            views = int((await db.execute(select(func.coalesce(func.sum(vistas.c.n), 0)))).scalar() or 0)
            mais_vistas = (
                await db.execute(
                    select(Look.id, Look.name, Look.photos, vistas.c.n)
                    .join(vistas, vistas.c.look_id == Look.id)
                    .order_by(vistas.c.n.desc())
                    .limit(5)
                )
            ).all()
    except Exception:  # noqa: BLE001
        logger.warning("Métricas sem visualizações (consulta a look_views falhou ou demorou)", exc_info=True)
        views, mais_vistas = None, []

    receita = Decimal(receita or 0)
    unidades = int(unidades or 0)
    vendidas_mais_estoque = unidades + int(unid_estoque or 0)
    return {
        "period_days": dias,
        "since": inicio,
        "revenue": receita,
        "revenue_prev": Decimal(receita_ant or 0),
        "units_sold": unidades,
        "units_sold_prev": int(unidades_ant or 0),
        "sales_count": n_vendas,
        "avg_ticket": (receita / n_vendas).quantize(Decimal("0.01")) if n_vendas else None,
        "revenue_app": por_canal.get("app", Decimal("0")),
        "revenue_external": sum((v for c, v in por_canal.items() if c != "app"), Decimal("0")),
        "revenue_by_channel": por_canal,
        "platform_fees": Decimal(taxas_app or 0),
        "mp_fees": Decimal(tarifas_mp or 0),
        "net_revenue_app": por_canal.get("app", Decimal("0")) - Decimal(taxas_app or 0) - Decimal(tarifas_mp or 0),
        "platform_fee": taxa_atual,
        "gross_profit": (Decimal(receita_com_custo) - Decimal(custo_total)) if receita_com_custo else None,
        "revenue_with_cost": Decimal(receita_com_custo or 0),
        "series": serie_diaria(pontos, inicio, dias),
        "pieces_total": int(pecas or 0),
        "pieces_active": int(ativas or 0),
        "pieces_paused": int(pausadas or 0),
        "units_in_stock": int(unid_estoque or 0),
        "units_reserved": int(unid_reserv or 0),
        "out_of_stock": int(esgotadas or 0),
        "low_stock": int(acabando or 0),
        "stock_value_price": Decimal(valor_venda or 0),
        "stock_value_cost": Decimal(valor_custo or 0),
        "pieces_without_cost": int(sem_custo or 0),
        "sell_through_pct": round(unidades * 100 / vendidas_mais_estoque, 1) if vendidas_mais_estoque else None,
        "avg_days_to_sell": round(float(dias_ate_vender), 1) if dias_ate_vender is not None else None,
        "stale_count": int(n_parados),
        "stale_days": DIAS_PARADO,
        "views": views,
        "likes": int(curtidas or 0),
        "saves": int(salvos or 0),
        "to_ship": int(a_enviar),
        "top_sold": [
            {"look_id": i, "name": n, "photo": (f or [None])[0], "value": int(u or 0), "detail": str(Decimal(v or 0))}
            for i, n, f, u, v in top
        ],
        "top_viewed": [
            {"look_id": i, "name": n, "photo": (f or [None])[0], "value": int(c or 0)} for i, n, f, c in mais_vistas
        ],
        "stale": [
            {
                "look_id": i, "name": n, "photo": (f or [None])[0],
                "value": (agora - r).days if r else 0,
                "detail": "dias sem vender",
            }
            for i, n, f, r in parados
        ],
    }
