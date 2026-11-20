import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL")

    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").rstrip("/")
    # Service role key — só para operações administrativas server-side.
    # Nunca enviar ao app, nunca logar, nunca devolver em erro.
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY")

    # Segredo HS256 legado. Projetos novos do Supabase assinam com chave
    # ASSIMÉTRICA (ES256/RS256) e não têm esse segredo — nesse caso a
    # verificação usa o JWKS abaixo. Deixe vazio se o projeto for assimétrico.
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET")

    # Endpoint público com as chaves de verificação do projeto.
    SUPABASE_JWKS_URL: str = os.getenv(
        "SUPABASE_JWKS_URL", f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    )

    # O Supabase assina os access tokens com aud="authenticated".
    JWT_AUDIENCE: str = "authenticated"
    # Os algoritmos aceitos são fixados em core/security.py POR TIPO DE CHAVE (ES256/RS256
    # com o JWKS, HS256 só com o segredo) — uma lista única abre confusão de algoritmo.

    # Chave simétrica (AES-256, base64) para cifrar CPF/CNPJ antes de gravar em
    # sellers_private.document_enc. Ver core/crypto.py. Só é exigida na hora de
    # usar (PUT /sellers/me/document) — não trava o boot do servidor, porque
    # boa parte do app roda sem nunca tocar nesse fluxo.
    DOCUMENT_ENCRYPTION_KEY: str = os.getenv("DOCUMENT_ENCRYPTION_KEY", "")

    # Bucket público (só leitura) das imagens enviadas por POST /api/uploads/image.
    # É criado sob demanda no primeiro upload — ver service/storage_service.py.
    STORAGE_BUCKET: str = os.getenv("STORAGE_BUCKET", "lookly-media")

    # Mercado Pago (Checkout Pro). Access Token é SEGREDO de servidor: nunca vai ao
    # app nem a log. Sem ele, POST /orders/checkout responde 503 em vez de quebrar o boot.
    MERCADOPAGO_ACCESS_TOKEN: str = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
    # Segredo da assinatura do webhook (painel MP > Webhooks). Opcional: sem ele o
    # webhook ainda é seguro porque o status é sempre relido na API do Mercado Pago.
    MERCADOPAGO_WEBHOOK_SECRET: str = os.getenv("MERCADOPAGO_WEBHOOK_SECRET", "")
    # Para onde o Mercado Pago devolve a pessoa depois de pagar, e a URL pública
    # desta API (o MP chama {PUBLIC_API_URL}/api/payments/webhook).
    PUBLIC_SITE_URL: str = os.getenv("PUBLIC_SITE_URL", "https://lookerstyle.lookerstyle.workers.dev").rstrip("/")
    PUBLIC_API_URL: str = os.getenv("PUBLIC_API_URL", "https://lookly-backend-2.onrender.com").rstrip("/")

    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set in the environment variables.")

    # Sem SUPABASE_URL não há como descobrir o JWKS para validar os tokens.
    if not SUPABASE_URL and not SUPABASE_JWT_SECRET:
        raise ValueError(
            "Defina SUPABASE_URL (para validação via JWKS) ou SUPABASE_JWT_SECRET (HS256 legado)."
        )


settings = Settings()
