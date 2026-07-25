"""Tipos ENUM do Postgres (definidos no schema.sql).

Fábricas retornam uma instância nova por coluna (`create_type=False`: o tipo
já existe no banco, SQLAlchemy não deve tentar criá-lo). Sem isso, o asyncpg
manda o parâmetro como VARCHAR e o Postgres recusa
(`column is of type ... but expression is of type character varying`).
"""
from sqlalchemy.dialects.postgresql import ENUM as PGEnum


def content_status():
    return PGEnum(
        "draft", "active", "under_review", "removed",
        name="content_status", create_type=False,
    )


def account_status():
    return PGEnum(
        "active", "suspended", "banned", "deleted",
        name="account_status", create_type=False,
    )


def swipe_direction():
    return PGEnum("RIGHT", "LEFT", name="swipe_direction", create_type=False)


def report_target():
    return PGEnum(
        "profile", "seller", "look", name="report_target", create_type=False
    )


def report_status():
    return PGEnum(
        "open", "reviewing", "resolved", "rejected",
        name="report_status", create_type=False,
    )


def store_role():
    return PGEnum("owner", "manager", "staff", name="store_role", create_type=False)
