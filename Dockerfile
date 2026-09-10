# Build a partir da raiz do repo (contexto = raiz), mas todo o código roda de
# dentro de `app/` — os imports são absolutos (`from routers import router`),
# então `app/` precisa estar em sys.path. É por isso que copiamos o CONTEÚDO
# de `app/` para `/app` (WORKDIR), não a pasta `app/` inteira como subpasta.
FROM python:3.12-slim

WORKDIR /app

# Copia só o requirements primeiro pra cachear a camada de instalação —
# mudar código não invalida o cache de dependências.
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

# Documentacional — o Render ignora EXPOSE e injeta a porta real via $PORT.
EXPOSE 8000

# --host 0.0.0.0 é obrigatório (Render não alcança 127.0.0.1 dentro do
# container); $PORT vem do Render em runtime, não existe em build time — por
# isso "sh -c" em vez de exec form, senão a variável não expande.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
