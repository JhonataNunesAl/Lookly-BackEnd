"""A URL do banco sempre usa o driver asyncpg (correção vinda da main, 294e967).

O Render e o Supabase costumam entregar `postgresql://...` ou `postgres://...`; sem a troca,
o SQLAlchemy procuraria o psycopg2, que não está instalado, e a API não subiria.
"""
import pytest

from db.database import _get_async_url


@pytest.mark.parametrize(
    "entrada",
    [
        "postgresql://u:p@host:5432/db",
        "postgres://u:p@host:5432/db",
        "postgresql+psycopg2://u:p@host:5432/db",
        "postgresql+psycopg://u:p@host:5432/db",
        "postgresql+asyncpg://u:p@host:5432/db",
    ],
)
def test_url_sempre_vira_asyncpg(entrada):
    assert _get_async_url(entrada) == "postgresql+asyncpg://u:p@host:5432/db"


def test_url_de_outro_banco_nao_e_alterada():
    assert _get_async_url("sqlite+aiosqlite:///x.db") == "sqlite+aiosqlite:///x.db"
