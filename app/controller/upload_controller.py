from uuid import UUID
from fastapi import APIRouter, Depends, Request, status
from dependencies.auth import get_current_user_id
from schemas.upload import UploadResponse
from service import storage_service
from core.body_limit import ler_corpo_limitado
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
    corpo = await ler_corpo_limitado(request, storage_service.MAX_BYTES, "Imagem grande demais (máximo de 5 MB).")
    url = await storage_service.upload_imagem(user_id, request.headers.get("content-type"), corpo)
    return UploadResponse(url=url)
