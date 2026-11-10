from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
from dependencies.auth import get_current_user_id
from schemas.upload import UploadResponse
from service import storage_service
from core.rate_limiter import limiter

router = APIRouter(prefix="/uploads", tags=["Uploads"])


@router.post("/image", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def enviar_imagem(
    request: Request,
    user_id: UUID = Depends(get_current_user_id),
):
    """Recebe a imagem CRUA no corpo (`Content-Type: image/jpeg|png|webp`) — sem
    multipart, então não há parser de formulário na superfície de ataque. Devolve
    a URL pública para usar em `photos` de um look, `avatar_url` ou
    `store_logo_url`."""
    # Recusa antes de ler o corpo inteiro quando o cliente já declara o tamanho.
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > storage_service.MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Imagem grande demais (máximo de 5 MB).",
        )
    corpo = await request.body()
    url = await storage_service.upload_imagem(user_id, request.headers.get("content-type"), corpo)
    return UploadResponse(url=url)
