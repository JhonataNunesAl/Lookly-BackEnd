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
    JWT_ALGORITHMS: list[str] = ["ES256", "RS256", "HS256"]

    # Chave simétrica (AES-256, base64) para cifrar CPF/CNPJ antes de gravar em
    # sellers_private.document_enc. Ver core/crypto.py. Só é exigida na hora de
    # usar (PUT /sellers/me/document) — não trava o boot do servidor, porque
    # boa parte do app roda sem nunca tocar nesse fluxo.
    DOCUMENT_ENCRYPTION_KEY: str = os.getenv("DOCUMENT_ENCRYPTION_KEY", "")

    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set in the environment variables.")

    # Sem SUPABASE_URL não há como descobrir o JWKS para validar os tokens.
    if not SUPABASE_URL and not SUPABASE_JWT_SECRET:
        raise ValueError(
            "Defina SUPABASE_URL (para validação via JWKS) ou SUPABASE_JWT_SECRET (HS256 legado)."
        )


settings = Settings()
