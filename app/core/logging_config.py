import logging
import logging.handlers
import os
import uuid
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Guarda o request_id da requisição em andamento nesta task async — é assim
# que uma linha de log solta (ex.: dentro de um service) sabe a qual
# requisição pertence, sem precisar passar o id explicitamente por toda
# chamada. Setado pelo middleware em main.py, uma vez por requisição.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Injeta o request_id atual em todo record de log."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class RequestIdMiddleware:
    """Middleware ASGI puro (NÃO `BaseHTTPMiddleware`/`@app.middleware("http")`)
    de propósito: `BaseHTTPMiddleware` roda o resto do request numa task
    separada via `anyio.create_task_group()`, e o contextvar setado antes de
    `call_next()` não atravessa essa fronteira de forma confiável. Middleware
    ASGI roda tudo na MESMA task, então o contextvar fica visível em
    qualquer código chamado durante o request.

    Também é aqui, e não em `@app.exception_handler(Exception)`, que a
    exceção não tratada é pega e logada. Motivo (descoberto testando, não
    óbvio): handler registrado para `Exception` roda dentro do
    `ServerErrorMiddleware` do Starlette, que fica FORA de qualquer
    middleware adicionado via `add_middleware` — ou seja, fora deste aqui.
    Um `try/finally` que reseta o contextvar ao propagar a exceção já
    tinha rodado o `finally` (resetando pra "-") antes da exceção alcançar
    aquele handler externo, e o header de resposta que ele monta nunca
    passava pelo `send_wrapper` daqui (que só vê mensagens de dentro desta
    camada pra baixo). Capturando a exceção AQUI, com o contextvar ainda
    válido e controle total da resposta enviada, os dois problemas somem.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = uuid.uuid4().hex[:8]
        token = request_id_ctx.set(rid)
        response_started = False

        async def send_wrapper(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = MutableHeaders(scope=message)
                headers.append("X-Request-ID", rid)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # Rede de segurança: qualquer exceção que nenhum código tratou
            # explicitamente (não é o HTTPException que os services levantam
            # de propósito — esses já viram resposta limpa antes de chegar
            # aqui). Loga o traceback completo; nunca devolve a stack trace
            # real pro cliente, isso seria vazamento de informação interna.
            logger.exception(
                "Erro não tratado em %s %s", scope.get("method"), scope.get("path")
            )
            if not response_started:
                resposta = JSONResponse(
                    status_code=500,
                    content={"detail": "Erro interno. Tente novamente."},
                    headers={"X-Request-ID": rid},
                )
                await resposta(scope, receive, send)
            else:
                raise
        finally:
            request_id_ctx.reset(token)


def setup_logging() -> None:
    """Chamada uma vez na subida do app. Configura console + arquivo com
    rotação (5MB x 5 arquivos). Nível via env `LOG_LEVEL` (default INFO).

    NUNCA logar aqui ou em qualquer chamador: token JWT, CPF/CNPJ em claro,
    senha, ou dado corporal decifrado. Só identificadores (user_id, look_id)
    e a mensagem de erro — a base já lida com dado sensível cifrado
    (core/crypto.py) e log em arquivo não tem o mesmo controle de acesso que
    o banco.
    """
    nivel = os.getenv("LOG_LEVEL", "INFO").upper()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s [%(request_id)s] %(message)s"
    )
    request_filter = RequestIdFilter()

    os.makedirs("logs", exist_ok=True)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(request_filter)

    file_handler = logging.handlers.RotatingFileHandler(
        "logs/app.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(request_filter)

    root = logging.getLogger()
    root.setLevel(nivel)
    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(file_handler)
