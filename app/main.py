import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

from routers import router
from core.rate_limiter import limiter

app = FastAPI(title="Lucker API")

# Rate Limit
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit excedido"}
    )

# CORS — origens permitidas via env (CORS_ORIGINS, separadas por vírgula).
# Default restrito ao ambiente local de desenvolvimento.
_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8081")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_credentials=True,
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