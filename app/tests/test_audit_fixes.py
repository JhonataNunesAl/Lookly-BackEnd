"""Testes da auditoria de bugs reais (sessão 2026-08-18).

Sem banco: os testes de schema validam Pydantic puro (é a linha de defesa
que substitui um round-trip até o Postgres). Os testes de service usam uma
sessão async falsa (`FakeSession`) que simula o `IntegrityError` que o
Postgres levantaria — o objetivo é provar que o CÓDIGO DE TRATAMENTO reage
certo, não redemonstrar que o Postgres aplica CHECK/UNIQUE (isso já é
garantido pelo próprio banco).

Roda com: cd app && python -m pytest tests/ -v
"""
import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from model.profile import Profile
from model.seller import Seller
from schemas.body_profile import BodyProfileUpdate
from schemas.collection import CollectionCreate
from schemas.look import LookCreate, LookUpdate
from schemas.profile import ProfileUpdate
from schemas.seller import SellerCreate
from service import look_service, profile_service, seller_service, wardrobe_service


def run(coro):
    """Roda uma coroutine de teste sem precisar de pytest-asyncio."""
    return asyncio.run(coro)


class FakeResult:
    """Simula o retorno de `db.execute(...)` — sempre "não encontrado"/vazio.
    Suficiente pra estes testes: o que importa é a QUERY montada e o
    comportamento do commit, não o dado que voltaria de verdade."""

    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return self

    def all(self):
        return []

    def first(self):
        return None


class FakeSession:
    """Sessão async falsa. `commit_exc`, se dado, é levantado no commit —
    é assim que simulamos um CHECK/UNIQUE do Postgres sem precisar de um
    Postgres de verdade."""

    def __init__(self, commit_exc: Exception | None = None):
        self._commit_exc = commit_exc
        self.rolled_back = False
        self.committed = False
        self.executed_queries: list = []

    async def execute(self, query):
        self.executed_queries.append(query)
        return FakeResult()

    async def commit(self):
        if self._commit_exc is not None:
            raise self._commit_exc
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def refresh(self, obj):
        pass

    def add(self, obj):
        pass

    async def delete(self, obj):
        pass


class _FakeOrig(Exception):
    """Simula a exceção do driver (asyncpg) que `IntegrityError.orig`
    encapsula — só o atributo `sqlstate` importa pro código que escrevemos."""

    def __init__(self, sqlstate: str):
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


def integrity_error(sqlstate: str) -> IntegrityError:
    return IntegrityError("stmt", {}, _FakeOrig(sqlstate))


def sql_of(query) -> str:
    """SQL com literais embutidos (não `%s`), pra dar pra grepar por valor."""
    return str(query.compile(compile_kwargs={"literal_binds": True}))


# ── schemas/profile.py — username/bio ──────────────────────────────────────

@pytest.mark.parametrize(
    "username",
    ["ab", "a" * 31, "Maiuscula", "tem espaço", "tem-hifen", "acentuação"],
)
def test_profile_username_formato_invalido_rejeitado(username):
    with pytest.raises(ValidationError):
        ProfileUpdate(username=username)


@pytest.mark.parametrize("username", ["abc", "a" * 30, "nome.de_usuario123"])
def test_profile_username_formato_valido_aceito(username):
    assert ProfileUpdate(username=username).username == username


def test_profile_bio_muito_longa_rejeitada():
    with pytest.raises(ValidationError):
        ProfileUpdate(bio="x" * 301)


def test_profile_bio_no_limite_aceita():
    assert ProfileUpdate(bio="x" * 300).bio == "x" * 300


# ── schemas/look.py — nome/preço ────────────────────────────────────────────

def _look_payload(**over):
    base = dict(category_id=uuid4(), name="Jaqueta Bomber", photos=["http://x/1.jpg"])
    base.update(over)
    return base


@pytest.mark.parametrize("name", ["A", "x" * 121])
def test_look_nome_fora_da_faixa_rejeitado(name):
    with pytest.raises(ValidationError):
        LookCreate(**_look_payload(name=name))


def test_look_preco_negativo_rejeitado():
    with pytest.raises(ValidationError):
        LookCreate(**_look_payload(price=-1))


def test_look_preco_zero_aceito():
    assert LookCreate(**_look_payload(price=0)).price == 0


def test_look_update_nome_curto_rejeitado():
    with pytest.raises(ValidationError):
        LookUpdate(name="A")


# ── schemas/seller.py — nome/slug da loja ───────────────────────────────────

@pytest.mark.parametrize("slug", ["ab", "Maiusculo", "tem espaço", "tem_underscore"])
def test_seller_slug_formato_invalido_rejeitado(slug):
    with pytest.raises(ValidationError):
        SellerCreate(store_name="Loja Legal", store_slug=slug)


def test_seller_slug_formato_valido_aceito():
    s = SellerCreate(store_name="Loja Legal", store_slug="loja-legal-123")
    assert s.store_slug == "loja-legal-123"


def test_seller_nome_muito_curto_rejeitado():
    with pytest.raises(ValidationError):
        SellerCreate(store_name="A", store_slug="loja-valida")


# ── schemas/collection.py — nome da coleção ─────────────────────────────────

def test_collection_nome_vazio_rejeitado():
    with pytest.raises(ValidationError):
        CollectionCreate(name="")


def test_collection_nome_muito_longo_rejeitado():
    with pytest.raises(ValidationError):
        CollectionCreate(name="x" * 61)


# ── schemas/body_profile.py — peso/altura plausíveis ────────────────────────

@pytest.mark.parametrize("peso", [0, -5, 501])
def test_body_profile_peso_implausivel_rejeitado(peso):
    with pytest.raises(ValidationError):
        BodyProfileUpdate(weight_kg=peso)


@pytest.mark.parametrize("altura", [0, -1, 301])
def test_body_profile_altura_implausivel_rejeitada(altura):
    with pytest.raises(ValidationError):
        BodyProfileUpdate(height_cm=altura)


def test_body_profile_valores_plausiveis_aceitos():
    dados = BodyProfileUpdate(weight_kg=68.5, height_cm=172)
    assert dados.weight_kg == 68.5
    assert dados.height_cm == 172


# ── service/profile_service.py — commit sem tratamento de conflito ─────────

def test_profile_update_username_duplicado_vira_409_claro():
    async def _run():
        profile = Profile(id=uuid4(), username="antigo", birth_date=date(2000, 1, 1))
        session = FakeSession(commit_exc=integrity_error("23505"))
        with patch.object(profile_service, "_get_profile", AsyncMock(return_value=profile)):
            with pytest.raises(HTTPException) as exc:
                await profile_service.update_me(
                    session, profile.id, ProfileUpdate(username="ja_existe")
                )
        assert exc.value.status_code == 409
        assert "uso" in exc.value.detail
        assert session.rolled_back is True

    run(_run())


def test_profile_update_outro_erro_de_integridade_vira_409_generico():
    async def _run():
        profile = Profile(id=uuid4(), username="antigo", birth_date=date(2000, 1, 1))
        session = FakeSession(commit_exc=integrity_error("23514"))  # check_violation
        with patch.object(profile_service, "_get_profile", AsyncMock(return_value=profile)):
            with pytest.raises(HTTPException) as exc:
                await profile_service.update_me(
                    session, profile.id, ProfileUpdate(full_name="Nome Válido")
                )
        assert exc.value.status_code == 409
        assert "uso" not in exc.value.detail

    run(_run())


# ── service/look_service.py — commit sem tratamento de conflito ────────────

def test_create_look_erro_de_integridade_vira_400_nao_500():
    async def _run():
        seller = Seller(
            id=uuid4(), owner_profile_id=uuid4(), store_name="Loja", store_slug="loja"
        )
        session = FakeSession(commit_exc=integrity_error("23514"))
        dados = LookCreate(**_look_payload())
        with patch.object(
            look_service.seller_service, "get_seller_by_owner", AsyncMock(return_value=seller)
        ), patch.object(look_service, "_validar_categoria", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await look_service.create_look(session, seller.owner_profile_id, dados)
        assert exc.value.status_code == 400
        assert session.rolled_back is True

    run(_run())


def test_update_look_erro_de_integridade_vira_400_nao_500():
    async def _run():
        from model.look import Look

        look = Look(id=uuid4(), seller_id=uuid4(), category_id=uuid4(), name="Antigo", photos=["x"])
        session = FakeSession(commit_exc=integrity_error("23514"))
        with patch.object(look_service, "_get_manageable_look", AsyncMock(return_value=look)):
            with pytest.raises(HTTPException) as exc:
                await look_service.update_look(
                    session, uuid4(), look.id, LookUpdate(name="Nome Válido")
                )
        assert exc.value.status_code == 400

    run(_run())


# ── service/seller_service.py — mensagem certa por tipo de conflito ────────

def test_become_seller_corrida_de_dono_da_mensagem_certa():
    """Duas requisições da MESMA pessoa colidem no owner_profile_id — a
    mensagem não pode dizer 'slug em uso' (o slug pode nem ter conflito)."""

    async def _run():
        user_id = uuid4()
        seller_ja_existente = Seller(
            id=uuid4(), owner_profile_id=user_id, store_name="Loja", store_slug="loja"
        )
        session = FakeSession(commit_exc=integrity_error("23505"))
        dados = SellerCreate(store_name="Loja Nova", store_slug="loja-nova")
        with patch.object(
            seller_service,
            "get_seller_by_owner",
            AsyncMock(side_effect=[None, seller_ja_existente]),
        ):
            with pytest.raises(HTTPException) as exc:
                await seller_service.become_seller(session, user_id, dados)
        assert exc.value.status_code == 400
        assert "já tem uma loja" in exc.value.detail

    run(_run())


def test_become_seller_slug_duplicado_da_mensagem_certa():
    async def _run():
        user_id = uuid4()
        session = FakeSession(commit_exc=integrity_error("23505"))
        dados = SellerCreate(store_name="Loja Nova", store_slug="loja-nova")
        with patch.object(
            seller_service, "get_seller_by_owner", AsyncMock(side_effect=[None, None])
        ):
            with pytest.raises(HTTPException) as exc:
                await seller_service.become_seller(session, user_id, dados)
        assert exc.value.status_code == 400
        assert "slug" in exc.value.detail

    run(_run())


# ── service/wardrobe_service.py — moderação (status == active) ─────────────

def test_save_look_filtra_por_status_active():
    async def _run():
        session = FakeSession()
        with pytest.raises(HTTPException):
            await wardrobe_service.save_look(session, uuid4(), uuid4())
        assert len(session.executed_queries) == 1
        sql = sql_of(session.executed_queries[0])
        assert "status" in sql and "active" in sql

    run(_run())


def test_list_saved_looks_filtra_por_status_active():
    async def _run():
        session = FakeSession()
        await wardrobe_service.list_saved_looks(session, uuid4())
        sql = sql_of(session.executed_queries[0])
        assert "status" in sql and "active" in sql

    run(_run())


def test_add_look_to_collection_filtra_por_status_active():
    async def _run():
        session = FakeSession()
        with patch.object(
            wardrobe_service, "_get_owned_collection", AsyncMock(return_value=None)
        ):
            with pytest.raises(HTTPException):
                await wardrobe_service.add_look_to_collection(
                    session, uuid4(), uuid4(), uuid4()
                )
        assert len(session.executed_queries) == 1
        sql = sql_of(session.executed_queries[0])
        assert "status" in sql and "active" in sql

    run(_run())


def test_list_collection_looks_filtra_por_status_active():
    async def _run():
        session = FakeSession()
        with patch.object(
            wardrobe_service, "_get_owned_collection", AsyncMock(return_value=None)
        ):
            await wardrobe_service.list_collection_looks(session, uuid4(), uuid4())
        sql = sql_of(session.executed_queries[0])
        assert "status" in sql and "active" in sql

    run(_run())
