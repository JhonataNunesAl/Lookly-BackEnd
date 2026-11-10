"""Exclusão da conta (LGPD / exigência das lojas de aplicativo).

O que sai, e em que ordem — a ordem importa:

1. **Pedidos primeiro (trava).** Quem tem pedido — como comprador ou como dono de
   loja com peça vendida — NÃO pode apagar tudo: pedido é registro fiscal e
   comercial. A resposta é 409 e o suporte trata o caso. Hoje não existe checkout,
   então na prática a trava só vale quando ele existir.
2. **Banco, numa transação.** `look_views` (particionada, sem FK — não é limpa por
   cascata), a loja (que leva junto peças, documento fiscal, membros, curtidas,
   salvos e carrinhos que a citam) e por fim o perfil, de onde o resto cai em
   cascata (medidas, salvos, coleções, curtidas, carrinho, endereços). A loja
   precisa ser apagada ANTES: `sellers.owner_profile_id` é RESTRICT.
3. **Arquivos** do Storage (`<user_id>/...`): melhor esforço, nunca derruba a
   exclusão.
4. **Supabase Auth por último**: encerra o login. Se falhar, os dados já foram
   apagados e repetir a chamada termina o serviço (cada passo é idempotente).
"""
import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from model.orders import Order
from model.orders_items import OrderItems
from model.look import Look
from model.profile import Profile
from model.seller import Seller
from service import auth_admin_service, seller_service, storage_service

logger = logging.getLogger(__name__)


async def _tem_pedidos(db: AsyncSession, user_id: UUID, seller_id: UUID | None) -> bool:
    """True se há pedido do usuário (comprador) ou de peça da loja dele. As
    tabelas de pedido podem nem existir no banco ainda — nesse caso a consulta
    falha dentro de um savepoint (não aborta a transação) e conta como "sem pedidos"."""
    try:
        async with db.begin_nested():
            if (await db.execute(select(Order.id).where(Order.user_id == user_id).limit(1))).first():
                return True
            if seller_id is not None:
                achou = await db.execute(
                    select(OrderItems.id)
                    .join(Look, Look.id == OrderItems.look_id)
                    .where(Look.seller_id == seller_id)
                    .limit(1)
                )
                if achou.first():
                    return True
    except DBAPIError as e:
        logger.warning("Consulta de pedidos indisponível na exclusão de conta (%s) — seguindo sem trava", type(e).__name__)
    return False


async def excluir_conta(db: AsyncSession, user_id: UUID) -> None:
    profile = (await db.execute(select(Profile).where(Profile.id == user_id))).scalar_one_or_none()

    if profile is not None:
        seller = await seller_service.get_seller_by_owner(db, user_id)
        seller_id = seller.id if seller else None

        if await _tem_pedidos(db, user_id, seller_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Esta conta tem pedidos registrados e não pode ser excluída pelo app. Fale com o suporte.",
            )

        try:
            await db.execute(text("DELETE FROM public.look_views WHERE user_id = :u"), {"u": user_id})
            if seller_id is not None:
                await db.execute(
                    text("DELETE FROM public.look_views WHERE look_id IN (SELECT id FROM public.looks WHERE seller_id = :s)"),
                    {"s": seller_id},
                )
                await db.execute(delete(Seller).where(Seller.id == seller_id))
            await db.execute(delete(Profile).where(Profile.id == user_id))
            await db.commit()
        except IntegrityError:
            await db.rollback()
            logger.exception("Exclusão de conta barrada por integridade (user_id=%s)", user_id)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Não foi possível excluir a conta agora. Fale com o suporte.",
            )
        logger.info("Dados da conta apagados user_id=%s loja=%s", user_id, bool(seller_id))
    else:
        logger.info("Exclusão de conta: perfil já não existia (user_id=%s) — concluindo no Auth", user_id)

    await storage_service.remover_pasta_do_usuario(user_id)
    await auth_admin_service.excluir_usuario(user_id)
    logger.info("Conta excluída user_id=%s", user_id)
