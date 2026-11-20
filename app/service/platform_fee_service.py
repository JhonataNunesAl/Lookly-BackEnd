"""Taxa da plataforma sobre as peças vendidas no app.

Regra (configurável em `platform_fee_config`, uma linha só):
  1. Demo (sem data de fim, ou antes dela): 0% para todas as lojas. A loja
     recebe o valor inteiro da peça.
  2. Depois da demo, cada loja tem `grace_days` (60) dias a 0%, contados do que
     vier por último: o fim da demo ou o cadastro da loja. Assim quem entrou na
     demo também ganha os 60 dias depois que ela acaba.
  3. Passada a carência: `fee_percent` (11%).

A taxa é calculada e CONGELADA em cada `order_items` quando o pagamento é
aprovado (webhook). Mudar a regra depois nunca altera vendas passadas.

Hoje todo pagamento cai na conta Mercado Pago da plataforma (Checkout Pro com
um só Access Token), e é ela quem paga a tarifa do MP. Por isso o repasse é:

    seller_net_amount = subtotal - taxa da plataforma - parte da peça na tarifa do MP

(a tarifa do pagamento é rateada pelas peças, proporcional ao subtotal).
`payout_status` marca se o repasse já foi feito.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from model.look import Look
from model.orders import Order, PaymentStatus
from model.orders_items import OrderItems
from model.platform_fee import PlatformFeeConfig
from model.seller import Seller
from schemas.platform_fee import PlatformFeeConfigUpdate

logger = logging.getLogger(__name__)

CENTAVO = Decimal("0.01")
PADRAO_PERCENT = Decimal("11")
PADRAO_CARENCIA = 60


@dataclass(frozen=True)
class Regra:
    demo_ends_at: datetime | None
    fee_percent: Decimal
    grace_days: int


@dataclass(frozen=True)
class Taxa:
    percent: Decimal
    fase: str  # demo | carencia | padrao
    fim_carencia: datetime | None


REGRA_PADRAO = Regra(demo_ends_at=None, fee_percent=PADRAO_PERCENT, grace_days=PADRAO_CARENCIA)


def _utc(d: datetime | None) -> datetime | None:
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def taxa_em(regra: Regra, loja_criada_em: datetime | None, quando: datetime) -> Taxa:
    """Taxa que vale para uma venda da loja no instante `quando`. Função pura."""
    quando = _utc(quando)
    fim_demo = _utc(regra.demo_ends_at)
    if fim_demo is None or quando < fim_demo:
        return Taxa(Decimal("0"), "demo", None)
    inicio = max(fim_demo, _utc(loja_criada_em) or fim_demo)
    fim_carencia = inicio + timedelta(days=regra.grace_days)
    if quando < fim_carencia:
        return Taxa(Decimal("0"), "carencia", fim_carencia)
    return Taxa(Decimal(regra.fee_percent), "padrao", fim_carencia)


def dividir(subtotal: Decimal, percent: Decimal, tarifa_mp: Decimal | None = None) -> tuple[Decimal, Decimal]:
    """(taxa da plataforma, líquido da loja), em centavos. A taxa arredonda meio
    centavo para cima; o líquido desconta também a parte da tarifa do MP."""
    subtotal = Decimal(subtotal)
    taxa = (subtotal * Decimal(percent) / 100).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    return taxa, subtotal - taxa - Decimal(tarifa_mp or 0)


def ratear(total: Decimal, pesos: list[Decimal]) -> list[Decimal]:
    """Divide `total` em centavos proporcional aos `pesos`; a sobra de
    arredondamento vai para a última parte, então a soma bate exatamente."""
    total = Decimal(total)
    soma = sum((Decimal(p) for p in pesos), Decimal("0"))
    if not pesos:
        return []
    if soma <= 0:
        partes = [Decimal("0.00")] * len(pesos)
        partes[-1] = total.quantize(CENTAVO)
        return partes
    partes = [(total * Decimal(p) / soma).quantize(CENTAVO, rounding=ROUND_HALF_UP) for p in pesos[:-1]]
    partes.append((total - sum(partes, Decimal("0"))).quantize(CENTAVO))
    return partes


async def _linha(db: AsyncSession, travar: bool = False) -> PlatformFeeConfig | None:
    q = select(PlatformFeeConfig).where(PlatformFeeConfig.id == 1)
    if travar:
        q = q.with_for_update()
    return (await db.execute(q)).scalar_one_or_none()


def _regra(linha: PlatformFeeConfig | None) -> Regra:
    if linha is None:
        return REGRA_PADRAO
    return Regra(linha.demo_ends_at, Decimal(linha.fee_percent), int(linha.grace_days))


async def regra_atual(db: AsyncSession) -> Regra:
    """Sem a linha (ou sem a tabela), vale a demo: 0% é o lado seguro para a loja.
    Num SAVEPOINT: se a leitura falhar, a transação de quem chamou segue viva."""
    try:
        async with db.begin_nested():
            return _regra(await _linha(db))
    except Exception:  # noqa: BLE001
        logger.warning("platform_fee_config indisponível; usando demo (0%%)", exc_info=True)
        return REGRA_PADRAO


def _config_saida(linha: PlatformFeeConfig | None, agora: datetime | None = None) -> dict:
    agora = agora or datetime.now(timezone.utc)
    fim = _utc(linha.demo_ends_at) if linha else None
    return {
        "demo_active": fim is None or agora < fim,
        "demo_ends_at": fim,
        "fee_percent": Decimal(linha.fee_percent) if linha else PADRAO_PERCENT,
        "grace_days": int(linha.grace_days) if linha else PADRAO_CARENCIA,
        "updated_at": linha.updated_at if linha else None,
    }


# ── admin (as rotas ficam no painel de administração) ─────────────────────────

async def obter_config(db: AsyncSession) -> dict:
    return _config_saida(await _linha(db))


async def atualizar_config(db: AsyncSession, dados: PlatformFeeConfigUpdate, admin_profile_id: UUID) -> dict:
    linha = await _linha(db, travar=True)
    if linha is None:
        linha = PlatformFeeConfig(id=1, fee_percent=PADRAO_PERCENT, grace_days=PADRAO_CARENCIA)
        db.add(linha)
    agora = datetime.now(timezone.utc)
    if dados.fee_percent is not None:
        linha.fee_percent = dados.fee_percent
    if dados.grace_days is not None:
        linha.grace_days = dados.grace_days
    if dados.end_demo_now:
        linha.demo_ends_at = agora
    elif "demo_ends_at" in dados.model_fields_set:
        linha.demo_ends_at = dados.demo_ends_at
    linha.updated_at = agora
    linha.updated_by = admin_profile_id
    await db.commit()
    logger.warning(
        "Taxa da plataforma alterada por %s: demo_ends_at=%s fee=%s%% carencia=%sd",
        admin_profile_id, linha.demo_ends_at, linha.fee_percent, linha.grace_days,
    )
    return _config_saida(linha, agora)


async def repasses_pendentes(db: AsyncSession) -> list[dict]:
    """Quanto a plataforma deve a cada loja (vendas pagas com repasse pendente)."""
    linhas = (
        await db.execute(
            select(
                Seller.id,
                Seller.store_name,
                func.count(OrderItems.id),
                func.coalesce(func.sum(OrderItems.subtotal), 0),
                func.coalesce(func.sum(OrderItems.platform_fee_amount), 0),
                func.coalesce(func.sum(OrderItems.mp_fee_amount), 0),
                func.coalesce(func.sum(func.coalesce(OrderItems.seller_net_amount, OrderItems.subtotal)), 0),
            )
            .select_from(OrderItems)
            .join(Order, Order.id == OrderItems.order_id)
            .join(Look, Look.id == OrderItems.look_id)
            .join(Seller, Seller.id == Look.seller_id)
            .where(Order.payment_status == PaymentStatus.APPROVED, OrderItems.payout_status == "pending")
            .group_by(Seller.id, Seller.store_name)
            .order_by(func.sum(OrderItems.subtotal).desc())
        )
    ).all()
    return [
        {"seller_id": str(s), "store_name": n, "items": int(q), "gross": g, "fees": f, "mp_fees": m, "net": l}
        for s, n, q, g, f, m, l in linhas
    ]


async def marcar_repasse_pago(db: AsyncSession, seller_id: UUID, admin_profile_id: UUID) -> int:
    """Marca como repassadas todas as peças pagas e pendentes da loja. Devolve quantas."""
    itens = (
        await db.execute(
            select(OrderItems)
            .join(Order, Order.id == OrderItems.order_id)
            .join(Look, Look.id == OrderItems.look_id)
            .where(
                Look.seller_id == seller_id,
                Order.payment_status == PaymentStatus.APPROVED,
                OrderItems.payout_status == "pending",
            )
            .with_for_update(of=OrderItems)
        )
    ).scalars().all()
    agora = datetime.now(timezone.utc)
    for item in itens:
        item.payout_status = "paid"
        item.paid_out_at = agora
    await db.commit()
    logger.warning("Repasse de %s peças da loja %s marcado como pago por %s", len(itens), seller_id, admin_profile_id)
    return len(itens)


# ── venda aprovada (webhook) ──────────────────────────────────────────────────

def aplicar_no_item(
    item: OrderItems, regra: Regra, loja_criada_em: datetime | None, quando: datetime,
    tarifa_mp: Decimal | None = None,
) -> Taxa:
    taxa = taxa_em(regra, loja_criada_em, quando)
    valor, liquido = dividir(item.subtotal, taxa.percent, tarifa_mp)
    item.platform_fee_percent = taxa.percent
    item.platform_fee_amount = valor
    item.mp_fee_amount = tarifa_mp
    item.seller_net_amount = liquido
    item.fee_rule = taxa.fase
    return taxa


async def congelar_taxas(
    db: AsyncSession, itens: list[tuple[OrderItems, UUID | None]], quando: datetime,
    tarifa_mp: Decimal | None = None,
) -> None:
    """Grava a taxa em cada peça do pedido aprovado. `itens` = [(item, seller_id)];
    `tarifa_mp` = tarifa do Mercado Pago no pagamento inteiro (rateada aqui).

    Num SAVEPOINT e sem deixar o erro subir: a taxa nunca pode impedir um
    pagamento aprovado de ser registrado. Se falhar, a peça fica sem taxa
    gravada e as telas calculam pela regra na data do pedido."""
    try:
        async with db.begin_nested():
            regra = _regra(await _linha(db))
            criada_em: dict[UUID, datetime | None] = {}
            for _, sid in itens:
                if sid is not None and sid not in criada_em:
                    loja = await db.get(Seller, sid)
                    criada_em[sid] = loja.created_at if loja else None
            partes = (
                ratear(tarifa_mp, [i.subtotal or Decimal("0") for i, _ in itens])
                if tarifa_mp is not None else [None] * len(itens)
            )
            for (item, sid), parte in zip(itens, partes):
                aplicar_no_item(item, regra, criada_em.get(sid), quando, parte)
    except Exception:  # noqa: BLE001
        logger.warning("Não foi possível gravar a taxa da plataforma do pedido", exc_info=True)


@dataclass(frozen=True)
class TaxaItem:
    percent: Decimal
    taxa: Decimal  # taxa da plataforma
    tarifa_mp: Decimal | None  # parte da tarifa do Mercado Pago (None = não informada)
    liquido: Decimal  # a repassar para a loja
    fase: str


def taxa_do_item(item, regra: Regra, loja_criada_em: datetime | None, pedido_em: datetime) -> TaxaItem:
    """Taxas e líquido de uma peça vendida: o que foi gravado na aprovação ou,
    se não houver, a regra atual aplicada na data do pedido."""
    tarifa = getattr(item, "mp_fee_amount", None)
    tarifa = Decimal(tarifa) if tarifa is not None else None
    if item.platform_fee_percent is not None and item.seller_net_amount is not None:
        return TaxaItem(
            Decimal(item.platform_fee_percent),
            Decimal(item.platform_fee_amount or 0),
            tarifa,
            Decimal(item.seller_net_amount),
            item.fee_rule or "demo",
        )
    t = taxa_em(regra, loja_criada_em, pedido_em)
    valor, liquido = dividir(item.subtotal or Decimal("0"), t.percent, tarifa)
    return TaxaItem(t.percent, valor, tarifa, liquido, t.fase)


# ── loja ──────────────────────────────────────────────────────────────────────

def _brl(d: datetime) -> str:
    from zoneinfo import ZoneInfo

    return d.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")


def _pct(p: Decimal) -> str:
    return f"{Decimal(p).normalize():f}".replace(".", ",") + "%"


def taxa_da_loja(regra: Regra, loja_criada_em: datetime | None, agora: datetime | None = None) -> dict:
    agora = agora or datetime.now(timezone.utc)
    t = taxa_em(regra, loja_criada_em, agora)
    padrao = _pct(regra.fee_percent)
    if t.fase == "demo":
        msg = ("Período de demonstração: taxa Lookly de 0%. Você recebe o valor de cada peça vendida no app, "
               "descontada só a tarifa do Mercado Pago.")
        if regra.demo_ends_at:
            msg += f" A demonstração termina em {_brl(_utc(regra.demo_ends_at))}; depois você ainda tem {regra.grace_days} dias a 0%."
        else:
            msg += f" Quando a demonstração acabar, você ainda terá {regra.grace_days} dias a 0% e depois a taxa será de {padrao}."
    elif t.fase == "carencia":
        msg = f"Taxa Lookly de 0% até {_brl(t.fim_carencia)}. Depois, {padrao} sobre as peças vendidas no app."
    else:
        msg = f"Taxa Lookly de {padrao} sobre as peças vendidas no app. Vendas feitas fora do app não pagam taxa."
    return {
        "phase": t.fase,
        "current_percent": t.percent,
        "standard_percent": regra.fee_percent,
        "grace_days": regra.grace_days,
        "demo_ends_at": _utc(regra.demo_ends_at),
        "grace_ends_at": t.fim_carencia,
        "message": msg,
    }


async def taxa_da_minha_loja(db: AsyncSession, seller: Seller) -> dict:
    return taxa_da_loja(await regra_atual(db), seller.created_at)
