"""Painel de administração. TODA rota daqui depende de `require_admin`
(dependencies/admin.py): a checagem é no servidor, a tela do app só esconde o botão."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.rate_limiter import limiter
from db.database import get_db
from dependencies.admin import email_do_token, require_admin
from dependencies.auth import get_token_payload
from schemas.admin import (
    AdminMe,
    CategoriaAdmin,
    CategoriaCreate,
    CategoriaUpdate,
    DenunciaAdmin,
    DenunciasResponse,
    DenunciaUpdate,
    LojaAdmin,
    LojasResponse,
    LojaUpdate,
    PecaAdmin,
    PecasResponse,
    PecaUpdate,
    PedidosResponse,
    Resumo,
    StatusConta,
    StatusConteudo,
    StatusDenuncia,
    UsuarioAdmin,
    UsuariosResponse,
    UsuarioUpdate,
)
from service import admin_service as svc

router = APIRouter(prefix="/admin", tags=["Administração"], dependencies=[Depends(require_admin)])

_Q = Query(None, min_length=1, max_length=80)
_CONFIRM = Query(None, max_length=20, description='Digite "APAGAR" para confirmar')


@router.get("/me", response_model=AdminMe)
async def eu(admin_id: UUID = Depends(require_admin), payload: dict = Depends(get_token_payload)):
    """200 = é admin (o app mostra o painel); 403 = não é."""
    return {"user_id": admin_id, "email": email_do_token(payload)}


@router.get("/overview", response_model=Resumo)
@limiter.limit("60/minute")
async def resumo(request: Request, db: AsyncSession = Depends(get_db)):
    return await svc.resumo(db)


# ── usuários ──
@router.get("/users", response_model=UsuariosResponse)
@limiter.limit("120/minute")
async def usuarios(
    request: Request,
    q: str | None = _Q,
    status_: StatusConta | Literal["deleted"] | None = Query(None, alias="status"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await svc.listar_usuarios(db, q, status_, limit, offset)


@router.patch("/users/{user_id}", response_model=UsuarioAdmin)
async def editar_usuario(user_id: UUID, dados: UsuarioUpdate, admin_id: UUID = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Editar nome/usuário e bloquear (suspended/banned) ou reativar. Bloquear também
    trava o login no Supabase Auth."""
    return await svc.atualizar_usuario(db, admin_id, user_id, dados)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def apagar_usuario(request: Request, user_id: UUID, confirm: str | None = _CONFIRM, admin_id: UUID = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Apaga a conta (dados, arquivos e login). 409 se houver pedidos."""
    await svc.apagar_usuario(db, admin_id, user_id, confirm)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── lojas ──
@router.get("/stores", response_model=LojasResponse)
@limiter.limit("120/minute")
async def lojas(
    request: Request,
    q: str | None = _Q,
    status_: StatusConteudo | None = Query(None, alias="status"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await svc.listar_lojas(db, q, status_, limit, offset)


@router.patch("/stores/{seller_id}", response_model=LojaAdmin)
async def editar_loja(seller_id: UUID, dados: LojaUpdate, admin_id: UUID = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Editar nome/descrição ou tirar do ar (status ≠ active: some do feed, da busca e do checkout)."""
    return await svc.atualizar_loja(db, admin_id, seller_id, dados)


@router.delete("/stores/{seller_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def apagar_loja(request: Request, seller_id: UUID, confirm: str | None = _CONFIRM, admin_id: UUID = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Apaga a loja e as peças dela. 409 se alguma peça estiver em pedido."""
    await svc.apagar_loja(db, admin_id, seller_id, confirm)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── peças ──
@router.get("/looks", response_model=PecasResponse)
@limiter.limit("120/minute")
async def pecas(
    request: Request,
    q: str | None = _Q,
    status_: StatusConteudo | None = Query(None, alias="status"),
    seller_id: UUID | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await svc.listar_pecas(db, q, status_, seller_id, limit, offset)


@router.patch("/looks/{look_id}", response_model=PecaAdmin)
async def editar_peca(look_id: UUID, dados: PecaUpdate, admin_id: UUID = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await svc.atualizar_peca(db, admin_id, look_id, dados)


@router.delete("/looks/{look_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def apagar_peca(request: Request, look_id: UUID, confirm: str | None = _CONFIRM, admin_id: UUID = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """409 se a peça estiver em algum pedido."""
    await svc.apagar_peca(db, admin_id, look_id, confirm)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── pedidos (só leitura: pagamento é do Mercado Pago) ──
@router.get("/orders", response_model=PedidosResponse)
@limiter.limit("120/minute")
async def pedidos(
    request: Request,
    payment_status: Literal["pending", "approved", "refused", "refunded"] | None = Query(None),
    q: str | None = _Q,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await svc.listar_pedidos(db, payment_status, q, limit, offset)


# ── categorias ──
@router.get("/categories", response_model=list[CategoriaAdmin])
async def categorias(db: AsyncSession = Depends(get_db)):
    return await svc.listar_categorias(db)


@router.post("/categories", response_model=CategoriaAdmin, status_code=status.HTTP_201_CREATED)
async def criar_categoria(dados: CategoriaCreate, admin_id: UUID = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await svc.criar_categoria(db, admin_id, dados)


@router.patch("/categories/{cat_id}", response_model=CategoriaAdmin)
async def editar_categoria(cat_id: UUID, dados: CategoriaUpdate, admin_id: UUID = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await svc.atualizar_categoria(db, admin_id, cat_id, dados)


@router.delete("/categories/{cat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_categoria(cat_id: UUID, confirm: str | None = _CONFIRM, admin_id: UUID = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await svc.apagar_categoria(db, admin_id, cat_id, confirm)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── denúncias ──
@router.get("/reports", response_model=DenunciasResponse)
async def denuncias(
    status_: StatusDenuncia | None = Query(None, alias="status"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await svc.listar_denuncias(db, status_, limit, offset)


@router.patch("/reports/{report_id}", response_model=DenunciaAdmin)
async def editar_denuncia(report_id: UUID, dados: DenunciaUpdate, admin_id: UUID = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await svc.atualizar_denuncia(db, admin_id, report_id, dados)
