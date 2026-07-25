from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from schemas.category import CategoryResponse
from service import category_service

router = APIRouter(prefix="/categories", tags=["Categorias"])


@router.get("", response_model=list[CategoryResponse])
async def listar_categorias(db: AsyncSession = Depends(get_db)):
    return await category_service.list_categories(db)


# Não existe POST aqui de propósito: a conexão do FastAPI com o Postgres usa o
# role `postgres` (superusuário — ver DATABASE_URL), que ignora RLS por
# completo. O REVOKE de INSERT/UPDATE/DELETE em `categories` no schema.sql só
# vale para `anon`/`authenticated` via PostgREST direto; não protege nada que
# passe por este backend. Sem um conceito de admin real, qualquer usuário
# autenticado poderia criar categoria à vontade. Categorias são cadastradas
# via acesso direto ao Supabase (SQL editor), como o próprio schema já
# documentava ("Escrita só via service_role/painel admin").
