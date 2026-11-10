import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

from routers import router
from core.rate_limiter import limiter
from core.logging_config import setup_logging, RequestIdMiddleware

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Rede de segurança de schema (ver core/schema_guard.py). Nunca impede a subida:
    # com o banco pausado ou lento, loga e segue.
    try:
        from db.database import engine
        from core.schema_guard import garantir_schema

        await asyncio.wait_for(garantir_schema(engine), timeout=15)
    except Exception:  # noqa: BLE001
        logger.exception("Schema guard não pôde rodar (banco indisponível?) — API sobe mesmo assim")
    yield


app = FastAPI(title="Lookly API", lifespan=lifespan)

# Um id curto por requisição, propagado via contextvar pra todo log emitido
# durante ela carregar o mesmo id — indispensável pra separar requisições
# concorrentes num servidor async. Devolvido em X-Request-ID pro cliente
# poder citar numa eventual investigação. Também é aqui dentro (não em
# @app.exception_handler(Exception)) que erro não tratado é pego e logado
# — ver o docstring de RequestIdMiddleware pra entender por quê.
app.add_middleware(RequestIdMiddleware)

# Rate Limit
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(status_code=429, content={"detail": "Rate limit excedido"})


# CORS — só afeta navegador (Expo Web). O app NATIVO no celular não manda
# Origin e ignora CORS. Config via env CORS_ORIGINS (separadas por vírgula);
# "*" libera qualquer origem (útil em dev). Com "*", allow_credentials precisa
# ser False, senão o próprio spec de CORS invalida o wildcard.
_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
_allow_all = _origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=not _allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rotas
app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    return {"status": "API rodando 🚀"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
