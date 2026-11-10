from fastapi import HTTPException, Request


async def ler_corpo_limitado(request: Request, max_bytes: int, detalhe: str) -> bytes:
    """Lê o corpo da requisição abortando assim que passa de `max_bytes` (413).

    Confere o `Content-Length` declarado antes de ler qualquer coisa e, mesmo
    assim, conta o que de fato chega: com o cabeçalho mentindo ou ausente (corpo
    "chunked"), um corpo gigante nunca chega inteiro à memória.
    """
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > max_bytes:
        raise HTTPException(status_code=413, detail=detalhe)
    pedacos, total = [], 0
    async for pedaco in request.stream():
        total += len(pedaco)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail=detalhe)
        pedacos.append(pedaco)
    return b"".join(pedacos)
