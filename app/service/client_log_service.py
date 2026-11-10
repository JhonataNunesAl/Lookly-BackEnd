"""Recebe erros e exceções registrados pelo app e os escreve no log do servidor.

Vai para o mesmo destino de todo log (console do Render + `logs/app.log` com
rotação), no logger `client`, uma linha JSON por entrada — fácil de buscar e sem
risco de uma mensagem com quebra de linha forjar linhas falsas no arquivo.
Tudo que o app manda é NÃO CONFIÁVEL: o texto é limpo (`core.log_scrub`) e
cortado, e o `user_id` só é anexado quando vem de um token verificado, nunca do
corpo da requisição.
"""
import json
import logging
from uuid import UUID

from core.log_scrub import limpar
from schemas.account import ClientLogLote

logger = logging.getLogger("client")

_NIVEIS = {"warn": logging.WARNING, "error": logging.ERROR, "fatal": logging.CRITICAL}


def registrar(lote: ClientLogLote, user_id: UUID | None) -> int:
    for e in lote.entradas:
        registro = {
            "nivel": e.nivel,
            "origem": e.origem,
            "mensagem": limpar(e.mensagem),
            "pilha": limpar(e.pilha),
            "tela": e.tela,
            "ts": e.ts,
            "contexto": {k: (limpar(v) if isinstance(v, str) else v) for k, v in e.contexto.items()},
            "app_versao": lote.app_versao,
            "plataforma": lote.plataforma,
            "user_id": str(user_id) if user_id else None,
        }
        logger.log(_NIVEIS[e.nivel], "client_log %s", json.dumps(registro, ensure_ascii=False))
    return len(lote.entradas)
